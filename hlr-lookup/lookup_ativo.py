# HLR Lookups (hlr-lookups.com) — linha ativa na operadora.
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PHONE = "+5585996533131"


class HlrLookupError(Exception):
    """Falha ao consultar a hlr-lookups (rede, HTTP, JSON ou config)."""


def _load_config() -> None:
    cfg = Path(__file__).resolve().parent / "config.env"
    if not cfg.exists():
        return
    for line in cfg.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _e164(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    return "+" + digits


def _auth_header() -> str:
    key = os.environ.get("HLR_API_KEY", "").strip()
    secret = os.environ.get("HLR_API_SECRET", "").strip()
    if not key or not secret:
        raise HlrLookupError(
            "Preencha HLR_API_KEY e HLR_API_SECRET em "
            "hlr-lookup/config.env "
            "(painel: https://www.hlr-lookups.com → API Settings)."
        )
    token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    return "Basic " + token


def lookup(phone: str) -> dict:
    base = os.environ.get("HLR_BASE_URL", "https://www.hlr-lookups.com/api/v2")
    url = base.rstrip("/") + "/hlr-lookup"
    body = json.dumps({"msisdn": _e164(phone)}).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise HlrLookupError(f"HLR HTTP {exc.code}: {payload}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise HlrLookupError(f"HLR erro: {exc}") from exc


def linha_ativa(data: dict) -> bool | str:
    status = (data.get("connectivity_status") or "").strip().upper()
    processing = (data.get("processing_status") or "").strip().upper()
    if processing in {"REJECTED", "FAILED"}:
        return "indisponivel"
    if status == "CONNECTED":
        return True
    if status == "ABSENT":
        return True  # número atribuído; aparelho desligado / sem cobertura
    if status == "INVALID_MSISDN":
        return False
    return "indisponivel"


def in_mnp(data: dict) -> bool:
    """True se o número está na base MNP; False se inválido ou rejeitado."""
    processing = (data.get("processing_status") or "").strip().upper()
    status = (data.get("connectivity_status") or "").strip().upper()
    if processing in {"REJECTED", "FAILED"}:
        return False
    if status == "INVALID_MSISDN":
        return False
    if processing == "COMPLETED":
        return True
    return False


def _nota(data: dict) -> str | None:
    status = data.get("connectivity_status")
    if status == "UNDETERMINED" or data.get("data_source") == "MNP_DB":
        return "sem HLR ao vivo (cobertura da rota ou só portabilidade)."
    if status == "ABSENT":
        return "linha atribuída, mas o telemóvel está desligado ou fora de rede."
    return None


_load_config()


if __name__ == "__main__":
    phone = sys.argv[1] if len(sys.argv) > 1 else PHONE
    try:
        data = lookup(phone)
    except HlrLookupError as exc:
        raise SystemExit(str(exc)) from exc
    status = data.get("connectivity_status")
    ativa = linha_ativa(data)
    operadora = data.get("ported_network_name") or data.get("original_network_name")

    print("numero:", data.get("msisdn") or _e164(phone))
    print("connectivity_status:", status)
    print("processing_status:", data.get("processing_status"))
    print("data_source:", data.get("data_source"))
    print("mccmnc:", data.get("mccmnc"))
    print("operadora:", operadora)
    print("portado:", data.get("is_ported"))
    print("roaming:", data.get("is_roaming"))
    print("erro:", data.get("error_code"), data.get("error_description"))
    print("linha_ativa:", ativa)
    nota = _nota(data)
    if nota:
        print("nota:", nota)
