"""API LAN do telecheck-: /whatscheck, /telcheck, /lookup, /override, /health."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "hlr-lookup"))

import override  # noqa: E402
from lookup_ativo import HlrLookupError, _e164, _nota, in_mnp, linha_ativa, lookup  # noqa: E402
from number_check import normalize_phone  # noqa: E402
from whatsapp_client import InstanceRotation, new_rotation, provider_name, whatscheck  # noqa: E402

app = FastAPI(title="telecheck-")


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code


def _error_body(message: str) -> dict:
    return {"error": True, "message": message}


class OverrideRequestBody(BaseModel):
    operador: str = Field(description="Quem esta pedindo a liberacao")
    phone: str = Field(description="Telefone que sera cadastrado sem WhatsApp")
    cliente_nome: str = Field(default="", description="Nome do cliente, para a gestora decidir")
    motivo: str = Field(default="", description="Por que o cadastro precisa deste numero")
    ddd: str | None = Field(default=None, description="Obrigatorio se o numero vier sem DDD")


class OverrideConfirmBody(BaseModel):
    request_id: str = Field(description="Devolvido pelo /override/request")
    codigo: str = Field(description="Codigo que a gestora recebeu no WhatsApp")
    phone: str = Field(description="O mesmo telefone do pedido; e reconferido aqui")
    ddd: str | None = Field(default=None)


@app.exception_handler(ApiError)
async def api_error_handler(_request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_error_body(exc.message))


@app.exception_handler(override.OverrideError)
async def override_error_handler(_request, exc: override.OverrideError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={**_error_body(exc.message), **exc.details},
    )


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


def _split_phones(values: list[str] | None) -> list[str]:
    """Aceita `?phone=a&phone=b` e `?phone=a,b`, na ordem recebida."""
    entries = []
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip()
            if part:
                entries.append(part)
    return entries


def _normalize_batch(entries: list[str], ddd: str | None) -> list[tuple[str, str | None, str | None]]:
    """(entrada, número normalizado, erro) por item, sem chamar nada externo."""
    return [(entry, *normalize_phone(entry, ddd)) for entry in entries]


def _batch_results(parsed: list[tuple[str, str | None, str | None]], check) -> dict:
    """Aplica `check` a cada número válido. Um item com erro não derruba o lote."""
    results = []
    for entry, numero, err in parsed:
        if err:
            results.append({"input": entry, "error": True, "message": err})
            continue
        try:
            results.append({"phone": numero, **check(numero)})
        except ApiError as exc:
            results.append({"phone": numero, "error": True, "message": exc.message})
    return {"count": len(results), "results": results}


def _new_rotation() -> InstanceRotation:
    try:
        return new_rotation()
    except RuntimeError as exc:
        raise ApiError(str(exc), 503) from exc


def _whatscheck(numero: str, rotation: InstanceRotation | None = None) -> bool:
    try:
        return whatscheck(numero, rotation)
    except RuntimeError as exc:
        raise ApiError(str(exc), 503) from exc
    except Exception as exc:
        raise ApiError(f"Erro no programa: {exc}", 500) from exc


def _lookup(numero: str) -> dict:
    try:
        return lookup(numero)
    except HlrLookupError as exc:
        raise ApiError(f"Erro no programa: {exc}", 502) from exc
    except Exception as exc:
        raise ApiError(f"Erro no programa: {exc}", 500) from exc


@app.get("/health")
def health() -> dict:
    """Vivo, e qual provedor de WhatsApp esta valendo neste momento."""
    return {"ok": True, "whatsapp": provider_name()}


@app.get("/whatscheck")
def whatscheck_endpoint(
    phone: list[str] | None = Query(default=None),
    ddd: str | None = Query(default=None),
) -> dict:
    entries = _split_phones(phone)
    if not entries:
        raise ApiError("Numero invalido", 400)

    if len(entries) == 1:
        numero = _require_phone(entries[0], ddd)
        return {"phone": numero, "exists": _whatscheck(numero, _new_rotation())}

    parsed = _normalize_batch(entries, ddd)
    rotation = _new_rotation() if any(numero for _, numero, _ in parsed) else None
    return _batch_results(parsed, lambda numero: {"exists": _whatscheck(numero, rotation)})


@app.get("/telcheck")
def telcheck_endpoint(
    phone: list[str] | None = Query(default=None),
    ddd: str | None = Query(default=None),
) -> dict:
    entries = _split_phones(phone)
    if not entries:
        raise ApiError("Numero invalido", 400)

    if len(entries) == 1:
        numero = _require_phone(entries[0], ddd)
        return {"phone": numero, "in_mnp": in_mnp(_lookup(numero))}

    parsed = _normalize_batch(entries, ddd)
    return _batch_results(parsed, lambda numero: {"in_mnp": in_mnp(_lookup(numero))})


@app.get("/lookup")
def lookup_endpoint(
    phone: str | None = Query(default=None),
    ddd: str | None = Query(default=None),
) -> dict:
    numero = _require_phone(phone, ddd)
    data = _lookup(numero)
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


@app.post("/override/request")
def override_request_endpoint(body: OverrideRequestBody) -> dict:
    """Pede liberacao para cadastrar um numero sem WhatsApp.

    O codigo nao volta nesta resposta: ele vai para o WhatsApp da gestora.
    """
    return override.request_override(
        operador=body.operador,
        cliente_nome=body.cliente_nome,
        phone=body.phone,
        motivo=body.motivo,
        ddd=body.ddd,
    )


@app.post("/override/confirm")
def override_confirm_endpoint(body: OverrideConfirmBody) -> dict:
    """Confere o codigo da gestora e consome a liberacao."""
    return override.confirm_override(
        request_id=body.request_id,
        codigo=body.codigo,
        phone=body.phone,
        ddd=body.ddd,
    )
