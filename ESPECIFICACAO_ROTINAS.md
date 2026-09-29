# Especificação: rotinas `/whatscheck` e `/telcheck`

Este documento descreve **como o script deve funcionar**. Não substitui o `GUIA_API_LAN.md` (rede, venv, Windows).

O servidor escuta na LAN (ex.: `http://192.168.1.50:8080`). Código: `servidor.py` na raiz do **telecheck-**.

---

## Validação do número (antes de qualquer endpoint)

**Nenhum** endpoint que recebe telefone chama Z-API ou hlr-lookups sem passar primeiro pela lógica de `number_check.py` (a mesma de `_Archive/PycharmProjects/tel_app/number_check.py` → `format_number`).

Query:

```
?phone=85996533131
?phone=5585996533131
?phone=996533131&ddd=85
```

| Parâmetro | Uso |
| --- | --- |
| `phone` | Número (com ou sem máscara, com ou sem DDI 55) |
| `ddd` | Obrigatório só se o número tiver **8 ou 9 dígitos** (sem DDD) |

Regras (depois de tirar tudo o que não é dígito):

- **10 dígitos** e não começa por `9` → fixo com DDD → válido (`55` + número).
- **11 dígitos** e o 3.º dígito é `9` → celular com DDD → válido (`55` + número).
- Já vem com DDI **55** (12 ou 13 dígitos) → corta o `55` e aplica as regras acima.
- **8 dígitos** a começar por 6–9 → acrescenta o `9` do celular; precisa de `ddd` com 2 dígitos.
- **9 dígitos** a começar por `9` → precisa de `ddd` com 2 dígitos.
- Qualquer outro comprimento/padrão → inválido.

Se a validação falhar, o endpoint **para**. Não há chamada externa. Resposta:

```json
{
  "error": true,
  "message": "Numero invalido"
}
```

HTTP **400**. Se faltar DDD quando o número não tem DDD:

```json
{
  "error": true,
  "message": "DDD invalido"
}
```

O campo `phone` devolvido nos sucessos é sempre o número já normalizado (DDI 55, só dígitos).

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

## Configuração das instâncias Z-API (ficheiro separado)

As credenciais Z-API **não** ficam no código. Ficam num JSON à parte:

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

---

## Rotina `GET /whatscheck`

**Objetivo:** dizer se o número existe no WhatsApp, usando Z-API, sem gastar sempre a mesma instância.

### Fluxo

1. Validar `phone` / `ddd` (`number_check.py`). Se inválido → erro 400, **não** chama a Z-API.
2. Ler `zapi/instances.json` e montar a lista de instâncias válidas.
3. Se a lista estiver vazia, responder como se nenhuma instância tivesse funcionado (passo 8).
4. **Embaralhar** a lista (ordem aleatória). Não usar sempre a primeira.
5. Percorrer a lista. Para **cada** instância:
   - **Antes** de chamar a Z-API, pausar um tempo **aleatório entre 0,5 e 1,0 segundo**.
   - Chamar `phone-exists` com essa instância.
   - Se a HTTP for **200**: parar. Devolver o valor da Z-API (`exists`: `true` ou `false`).
   - Se a HTTP for **qualquer outro código** (ou timeout, ou erro de rede): **não** devolver esse erro ao cliente. Escolher a **próxima** instância da lista já embaralhada e repetir (pausa + chamada).
6. Não reutilizar, no mesmo pedido, uma instância que já falhou.
7. A primeira instância que responder **200** ganha. O corpo dessa resposta é o resultado.
8. Se **nenhuma** instância der HTTP 200, devolver exatamente:

```
Nenhuma instancia esta ativa ou ZAPI nao respode
```

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

## Resumo

| Endpoint | Fonte | Sucesso | Falha |
| --- | --- | --- | --- |
| `/whatscheck` | validação → Z-API (instância aleatória, retry) | `exists` true/false | 400 número; 503 frase Z-API; 500 programa |
| `/telcheck` | validação → hlr-lookups (MNP) | `in_mnp` true/false | 400 número; 502/500 `Erro no programa: …` |
| `/lookup` | validação → hlr-lookups (detalhe) | JSON HLR | igual ao `/telcheck` |
| `/health` | — | `{"ok": true}` | 500 `Erro no programa: …` |

`/whatscheck` nunca deve martelar a mesma instância: pausa 0,5–1 s aleatória, ordem aleatória, e instância nova no JSON = instância usada no pedido seguinte.
