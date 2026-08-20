"""Tests for policy loading and isolation-level mapping."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from smallbank.policies import ISOLATION_SQL, TRANSACTIONS, isolation_sql, load_policies

CONFIG = Path(__file__).resolve().parents[1] / "config" / "policies.json"


def write_policies(tmp_path: Path, policies: dict) -> Path:
    path = tmp_path / "policies.json"
    path.write_text(json.dumps(policies), encoding="utf-8")
    return path


def test_shipped_config_loads():
    policies = load_policies(CONFIG)
    assert set(policies) == {"rc", "si", "ssi", "mixed_robust"}
    for allocation in policies.values():
        assert set(allocation) == set(TRANSACTIONS)


def test_mixed_robust_is_actually_mixed():
    """The point of the mixed policy is that not every transaction is SSI."""
    allocation = load_policies(CONFIG)["mixed_robust"]
    assert len(set(allocation.values())) > 1


def test_missing_transaction_is_rejected(tmp_path):
    allocation = {tx: "RC" for tx in TRANSACTIONS if tx != "amalgamate"}
    path = write_policies(tmp_path, {"partial": allocation})
    with pytest.raises(ValueError, match="amalgamate"):
        load_policies(path)


def test_unknown_isolation_is_rejected(tmp_path):
    allocation = dict.fromkeys(TRANSACTIONS, "RC")
    allocation["balance"] = "READ UNCOMMITTED"
    path = write_policies(tmp_path, {"bogus": allocation})
    with pytest.raises(ValueError, match="unknown isolation"):
        load_policies(path)


@pytest.mark.parametrize(
    ("label", "expected"),
    [("RC", "READ COMMITTED"), ("SI", "REPEATABLE READ"), ("SSI", "SERIALIZABLE")],
)
def test_isolation_sql_mapping(label, expected):
    assert isolation_sql(label) == expected


def test_isolation_sql_rejects_unknown_label():
    with pytest.raises(ValueError, match="Unknown isolation label"):
        isolation_sql("SNAPSHOT")


def test_every_label_maps_to_real_postgres_syntax():
    assert set(ISOLATION_SQL.values()) <= {
        "READ COMMITTED",
        "REPEATABLE READ",
        "SERIALIZABLE",
    }
