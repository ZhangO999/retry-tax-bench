from __future__ import annotations

import random
from dataclasses import dataclass

from .policies import TRANSACTIONS


@dataclass(frozen=True)
class SmallBankConfig:
    account_count: int
    initial_savings: int
    initial_checking: int
    hotspot_size: int
    hotspot_probability: float
    amount_min: int
    amount_max: int


class Sampler:
    def __init__(self, config: SmallBankConfig, seed: int):
        if config.hotspot_size >= config.account_count:
            raise ValueError("hotspot_size must be smaller than account_count")
        self.config = config
        self.rng = random.Random(seed)

    def transaction_name(self) -> str:
        return self.rng.choice(TRANSACTIONS)

    def account_id(self) -> int:
        cfg = self.config
        if self.rng.random() < cfg.hotspot_probability:
            return self.rng.randint(1, cfg.hotspot_size)
        return self.rng.randint(cfg.hotspot_size + 1, cfg.account_count)

    def two_distinct_accounts(self) -> tuple[int, int]:
        first = self.account_id()
        second = self.account_id()
        while second == first:
            second = self.account_id()
        return first, second

    def amount(self) -> int:
        return self.rng.randint(self.config.amount_min, self.config.amount_max)


def config_from_dict(data: dict) -> SmallBankConfig:
    return SmallBankConfig(
        account_count=int(data["account_count"]),
        initial_savings=int(data["initial_savings"]),
        initial_checking=int(data["initial_checking"]),
        hotspot_size=int(data["hotspot_size"]),
        hotspot_probability=float(data["hotspot_probability"]),
        amount_min=int(data["amount_min"]),
        amount_max=int(data["amount_max"]),
    )
