"""uazapi (uazapiGO): /chat/check e /send/text com N instâncias.

Base e autenticação conforme a especificação oficial
(https://docs.uazapi.com/openapi-bundled.json): o servidor é
`https://{subdominio}.uazapi.com`, ou o próprio host quando for self-hosted,
e cada chamada leva o token da instância no header `token`.

Este módulo não sorteia nem espera. Quem gira as instâncias e aplica a pausa
de 0,5 a 1 s é o `whatsapp_client.py`, igual para os dois provedores.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NAME = "uazapi"

ROOT = Path(__file__).resolve().parent
INSTANCES_PATH = ROOT / "uazapi" / "instances.json"
TIMEOUT_SECONDS = 15


def load_instances() -> list[dict]:
    """Instâncias válidas do `uazapi/instances.json`.

    Precisa de `token` e `base_url`. O `base_url` pode vir uma vez no topo do
    arquivo e valer para todas, porque o normal é as instâncias de uma conta
    viverem no mesmo subdomínio; por instância, ele sobrepõe o do topo.
    """
    if not INSTANCES_PATH.exists():
        return []
    try:
        raw = json.loads(INSTANCES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(raw, dict):
        items = raw.get("instances")
        base_padrao = str(raw.get("base_url") or "").strip()
    else:
        items, base_padrao = raw, ""
    if not isinstance(items, list):
        return []

    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        token = str(item.get("token") or "").strip()
        base_url = (str(item.get("base_url") or "").strip() or base_padrao).rstrip("/")
        if token and base_url:
            valid.append(
                {
                    "name": str(item.get("name") or base_url).strip(),
                    "base_url": base_url,
                    "token": token,
                }
            )
    return valid


def _post(instance: dict, path: str, payload: dict) -> tuple[int | None, object | None]:
    req = Request(
        f"{instance['base_url']}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "token": instance["token"],
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status = getattr(resp, "status", 200)
            return status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        # Inclui o 429 de limite de chamadas: a rotação passa para a seguinte.
        return exc.code, None
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None, None


def phone_exists(instance: dict, phone: str) -> tuple[int | None, bool | None]:
    """(status, existe) a partir do `isInWhatsapp` do `/chat/check`.

    A resposta é uma lista com um item por número pedido, e aqui pedimos um.
    Item com `error` conta como falha da instância, não como "não tem
    WhatsApp": a rotação precisa tentar a instância seguinte.
    """
    status, data = _post(instance, "/chat/check", {"numbers": [phone]})
    if status != 200 or not isinstance(data, list) or not data:
        return status, None
    item = data[0]
    if not isinstance(item, dict) or item.get("error"):
        return status, None
    existe = item.get("isInWhatsapp")
    return status, existe if isinstance(existe, bool) else None


def send_text(instance: dict, phone: str, message: str) -> tuple[int | None, dict | None]:
    """(status, {"message_id": …}) do `/send/text`."""
    status, data = _post(instance, "/send/text", {"number": phone, "text": message})
    if status != 200 or not isinstance(data, dict):
        return status, None
    return status, {"message_id": data.get("messageid") or data.get("id")}
