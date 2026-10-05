# Guia: API na rede fechada — **telecheck-** (servidor Windows)

O programa chama-se **telecheck-**, o mesmo nome do repositório GitHub (`telecheck-`).

Este documento descreve **como desenvolver** o serviço: o **telecheck-** corre num **PC Windows servidor**; outro computador da **mesma rede local** chama HTTP como se fosse uma API. O tráfego **não passa pela internet**. Só o Windows servidor (opcionalmente) fala com a hlr-lookups.com.

Premissa: o **servidor é Windows**. Os outros PCs / o SACI são **clientes**.

Ambiente Python: um **venv só para o telecheck-** (não uses conda `hypy` nem o Python global).

```
[PC cliente: SACI / browser / curl]
        |
        |  LAN  (ex.: http://192.168.1.50:8080/telcheck?phone=5585…)
        v
[Windows servidor: telecheck-  (venv)  escuta a porta 8080]
        |
        |  só daqui  (hlr-lookups.com e/ou Z-API)
        v
[Internet — o cliente nunca vê as chaves]
```

---

## 1. O que vais construir

O **telecheck-** é um **servidor HTTP** (`servidor.py` na raiz):

- Fica **à escuta** o dia todo (enquanto o Windows estiver ligado).
- **Antes** de `/whatscheck`, `/telcheck`, `/lookup` e `/override/request`, valida o número com `number_check.py` (DDD atribuído, fixo 2–5, celular 9 + 6–9). Número que não pode ser real → erro JSON, **sem** chamada externa e **sem** avisar a gestora.
- Se o programa falhar de forma inesperada, **todos** os endpoints devolvem `{"error": true, "message": "Erro no programa: …"}`.
- Escuta em `0.0.0.0` (toda a LAN), **não** só em `127.0.0.1`.

Rotinas detalhadas: `ESPECIFICACAO_ROTINAS.md`.

Não precisas de domínio, cloud nem ngrok.

---

## 2. Antes de programar: rede no Windows servidor

### 2.1 Confirmar o IP local

No **Prompt de Comando** ou **PowerShell**:

```bat
ipconfig
```

Procura **IPv4** da placa que usas (Ethernet ou Wi‑Fi), por exemplo `192.168.1.50`.  
É este endereço que o **outro computador** vai usar. Ignora `127.0.0.1` e IPs `169.254.…`.

Se não houver IPv4 útil, o PC não está na LAN. Liga cabo/Wi‑Fi e repete.

### 2.2 Mesma rede que os clientes

Os PCs clientes têm de estar no **mesmo intervalo** (ex. todos `192.168.1.x`).  
Rede de **convidados** do router muitas vezes **isola** máquinas: o cliente não chega ao servidor.

### 2.3 IP que não muda

Se o DHCP mudar o IP deste Windows, os clientes quebram. No router, **reserva DHCP** para o endereço MAC desta placa, sempre o mesmo IP.

No Windows, o MAC (físico):

```bat
getmac /v
```

Ou em `ipconfig /all` → **Endereço físico**.

---

## 3. Desenho da API (o que o cliente chama)

| Método | Caminho | Exemplo |
| --- | --- | --- |
| GET | `/whatscheck` | `http://192.168.1.50:8080/whatscheck?phone=5585996533131` |
| GET | `/telcheck` | `http://192.168.1.50:8080/telcheck?phone=5585996533131` |
| GET | `/lookup` | `http://192.168.1.50:8080/lookup?phone=5585996533131` |
| GET | `/health` | `http://192.168.1.50:8080/health` → `{"ok": true}` |

Número sem DDD (8 ou 9 dígitos): acrescenta `&ddd=85`.

**Validação primeiro.** Só depois Z-API ou MNP. Número inválido:

```json
{"error": true, "message": "Numero invalido"}
```

Programa a falhar (qualquer endpoint):

```json
{"error": true, "message": "Erro no programa: …"}
```

`/telcheck` sucesso: `{"phone": "5585996533131", "in_mnp": true}`.  
`/whatscheck` sucesso: `{"phone": "5585996533131", "exists": true}`.

`/lookup` (detalhe HLR):

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

Com `data_source: MNP_DB`, `linha_ativa` **não** prova chip ligado.

Opcional: um token no header (`X-Telecheck-Key`) para a LAN não ficar aberta a qualquer PC da empresa. Não é HTTPS público; é só um filtro.

---

## 4. Criar o venv só para o telecheck-

