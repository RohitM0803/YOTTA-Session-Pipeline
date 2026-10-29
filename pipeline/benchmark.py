"""Simple performance measurement + one optimisation experiment.

1. End-to-end: generate N rows, run the pipeline, report per-stage time and rows/second,
   then re-run the same file to show the idempotent rerun cost.
2. Optimisation: rebuilding sessions only for users that received new events (incremental)
   vs. rebuilding every user (full).
"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path
from typing import Optional

from . import store
from .config import Config
from .datagen import generate
from .runner import rebuild_sessions, run_pipeline


def _rebuild_experiment(db_path: str, gap_seconds: int) -> dict:
    """Time rebuilding sessions for ~1% of users (what a small late batch triggers) vs all users.

    Each measurement runs inside a transaction that is rolled back, so the database is unchanged.
    """
    conn = store.connect(db_path)
    users = store.all_event_user_ids(conn)
    subset = users[: max(1, len(users) // 100)]
    out = {"users_total": len(users), "users_subset": len(subset)}
    for label, ids in (("incremental", subset), ("full", users)):
        conn.execute("BEGIN")
        t0 = time.perf_counter()
        rebuild_sessions(conn, ids, gap_seconds, "benchmark")
        out[label] = time.perf_counter() - t0
        conn.execute("ROLLBACK")
    conn.close()
    return out


def run_benchmark(rows: int, seed: int, workdir: str, output: Optional[str] = None) -> str:
    work = Path(workdir).resolve()

    if work.exists() and not work.is_dir():
        raise ValueError(f"Benchmark workdir exists but is not a directory: {work}")

    work.mkdir(parents=True, exist_ok=True)

    for name in ("data", "expected"):
        path = work / name
        if path.exists():
            if not path.is_dir():
                raise ValueError(f"Expected a directory but found a file: {path}")
            shutil.rmtree(path)

    for name in ("bench.db", "bench.db-journal", "bench.db-wal", "bench.db-shm"):
        path = work / name
        if path.exists():
            if not path.is_file():
                raise ValueError(f"Expected a file but found a directory: {path}")
            path.unlink()
    t0 = time.perf_counter()
    generate(str(work / "data"), str(work / "expected"), rows=rows, seed=seed)
    gen_seconds = time.perf_counter() - t0
    cfg = Config(db_path=str(work / "bench.db"), report_dir=str(work / "reports"))
    inputs = [str(work / "data" / "events.csv")]
    users = str(work / "data" / "users.csv")
    first = run_pipeline(cfg, inputs, users)
    second = run_pipeline(cfg, inputs, users)
    exp = _rebuild_experiment(cfg.db_path, cfg.gap_seconds)

    def stage_rows(res):
        return "".join(f"| {k} | {v} |\n" for k, v in res.timings.items())

    lines = [
        f"# Benchmark ({rows:,} rows, seed {seed}, SQLite {sqlite3.sqlite_version})", "",
        f"Data generation: {gen_seconds:.2f}s", "",
        f"## First run ({first.status})", "",
        f"Total {first.duration_seconds:.2f}s -> {rows / max(first.duration_seconds, 1e-9):,.0f} rows/second", "",
        "| Stage | Seconds |", "|---|---|", stage_rows(first).rstrip(), "",
        f"## Re-run of the same file ({second.status})", "",
        f"Total {second.duration_seconds:.2f}s; new events inserted: {second.rows_inserted}; "
        f"already loaded: {second.rows_skipped_existing}; sessions rebuilt: {second.sessions_written}", "",
        "## Optimisation experiment: rebuild only affected users", "",
        "A small late-arriving batch touches few users. The pipeline rebuilds sessions only for those users "
        "instead of everyone.", "",
        "| Strategy | Users rebuilt | Seconds |", "|---|---|---|",
        f"| incremental (affected users only, ~1%) | {exp['users_subset']} | {exp['incremental']:.3f} |",
        f"| full rebuild (all users) | {exp['users_total']} | {exp['full']:.3f} |", "",
    ]
    text = "\n".join(lines)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text + "\n", encoding="utf-8")
    return text
