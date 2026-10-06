# Especificação: rotinas `/whatscheck` e `/telcheck`

Este documento descreve **como o script deve funcionar**. Não substitui o `GUIA_API_LAN.md` (rede, venv, Windows).

O servidor escuta na LAN (ex.: `http://192.168.1.50:8080`). Código: `servidor.py` na raiz do **telecheck-**.

---

## Validação do número (antes de qualquer endpoint)

**Nenhum** endpoint que recebe telefone chama Z-API ou hlr-lookups sem passar primeiro pelo `number_check.py`. O `/override/request` também não: não se acorda a gestora por um número que não pode existir.

Esta é a **primeira barreira** e é de graça: só análise estática, sem rede. O objetivo é recusar aqui tudo o que **não pode ser real**, para não gastar chamada paga nem pedido de liberação com número digitado errado.

As faixas vêm do plano de numeração brasileiro do **libphonenumber** do Google (`PhoneNumberMetadata.xml`, `<territory id="BR">`, tags `fixedLine` e `mobile`).

Query:

```
?phone=85996533131
?phone=5585996533131
?phone=996533131&ddd=85
?phone=5585996533131,5585988887777
?phone=5585996533131&phone=5585988887777
```

| Parâmetro | Uso |
| --- | --- |
| `phone` | Número (com ou sem máscara, com ou sem DDI 55). Em `/whatscheck` e `/telcheck` aceita vários, por vírgula ou repetindo `phone=` |
| `ddd` | Obrigatório só se o número tiver **8 ou 9 dígitos** (sem DDD). Vale para todos os números do pedido |

### O que é um número válido no Brasil

Depois de tirar tudo o que não é dígito, o número tem de ser `55` + **DDD** + **parte local**:

| Parte | Regra |
| --- | --- |
| DDD | 2 dígitos, e só os **67 códigos realmente atribuídos** |
| Fixo | 8 dígitos, o primeiro de **2 a 5** |
| Celular | 9 dígitos: o **9** do nono dígito, e depois **6, 7, 8 ou 9** |

Os DDDs aceitos:

```
11 12 13 14 15 16 17 18 19   21 22 24 27 28   31 32 33 34 35 37 38
41 42 43 44 45 46 47 48 49   51 53 54 55      61 62 63 64 65 66 67 68 69
71 73 74 75 77 79            81 82 83 84 85 86 87 88 89
91 92 93 94 95 96 97 98 99
```

Não existem, entre outros, **20, 23, 25, 26, 29, 30, 36, 39, 40, 50, 52, 56–60, 70, 72, 76, 78, 80 e 90**. Um `(20) 3333-4444` é recusado sem gastar nada.

### Como o número chega

| Dígitos recebidos | Tratamento |
| --- | --- |
| 12 ou 13 começando por `55` | Corta o DDI e aplica as regras abaixo |
| 10 ou 11 | Os 2 primeiros são o DDD; o resto é a parte local |
| 8 ou 9 | É tudo parte local; o DDD vem do `ddd=` ou é o **85** |
| Qualquer outro comprimento | Inválido |

Depois disso, **parte local de 8 dígitos começada em 6–9** é celular anterior ao nono dígito (o fixo nunca passa de 5) e ganha o `9` na frente, como fez a Anatel. Isso vale **com e sem DDD**, porque base antiga guarda os dois formatos: `8593334444` e `93334444&ddd=85` dão os dois `5585993334444`.

O `55` da frente só é tratado como DDI quando o que sobra tem tamanho de número nacional. Por isso `5533331234` é lido como o **DDD 55** (Santa Maria), e não como DDI + 8 dígitos.

### Resposta quando falha

Com **um** número, o endpoint **para** e não há chamada externa. HTTP **400**:

```json
{
  "error": true,
  "message": "Numero invalido: celular comeca com 9 seguido de 6, 7, 8 ou 9"
}
```

