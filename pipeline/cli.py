"""Command line interface:  python -m pipeline <command> [options]

Commands
  run        process input file(s) into sessions
  generate   create synthetic input data plus an answer key
  reconcile  run the consistency checks on an existing database
  queries    print the sample analytical queries
  benchmark  measure speed on generated data

Exit codes: 0 = success, 1 = run failed, 2 = bad usage/config, 3 = reconciliation check failed
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from . import store
from .config import Config, ConfigError, load_config
from .datagen import generate
from .reconcile import compare_with_expected, reconcile
from .report import export_csvs, format_table, load_sample_queries, write_report
from .runner import run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m pipeline", description="Clickstream sessionization pipeline")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="process input files into sessions")
    r.add_argument("--input", nargs="+", required=True, help="one or more .csv / .jsonl files")
    r.add_argument("--users", help="users.csv with a user_id column (enables the reference-key check)")
    r.add_argument("--db", help="SQLite database path (default out/sessions.db)")
    r.add_argument("--gap-minutes", type=float, help="inactivity gap that starts a new session (default 30)")
    r.add_argument("--report-dir", help="where to write the report and CSV exports (default out/reports)")
    r.add_argument("--config", help="JSON config file (flags override it)")
    r.add_argument("--max-reject-rate", type=float, help="fail the run if more than this share is rejected (0-1)")
    r.add_argument("--run-id", help="use a specific run id (default: generated)")
    r.add_argument("--expected-dir", help="answer-key folder from 'generate'; adds comparison checks")

    g = sub.add_parser("generate", help="create reproducible synthetic data")
    g.add_argument("--out-dir", default="data/generated")
    g.add_argument("--expected-dir", default="data/expected/generated")
    g.add_argument("--rows", type=int, default=1000, help="total rows in the file (default 1000)")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--gap-minutes", type=float, default=30)
    g.add_argument("--format", choices=["csv", "jsonl"], default="csv")
    g.add_argument("--anomaly-rate", type=float, default=0.06, help="share of rows that are bad/duplicate")
    g.add_argument("--max-sessions", type=int, default=6, help="max sessions per user")
    g.add_argument("--max-events", type=int, default=12, help="max events per session")

    c = sub.add_parser("reconcile", help="check an existing database")
    c.add_argument("--db", default="out/sessions.db")
    c.add_argument("--run-id")
    c.add_argument("--expected-dir")

    q = sub.add_parser("queries", help="run the sample analytical queries")
    q.add_argument("--db", default="out/sessions.db")

    b = sub.add_parser("benchmark", help="time the pipeline on generated data")
    b.add_argument("--rows", type=int, default=100000)
    b.add_argument("--seed", type=int, default=42)
    b.add_argument("--workdir", default="out/benchmark")
    b.add_argument("--output", help="also write the markdown results to this file")
    return p


def _config_from_args(args) -> Config:
    cfg = load_config(args.config) if args.config else Config()
    if args.db:
        cfg.db_path = args.db
    if args.gap_minutes is not None:
        cfg.gap_minutes = args.gap_minutes
    if args.report_dir:
        cfg.report_dir = args.report_dir
    if args.max_reject_rate is not None:
        cfg.max_reject_rate = args.max_reject_rate
    return cfg.validate()


def _print_checks(checks) -> None:
    for c in checks:
        print(f"  [{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}")


def _cmd_run(args) -> int:
    cfg = _config_from_args(args)
    result = run_pipeline(cfg, args.input, users_path=args.users, run_id=args.run_id)
    print(f"\nRun {result.run_id}: {result.status}")
    if result.status == "FAILED":
        print(f"  failure reason: {result.failure_reason}")
        conn = store.connect(cfg.db_path)
        path = write_report(conn, result, [], cfg.report_dir)
        conn.close()
        print(f"  report: {path}")
        return 1
    print(f"  rows read={result.rows_in}  new events={result.rows_inserted}  "
          f"already loaded={result.rows_skipped_existing}  rejected={result.rows_rejected}")
    print(f"  late-arriving events={result.late_events}  users re-sessionized={result.users_affected}  "
          f"sessions written={result.sessions_written}  duration={result.duration_seconds:.2f}s")
    if result.rejects_by_reason:
        print("  rejects by reason: " + ", ".join(f"{k}={v}" for k, v in sorted(result.rejects_by_reason.items())))
    conn = store.connect(cfg.db_path)
    checks = reconcile(conn, result.run_id)
    if args.expected_dir:
        checks += compare_with_expected(conn, args.expected_dir, result.run_id)
    print("Reconciliation:")
    _print_checks(checks)
    report = write_report(conn, result, checks, cfg.report_dir)
    sessions_csv, rejects_csv = export_csvs(conn, cfg.report_dir, result.run_id)
    conn.close()
    print(f"Report:  {report}\nExports: {sessions_csv}, {rejects_csv}")
    return 0 if all(c.passed for c in checks) else 3


def _cmd_generate(args) -> int:
    manifest = generate(args.out_dir, args.expected_dir, rows=args.rows, seed=args.seed,
                        gap_minutes=args.gap_minutes, fmt=args.format, anomaly_rate=args.anomaly_rate,
                        max_sessions=args.max_sessions, max_events=args.max_events)
    print(f"Wrote {manifest['events_file']} ({manifest['rows']} rows, {manifest['users']} users) "
          f"and answer key in {args.expected_dir}")
    print(f"Expected: {manifest['expected_sessions']} sessions, {manifest['expected_rejects']} rejects "
          f"{manifest['expected_rejects_by_reason']}")
    return 0


def _cmd_reconcile(args) -> int:
    conn = store.connect(args.db)
    store.init_db(conn)
    checks = reconcile(conn, args.run_id)
    if args.expected_dir:
        checks += compare_with_expected(conn, args.expected_dir, args.run_id)
    conn.close()
    _print_checks(checks)
    return 0 if all(c.passed for c in checks) else 3


def _cmd_queries(args) -> int:
    conn = store.connect(args.db)
    for name, sql in load_sample_queries():
        cur = conn.execute(sql)
        print(f"\n== {name} ==")
        print(format_table([d[0] for d in cur.description], cur.fetchall()))
    conn.close()
    return 0


def _cmd_benchmark(args) -> int:
    from .benchmark import run_benchmark
    print(run_benchmark(args.rows, args.seed, args.workdir, args.output))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    try:
        handler = {"run": _cmd_run, "generate": _cmd_generate, "reconcile": _cmd_reconcile,
                   "queries": _cmd_queries, "benchmark": _cmd_benchmark}[args.command]
        return handler(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
