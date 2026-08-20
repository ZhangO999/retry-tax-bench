"""Tests for the SmallBank workload sampler.

The sampler decides which accounts a transaction touches, so the hotspot
behaviour here is what actually produces contention in the experiment.
"""

from __future__ import annotations

import pytest

from smallbank.policies import TRANSACTIONS
from smallbank.sampler import Sampler, SmallBankConfig, config_from_dict

BASE = {
    "account_count": 1000,
    "initial_savings": 10_000,
    "initial_checking": 10_000,
    "hotspot_size": 10,
    "hotspot_probability": 0.5,
    "amount_min": 1,
    "amount_max": 100,
}


def make(**overrides) -> Sampler:
    data = {**BASE, **overrides}
    seed = data.pop("seed", 1234)
    return Sampler(config_from_dict(data), seed=seed)


def test_config_from_dict_coerces_types():
    cfg = config_from_dict({**BASE, "account_count": "500", "hotspot_probability": "0.25"})
    assert cfg == SmallBankConfig(
        account_count=500,
        initial_savings=10_000,
        initial_checking=10_000,
        hotspot_size=10,
        hotspot_probability=0.25,
        amount_min=1,
        amount_max=100,
    )


def test_hotspot_must_fit_inside_the_account_space():
    with pytest.raises(ValueError, match="hotspot_size"):
        make(hotspot_size=1000)


def test_same_seed_gives_the_same_stream():
    """Runs are supposed to be reproducible from the seed alone."""
    a, b = make(seed=7), make(seed=7)
    draws = [(s.transaction_name(), s.account_id(), s.amount()) for s in (a, b)]
    assert draws[0] == draws[1]


def test_different_seeds_diverge():
    a, b = make(seed=1), make(seed=2)
    assert [a.account_id() for _ in range(50)] != [b.account_id() for _ in range(50)]


def test_probability_one_always_hits_the_hotspot():
    sampler = make(hotspot_probability=1.0)
    assert all(sampler.account_id() <= BASE["hotspot_size"] for _ in range(200))


def test_probability_zero_never_hits_the_hotspot():
    sampler = make(hotspot_probability=0.0)
    assert all(sampler.account_id() > BASE["hotspot_size"] for _ in range(200))


def test_account_ids_stay_in_range():
    sampler = make()
    assert all(1 <= sampler.account_id() <= BASE["account_count"] for _ in range(500))


def test_two_distinct_accounts_are_distinct():
    sampler = make()
    for _ in range(200):
        first, second = sampler.two_distinct_accounts()
        assert first != second


def test_amounts_stay_within_bounds():
    sampler = make(amount_min=5, amount_max=9)
    assert {sampler.amount() for _ in range(200)} <= {5, 6, 7, 8, 9}


def test_transaction_names_come_from_the_known_set():
    sampler = make()
    assert {sampler.transaction_name() for _ in range(200)} <= set(TRANSACTIONS)