A mensagem diz o que está errado, para a operadora corrigir sem adivinhar:

| Mensagem | Quando |
| --- | --- |
| `Numero invalido` | Sem dígito nenhum |
| `Numero invalido: precisa de 8 a 11 digitos, ou 12 a 13 com o 55` | Comprimento impossível |
| `Numero invalido: fixo comeca com 2, 3, 4 ou 5` | 8 dígitos locais fora da faixa de fixo |
| `Numero invalido: celular comeca com 9 seguido de 6, 7, 8 ou 9` | 9 dígitos locais fora da faixa de celular |
| `DDD invalido` | O `ddd=` não tem 2 dígitos |
| `DDD inexistente no Brasil` | O DDD tem 2 dígitos, mas não é um dos 67 |

O campo `phone` devolvido nos sucessos é sempre o número já normalizado (DDI 55, só dígitos).

### Onde isto é mais restrito que o libphonenumber

Dois pontos, de propósito, porque a Anatel não atribui essas faixas e o objetivo é barrar o que não pode ser real:

1. **Celular `9` seguido de 0 a 5.** O libphonenumber aceita o `9` seguido de qualquer dígito; a faixa móvel real começa em 6. Para afrouxar, troque `CELULAR_RE` por `r"^9\d{8}$"`.
2. **Fixo de 8 dígitos começando por `7`.** Era o trunking da Nextel (SME), desligado em 2018. Para aceitar, use `r"^[2-57]\d{7}$"` em `FIXO_RE`.

Fora destes dois casos, a validação aceita exatamente o mesmo conjunto que o libphonenumber: nunca recusa um número que ele considere real.

---

## Lista de telefones (`/whatscheck` e `/telcheck`)

Os dois endpoints aceitam **N números por pedido**, por vírgula (`phone=a,b`) ou repetindo o parâmetro (`phone=a&phone=b`). Espaços em volta de cada número são ignorados; valores vazios são descartados.

Regras:

1. Cada número passa pela mesma validação de `number_check.py`, na ordem recebida.
2. Com **um** número, a resposta e os códigos HTTP são os de sempre (compatibilidade).
3. Com **dois ou mais**, a resposta é HTTP **200** com `count` e `results`, na ordem recebida.
4. Um item com erro **não** derruba o lote. Ele leva o próprio `error` / `message` e os outros seguem.
5. Item que não passou na validação vem com `input` (o valor enviado) em vez de `phone`, e **não** gasta chamada externa.
6. `count` é sempre igual à quantidade de telefones enviados.

Derrubam o pedido inteiro apenas:

| Situação | HTTP |
| --- | --- |
| `phone` ausente ou vazio | 400 `Numero invalido` |
| Nenhuma instância Z-API configurada (`/whatscheck`) | 503 |

Formato:

```json
{
  "count": 3,
  "results": [
    { "phone": "5585996533131", "exists": true },
    { "phone": "5585988887777", "exists": false },
    { "input": "123", "error": true, "message": "Numero invalido" }
  ]
}
```

`/lookup` continua a receber **um** número por pedido.

---

## Erro em todos os endpoints

Se o programa **não funcionar como esperado** (exceção, API externa a falhar, config em falta), **todos** os endpoints devolvem o mesmo formato:

```json
{
  "error": true,
  "message": "Erro no programa: …"
}
```

| Situação | HTTP | `message` |
| --- | --- | --- |
| Número ou DDD inválido | 400 | `Numero invalido` ou `DDD invalido` |
| Falha inesperada no código | 500 | `Erro no programa: …` |
| hlr-lookups inacessível (`/telcheck`, `/lookup`) | 502 | `Erro no programa: …` |
| Nenhuma instância Z-API com HTTP 200 (`/whatscheck`) | 503 | `Nenhuma instancia esta ativa ou ZAPI nao respode` |

`/health` não recebe telefone. Se rebentar, também devolve `error` / `message` (HTTP 500).

