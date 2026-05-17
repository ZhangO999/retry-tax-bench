# Result 1: Failure Rate vs Retry Budget

This folder contains the exact data used for `figures/slides/result1_failure_rate_only_mpl64_p09_95ci.png`.

Filter used:

```text
mpl = 64
hotspot_probability = 0.9
all four policies
all four retry budgets
5 repeats per plotted point
```

Whiskers in the graph are 95% confidence intervals:

```text
CI95 = 2.776 * SD / sqrt(5)
```

Files:

- `result1_failure_rate_raw_subset.csv`: exact raw CSV rows used for the graph.
- `result1_failure_rate_aggregate.csv`: mean, SD, and 95% CI values used for plotting.
- `result1_failure_rate_slide_table.csv`: compact table for slide/report use.

Compact slide table:

| Policy       | 1 retry | 3 retries | 10 retries | Retry forever |
| ------------ | ------- | --------- | ---------- | ------------- |
| RC           | 0.00%   | 0.00%     | 0.00%      | 0.00%         |
| SI           | 16.54%  | 7.35%     | 1.15%      | 0.00%         |
| SSI          | 10.22%  | 3.81%     | 0.27%      | 0.00%         |
| Mixed-robust | 11.22%  | 3.99%     | 0.31%      | 0.00%         |

Values are mean failed user request rates, in percent.
