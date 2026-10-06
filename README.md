# telecheck-

API HTTP na LAN para verificar telefone no WhatsApp (`/whatscheck`) e na base MNP (`/telcheck`).

Base: `http://IP_DO_SERVIDOR:8080`

## Rodar no seu computador

Precisa de **Python 3.11 ou mais novo**. Na raiz do projeto:

**macOS ou Linux**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn servidor:app --host 127.0.0.1 --port 8080
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn servidor:app --host 127.0.0.1 --port 8080
```

Está no ar quando aparecer `Uvicorn running on http://127.0.0.1:8080`. Para parar, `Ctrl + C`.

O `--host 127.0.0.1` deixa a API só neste computador, que é o certo para testar. No servidor do escritório use `--host 0.0.0.0`, para os outros PCs alcançarem.

### Liberar o firewall para outros computadores

A API precisa estar no ar com `--host 0.0.0.0`. O firewall do Windows, separado disso, é o que barra o cliente. Neste computador a Ethernet está como rede **Pública**, então a regra tem de ser desse perfil: uma regra só de rede privada não vale aqui.

Cole no PowerShell **como administrador**:

```powershell
if (Get-NetFirewallRule -DisplayName "telecheck-" -ErrorAction SilentlyContinue) { Remove-NetFirewallRule -DisplayName "telecheck-" }; New-NetFirewallRule -DisplayName "telecheck-" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Public
```

Isso libera a entrada TCP na porta **8080** para máquinas que alcançam este PC. Não abre o roteador para a internet. O cliente chama `http://192.168.0.125:8080`.

### Checar se está funcionando

Numa **outra** janela de terminal, deixando a do uvicorn rodando. Nenhum dos dois testes gasta Z-API, HLR ou crédito nenhum:

```bash
curl -s "http://127.0.0.1:8080/health"
curl -s "http://127.0.0.1:8080/whatscheck?phone=2033334444"
```

Esperado:

```json
{"ok": true, "whatsapp": "zapi"}
{"error": true, "message": "DDD inexistente no Brasil"}
```

O primeiro diz que o serviço subiu, e o `whatsapp` mostra qual provedor está configurado. O segundo prova que a validação está barrando número impossível **antes** de chamar qualquer API paga — o DDD 20 não existe no Brasil.

No PowerShell escreva `curl.exe`, com o `.exe`: só `curl` é apelido do `Invoke-WebRequest` e mostra a saída de outro jeito.

A documentação interativa do FastAPI fica em `http://127.0.0.1:8080/docs`, e dá para disparar as chamadas por lá.

### O que funciona sem nenhuma chave

O serviço sobe e responde sem configurar nada. O que depende de config:

| Endpoint | Precisa de |
| --- | --- |
| `/health`, `/numbercheck` | nada |
| `/whatscheck` | `zapi/instances.json` ou `uazapi/instances.json`. Sem isso, **503** |
| `/telcheck`, `/lookup` | `hlr-lookup/config.env` com a chave da hlr-lookups |
| `/override/request`, `/override/confirm` | `override/config.env`, `db/config.env` e a tabela do `db/schema.sql`. Sem o driver ODBC, **503** |

Validação de número inválido responde **400** em qualquer caso, porque não chama nada externo. Passo a passo de teste no Windows, com cada endpoint: `COMO_TESTAR.md`.

## Chamadas

```
GET  /numbercheck?phone=5585996533131
GET  /whatscheck?phone=5585996533131
GET  /telcheck?phone=5585996533131
GET  /lookup?phone=5585996533131
POST /override/request
POST /override/confirm
GET  /health
```

`/numbercheck` só aplica o `number_check.py` (DDD, fixo, celular) e devolve o número normalizado, sem chamar nada externo: `{"phone": "5585996533131", "valid": true}`, ou **400** com a mesma mensagem dos outros endpoints. É o que o SACI usa no telefone adicional, que não precisa ter WhatsApp. Aceita lista como `/whatscheck`.

`phone` aceita com ou sem DDI 55 e com máscara. Sem `&ddd=`, usa **85**. Para forçar outro DDD:

```
GET /whatscheck?phone=996533131&ddd=11
```

## Lista de telefones

`/whatscheck` e `/telcheck` aceitam **vários números num pedido**, por vírgula ou repetindo `phone=`:

```
GET /whatscheck?phone=5585996533131,5585988887777
GET /telcheck?phone=5585996533131&phone=5585988887777
```

O `ddd=` vale para todos os números do pedido que vierem sem DDD.