---

## Configuração das instâncias (ficheiro separado)

O provedor de WhatsApp é escolhido em `whatsapp/config.env` (`WHATSAPP_PROVIDER=zapi` ou `uazapi`) — ver "Trocar para o uazapi", mais abaixo. O padrão é a Z-API.

As credenciais **não** ficam no código. Ficam num JSON à parte:

| Ficheiro | Função |
| --- | --- |
| `zapi/instances.example.json` | Modelo (pode ir para o git) |
| `zapi/instances.json` | Instâncias reais (não vai para o git) |

Copia o exemplo e preenche:

```bat
copy zapi\instances.example.json zapi\instances.json
```

Formato:

```json
{
  "instances": [
    {
      "name": "instancia-1",
      "instance_id": "…",
      "instance_token": "…",
      "client_token": "…"
    },
    {
      "name": "instancia-2",
      "instance_id": "…",
      "instance_token": "…",
      "client_token": "…"
    }
  ]
}
```

Regras:

1. Podes ter **N instâncias**. Cada objeto em `instances` é uma.
2. Sempre que adicionares uma instância nova ao `instances.json`, ela passa a ser usada. **Não** é preciso alterar código.
3. O servidor **rele o ficheiro em cada pedido**. Assim uma instância nova vale no pedido seguinte, sem reiniciar o processo.
4. Só entram instâncias com `instance_id`, `instance_token` e `client_token` preenchidos.

Endpoint Z-API por instância:

```
GET https://api.z-api.io/instances/{instance_id}/token/{instance_token}/phone-exists/{numero}
Header: Client-Token: {client_token}
```

### Trocar para o uazapi

O provedor sai de `WHATSAPP_PROVIDER` em `whatsapp/config.env`, e vale só para as chamadas de WhatsApp (`/whatscheck` e a mensagem do `/override/request`). O HLR não muda.

```
WHATSAPP_PROVIDER=uazapi
```

É preciso **reiniciar o servidor**: o valor é lido no import, não a cada pedido. O `GET /health` mostra o que está valendo. Vazio ou valor desconhecido cai em `zapi`, para uma linha com erro de digitação não derrubar o serviço.

Com `uazapi`, o arquivo lido passa a ser `uazapi/instances.json`:

```json
{
  "base_url": "https://SEU_SUBDOMINIO.uazapi.com",
  "instances": [
    { "name": "linha-1", "token": "…" },
    { "name": "linha-2", "token": "…" },
    { "name": "linha-3", "token": "…", "base_url": "https://wa.empresa.com.br" }
  ]
}
```

O `base_url` do topo vale para todas, porque o normal é as instâncias de uma conta viverem no mesmo subdomínio. Por instância, ele sobrepõe o do topo — serve para self-hosted. Só entram instâncias com `token` e algum `base_url`.

