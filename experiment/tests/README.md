# Tests

These cover the parts of the harness that do not need a database: the policy
loader (`smallbank/policies.py`) and the workload sampler
(`smallbank/sampler.py`).

Run them from the `experiment/` directory, so that `smallbank` is importable:

```bash
cd experiment
python -m pytest tests -q
```

Anything that talks to PostgreSQL is exercised by the SQL sanity checks in
`sql/sanity_checks.sql` and by `validate_results.py`, not by this suite.