Com **um** número a resposta é a de sempre (`{"phone": …, "exists": …}`). Com **dois ou mais** vem a lista, na ordem recebida:

```json
{
  "count": 3,
  "results": [
    {"phone": "5585996533131", "exists": true},
    {"phone": "5585988887777", "exists": false},
    {"input": "123", "error": true, "message": "Numero invalido"}
  ]
}
```

HTTP é **200** mesmo com itens com erro: cada item carrega o seu próprio `error`. Número que não passou na validação vem com `input` (o que foi enviado) em vez de `phone`, e não gasta chamada externa.

As duas exceções, que continuam a derrubar o pedido inteiro, são **nenhuma instância Z-API configurada** (503, no `/whatscheck`) e `phone` ausente ou vazio (400).

## Lógica

### Validação do número: a primeira barreira

Todo endpoint que recebe telefone passa primeiro por `number_check.py` — inclusive o `/override/request`. É análise estática, de graça e sem rede, e serve para recusar o que **não pode ser real** antes de gastar Z-API, hlr-lookups ou um pedido de liberação à gestora.

Um número válido é `55` + DDD + parte local, com:

- **DDD** entre os **67 códigos atribuídos**. Não existem 20, 23, 25, 26, 29, 30, 36, 39, 40, 50, 52, 56–60, 70, 72, 76, 78, 80 e 90.
- **Fixo** com 8 dígitos, o primeiro de **2 a 5**.
- **Celular** com 9 dígitos: o **9** do nono dígito, e depois **6, 7, 8 ou 9**.

As faixas vêm do plano de numeração brasileiro do libphonenumber do Google. A mensagem de erro diz qual regra falhou (ex.: `Numero invalido: celular comeca com 9 seguido de 6, 7, 8 ou 9`, `DDD inexistente no Brasil`).

Com um número só, número ou DDD inválido devolve **400** e **não** chama WhatsApp nem HLR. Em lista, o item inválido fica com erro próprio e os outros seguem. Tabela completa de regras e mensagens: `ESPECIFICACAO_ROTINAS.md`.

### Provedor de WhatsApp: Z-API ou uazapi

O `/whatscheck` e o `/override/request` falam com **um** provedor por vez, escolhido em `whatsapp/config.env`:

```
WHATSAPP_PROVIDER=zapi     # ou uazapi
```

Trocar é mudar essa linha e **reiniciar o servidor**. Vazio ou valor desconhecido cai em `zapi`. Para ver o que está valendo, `GET /health` devolve `{"ok": true, "whatsapp": "zapi"}`.

| | Z-API (`zapi`) | uazapi (`uazapi`) |
| --- | --- | --- |
| Instâncias | `zapi/instances.json` | `uazapi/instances.json` |
| Base | `https://api.z-api.io` | `https://{subdominio}.uazapi.com`, ou o seu host |
| Autenticação | header `Client-Token` | header `token` |
| Existe no WhatsApp | `GET /phone-exists/{numero}` → `exists` | `POST /chat/check` com `{"numbers": [...]}` → `isInWhatsapp` |
| Enviar texto | `POST /send-text` com `phone` e `message` | `POST /send/text` com `number` e `text` |

Os dois arquivos de instâncias podem ficar no disco ao mesmo tempo. Só o do provedor escolhido é lido, então dá para voltar atrás sem perder configuração.

O código que conhece cada provedor está em `zapi_client.py` e `uazapi_client.py`. Tudo o que é comum — ler o config, sortear, girar a ordem, a pausa e o failover — está em `whatsapp_client.py`, e é idêntico para os dois.

O envio do código para a gestora é a exceção: usa **sempre a primeira instância** do `instances.json` do provedor ativo, sem sorteio, sem pausa e sem failover, para ela receber todo código do mesmo número. Se essa instância falhar, o `/override/request` devolve **503** e não tenta outra.

### `/whatscheck`

1. Lê as instâncias do provedor configurado. Entrada incompleta é ignorada.
2. **Embaralha a lista uma única vez por pedido.** Os números seguintes não voltam a embaralhar: giram nessa ordem, em loop.
3. Cada tentativa é uma chamada ao provedor, sempre depois de uma pausa de 0,5 a 1 s.
4. A primeira resposta **HTTP 200** define o resultado: `exists: true` ou `exists: false`.
5. Se nenhuma instância responder 200, devolve **503** (número único) ou marca o item com erro (lista).

`exists: false` é resposta válida (o número não tem WhatsApp). Não é erro. No uazapi, um item que volta com `error` conta como **falha da instância**, não como "não tem WhatsApp": a rotação tenta a seguinte.