Endpoints uazapi por instância, conforme a [especificação oficial](https://docs.uazapi.com/openapi-bundled.json):

```
POST {base_url}/chat/check    {"numbers": ["{numero}"]}
POST {base_url}/send/text     {"number": "{numero}", "text": "…"}
Header: token: {token}
```

O `/chat/check` responde uma **lista**, um item por número pedido, e aqui pedimos um por chamada para manter a rotação de instâncias. O `isInWhatsapp` do primeiro item é o `exists`. Item que volta com `error` conta como **falha da instância**, não como "não tem WhatsApp", e a rotação tenta a seguinte. O mesmo vale para o HTTP **429** de limite de chamadas.

O resto — sorteio, ordem em loop, pausa de 0,5 a 1 s, failover e os códigos HTTP — é idêntico nos dois provedores: está em `whatsapp_client.py`, fora do código de cada um.

---

## Rotina `GET /whatscheck`

**Objetivo:** dizer se o número existe no WhatsApp, usando o provedor configurado, sem gastar sempre a mesma instância.

### Fluxo

1. Validar `phone` / `ddd` (`number_check.py`). Com um número só, inválido → erro 400 e **não** chama a Z-API. Em lista, o item inválido fica marcado e os outros seguem.
2. Ler `zapi/instances.json` e montar a lista de instâncias válidas.
3. Se a lista estiver vazia, responder como se nenhuma instância tivesse funcionado (passo 9).
4. **Embaralhar** a lista **uma única vez por pedido**. Essa ordem sorteada vale para todos os números do pedido.
5. Cada número começa na instância **seguinte** à do número anterior, girando a ordem em loop. Sorteio `(B, C, D, A)` com 6 números dá `B, C, D, A, B, C`. Não há segundo embaralhamento.
6. Para cada tentativa de um número:
   - **Antes** de chamar a Z-API, pausar um tempo **aleatório entre 0,5 e 1,0 segundo**.
   - Chamar `phone-exists` com essa instância.
   - Se a HTTP for **200**: parar. Devolver o valor da Z-API (`exists`: `true` ou `false`).
   - Se a HTTP for **qualquer outro código** (ou timeout, ou erro de rede): **não** devolver esse erro ao cliente. Passar para a **próxima** instância da ordem sorteada e repetir (pausa + chamada).
7. Dentro do mesmo número não se repete instância que já falhou. O failover não muda onde o número seguinte começa: cada número avança exatamente uma posição em relação ao anterior.
8. A primeira instância que responder **200** ganha. O corpo dessa resposta é o resultado.
9. Se **nenhuma** instância der HTTP 200, devolver exatamente:

```
Nenhuma instancia esta ativa ou ZAPI nao respode
```

Num lote, isso vale por número: o número que esgotar todas as instâncias fica com esse `message` no próprio item, sem derrubar os outros.

### Resposta quando a Z-API responde 200

HTTP 200. JSON com o `exists` da Z-API (`true` ou `false`):

```json
{
  "phone": "5585996533131",
  "exists": true
}
```

`exists: true` = número tem WhatsApp. `exists: false` = número não tem WhatsApp. Isto **não** é falha de instância.

### Resposta quando nenhuma instância funciona

HTTP 503:

```json
{
  "error": true,
  "message": "Nenhuma instancia esta ativa ou ZAPI nao respode"
}
```

### Exemplo

```
GET http://192.168.1.50:8080/whatscheck?phone=5585996533131
```

---

## Rotina `GET /telcheck`

**Objetivo:** dizer se o número está na base MNP (hlr-lookups.com). Só `true` ou `false`.

Usar a mesma chamada que `hlr-lookup/lookup_ativo.py` (`POST /api/v2/hlr-lookup`, chaves em `hlr-lookup/config.env`).

### Fluxo

1. Validar `phone` / `ddd`. Se inválido → erro 400, **não** chama a hlr-lookups.
2. Consultar a API hlr-lookups com o número já normalizado.
3. Interpretar:

| Situação | Retorno |
| --- | --- |
| Pedido concluído e o número **não** é `INVALID_MSISDN` (está na base MNP) | `true` |
| `INVALID_MSISDN`, ou processamento `REJECTED` / `FAILED` | `false` |

`CONNECTED` e `ABSENT` no MNP contam como **está na base** → `true`. O que importa nesta rotina é **existência na MNP**, não chip ligado.

Se a hlr-lookups falhar por rede/HTTP (não der para consultar), **não** inventar `false`. Devolver:

```json
{
  "error": true,
  "message": "Erro no programa: …"
}
```

HTTP **502**.

### Resposta de sucesso

HTTP 200:

```json
{
  "phone": "5585996533131",
  "in_mnp": true
}
```

`in_mnp` é o `true`/`false` da tabela acima.

### Exemplo

```
GET http://192.168.1.50:8080/telcheck?phone=5585996533131
```

---

## Rotinas `POST /override/request` e `POST /override/confirm`

**Objetivo:** permitir cadastrar cliente cujo número não tem WhatsApp, com autorização da gestora, sem que a máquina de quem pede conheça o código.

### Invariantes

1. O `request` **não** devolve o código. Devolve `request_id`, `phone` normalizado e `expira_em`. O código vai por Z-API só para `OVERRIDE_GESTORA_PHONE`.
2. O código é gerado com `secrets`. No banco fica apenas o HMAC-SHA256 de `request_id:codigo` com o `OVERRIDE_PEPPER`.
3. **Uso único.** A aprovação é um `UPDATE ... WHERE LIB_STATUS='PENDENTE'` com conferência de `rowcount`, então duas confirmações simultâneas não passam as duas.
4. **Preso ao telefone.** O `confirm` recusa se o telefone não for o mesmo do `request`. Sem isso, um código aprovado viraria passe livre para qualquer número.
5. Tentativa errada incrementa o contador; ao atingir `OVERRIDE_MAX_ATTEMPTS` o código vira `BLOQUEADA`. Telefone trocado também conta como tentativa.
6. Código errado, expirado, consumido e telefone trocado devolvem **a mesma mensagem**. A distinção entre eles não é exposta.
7. A linha de auditoria é criada no **pedido**. Pedido abandonado, expirado ou recusado também fica gravado.

### Estados

| Status | Significado |
| --- | --- |
| `PENDENTE` | aguardando a operadora digitar o código |
| `APROVADA` | código conferido e consumido |
| `BLOQUEADA` | estourou o limite de tentativas |
| `EXPIRADA` | passou da validade sem uso |
| `FALHA_ENVIO` | o Z-API não entregou a mensagem à gestora |

### Erros

| Situação | HTTP | `message` |
| --- | --- | --- |
| Código errado, expirado, usado, ou telefone diferente | 400 | `Codigo invalido ou expirado` |
| `override/config.env` sem número da gestora ou sem pepper | 503 | `Liberacao nao configurada no servidor` |
| SQL Server inacessível ou `pyodbc` ausente | 503 | `Erro no programa: …` |
| Z-API não entregou a mensagem | 503 | `Nao foi possivel avisar a gestora` |

O número do pedido passa pela **mesma validação** de `/whatscheck` e `/telcheck`, e um número inválido devolve 400 com a mensagem do `number_check` **antes** de qualquer mensagem à gestora. A liberação dispensa o WhatsApp, não o formato: não se acorda a gestora por um número que não pode existir.

Detalhe de instalação, adaptação do SACI e a trigger: `IMPLEMENTACAO_LIBERACAO_WHATSAPP.md`.

---

## Resumo

| Endpoint | Fonte | Sucesso | Falha |
| --- | --- | --- | --- |
| `/whatscheck` | validação → Z-API (ordem sorteada por pedido, em loop, com retry) | `exists` true/false | 400 número; 503 frase Z-API; 500 programa |
| `/telcheck` | validação → hlr-lookups (MNP) | `in_mnp` true/false | 400 número; 502/500 `Erro no programa: …` |
| `/lookup` | validação → hlr-lookups (detalhe) | JSON HLR | igual ao `/telcheck` |
| `/override/request` | código novo → SQL Server → Z-API para a gestora | `request_id` e `expira_em`, sem o código | 400 número; 503 config, banco ou Z-API |
| `/override/confirm` | SQL Server (uso único, preso ao telefone) | `ok true` | 400 `Codigo invalido ou expirado`; 503 banco |
| `/health` | — | `{"ok": true, "whatsapp": "zapi"}` | 500 `Erro no programa: …` |

`/whatscheck` e `/telcheck` aceitam lista de telefones; `/lookup` só um número.

`/whatscheck` nunca deve martelar a mesma instância: pausa 0,5–1 s aleatória antes de cada chamada, ordem sorteada a cada pedido e girada em loop entre os números, e instância nova no JSON = instância usada no pedido seguinte.