Faz isto **uma vez** no Windows servidor, na pasta do repositório. Precisas de **Python 3** instalado ([python.org](https://www.python.org/downloads/windows/)); na instalação marca **Add python.exe to PATH**.

Confirma:

```bat
python --version
```

### 4.1 Ir à pasta do projeto

```bat
cd C:\caminho\para\telecheck-
```

(ajusta o caminho; a pasta chama-se **telecheck-**, com hífen, como o repo.)

### 4.2 Criar o ambiente virtual

```bat
python -m venv .venv
```

Isto cria a pasta `.venv\` **só para o telecheck-**. Não mistures com outros projetos.

### 4.3 Ativar o venv

**Prompt de Comando (cmd):**

```bat
.venv\Scripts\activate.bat
```

**PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear scripts:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Quando o venv está ativo, o prompt começa com `(.venv)`.

Para sair mais tarde: `deactivate`.

### 4.4 Instalar dependências

Com o venv **ativo**, na raiz do `telecheck-`:

```bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

O `requirements.txt` deste repo tem FastAPI e Uvicorn (o servidor HTTP).

Instalação equivalente à mão:

```bat
pip install fastapi uvicorn
```

### 4.5 Confirmar

```bat
python -c "import fastapi, uvicorn; print('ok')"
```

Em cada sessão nova no servidor: `cd` para `telecheck-` → ativar `.venv` → só depois `uvicorn`. Sem ativar o venv, o Windows usa outro Python e as bibliotecas “não existem”.

---

## 5. Passo a passo de desenvolvimento

Trabalha na pasta:

`C:\caminho\para\telecheck-`

### Passo A — Não misturar chaves no servidor HTTP

Deixa `hlr-lookup\config.env` **só neste Windows**. Já está no `.gitignore`. O cliente **nunca** recebe `HLR_API_KEY`.  
Copia a partir de `hlr-lookup\config.example.env` se ainda não existir `config.env`.

### Passo B — Ficheiros do servidor

Já no repo:

- `number_check.py` — validação (corre **antes** de cada endpoint com `phone`).
- `zapi_client.py` + `zapi\instances.json` — `/whatscheck`.
- `hlr-lookup\lookup_ativo.py` — `/telcheck` e `/lookup` (CLI só com `if __name__ == "__main__"`).
- `servidor.py` — FastAPI na **raiz** do telecheck-.

Copia `zapi\instances.example.json` → `zapi\instances.json` e preenche as instâncias.

### Passo C — Servidor HTTP (FastAPI)

Com o **venv ativo** (secção 4), **na raiz** do `telecheck-`:

```bat
cd C:\caminho\para\telecheck-
.venv\Scripts\activate.bat
uvicorn servidor:app --host 0.0.0.0 --port 8080
```

`0.0.0.0` = “aceita ligações da LAN”.  
`--host 127.0.0.1` = **só este Windows**; o outro PC falha.

### Passo D — Testar neste Windows primeiro

Noutro Prompt **neste** PC (`curl` no Windows 10/11, ou o browser):

```bat
curl -s "http://127.0.0.1:8080/health"
curl -s "http://127.0.0.1:8080/telcheck?phone=5585996533131"
curl -s "http://127.0.0.1:8080/whatscheck?phone=5585996533131"
curl -s "http://127.0.0.1:8080/lookup?phone=nao-e-numero"
```

O último deve devolver `{"error": true, "message": "Numero invalido"}` **sem** gastar Z-API nem HLR.

Se `/health` não responder, o uvicorn não está a correr ou a porta está errada.

Depois testa pelo **IP da LAN** (ainda neste Windows):

```bat
curl -s "http://SEU_IP_LAN:8080/health"
```

Substitui `SEU_IP_LAN` pelo IPv4 do passo 2.1. Se `127.0.0.1` funciona e o IP da LAN não, o bind não é `0.0.0.0`.

### Passo E — Firewall do Windows

Quando o uvicorn arranca, o Windows pode perguntar se permites **Python**. Aceita em **redes privadas**.

À mão: **Definições → Rede e Internet → Firewall do Windows → Definições avançadas → Regras de entrada → Nova regra**:

- Tipo: **Porta** → TCP → **8080**
- Permitir a ligação
- Perfil: **Privada** (não é preciso “Pública” se a LAN for privada)
- Nome: `telecheck-`

Teste: no cliente, *timeout* com curl local a funcionar = firewall ou rede de convidados.

### Passo F — Testar no outro computador

No PC cliente (mesmo Wi‑Fi/cabo):

```bat
curl -s "http://SEU_IP_LAN:8080/health"
curl -s "http://SEU_IP_LAN:8080/telcheck?phone=5585996533131"
curl -s "http://SEU_IP_LAN:8080/whatscheck?phone=5585996533131"
```

Ou o mesmo URL no Chrome. **Não** uses `localhost` no cliente.

---

## 6. Ligar o SACI (Delphi) a esta API

O SACI não precisa das chaves HLR. Faz um `GET` HTTP para o IP do **Windows servidor**.

- URL: `http://192.168.x.x:8080/telcheck?phone=` ou `/whatscheck?phone=` + número.
- Timeout: 30 s (HLR/Z-API podem ser lentos; o WhatsApp ainda espera 0,5–1 s por instância).
- JSON com `"error": true` = falha do programa ou número inválido; **não** é o mesmo que `in_mnp: false` / `exists: false`.
- Se o Windows estiver desligado, o SACI trata como “serviço indisponível”, não como “número morto”.

Isto fica **depois** do servidor estável no curl.

---

## 7. Deixar o telecheck- sempre a correr no Windows

Enquanto desenvolves, a janela do Prompt com `uvicorn` chega.

Para o escritório:

1. **Energia:** Definições → Sistema → Energia → o PC servidor **não deve hibernar** na corrente.
2. **Arranque automático:** Agendador de tarefas → criar tarefa ao *logon* / ao arranque:
   - Programa: `C:\caminho\para\telecheck-\.venv\Scripts\uvicorn.exe`
   - Argumentos: `servidor:app --host 0.0.0.0 --port 8080`
   - Iniciar em: `C:\caminho\para\telecheck-`
3. Alternativa: atalho na pasta **Arranque** (`shell:startup`) para um `.bat` que ativa o venv e chama o uvicorn.

Se o Windows dormir, a API cai.

Exemplo `start_telecheck.bat` na raiz do repo:

```bat
cd /d C:\caminho\para\telecheck-
call .venv\Scripts\activate.bat
uvicorn servidor:app --host 0.0.0.0 --port 8080
```

---

## 8. Segurança na rede fechada (mínimo útil)

- Não abras a porta 8080 no router (sem *port forwarding*).
- `config.env` só no disco do servidor.
- Token partilhado no header, se houver PCs que não devem consultar.
- Logs: não imprimas a API secret.

Não uses ngrok nem “expor IP público” para isto.

---

## 9. Checklist de desenvolvimento

1. [ ] Python no PATH; venv `.venv` na raiz do **telecheck-**; `pip install -r requirements.txt`.
2. [ ] `hlr-lookup\config.env` e `zapi\instances.json` preenchidos.
3. [ ] `servidor.py` na raiz: `/health`, `/whatscheck`, `/telcheck`, `/lookup`.
4. [ ] venv ativo; `uvicorn servidor:app --host 0.0.0.0 --port 8080`.
5. [ ] `curl` em `127.0.0.1`: health, número inválido (erro JSON), telcheck/whatscheck.
6. [ ] `ipconfig` e `curl` no IPv4 da LAN neste Windows.
7. [ ] Firewall (regra **telecheck-**, porta 8080, rede privada).
8. [ ] `curl` / browser noutro PC da LAN.
9. [ ] Reserva DHCP.
10. [ ] (Depois) chamada HTTP no SACI.
11. [ ] (Depois) Agendador de tarefas / `start_telecheck.bat`.

---

## 10. Problemas frequentes

| Sintoma | Causa típica |
| --- | --- |
| `fastapi` / `uvicorn` not found | venv não está ativo; instalaste no Python global |
| Cliente: connection refused | uvicorn não está a correr, ou porta errada |
| Cliente: timeout | firewall do Windows, ou redes diferentes / guest Wi‑Fi |
| Só funciona neste PC | `--host 127.0.0.1` em vez de `0.0.0.0` |
| Funcionava ontem, hoje não | DHCP mudou o IP deste Windows |
| Lookup falha, `/health` ok | `config.env` em falta ou hlr-lookups.com inacessível **deste** Windows |
| `Numero invalido…` | `phone` não passou em `number_check.py`; Z-API/HLR **não** foram chamados. A mensagem diz qual regra falhou |
| `DDD invalido` | o `&ddd=` não tem 2 dígitos |
| `DDD inexistente no Brasil` | o DDD tem 2 dígitos mas não é atribuído (ex.: 20, 36, 90) |
| `Erro no programa: …` | falha inesperada; o corpo JSON é o mesmo em todos os endpoints |
| `Nenhuma instancia esta ativa ou ZAPI nao respode` | nenhuma instância Z-API deu HTTP 200 |
| PowerShell: “execution of scripts is disabled” | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| JSON com `MNP_DB` | esperado hoje: não é HLR ao vivo |

---

## 11. Ordem recomendada (não saltar)

1. Rede e IP no Windows (secção 2).  
2. venv do **telecheck-** (secção 4).  
3. Refactor + servidor (secção 5 A–D).  
4. Outro PC (5 F).  
5. Só então SACI e arranque automático.

O `servidor.py` já está na raiz do repo. Detalhe das rotinas: `ESPECIFICACAO_ROTINAS.md`.
