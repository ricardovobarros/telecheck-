# Como testar a API telecheck- neste servidor

Este computador é o **servidor**.

| Item | Valor |
| --- | --- |
| Pasta do projeto | `C:\Users\tarciopontes\Documents\_Victor\telecheck-` |
| Python | 3.11.9 |
| Ambiente virtual | `.venv` (dentro da pasta do projeto) |
| IP na LAN | `192.168.0.125` (placa `Ethernet`) |
| Porta | `8080` |
| Base local | `http://127.0.0.1:8080` |
| Base na LAN | `http://192.168.0.125:8080` |

---

## 1. Ligar o servidor

Abra o PowerShell e rode:

```powershell
cd C:\Users\tarciopontes\Documents\_Victor\telecheck-
.\.venv\Scripts\Activate.ps1
uvicorn servidor:app --host 0.0.0.0 --port 8080
```

Se o PowerShell bloquear o `Activate.ps1`, rode uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Alternativa sem ativar o venv (funciona igual):

```powershell
cd C:\Users\tarciopontes\Documents\_Victor\telecheck-
.\.venv\Scripts\python.exe -m uvicorn servidor:app --host 0.0.0.0 --port 8080
```

O servidor está no ar quando aparecer:

```
Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

Para parar: `Ctrl + C` nessa janela.

---

## 2. Testar neste computador

Abra **outra** janela do PowerShell (deixe a do uvicorn rodando) e use `curl.exe`.

> No PowerShell escreva `curl.exe`, com o `.exe`. Só `curl` é um apelido do `Invoke-WebRequest` e mostra a saída de outro jeito.

### 2.1 Saúde do serviço

```powershell
curl.exe -s "http://127.0.0.1:8080/health"
```

Esperado: `{"ok":true}`

### 2.2 Número inválido (não gasta Z-API nem HLR)

```powershell
curl.exe -s "http://127.0.0.1:8080/lookup?phone=nao-e-numero"
```

Esperado: `{"error":true,"message":"Numero invalido"}` com HTTP 400.

### 2.3 WhatsApp

```powershell
curl.exe -s "http://127.0.0.1:8080/whatscheck?phone=5585996533131"
```

Esperado: `{"phone":"5585996533131","exists":true}`

### 2.4 Base MNP

```powershell
curl.exe -s "http://127.0.0.1:8080/telcheck?phone=5585996533131"
```

Esperado: `{"phone":"5585996533131","in_mnp":true}`

### 2.5 Detalhe HLR

```powershell
curl.exe -s "http://127.0.0.1:8080/lookup?phone=5585996533131"
```

Esperado (exemplo real deste servidor):

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

### 2.6 Número sem DDD

Sem `ddd=`, a API assume **85**:

```powershell
curl.exe -s "http://127.0.0.1:8080/telcheck?phone=996533131"
```

Para forçar outro DDD:

```powershell
curl.exe -s "http://127.0.0.1:8080/telcheck?phone=996533131&ddd=11"
```

DDD com quantidade de dígitos errada devolve `{"error":true,"message":"DDD invalido"}`.

> No PowerShell, URLs com `&` precisam de aspas (os exemplos já estão entre aspas).

### 2.7 Ver o código HTTP junto da resposta

```powershell
curl.exe -s -w "`nHTTP %{http_code}`n" "http://127.0.0.1:8080/health"
```

### 2.8 Pelo navegador

Abra no Chrome:

```
http://127.0.0.1:8080/health
http://127.0.0.1:8080/lookup?phone=5585996533131
```

A documentação automática do FastAPI fica em `http://127.0.0.1:8080/docs`, e dá para disparar as chamadas por lá.

---

## 3. Testar pelo IP da LAN (ainda neste computador)

```powershell
curl.exe -s "http://192.168.0.125:8080/health"
```

Se `127.0.0.1` responde e o IP da LAN não, o servidor subiu com `--host 127.0.0.1` em vez de `0.0.0.0`.

---

## 4. Testar de outro computador da rede

No PC cliente (mesma rede, sem usar `localhost`):

```powershell
curl.exe -s "http://192.168.0.125:8080/health"
curl.exe -s "http://192.168.0.125:8080/telcheck?phone=5585996533131"
curl.exe -s "http://192.168.0.125:8080/whatscheck?phone=5585996533131"
```

### Liberar a porta no firewall

Ainda **não existe** regra de firewall para a porta 8080 neste servidor. Enquanto não criar, outro PC pode dar timeout. Rode uma vez no PowerShell **como administrador**:

```powershell
New-NetFirewallRule -DisplayName "telecheck-" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private
```

---

## 5. Conferir se está tudo no lugar

```powershell
cd C:\Users\tarciopontes\Documents\_Victor\telecheck-

# dependências instaladas no venv
.\.venv\Scripts\python.exe -c "import fastapi, uvicorn; print('ok')"

# arquivos de configuração (devem existir, e ficam fora do git)
Test-Path .\hlr-lookup\config.env
Test-Path .\zapi\instances.json

# quem está escutando a porta
Get-NetTCPConnection -LocalPort 8080 -State Listen
```

---

## 6. Resumo dos endpoints

| Endpoint | Para quê | Resposta de sucesso |
| --- | --- | --- |
| `GET /health` | Serviço está no ar | `{"ok": true}` |
| `GET /whatscheck?phone=` | Número tem WhatsApp | `{"phone": "...", "exists": true}` |
| `GET /telcheck?phone=` | Número está na base MNP | `{"phone": "...", "in_mnp": true}` |
| `GET /lookup?phone=` | Detalhe HLR (operadora, portabilidade) | JSON completo |

Erros seguem sempre o mesmo formato:

```json
{"error": true, "message": "..."}
```

| Mensagem | HTTP | Quando acontece |
| --- | --- | --- |
| `Numero invalido` | 400 | `phone` não passou na validação; nada externo foi chamado |
| `DDD invalido` | 400 | número de 8 ou 9 dígitos com `ddd` fora do formato de 2 dígitos |
| `Nenhuma instancia esta ativa ou ZAPI nao respode` | 503 | nenhuma instância Z-API devolveu HTTP 200 |
| `Erro no programa: ...` | 500 / 502 | falha inesperada, ou a hlr-lookups não respondeu |

Atenção: `exists: false` e `in_mnp: false` são **respostas válidas**, não erro. Erro é só quando vem `"error": true`.

---

## 7. Problemas comuns

| Sintoma | Causa provável |
| --- | --- |
| `fastapi not found` | rodou com o Python global em vez do `.venv` |
| Nada responde em `127.0.0.1:8080` | o uvicorn não está rodando, ou a janela foi fechada |
| Funciona aqui, mas não no outro PC | falta a regra de firewall da porta 8080, ou os PCs estão em redes diferentes |
| Funcionava ontem, hoje não | o IP `192.168.0.125` mudou (DHCP). Confira com `ipconfig` e considere reserva de DHCP no roteador |
| `pip` falha com erro de certificado SSL | rede com inspeção TLS. Use `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt` |
| `Nenhuma instancia esta ativa` | a instância em `zapi\instances.json` caiu ou o token expirou |

---

## 8. Segredos

Ficam só neste computador e estão fora do git:

- `hlr-lookup\config.env` — chaves da hlr-lookups
- `zapi\instances.json` — instâncias da Z-API

Os arquivos `*.example` do repositório devem conter **apenas placeholders**. Nunca coloque chave real neles: o repositório é público.
