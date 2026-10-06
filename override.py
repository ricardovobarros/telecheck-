"""Liberacao de cadastro sem WhatsApp: codigo de uso unico, preso a operacao.

O codigo nunca volta para quem pediu. Ele sai do servidor direto para o
WhatsApp da gestora, e a maquina da operadora so conhece o request_id.
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

import override_store
import whatsapp_client
from number_check import normalize_phone

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "override" / "config.env"

# Mesma frase para codigo errado, expirado, consumido e telefone trocado:
# dizer qual dos quatro falhou entrega informacao para quem esta tentando adivinhar.
MESSAGE_CODE_INVALID = "Codigo invalido ou expirado"
MESSAGE_NOT_CONFIGURED = "Liberacao nao configurada no servidor"
MESSAGE_SEND_FAILED = "Nao foi possivel avisar a gestora"


class OverrideError(Exception):
    def __init__(self, message: str, status_code: int = 400, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _load_config() -> None:
    if not CONFIG_PATH.exists():
        return
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return max(minimum, int(raw)) if raw else default
    except ValueError:
        return default


def gestora_phone() -> str:
    return re.sub(r"[^\d]", "", os.environ.get("OVERRIDE_GESTORA_PHONE", ""))


def ttl_seconds() -> int:
    return _int_env("OVERRIDE_TTL_SECONDS", 300, minimum=30)


def max_attempts() -> int:
    return _int_env("OVERRIDE_MAX_ATTEMPTS", 3)


def code_digits() -> int:
    return min(10, _int_env("OVERRIDE_CODE_DIGITS", 6, minimum=4))


def _pepper() -> bytes:
    return os.environ.get("OVERRIDE_PEPPER", "").strip().encode("utf-8")


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def canonical_phone(phone: str | None, ddd: str | None = None) -> str:
    """Forma canonica usada no pedido e reconferida na confirmacao.

    A liberacao dispensa o WhatsApp, nao o formato: nao faz sentido acordar a
    gestora por um numero que nao pode existir. Vale a mesma regra do
    number_check, e o erro dele e repassado como veio.
    """
    normalizado, err = normalize_phone(phone, ddd)
    if err:
        raise OverrideError(err, 400)
    return normalizado


def _new_code() -> str:
    digits = code_digits()
    return f"{secrets.randbelow(10 ** digits):0{digits}d}"


def hash_code(code: str, request_id: str) -> str:
    """HMAC do codigo preso ao request_id. O codigo em claro nunca e gravado."""
    return hmac.new(_pepper(), f"{request_id}:{code}".encode("utf-8"), sha256).hexdigest()


def _code_matches(code: str, request_id: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code, request_id), str(stored_hash))


def gestora_message(
    *,
    operador: str,
    cliente_nome: str,
    phone: str,
    motivo: str,
    codigo: str,
    minutos: int,
) -> str:
    linhas = ["LIBERACAO DE CADASTRO SEM WHATSAPP", "", f"Operador: {operador}"]
    if cliente_nome:
        linhas.append(f"Cliente: {cliente_nome}")
    linhas.append(f"Telefone: {phone}")
    if motivo:
        linhas.append(f"Motivo: {motivo}")
    linhas += [
        "",
        f"Codigo: {codigo}",
        f"Vale {minutos} min e so para este telefone.",
        "",
        "Se voce nao reconhece este pedido, nao passe o codigo.",
    ]
    return "\n".join(linhas)


def request_override(
    *,
    operador: str,
    cliente_nome: str,
    phone: str,
    motivo: str,
    ddd: str | None = None,
) -> dict:
    """Gera o codigo, grava PENDENTE e manda para a gestora pelo WhatsApp.

    Quem entrega e o provedor configurado em whatsapp/config.env.
    """
    gestora = gestora_phone()
    if not gestora or not _pepper():
        raise OverrideError(MESSAGE_NOT_CONFIGURED, 503)

    numero = canonical_phone(phone, ddd)
    operador = (operador or "").strip()
    if not operador:
        raise OverrideError("Informe o operador", 400)

    codigo = _new_code()
    request_id = secrets.token_urlsafe(12)
    criado_em = _now()
    expira_em = criado_em + timedelta(seconds=ttl_seconds())

    try:
        override_store.create_request(
            request_id=request_id,
            phone=numero,
            code_hash=hash_code(codigo, request_id),
            operador=operador,
            cliente_nome=(cliente_nome or "").strip(),
            motivo=(motivo or "").strip(),
            gestora_phone=gestora,
            criado_em=criado_em,
            expira_em=expira_em,
        )
    except override_store.StoreUnavailable as exc:
        raise OverrideError(f"Erro no programa: {exc}", 503) from exc

    mensagem = gestora_message(
        operador=operador,
        cliente_nome=(cliente_nome or "").strip(),
        phone=numero,
        motivo=(motivo or "").strip(),
        codigo=codigo,
        minutos=max(1, ttl_seconds() // 60),
    )
    try:
        whatsapp_client.send_text(gestora, mensagem)
    except RuntimeError as exc:
        _safe_mark(request_id, override_store.STATUS_SEND_FAILED)
        raise OverrideError(MESSAGE_SEND_FAILED, 503) from exc

    return {
        "request_id": request_id,
        "phone": numero,
        "expira_em": expira_em.isoformat(timespec="seconds"),
        "validade_segundos": ttl_seconds(),
    }


def confirm_override(*, request_id: str, codigo: str, phone: str, ddd: str | None = None) -> dict:
    """Confere o codigo e consome a liberacao. So vale uma vez e para este telefone."""
    request_id = (request_id or "").strip()
    codigo = re.sub(r"[^\d]", "", str(codigo or ""))
    if not request_id or not codigo:
        raise OverrideError(MESSAGE_CODE_INVALID, 400)

    numero = canonical_phone(phone, ddd)

    try:
        pendente = override_store.load_request(request_id)
    except override_store.StoreUnavailable as exc:
        raise OverrideError(f"Erro no programa: {exc}", 503) from exc

    if pendente is None or pendente["status"] != override_store.STATUS_PENDING:
        raise OverrideError(MESSAGE_CODE_INVALID, 400)

    if pendente["expira_em"] <= _now():
        _safe_mark(request_id, override_store.STATUS_EXPIRED)
        raise OverrideError(MESSAGE_CODE_INVALID, 400)

    limite = max_attempts()
    if pendente["tentativas"] >= limite:
        raise OverrideError(MESSAGE_CODE_INVALID, 400)

    if pendente["phone"] != numero or not _code_matches(codigo, request_id, pendente["code_hash"]):
        raise OverrideError(
            MESSAGE_CODE_INVALID,
            400,
            {"tentativas_restantes": max(0, limite - _register_attempt(request_id, limite))},
        )

    try:
        consumida = override_store.approve(request_id, _now())
    except override_store.StoreUnavailable as exc:
        raise OverrideError(f"Erro no programa: {exc}", 503) from exc
    if not consumida:
        raise OverrideError(MESSAGE_CODE_INVALID, 400)

    return {"ok": True, "phone": numero}


def _register_attempt(request_id: str, limite: int) -> int:
    try:
        return override_store.register_attempt(request_id, limite)
    except override_store.StoreUnavailable:
        return limite


def _safe_mark(request_id: str, status: str) -> None:
    try:
        override_store.mark_status(request_id, status)
    except override_store.StoreUnavailable:
        pass


_load_config()
