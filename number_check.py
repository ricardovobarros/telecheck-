"""Limpeza e validação de telefone (mesma lógica de tel_app/number_check.py)."""
from __future__ import annotations

import re

DEFAULT_DDD = "85"


def format_number(number, ddd=DEFAULT_DDD):
    number = str(number)

    # Remove tudo que não for número (espaços, parênteses, hífens, etc)
    number = re.sub(r"[^\d]", "", number)

    original = number  # Guarda original limpo para marcar como inválido

    # Número já tem DDD? (10 ou 11 dígitos)
    if len(number) in [10, 11]:
        if len(number) == 10 and not number.startswith("9"):
            return f"55{number}", "valid"  # fixo com DDD
        elif len(number) == 11 and number[2] == "9":
            return f"55{number}", "valid"  # celular com DDD
        else:
            return number, "invalid"

    # Sem DDD — caso especial
    elif len(number) == 8 and number.startswith(("6", "7", "8", "9")):
        number = "9" + number  # celular com 8 dígitos sem 9

    if len(number) == 9 and number.startswith("9"):
        return f"55{ddd}{number}", "valid"

    # Inválido: mais de 9 dígitos sem DDD
    return original, "invalid"


def normalize_phone(phone: str | None, ddd: str | None = None) -> tuple[str | None, str | None]:
    """Devolve (numero com 55, None) ou (None, mensagem de erro).

    Números que já vêm com DDI 55 (12 ou 13 dígitos) são reduzidos à parte
    nacional e validados com a mesma regra de format_number.
    Números com 8 ou 9 dígitos usam o DDD 85 se `ddd` não vier na query.
    """
    if phone is None:
        return None, "Numero invalido"

    digits = re.sub(r"[^\d]", "", str(phone))
    if not digits:
        return None, "Numero invalido"

    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]

    if ddd is None or not str(ddd).strip():
        ddd_clean = DEFAULT_DDD
    else:
        ddd_clean = re.sub(r"[^\d]", "", str(ddd))

    if len(digits) in (8, 9):
        if len(ddd_clean) != 2:
            return None, "DDD invalido"
        ddd_use = ddd_clean
    else:
        ddd_use = ddd_clean if len(ddd_clean) == 2 else DEFAULT_DDD

    formatted, status = format_number(digits, ddd_use)
    if status != "valid":
        return None, "Numero invalido"
    return formatted, None
