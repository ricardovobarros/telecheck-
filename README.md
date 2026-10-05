# telecheck-

API HTTP na LAN para verificar telefone no WhatsApp (`/whatscheck`) e na base MNP (`/telcheck`).

Base: `http://IP_DO_SERVIDOR:8080`

## Chamadas

```
GET /whatscheck?phone=5585996533131
GET /telcheck?phone=5585996533131
GET /lookup?phone=5585996533131
GET /health
```

`phone` aceita com ou sem DDI 55 e com máscara. Sem `&ddd=`, usa **85**. Para forçar outro DDD:

```
GET /whatscheck?phone=996533131&ddd=11
```

## Lógica

As duas chamadas passam primeiro por `number_check.py`. Número ou DDD inválido devolve **400** e **não** chama WhatsApp nem HLR.

### `/whatscheck` (Z-API)

1. Lê as instâncias de `zapi/instances.json` (id, token da instância e client-token). Entrada incompleta é ignorada.
2. Embaralha a lista e tenta uma a uma, com pausa de 0,5 a 1 s.
3. Cada tentativa é um `GET` em `https://api.z-api.io/instances/{id}/token/{token}/phone-exists/{phone}`, com o header `Client-Token`.
4. A primeira resposta **HTTP 200** define o resultado: `exists: true` ou `exists: false`.
5. Se nenhuma instância responder 200, devolve **503**.

`exists: false` é resposta válida (o número não tem WhatsApp). Não é erro.

### `/telcheck` (base MNP)

1. Faz `POST` em `https://www.hlr-lookups.com/api/v2/hlr-lookup` com o número em E.164 (`+55…`). A chave fica só em `hlr-lookup/config.env`.
2. `in_mnp` sai dessa resposta:
   - `processing_status` = `COMPLETED` → `true` (o número está na base MNP)
   - `REJECTED`, `FAILED` ou `connectivity_status` = `INVALID_MSISDN` → `false`
   - qualquer outro caso → `false`
3. Se a hlr-lookups falhar (rede, HTTP ou config), devolve **502**.

`in_mnp: false` é resposta válida (número fora da MNP ou inválido para ela). Não é o mesmo que o serviço estar fora.

`/lookup` usa a mesma consulta HLR e devolve o detalhe (operadora, portabilidade, `linha_ativa`). Com `data_source: MNP_DB`, `linha_ativa` não prova que o chip está ligado.

## Respostas

### `/whatscheck`

| Situação | HTTP | Corpo |
| --- | --- | --- |
| Tem WhatsApp | 200 | `{"phone": "5585…", "exists": true}` |
| Não tem WhatsApp | 200 | `{"phone": "5585…", "exists": false}` |
| Número inválido | 400 | `{"error": true, "message": "Numero invalido"}` |
| DDD inválido | 400 | `{"error": true, "message": "DDD invalido"}` |
| Nenhuma instância Z-API ativa | 503 | `{"error": true, "message": "Nenhuma instancia esta ativa ou ZAPI nao respode"}` |
| Falha no programa | 500 | `{"error": true, "message": "Erro no programa: …"}` |

### `/telcheck`

| Situação | HTTP | Corpo |
| --- | --- | --- |
| Está na MNP | 200 | `{"phone": "5585…", "in_mnp": true}` |
| Não está na MNP | 200 | `{"phone": "5585…", "in_mnp": false}` |
| Número inválido | 400 | `{"error": true, "message": "Numero invalido"}` |
| DDD inválido | 400 | `{"error": true, "message": "DDD invalido"}` |
| hlr-lookups falhou | 502 | `{"error": true, "message": "Erro no programa: …"}` |
| Falha no programa | 500 | `{"error": true, "message": "Erro no programa: …"}` |

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

| Situação | HTTP | Corpo |
| --- | --- | --- |
| Número inválido | 400 | `{"error": true, "message": "Numero invalido"}` |
| DDD inválido | 400 | `{"error": true, "message": "DDD invalido"}` |
| hlr-lookups falhou | 502 | `{"error": true, "message": "Erro no programa: …"}` |
| Falha no programa | 500 | `{"error": true, "message": "Erro no programa: …"}` |

`/health` → `{"ok": true}`.

Rede, venv e Windows: `GUIA_API_LAN.md`. Regras das rotinas: `ESPECIFICACAO_ROTINAS.md`.
