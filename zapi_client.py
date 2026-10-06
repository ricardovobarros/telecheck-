"""Z-API: phone-exists e send-text com N instâncias em `zapi/instances.json`.

Este módulo não sorteia nem espera. Quem gira as instâncias e aplica a pausa
de 0,5 a 1 s é o `whatsapp_client.py`, igual para os dois provedores.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NAME = "zapi"

ROOT = Path(__file__).resolve().parent
INSTANCES_PATH = ROOT / "zapi" / "instances.json"
BASE_URL = "https://api.z-api.io"
TIMEOUT_SECONDS = 15


def load_instances() -> list[dict]:
    """Instâncias válidas do `zapi/instances.json`.

    Precisa de `instance_id`, `instance_token` e `client_token`. Sem um deles,
    a entrada é ignorada.
    """
    if not INSTANCES_PATH.exists():
        return []
    try:
        raw = json.loads(INSTANCES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = raw.get("instances") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        instance_id = str(item.get("instance_id") or "").strip()
        instance_token = str(item.get("instance_token") or "").strip()
        client_token = str(item.get("client_token") or "").strip()
        if instance_id and instance_token and client_token:
            valid.append(
                {
                    "name": str(item.get("name") or instance_id).strip(),
                    "instance_id": instance_id,
                    "instance_token": instance_token,
                    "client_token": client_token,
                }
            )
    return valid


def _url(instance: dict, suffix: str) -> str:
    return (
        f"{BASE_URL}/instances/{instance['instance_id']}"
        f"/token/{instance['instance_token']}/{suffix}"
    )


def _headers(instance: dict) -> dict:
    return {
        "Content-Type": "application/json",
        "Client-Token": instance["client_token"],
    }


def _call(req: Request) -> tuple[int | None, object | None]:
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status = getattr(resp, "status", 200)
            return status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, None
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None, None


def phone_exists(instance: dict, phone: str) -> tuple[int | None, bool | None]:
    """(status, existe) a partir do `exists` do `phone-exists`."""
    req = Request(
        _url(instance, f"phone-exists/{phone}"),
        headers=_headers(instance),
        method="GET",
    )
    status, data = _call(req)
    if status != 200 or not isinstance(data, dict):
        return status, None
    existe = data.get("exists")
    return status, existe if isinstance(existe, bool) else bool(existe)


def send_text(instance: dict, phone: str, message: str) -> tuple[int | None, dict | None]:
    """(status, {"message_id": …}) do `send-text`."""
    req = Request(
        _url(instance, "send-text"),
        data=json.dumps({"phone": phone, "message": message}).encode("utf-8"),
        headers=_headers(instance),
        method="POST",
    )
    status, data = _call(req)
    if status != 200 or not isinstance(data, dict):
        return status, None
    return status, {"message_id": data.get("messageId")}
