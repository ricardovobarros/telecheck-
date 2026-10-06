"""Escolhe o provedor de WhatsApp e gira as instâncias dele.

O provedor sai de `WHATSAPP_PROVIDER` em `whatsapp/config.env`: `zapi` ou
`uazapi`. Cada um tem o seu arquivo de instâncias e a sua forma de autenticar,
mas daqui para fora a interface é a mesma, e o sorteio, a ordem em loop e a
pausa de 0,5 a 1 s valem para os dois.

Trocar de provedor é trocar uma linha do config e reiniciar o servidor. Os
dois arquivos de instâncias podem continuar no disco: só o do provedor
escolhido é lido.
"""
from __future__ import annotations

import os
import random
import time
from pathlib import Path

import uazapi_client
import zapi_client

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "whatsapp" / "config.env"
DEFAULT_PROVIDER = zapi_client.NAME

PROVIDERS = {
    zapi_client.NAME: zapi_client,
    uazapi_client.NAME: uazapi_client,
}

# A frase é a mesma de antes, mesmo com o uazapi: o SACI e os documentos já
# tratam este texto como contrato. Vale para "nenhuma instância configurada"
# e para "nenhuma instância respondeu".
MESSAGE_NONE = "Nenhuma instancia esta ativa ou ZAPI nao respode"


def _load_config() -> None:
    if not CONFIG_PATH.exists():
        return
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def provider_name() -> str:
    """Nome do provedor configurado. Valor vazio ou desconhecido cai no padrão."""
    escolhido = os.environ.get("WHATSAPP_PROVIDER", "").strip().lower()
    return escolhido if escolhido in PROVIDERS else DEFAULT_PROVIDER


def provider():
    """Módulo do provedor configurado."""
    return PROVIDERS[provider_name()]


def load_instances() -> list[dict]:
    return provider().load_instances()


class InstanceRotation:
    """Ordem sorteada uma vez; cada número seguinte começa na instância seguinte.

    Com as instâncias (A, B, C, D) e o sorteio (B, C, D, A), os números de um
    pedido começam em B, C, D, A, B, C... Dentro de um número, a instância que
    falha passa a vez para a seguinte dessa mesma ordem.

    O provedor fica preso aqui, e não é relido a cada número: um pedido inteiro
    usa o mesmo provedor, mesmo que o config mude no meio.
    """

    def __init__(self, instances: list[dict], provider_module) -> None:
        self._instances = list(instances)
        random.shuffle(self._instances)
        self._start = 0
        self.provider = provider_module

    def __len__(self) -> int:
        return len(self._instances)

    def next_order(self) -> list[dict]:
        """Ordem de tentativa do próximo número e avança o ponto de partida."""
        total = len(self._instances)
        order = [self._instances[(self._start + i) % total] for i in range(total)]
        self._start = (self._start + 1) % total
        return order


def new_rotation() -> InstanceRotation:
    """Lê as instâncias do provedor configurado e sorteia a ordem.

    RuntimeError se o provedor escolhido não tiver nenhuma instância válida.
    """
    modulo = provider()
    instances = modulo.load_instances()
    if not instances:
        raise RuntimeError(MESSAGE_NONE)
    return InstanceRotation(instances, modulo)


def whatscheck(phone: str, rotation: InstanceRotation | None = None) -> bool:
    """Tenta as instâncias na ordem da rotação. RuntimeError se nenhuma der 200.

    Sem `rotation`, sorteia uma ordem só para este número. Passe a mesma
    rotação em todos os números de um lote para eles girarem as instâncias.
    """
    if rotation is None:
        rotation = new_rotation()
    for instance in rotation.next_order():
        time.sleep(random.uniform(0.5, 1.0))
        status, exists = rotation.provider.phone_exists(instance, phone)
        if status == 200 and exists is not None:
            return exists
    raise RuntimeError(MESSAGE_NONE)


def send_text(phone: str, message: str) -> dict:
    """Manda a mensagem sempre pela primeira instância do provedor configurado.

    Sem sorteio e sem failover: a gestora recebe todo código do mesmo número.
    Se essa instância não responder 200, RuntimeError, e não se tenta outra.
    """
    modulo = provider()
    instances = modulo.load_instances()
    if not instances:
        raise RuntimeError(MESSAGE_NONE)
    instance = instances[0]
    status, data = modulo.send_text(instance, phone, message)
    if status != 200 or data is None:
        raise RuntimeError(MESSAGE_NONE)
    return {
        "provider": modulo.NAME,
        "instance": instance["name"],
        "message_id": data.get("message_id"),
    }


_load_config()
