"""Tabela LIBERACAO_WHATSAPP no SQL Server do SACI (DDL em db/schema.sql)."""
from __future__ import annotations

import os
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "db" / "config.env"

STATUS_PENDING = "PENDENTE"
STATUS_APPROVED = "APROVADA"
STATUS_BLOCKED = "BLOQUEADA"
STATUS_EXPIRED = "EXPIRADA"
STATUS_SEND_FAILED = "FALHA_ENVIO"

TABLE = "dbo.LIBERACAO_WHATSAPP"


class StoreUnavailable(Exception):
    """Banco nao configurado, sem driver, ou fora do ar."""


def _load_config() -> None:
    if not CONFIG_PATH.exists():
        return
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def connection_string() -> str:
    return os.environ.get("DB_ODBC_CONNECTION_STRING", "").strip()


def _timeout() -> int:
    raw = os.environ.get("DB_TIMEOUT_SECONDS", "").strip()
    try:
        return max(1, int(raw)) if raw else 10
    except ValueError:
        return 10


def _connect():
    """Conecta ao SQL Server. O pyodbc e importado aqui, nao no topo do modulo,
    para o servidor subir e /whatscheck continuar funcionando sem o driver."""
    conn_str = connection_string()
    if not conn_str:
        raise StoreUnavailable(
            "Preencha DB_ODBC_CONNECTION_STRING em db/config.env "
            "(modelo em db/config.example.env)."
        )
    try:
        import pyodbc
    except ImportError as exc:
        raise StoreUnavailable(
            "pyodbc nao instalado. Rode: pip install -r requirements.txt"
        ) from exc
    try:
        return pyodbc.connect(conn_str, timeout=_timeout())
    except Exception as exc:
        raise StoreUnavailable(f"SQL Server inacessivel: {exc}") from exc


def create_request(
    *,
    request_id: str,
    phone: str,
    code_hash: str,
    operador: str,
    cliente_nome: str,
    motivo: str,
    gestora_phone: str,
    criado_em: datetime,
    expira_em: datetime,
) -> None:
    sql = (
        f"INSERT INTO {TABLE} (LIB_ID, LIB_PHONE, LIB_CODIGO_HASH, LIB_STATUS, "
        "LIB_TENTATIVAS, LIB_OPERADOR, LIB_CLIENTE_NOME, LIB_MOTIVO, "
        "LIB_GESTORA_PHONE, LIB_CRIADO_EM, LIB_EXPIRA_EM) "
        "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)"
    )
    with closing(_connect()) as conn, closing(conn.cursor()) as cur:
        cur.execute(
            sql,
            request_id,
            phone,
            code_hash,
            STATUS_PENDING,
            operador,
            cliente_nome or None,
            motivo or None,
            gestora_phone,
            criado_em,
            expira_em,
        )
        conn.commit()


def load_request(request_id: str) -> dict | None:
    sql = (
        "SELECT LIB_ID, LIB_PHONE, LIB_CODIGO_HASH, LIB_STATUS, LIB_TENTATIVAS, "
        f"LIB_EXPIRA_EM FROM {TABLE} WHERE LIB_ID = ?"
    )
    with closing(_connect()) as conn, closing(conn.cursor()) as cur:
        row = cur.execute(sql, request_id).fetchone()
    if row is None:
        return None
    return {
        "request_id": row[0],
        "phone": row[1],
        "code_hash": row[2],
        "status": row[3],
        "tentativas": int(row[4]),
        "expira_em": row[5],
    }


def register_attempt(request_id: str, max_attempts: int) -> int:
    """Soma 1 tentativa e devolve o total. Bloqueia ao chegar no limite."""
    sql = (
        f"UPDATE {TABLE} SET LIB_TENTATIVAS = LIB_TENTATIVAS + 1, "
        "LIB_STATUS = CASE WHEN LIB_TENTATIVAS + 1 >= ? THEN ? ELSE LIB_STATUS END "
        "OUTPUT INSERTED.LIB_TENTATIVAS "
        "WHERE LIB_ID = ? AND LIB_STATUS = ?"
    )
    with closing(_connect()) as conn, closing(conn.cursor()) as cur:
        row = cur.execute(
            sql, max_attempts, STATUS_BLOCKED, request_id, STATUS_PENDING
        ).fetchone()
        conn.commit()
    return int(row[0]) if row else max_attempts


def approve(request_id: str, consumido_em: datetime) -> bool:
    """Consome a liberacao. False se outra chamada já a consumiu."""
    sql = (
        f"UPDATE {TABLE} SET LIB_STATUS = ?, LIB_CONSUMIDO_EM = ? "
        "WHERE LIB_ID = ? AND LIB_STATUS = ?"
    )
    with closing(_connect()) as conn, closing(conn.cursor()) as cur:
        cur.execute(sql, STATUS_APPROVED, consumido_em, request_id, STATUS_PENDING)
        changed = cur.rowcount
        conn.commit()
    return changed == 1


def mark_status(request_id: str, status: str) -> None:
    sql = f"UPDATE {TABLE} SET LIB_STATUS = ? WHERE LIB_ID = ? AND LIB_STATUS = ?"
    with closing(_connect()) as conn, closing(conn.cursor()) as cur:
        cur.execute(sql, status, request_id, STATUS_PENDING)
        conn.commit()


_load_config()
