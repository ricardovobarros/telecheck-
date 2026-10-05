"""Limpeza e validação de telefone brasileiro: a primeira barreira do telecheck-.

Aqui não há chamada externa nenhuma. É só análise estática do número, feita
antes de gastar Z-API ou hlr-lookups e antes de incomodar a gestora com um
pedido de liberação. O que não pode ser real é recusado neste ponto.

As faixas vêm do plano de numeração brasileiro do libphonenumber do Google
(`PhoneNumberMetadata.xml`, `<territory id="BR">`, tags `fixedLine` e `mobile`).
"""
from __future__ import annotations

import re

DEFAULT_DDD = "85"

MESSAGE_INVALID = "Numero invalido"
MESSAGE_DDD_INVALID = "DDD invalido"
MESSAGE_DDD_UNKNOWN = "DDD inexistente no Brasil"
MESSAGE_LENGTH = "Numero invalido: precisa de 8 a 11 digitos, ou 12 a 13 com o 55"
MESSAGE_FIXO = "Numero invalido: fixo comeca com 2, 3, 4 ou 5"
MESSAGE_CELULAR = "Numero invalido: celular comeca com 9 seguido de 6, 7, 8 ou 9"

# DDDs em uso. É o prefixo de área do libphonenumber, que cobre apenas os
# códigos realmente atribuídos: não existem 20, 23, 25, 26, 29, 30, 36, 39,
# 40, 50, 52, 56 a 60, 70, 72, 76, 78, 80 e 90.
DDD_RE = re.compile(r"^(?:[14689][1-9]|2[12478]|3[1-578]|5[13-5]|7[13-579])$")

# Fixo: 8 dígitos, o primeiro de 2 a 5. O libphonenumber ainda aceita 8 dígitos
# começados em 7 como móvel (o trunking da antiga Nextel), e aqui isso é
# recusado: o serviço foi desligado em 2018. Para aceitar, use r"^[2-57]\d{7}$".
FIXO_RE = re.compile(r"^[2-5]\d{7}$")

# Celular: 9 dígitos, o nono dígito e depois a faixa móvel da Anatel (6 a 9).
# Somos de propósito mais restritos que o libphonenumber, que aceita o 9
# seguido de qualquer dígito: 9 seguido de 0 a 5 não é atribuído ao móvel,
# logo não pode ser real. Para aceitar, troque por r"^9\d{8}$".
CELULAR_RE = re.compile(r"^9[6-9]\d{7}$")


def _only_digits(value) -> str:
    return re.sub(r"[^\d]", "", str(value))


def _resolve_ddd(ddd: str | None) -> tuple[str | None, str | None]:
    """(ddd, None) ou (None, mensagem). Só vale para número que veio sem DDD."""
    if ddd is None or not str(ddd).strip():
        return DEFAULT_DDD, None
    clean = _only_digits(ddd)
    if len(clean) != 2:
        return None, MESSAGE_DDD_INVALID
    if not DDD_RE.match(clean):
        return None, MESSAGE_DDD_UNKNOWN
    return clean, None


def _check_local(local: str) -> str | None:
    """None se a parte local (já sem DDD) puder ser real; senão, o erro."""
    if len(local) == 8:
        return None if FIXO_RE.match(local) else MESSAGE_FIXO
    if len(local) == 9:
        return None if CELULAR_RE.match(local) else MESSAGE_CELULAR
    return MESSAGE_LENGTH


def normalize_phone(phone: str | None, ddd: str | None = None) -> tuple[str | None, str | None]:
    """Devolve (numero com 55, None) ou (None, mensagem de erro).

    Aceita a parte nacional (10 ou 11 dígitos), o número local sem DDD (8 ou 9,
    usando o `ddd` ou o 85) e o número já com DDI 55 (12 ou 13 dígitos).
    Celular antigo de 8 dígitos recebe o nono dígito, como fez a Anatel.
    """
    if phone is None:
        return None, MESSAGE_INVALID

    digits = _only_digits(phone)
    if not digits:
        return None, MESSAGE_INVALID

    # O 55 da frente só é DDI quando o que sobra tem tamanho de número
    # nacional. "5533331234" é o DDD 55 (Santa Maria), não DDI + 8 dígitos.
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]

    if len(digits) in (10, 11):
        area, local = digits[:2], digits[2:]
        if not DDD_RE.match(area):
            return None, MESSAGE_DDD_UNKNOWN
    elif len(digits) in (8, 9):
        area, err = _resolve_ddd(ddd)
        if err:
            return None, err
        local = digits
    else:
        return None, MESSAGE_LENGTH

    # Parte local de 8 dígitos começada em 6 a 9 é celular anterior ao nono
    # dígito (o fixo nunca passa de 5): ganha o 9 na frente, como fez a Anatel.
    # Vale com e sem DDD, porque base antiga guarda os dois formatos.
    if len(local) == 8 and local[0] in "6789":
        local = "9" + local

    err = _check_local(local)
    if err:
        return None, err
    return f"55{area}{local}", None


def format_number(number, ddd=DEFAULT_DDD):
    """Forma antiga, mantida para quem já chamava: (numero, "valid"|"invalid")."""
    formatted, err = normalize_phone(number, ddd)
    if err:
        return _only_digits(number), "invalid"
    return formatted, "valid"
