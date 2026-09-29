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
