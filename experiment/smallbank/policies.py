from __future__ import annotations

import json
from pathlib import Path


TRANSACTIONS = (
    "balance",
    "deposit_checking",
    "transact_savings",
    "write_check",
    "amalgamate",
)

ISOLATION_SQL = {
    "RC": "READ COMMITTED",
    "SI": "REPEATABLE READ",
    "SSI": "SERIALIZABLE",
}


def load_policies(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        policies = json.load(f)
    for policy_name, allocation in policies.items():
        missing = set(TRANSACTIONS) - set(allocation)
        if missing:
            raise ValueError(f"Policy {policy_name} is missing: {sorted(missing)}")
        for tx_name, isolation in allocation.items():
            if isolation not in ISOLATION_SQL:
                raise ValueError(f"Policy {policy_name}.{tx_name} uses unknown isolation {isolation}")
    return policies


def isolation_sql(label: str) -> str:
    try:
        return ISOLATION_SQL[label]
    except KeyError as exc:
        raise ValueError(f"Unknown isolation label: {label}") from exc
