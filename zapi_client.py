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


class InstanceRotation:
    """Ordem sorteada uma vez; cada número seguinte começa na instância seguinte.

    Com as instâncias (A, B, C, D) e o sorteio (B, C, D, A), os números de um
    pedido começam em B, C, D, A, B, C... Dentro de um número, a instância que
    falha passa a vez para a seguinte dessa mesma ordem.
    """

    def __init__(self, instances: list[dict]) -> None:
        self._instances = list(instances)
        random.shuffle(self._instances)
        self._start = 0

    def __len__(self) -> int:
        return len(self._instances)

    def next_order(self) -> list[dict]:
        """Ordem de tentativa do próximo número e avança o ponto de partida."""
        total = len(self._instances)
        order = [self._instances[(self._start + i) % total] for i in range(total)]
        self._start = (self._start + 1) % total
        return order


def new_rotation() -> InstanceRotation:
    """Lê o instances.json e sorteia a ordem. RuntimeError se não houver instância."""
    instances = load_instances()
    if not instances:
        raise RuntimeError(ZAPI_MESSAGE_NONE)
    return InstanceRotation(instances)


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


def _send_text(instance: dict, phone: str, message: str) -> tuple[int | None, dict | None]:
    url = (
        f"https://api.z-api.io/instances/{instance['instance_id']}"
        f"/token/{instance['instance_token']}/send-text"
    )
    body = json.dumps({"phone": phone, "message": message}).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Client-Token": instance["client_token"],
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            status = getattr(resp, "status", 200)
            data = json.loads(resp.read().decode("utf-8"))
        return status, data if isinstance(data, dict) else {}
    except HTTPError as exc:
        return exc.code, None
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None, None


def send_text(phone: str, message: str, rotation: InstanceRotation | None = None) -> dict:
    """Manda a mensagem pela primeira instancia que responder 200.

    Mesma pausa de 0,5 a 1 s do phone-exists, porque tambem e chamada de WhatsApp.
    """
    if rotation is None:
        rotation = new_rotation()
    for instance in rotation.next_order():
        time.sleep(random.uniform(0.5, 1.0))
        status, data = _send_text(instance, phone, message)
        if status == 200 and data is not None:
            return {"instance": instance["name"], "message_id": data.get("messageId")}
    raise RuntimeError(ZAPI_MESSAGE_NONE)


def whatscheck(phone: str, rotation: InstanceRotation | None = None) -> bool:
    """Tenta as instâncias na ordem da rotação. RuntimeError se nenhuma der 200.

    Sem `rotation`, sorteia uma ordem só para este número. Passe a mesma
    rotação em todos os números de um lote para eles girarem as instâncias.
    """
    if rotation is None:
        rotation = new_rotation()
    for instance in rotation.next_order():
        time.sleep(random.uniform(0.5, 1.0))
        status, exists = _phone_exists(instance, phone)
        if status == 200 and exists is not None:
            return exists
    raise RuntimeError(ZAPI_MESSAGE_NONE)
