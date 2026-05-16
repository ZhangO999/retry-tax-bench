from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

import psycopg2
from psycopg2.extensions import connection

from .policies import isolation_sql
from .sampler import Sampler


RETRIABLE_SQLSTATES = {"40001", "40P01"}


@dataclass
class TransactionOutcome:
    name: str
    isolation: str
    committed: bool
    attempts: int
    aborts: int
    latency_seconds: float
    abort_reasons: dict[str, int]


def is_retriable(exc: BaseException) -> bool:
    return getattr(exc, "pgcode", None) in RETRIABLE_SQLSTATES


def abort_reason(exc: BaseException) -> str:
    code = getattr(exc, "pgcode", "") or ""
    message = str(exc).lower()
    if code == "40P01":
        return "deadlock"
    if "concurrent update" in message:
        return "concurrent_update"
    if "pivot" in message or "dangerous structure" in message:
        return "dangerous_structure"
    if code == "40001":
        return "serialization_failure"
    return code or exc.__class__.__name__


def run_with_retry(
    conn: connection,
    sampler: Sampler,
    policy: dict[str, str],
    retry_limit: int | None,
) -> TransactionOutcome:
    tx_name = sampler.transaction_name()
    isolation = policy[tx_name]
    accounts = sampler.two_distinct_accounts()
    amount = sampler.amount()
    aborts = 0
    attempts = 0
    abort_reasons: dict[str, int] = {}
    start = perf_counter()

    while retry_limit is None or attempts <= retry_limit:
        attempts += 1
        try:
            _run_once(conn, tx_name, isolation, accounts, amount)
            return TransactionOutcome(
                name=tx_name,
                isolation=isolation,
                committed=True,
                attempts=attempts,
                aborts=aborts,
                latency_seconds=perf_counter() - start,
                abort_reasons=abort_reasons,
            )
        except Exception as exc:
            conn.rollback()
            if not is_retriable(exc):
                raise
            aborts += 1
            reason = abort_reason(exc)
            abort_reasons[reason] = abort_reasons.get(reason, 0) + 1

    return TransactionOutcome(
        name=tx_name,
        isolation=isolation,
        committed=False,
        attempts=attempts,
        aborts=aborts,
        latency_seconds=perf_counter() - start,
        abort_reasons=abort_reasons,
    )


def _run_once(
    conn: connection,
    tx_name: str,
    isolation: str,
    accounts: tuple[int, int],
    amount: int,
) -> None:
    conn.set_session(isolation_level=isolation_sql(isolation), readonly=False, autocommit=False)
    fn = TRANSACTION_FUNCTIONS[tx_name]
    with conn.cursor() as cur:
        fn(cur, accounts, amount)
    conn.commit()


def balance(cur, accounts: tuple[int, int], amount: int) -> None:
    del amount
    customer_id = _customer_id(cur, accounts[0])
    cur.execute("SELECT Balance FROM Savings WHERE CustomerId = %s", (customer_id,))
    balance_value = cur.fetchone()[0]
    cur.execute("SELECT Balance FROM Checking WHERE CustomerId = %s", (customer_id,))
    balance_value += cur.fetchone()[0]


def deposit_checking(cur, accounts: tuple[int, int], amount: int) -> None:
    customer_id = _customer_id(cur, accounts[0])
    cur.execute(
        "UPDATE Checking SET Balance = Balance + %s WHERE CustomerId = %s",
        (amount, customer_id),
    )


def transact_savings(cur, accounts: tuple[int, int], amount: int) -> None:
    customer_id = _customer_id(cur, accounts[0])
    cur.execute(
        "UPDATE Savings SET Balance = Balance + %s WHERE CustomerId = %s",
        (amount, customer_id),
    )


def write_check(cur, accounts: tuple[int, int], amount: int) -> None:
    customer_id = _customer_id(cur, accounts[0])
    cur.execute("SELECT Balance FROM Savings WHERE CustomerId = %s", (customer_id,))
    savings = cur.fetchone()[0]
    cur.execute("SELECT Balance FROM Checking WHERE CustomerId = %s", (customer_id,))
    checking = cur.fetchone()[0]
    debit = amount + 1 if savings + checking < amount else amount
    cur.execute(
        "UPDATE Checking SET Balance = Balance - %s WHERE CustomerId = %s",
        (debit, customer_id),
    )


def amalgamate(cur, accounts: tuple[int, int], amount: int) -> None:
    del amount
    source_id, destination_id = accounts
    customer_id1 = _customer_id(cur, source_id)
    customer_id2 = _customer_id(cur, destination_id)
    cur.execute(
        """
        UPDATE Savings AS new
        SET Balance = 0
        FROM Savings AS old
        WHERE new.CustomerId = %s
          AND old.CustomerId = new.CustomerId
        RETURNING old.Balance
        """,
        (customer_id1,),
    )
    balance1 = cur.fetchone()[0]
    cur.execute(
        """
        UPDATE Checking AS new
        SET Balance = 0
        FROM Checking AS old
        WHERE new.CustomerId = %s
          AND old.CustomerId = new.CustomerId
        RETURNING old.Balance
        """,
        (customer_id2,),
    )
    balance2 = cur.fetchone()[0]
    cur.execute(
        "UPDATE Checking SET Balance = Balance + %s + %s WHERE CustomerId = %s",
        (balance1, balance2, customer_id2),
    )


def _customer_id(cur, account_number: int) -> int:
    cur.execute("SELECT CustomerId FROM Account WHERE Name = %s", (f"name{account_number}",))
    return cur.fetchone()[0]


TRANSACTION_FUNCTIONS: dict[str, Callable] = {
    "balance": balance,
    "deposit_checking": deposit_checking,
    "transact_savings": transact_savings,
    "write_check": write_check,
    "amalgamate": amalgamate,
}
