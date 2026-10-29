"""Human-readable outputs: markdown run report, CSV exports and the sample-query runner."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import List, Tuple

from .models import RunResult
from .reconcile import Check

SAMPLE_QUERIES_PATH = Path(__file__).resolve().parent.parent / "sql" / "sample_queries.sql"


def export_csvs(conn, report_dir: str, run_id: str) -> Tuple[str, str]:
    out = Path(report_dir)
    out.mkdir(parents=True, exist_ok=True)
    sessions_path, rejects_path = out / "sessions.csv", out / "rejected_events.csv"
    cur = conn.execute("SELECT session_id, user_id, session_start, session_end, duration_seconds, event_count, "
                       "is_bounce FROM sessions ORDER BY user_id, session_start_ts")
    with open(sessions_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow([d[0] for d in cur.description])
        w.writerows(cur)
    cur = conn.execute("SELECT run_id, source_file, source_row, reject_reason, reject_detail, raw_record "
                       "FROM rejected_events WHERE run_id=? ORDER BY source_file, source_row", (run_id,))
    with open(rejects_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow([d[0] for d in cur.description])
        w.writerows(cur)
    return str(sessions_path), str(rejects_path)


def write_report(conn, result: RunResult, checks: List[Check], report_dir: str) -> str:
    out = Path(report_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"report_{result.run_id}.md"
    lines = [
        f"# Run report `{result.run_id}`", "",
        f"- **Status:** {result.status}",
        f"- **Duration:** {result.duration_seconds:.2f}s",
    ]
    if result.failure_reason:
        lines.append(f"- **Failure reason:** {result.failure_reason}")
    lines += ["", "## Counts", "", "| Metric | Value |", "|---|---|",
              f"| rows read | {result.rows_in} |",
              f"| new events loaded | {result.rows_inserted} |",
              f"| already loaded (skipped, not errors) | {result.rows_skipped_existing} |",
              f"| rejected | {result.rows_rejected} |",
              f"| late-arriving events | {result.late_events} |",
              f"| users re-sessionized | {result.users_affected} |",
              f"| sessions written | {result.sessions_written} |", ""]
    if result.rows_in:
        lines.append(f"Reject rate: {100.0 * result.rows_rejected / result.rows_in:.2f}%")
        lines.append("")
    lines += ["## Rejects by reason", ""]
    if result.rejects_by_reason:
        lines += ["| Reason | Rows |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(result.rejects_by_reason.items())]
    else:
        lines.append("None.")
    if result.timings:
        lines += ["", "## Stage timings (seconds)", "", "| Stage | Seconds |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in result.timings.items()]
    if result.notes:
        lines += ["", "## Notes", ""] + [f"- {k}: {v}" for k, v in sorted(result.notes.items())]
    if checks:
        lines += ["", "## Reconciliation", "", "| Check | Result | Detail |", "|---|---|---|"]
        lines += [f"| {c.name} | {'PASS' if c.passed else 'FAIL'} | {c.detail} |" for c in checks]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def load_sample_queries(path: Path = SAMPLE_QUERIES_PATH) -> List[Tuple[str, str]]:
    """Split sample_queries.sql into (name, sql) pairs using the '-- name:' markers."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^-- name:\s*(\S+)\s*$", text, flags=re.MULTILINE)
    return [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]


def format_table(columns: List[str], rows: List[tuple]) -> str:
    cells = [[str(c) for c in columns]] + [["" if v is None else str(v) for v in r] for r in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(columns))]
    fmt = lambda row: "  ".join(v.ljust(widths[i]) for i, v in enumerate(row))  # noqa: E731
    return "\n".join([fmt(cells[0]), "  ".join("-" * w for w in widths)] + [fmt(r) for r in cells[1:]])
