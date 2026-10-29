# Benchmark (100,000 rows, seed 42, SQLite 3.49.1)

Data generation: 0.93s

## First run (SUCCESS)

Total 2.38s -> 42,101 rows/second

| Stage | Seconds |
|---|---|
| read | 0.5425 |
| validate | 0.6734 |
| dedupe | 0.0284 |
| classify | 0.0586 |
| insert_events | 0.5413 |
| sessionize | 0.4688 |

## Re-run of the same file (SUCCESS)

Total 1.51s; new events inserted: 0; already loaded: 94000; sessions rebuilt: 0

## Optimisation experiment: rebuild only affected users

A small late-arriving batch touches few users. The pipeline rebuilds sessions only for those users instead of everyone.

| Strategy | Users rebuilt | Seconds |
|---|---|---|
| incremental (affected users only, ~1%) | 42 | 0.009 |
| full rebuild (all users) | 4223 | 0.510 |

