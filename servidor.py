"""API LAN do telecheck-: /whatscheck, /telcheck, /lookup, /health."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "hlr-lookup"))

from lookup_ativo import HlrLookupError, _e164, _nota, in_mnp, linha_ativa, lookup  # noqa: E402
from number_check import normalize_phone  # noqa: E402
from zapi_client import whatscheck  # noqa: E402

app = FastAPI(title="telecheck-")


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code


def _error_body(message: str) -> dict:
    return {"error": True, "message": message}


@app.exception_handler(ApiError)
async def api_error_handler(_request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_error_body(exc.message))


@app.exception_handler(Exception)
async def unexpected_error_handler(_request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=_error_body(f"Erro no programa: {exc}"),
    )


def _require_phone(phone: str | None, ddd: str | None) -> str:
    formatted, err = normalize_phone(phone, ddd)
    if err:
        raise ApiError(err, 400)
    return formatted


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/whatscheck")
def whatscheck_endpoint(
    phone: str | None = Query(default=None),
    ddd: str | None = Query(default=None),
) -> dict:
    numero = _require_phone(phone, ddd)
    try:
        exists = whatscheck(numero)
    except RuntimeError as exc:
        raise ApiError(str(exc), 503) from exc
    except Exception as exc:
        raise ApiError(f"Erro no programa: {exc}", 500) from exc
    return {"phone": numero, "exists": exists}


@app.get("/telcheck")
def telcheck_endpoint(
    phone: str | None = Query(default=None),
    ddd: str | None = Query(default=None),
) -> dict:
    numero = _require_phone(phone, ddd)
    try:
        data = lookup(numero)
    except HlrLookupError as exc:
        raise ApiError(f"Erro no programa: {exc}", 502) from exc
    except Exception as exc:
        raise ApiError(f"Erro no programa: {exc}", 500) from exc
    return {"phone": numero, "in_mnp": in_mnp(data)}


@app.get("/lookup")
def lookup_endpoint(
    phone: str | None = Query(default=None),
    ddd: str | None = Query(default=None),
) -> dict:
    numero = _require_phone(phone, ddd)
    try:
        data = lookup(numero)
    except HlrLookupError as exc:
        raise ApiError(f"Erro no programa: {exc}", 502) from exc
    except Exception as exc:
        raise ApiError(f"Erro no programa: {exc}", 500) from exc
    return {
        "numero": data.get("msisdn") or _e164(numero),
        "connectivity_status": data.get("connectivity_status"),
        "processing_status": data.get("processing_status"),
        "data_source": data.get("data_source"),
        "mccmnc": data.get("mccmnc"),
        "operadora": data.get("ported_network_name") or data.get("original_network_name"),
        "portado": data.get("is_ported"),
        "roaming": data.get("is_roaming"),
        "linha_ativa": linha_ativa(data),
        "nota": _nota(data),
    }
