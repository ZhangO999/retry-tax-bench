from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extensions import connection

from .sampler import SmallBankConfig


def dsn_from_config(db_config: dict[str, Any]) -> str:
    parts = []
    for key in ("host", "port", "dbname", "user", "password"):
        value = db_config.get(key)
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    return " ".join(parts)


def connect(db_config: dict[str, Any]) -> connection:
    return psycopg2.connect(dsn_from_config(db_config))


def initialize_database(db_config: dict[str, Any], cfg: SmallBankConfig, schema_path: Path) -> dict[str, int]:
    conn = connect(db_config)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(schema_path.read_text(encoding="utf-8"))
            cur.execute(
                """
                INSERT INTO Account(name, CustomerID)
                SELECT 'name' || i, i
                FROM generate_series(1, %s) AS i
                """,
                (cfg.account_count,),
            )
            cur.execute(
                """
                INSERT INTO Savings(CustomerID, Balance)
                SELECT i, %s
                FROM generate_series(1, %s) AS i
                """,
                (cfg.initial_savings, cfg.account_count),
            )
            cur.execute(
                """
                INSERT INTO Checking(CustomerID, Balance)
                SELECT i, %s
                FROM generate_series(1, %s) AS i
                """,
                (cfg.initial_checking, cfg.account_count),
            )
        conn.commit()
        return sanity_snapshot(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def sanity_snapshot(conn: connection) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM Account),
                (SELECT COUNT(*) FROM Savings),
                (SELECT COUNT(*) FROM Checking),
                COALESCE((SELECT SUM(Balance) FROM Savings), 0),
                COALESCE((SELECT SUM(Balance) FROM Checking), 0)
            """
        )
        account_count, savings_count, checking_count, savings_total, checking_total = cur.fetchone()
    return {
        "account_count": int(account_count),
        "savings_count": int(savings_count),
        "checking_count": int(checking_count),
        "savings_total": int(savings_total),
        "checking_total": int(checking_total),
        "total_funds": int(savings_total + checking_total),
    }


def expected_initial_total(cfg: SmallBankConfig) -> int:
    return cfg.account_count * (cfg.initial_savings + cfg.initial_checking)