#### Como as instâncias giram

Com as instâncias `(A, B, C, D)` e o sorteio dando `(B, C, D, A)`, um pedido com 6 números começa assim:

| Número | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- |
| Instância | B | C | D | A | B | C |

Se a instância do número falhar, ele passa para a seguinte **dessa mesma ordem** (o número 1 tentaria B, depois C, D, A). Isso não muda onde o número seguinte começa: cada número avança exactamente uma posição em relação ao anterior.

O sorteio é por pedido, então dois pedidos seguidos não começam na mesma instância. O `instances.json` é lido a cada pedido: instância nova passa a entrar no sorteio do pedido seguinte, sem reiniciar o processo.

#### Tempo de um lote

A pausa de 0,5 a 1 s vale para **cada** chamada de WhatsApp, nos dois provedores, então um lote de N números leva no mínimo `N × 0,5 s`. Com 60 números são 30 a 60 segundos de pedido — vale conferir o timeout do cliente antes de mandar listas grandes.

### `/telcheck` (base MNP)

1. Faz `POST` em `https://www.hlr-lookups.com/api/v2/hlr-lookup` com o número em E.164 (`+55…`). A chave fica só em `hlr-lookup/config.env`.
2. `in_mnp` sai dessa resposta:
   - `processing_status` = `COMPLETED` → `true` (o número está na base MNP)
   - `REJECTED`, `FAILED` ou `connectivity_status` = `INVALID_MSISDN` → `false`
   - qualquer outro caso → `false`
3. Se a hlr-lookups falhar (rede, HTTP ou config), devolve **502** (número único) ou marca o item com erro (lista).

Em lista, cada número é uma consulta HLR, feita na ordem recebida. Não há pausa entre elas: a pausa de 0,5 a 1 s é só das chamadas de WhatsApp.

`in_mnp: false` é resposta válida (número fora da MNP ou inválido para ela). Não é o mesmo que o serviço estar fora.

`/lookup` usa a mesma consulta HLR e devolve o detalhe (operadora, portabilidade, `linha_ativa`). Com `data_source: MNP_DB`, `linha_ativa` não prova que o chip está ligado.

## Respostas

### `/whatscheck` com um número

| Situação | HTTP | Corpo |
| --- | --- | --- |
| Tem WhatsApp | 200 | `{"phone": "5585…", "exists": true}` |
| Não tem WhatsApp | 200 | `{"phone": "5585…", "exists": false}` |
| Número inválido | 400 | `{"error": true, "message": "Numero invalido"}` |
| DDD inválido | 400 | `{"error": true, "message": "DDD invalido"}` |
| Nenhuma instância Z-API ativa | 503 | `{"error": true, "message": "Nenhuma instancia esta ativa ou ZAPI nao respode"}` |
| Falha no programa | 500 | `{"error": true, "message": "Erro no programa: …"}` |

### `/telcheck` com um número

| Situação | HTTP | Corpo |
| --- | --- | --- |
| Está na MNP | 200 | `{"phone": "5585…", "in_mnp": true}` |
| Não está na MNP | 200 | `{"phone": "5585…", "in_mnp": false}` |
| Número inválido | 400 | `{"error": true, "message": "Numero invalido"}` |
| DDD inválido | 400 | `{"error": true, "message": "DDD invalido"}` |
| hlr-lookups falhou | 502 | `{"error": true, "message": "Erro no programa: …"}` |
| Falha no programa | 500 | `{"error": true, "message": "Erro no programa: …"}` |

### `/whatscheck` e `/telcheck` com lista

O pedido é **200** e o resultado de cada número vai dentro de `results`.

| Item | Corpo |
| --- | --- |
| Deu certo | `{"phone": "5585…", "exists": true}` ou `{"phone": "5585…", "in_mnp": true}` |
| Número ou DDD inválido | `{"input": "123", "error": true, "message": "Numero invalido"}` |
| Nenhuma instância deu 200 nesse número | `{"phone": "5585…", "error": true, "message": "Nenhuma instancia esta ativa ou ZAPI nao respode"}` |
| hlr-lookups falhou nesse número | `{"phone": "5585…", "error": true, "message": "Erro no programa: …"}` |

`count` é o total de itens em `results`, que é sempre igual ao número de telefones enviados.

| Situação | HTTP | Corpo |
| --- | --- | --- |
| `phone` ausente ou vazio | 400 | `{"error": true, "message": "Numero invalido"}` |
| Nenhuma instância Z-API configurada (`/whatscheck`) | 503 | `{"error": true, "message": "Nenhuma instancia esta ativa ou ZAPI nao respode"}` |

