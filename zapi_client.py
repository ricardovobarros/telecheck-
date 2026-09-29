"""Z-API phone-exists com N instâncias em zapi/instances.json."""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
INSTANCES_PATH = ROOT / "zapi" / "instances.json"
ZAPI_MESSAGE_NONE = "Nenhuma instancia esta ativa ou ZAPI nao respode"


def load_instances() -> list[dict]:
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


def _phone_exists(instance: dict, phone: str) -> tuple[int | None, bool | None]:
    url = (
        f"https://api.z-api.io/instances/{instance['instance_id']}"
        f"/token/{instance['instance_token']}/phone-exists/{phone}"
    )
    req = Request(
        url,
        headers={
            "Content-Type": "application/json",
            "Client-Token": instance["client_token"],
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            status = getattr(resp, "status", 200)
            data = json.loads(resp.read().decode("utf-8"))
        exists = data.get("exists")
        if not isinstance(exists, bool):
            exists = bool(exists)
        return status, exists
    except HTTPError as exc:
        return exc.code, None
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None, None


def whatscheck(phone: str) -> bool:
    """Tenta instâncias em ordem aleatória. Levanta RuntimeError se nenhuma der 200."""
    instances = load_instances()
    if not instances:
        raise RuntimeError(ZAPI_MESSAGE_NONE)
    random.shuffle(instances)
    for instance in instances:
        time.sleep(random.uniform(0.5, 1.0))
        status, exists = _phone_exists(instance, phone)
        if status == 200 and exists is not None:
            return exists
    raise RuntimeError(ZAPI_MESSAGE_NONE)