### `/lookup`

Sucesso HTTP **200** (detalhe HLR):

```json
{
  "numero": "+5585996533131",
  "connectivity_status": "CONNECTED",
  "processing_status": "COMPLETED",
  "data_source": "MNP_DB",
  "mccmnc": "72402",
  "operadora": "TIM CELULAR S.A.",
  "portado": false,
  "roaming": false,
  "linha_ativa": true,
  "nota": "sem HLR ao vivo (cobertura da rota ou só portabilidade)."
}
```

`linha_ativa`: `true` (CONNECTED/ABSENT), `false` (INVALID_MSISDN) ou `"indisponivel"`.  
`nota` pode ser `null`. Com `data_source: MNP_DB`, `linha_ativa` **não** prova chip ligado.

`/lookup` recebe **um** número por pedido. Lista é só em `/whatscheck` e `/telcheck`.

## Liberação de cadastro sem WhatsApp

`POST /override/request` e `POST /override/confirm` permitem cadastrar um cliente cujo número **não** tem WhatsApp, com autorização da gestora. A operadora pede, a gestora recebe um código no WhatsApp dela e repassa. O código vale poucos minutos, serve **uma vez** e **só para aquele telefone**.

A regra central: **o código não volta na resposta do `request`.** O servidor devolve só um `request_id`; o código sai direto para o celular da gestora. A máquina de quem pede nunca vê o segredo.

### `POST /override/request`

```json
{ "operador": "joao", "phone": "8533334444", "cliente_nome": "Maria", "motivo": "cliente sem celular" }
```

```json
{ "request_id": "xK3p9vQmZ1Ab", "phone": "558533334444", "expira_em": "2026-10-05T16:35:00", "validade_segundos": 300 }
```

Grava a linha `PENDENTE` em `LIBERACAO_WHATSAPP` e manda a mensagem pelo Z-API. O `ddd` é aceito e vale como nos outros endpoints.

### `POST /override/confirm`

```json
{ "request_id": "xK3p9vQmZ1Ab", "codigo": "482915", "phone": "8533334444" }
```

| Situação | HTTP | Corpo |
| --- | --- | --- |
| Liberado | 200 | `{"ok": true, "phone": "5585…"}` |
| Código errado, expirado, já usado, ou telefone diferente do pedido | 400 | `{"error": true, "message": "Codigo invalido ou expirado", "tentativas_restantes": 2}` |
| Config incompleto, SQL Server fora, ou Z-API não entregou | 503 | `{"error": true, "message": "…"}` |

As quatro falhas do 400 devolvem **a mesma frase**, de propósito: dizer qual delas ocorreu entrega informação para quem está tentando adivinhar o código.

### Configuração

| Arquivo | Conteúdo | Vai para o git? |
| --- | --- | --- |
| `override/config.env` | número da gestora, pepper do HMAC, validade, tentativas | não |
| `db/config.env` | connection string ODBC do SQL Server do SACI | não |
| `db/schema.sql` | DDL da tabela `LIBERACAO_WHATSAPP` | sim |

Precisa do **ODBC Driver 17 ou 18 for SQL Server** na máquina e do `pyodbc` do `requirements.txt`. O `pyodbc` é importado só quando o banco é usado, então o serviço sobe e o `/whatscheck` funciona mesmo sem o driver — apenas os dois endpoints de liberação devolvem 503.

No banco fica apenas o **HMAC-SHA256** do código, nunca o código em claro. A auditoria nasce no pedido, não na aprovação, então tentativas abandonadas e recusadas também ficam registradas.

O passo a passo de instalação, a adaptação do SACI e a trigger de bloqueio estão em `IMPLEMENTACAO_LIBERACAO_WHATSAPP.md`.

| Situação | HTTP | Corpo |
| --- | --- | --- |
| Número inválido | 400 | `{"error": true, "message": "Numero invalido"}` |
| DDD inválido | 400 | `{"error": true, "message": "DDD invalido"}` |
| hlr-lookups falhou | 502 | `{"error": true, "message": "Erro no programa: …"}` |
| Falha no programa | 500 | `{"error": true, "message": "Erro no programa: …"}` |

`/health` → `{"ok": true, "whatsapp": "zapi"}`. O campo `whatsapp` diz qual provedor está valendo.

Rede, venv e Windows: `GUIA_API_LAN.md`. Regras das rotinas: `ESPECIFICACAO_ROTINAS.md`. Liberação de cadastro: `IMPLEMENTACAO_LIBERACAO_WHATSAPP.md`.
