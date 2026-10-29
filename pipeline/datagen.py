"""Reproducible synthetic data generator with a separate answer key.

Design: sessions are generated FIRST (with known boundaries), then events are placed inside them.
So the expected sessions are known by construction, independent of the pipeline's own logic.
Anomalies are ADDED as extra rows (each with exactly one defect) so they never change the answer.

Outputs
  <out_dir>/events.csv|jsonl      the input file the pipeline reads
  <out_dir>/users.csv             reference users
  <expected_dir>/expected_sessions.csv   answer key: the sessions the pipeline must produce
  <expected_dir>/expected_rejects.csv    answer key: which line must be rejected and why
  <expected_dir>/manifest.json           seed, counts and settings
The same seed always produces byte-identical files.
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

from .schema import Reason

EVENT_TYPES = ["page_view", "click", "search", "add_to_cart", "purchase"]
PAGES = ["/home", "/search", "/product/101", "/product/202", "/cart", "/checkout", "/help"]
BAD_TIMESTAMPS = ["not-a-time", "2026-13-45T99:00:00Z", "yesterday", "1767225600", "2026-01-01",
                  "1970-01-01T00:00:00Z", "0000-00-00T00:00:00Z"]
# (reason, share of anomalies)
ANOMALY_SHARES = [
    (Reason.DUPLICATE_EVENT, 0.35), (Reason.CONFLICTING_DUPLICATE_EVENT, 0.05),
    (Reason.MISSING_TIMESTAMP, 0.10), (Reason.INVALID_TIMESTAMP, 0.10),
    (Reason.MISSING_REQUIRED_FIELD, 0.10), (Reason.INVALID_REFERENCE_KEY, 0.15),
    (Reason.MALFORMED_ROW, 0.15),
]
HEADER = ["event_id", "user_id", "event_type", "event_time", "page"]
_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _render_time(ts: int, rng: random.Random) -> str:
    """Same instant, written either as UTC ('Z') or with a +05:30 offset (10% of rows)."""
    if rng.random() < 0.10:
        local = datetime.fromtimestamp(ts + 19800, timezone.utc)
        return local.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"
    return _iso_utc(ts)


def _anomaly_counts(n_anom: int) -> Dict[str, int]:
    reasons = [r for r, _ in ANOMALY_SHARES]
    if n_anom < len(reasons):
        return {r: (1 if i < n_anom else 0) for i, r in enumerate(reasons)}
    counts = {r: 1 for r in reasons}
    remaining = n_anom - len(reasons)
    given = 0
    for reason, share in ANOMALY_SHARES:
        extra = int(share * remaining)
        counts[reason] += extra
        given += extra
    counts[Reason.DUPLICATE_EVENT] += remaining - given
    return counts


def generate(out_dir: str, expected_dir: str, rows: int = 1000, seed: int = 42, gap_minutes: float = 30,
             fmt: str = "csv", anomaly_rate: float = 0.06, max_sessions: int = 6, max_events: int = 12) -> dict:
    if rows < 1:
        raise ValueError("rows must be >= 1")
    if fmt not in ("csv", "jsonl"):
        raise ValueError("fmt must be 'csv' or 'jsonl'")
    if not 0 <= anomaly_rate < 1:
        raise ValueError("anomaly_rate must be in [0, 1)")
    rng = random.Random(seed)
    gap = int(round(gap_minutes * 60))
    n_anom = int(round(rows * anomaly_rate))
    n_real = rows - n_anom
    if n_real < 1:
        raise ValueError("anomaly_rate leaves no valid rows")
    base_ts = int(_BASE.timestamp())

    # ---------- 1. real users, sessions and events (the ground truth)
    users: List[str] = []
    real: List[dict] = []
    truth: List[dict] = []
    uidx = 0
    while len(real) < n_real:
        uidx += 1
        user_id = f"user_{uidx:05d}"
        t = base_ts + rng.randint(0, 14 * 86400)
        sessions: List[List[int]] = []
        for _ in range(rng.randint(1, max_sessions)):
            times = [t]
            for _ in range(rng.randint(1, max_events) - 1):
                r = rng.random()
                if r < 0.03:
                    step = gap                      # boundary: exactly the gap -> SAME session
                elif r < 0.06:
                    step = 0                        # identical timestamps
                else:
                    step = rng.randint(1, max(1, gap - 1))
                times.append(times[-1] + step)
            sessions.append(times)
            nxt = gap + 1 if rng.random() < 0.05 else rng.randint(gap + 1, gap + 6 * 3600)
            t = times[-1] + nxt                     # boundary: gap+1 second -> NEW session
        excess = len(real) + sum(len(s) for s in sessions) - n_real
        while excess > 0:                           # trim so the total is exactly n_real
            if len(sessions[-1]) <= excess:
                excess -= len(sessions.pop())
            else:
                del sessions[-1][-excess:]
                excess = 0
        users.append(user_id)
        for times in sessions:
            truth.append({"user_id": user_id, "start": times[0], "end": times[-1], "count": len(times)})
            for ts in times:
                real.append({"event_id": f"evt_{len(real) + 1:08d}", "user_id": user_id,
                             "event_type": rng.choice(EVENT_TYPES), "ts": ts, "page": rng.choice(PAGES)})

    # ---------- 2. rows (real + anomalies), each with a position key to create disorder
    items: List[dict] = []
    for ev in real:
        key = ev["ts"] + (rng.randint(3600, 3 * 86400) if rng.random() < 0.10 else 0)  # 10% arrive late
        items.append({"kind": "valid", "key": key, "event_id": ev["event_id"], "user_id": ev["user_id"],
                      "event_type": ev["event_type"], "ts": ev["ts"], "page": ev["page"]})
    min_ts, max_ts = min(e["ts"] for e in real), max(e["ts"] for e in real)
    counts = _anomaly_counts(n_anom)
    seq = 0
    for reason, n in counts.items():
        for _ in range(n):
            seq += 1
            src = rng.choice(real)
            if reason in (Reason.DUPLICATE_EVENT, Reason.CONFLICTING_DUPLICATE_EVENT):
                page = src["page"] if reason == Reason.DUPLICATE_EVENT else "/conflicting-page"
                items.append({"kind": "dup", "key": src["ts"] + rng.randint(0, 7200), "event_id": src["event_id"],
                              "user_id": src["user_id"], "event_type": src["event_type"], "ts": src["ts"],
                              "page": page})
                continue
            item = {"kind": reason, "key": rng.randint(min_ts, max_ts), "event_id": f"evt_bad_{seq:06d}",
                    "user_id": src["user_id"], "event_type": rng.choice(EVENT_TYPES),
                    "ts": rng.randint(min_ts, max_ts), "page": rng.choice(PAGES), "time_text": None}
            if reason == Reason.MISSING_TIMESTAMP:
                item["time_text"] = rng.choice(["", "NULL", "null", None])
            elif reason == Reason.INVALID_TIMESTAMP:
                item["time_text"] = rng.choice(BAD_TIMESTAMPS)
            elif reason == Reason.MISSING_REQUIRED_FIELD:
                item["blank"] = rng.choice(["event_id", "user_id", "event_type"])
            elif reason == Reason.INVALID_REFERENCE_KEY:
                item["user_id"] = f"ghost_user_{seq:05d}"
            items.append(item)
    for i, it in enumerate(items):
        it["tie"] = i
    items.sort(key=lambda it: (it["key"], it["tie"]))

    # ---------- 3. serialise rows and compute the answer key for rejects
    first_seen: Dict[str, tuple] = {}
    expected_rejects: List[tuple] = []
    rendered: List[tuple] = []                    # (kind, record dict or None for malformed)
    first_line_no = 2 if fmt == "csv" else 1      # CSV header occupies line 1
    for idx, it in enumerate(items):
        line_no = first_line_no + idx
        kind = it["kind"]
        if kind in ("valid", "dup"):
            content = (it["user_id"], it["event_type"], it["ts"], it["page"])
            if it["event_id"] in first_seen:
                same = first_seen[it["event_id"]] == content
                expected_rejects.append(
                    (line_no, Reason.DUPLICATE_EVENT if same else Reason.CONFLICTING_DUPLICATE_EVENT))
            else:
                first_seen[it["event_id"]] = content
            rendered.append((kind, {"event_id": it["event_id"], "user_id": it["user_id"],
                                    "event_type": it["event_type"], "event_time": _render_time(it["ts"], rng),
                                    "page": it["page"]}))
            continue
        expected_rejects.append((line_no, kind))
        if kind == Reason.MALFORMED_ROW:
            rendered.append((kind, None))
            continue
        record = {"event_id": it["event_id"], "user_id": it["user_id"], "event_type": it["event_type"],
                  "event_time": _render_time(it["ts"], rng), "page": it["page"]}
        if kind in (Reason.MISSING_TIMESTAMP, Reason.INVALID_TIMESTAMP):
            record["event_time"] = it["time_text"]
        elif kind == Reason.MISSING_REQUIRED_FIELD:
            record[it["blank"]] = ""
        rendered.append((kind, record))

    out, exp = Path(out_dir), Path(expected_dir)
    out.mkdir(parents=True, exist_ok=True)
    exp.mkdir(parents=True, exist_ok=True)
    events_path = out / ("events.csv" if fmt == "csv" else "events.jsonl")
    if fmt == "csv":
        with open(events_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(HEADER)
            for kind, rec in rendered:
                if rec is None:                       # malformed: wrong number of fields
                    w.writerow(["evt_short", "user_00001"] if rng.random() < 0.5 else
                               ["evt_long", "user_00001", "click", "2026-01-01T00:00:00Z", "/home", "x", "y"])
                else:
                    w.writerow([("" if rec[c] is None else rec[c]) for c in HEADER])
    else:
        with open(events_path, "w", newline="", encoding="utf-8") as fh:
            for kind, rec in rendered:
                if rec is None:
                    text = rng.choice(['{"event_id": "evt_cut", "user_id": ', "[1, 2, 3]", "not json at all"])
                else:
                    obj = dict(rec)
                    if kind == Reason.MISSING_TIMESTAMP and rng.random() < 0.5:
                        obj.pop("event_time")         # key absent instead of blank/null
                    if kind == Reason.MISSING_REQUIRED_FIELD and rng.random() < 0.5:
                        obj.pop(next(k for k in ("event_id", "user_id", "event_type") if obj[k] == ""))
                    text = json.dumps(obj)
                fh.write(text + "\n")

    with open(out / "users.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["user_id"])
        w.writerows([[u] for u in users])

    with open(exp / "expected_sessions.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["user_id", "session_start", "session_end", "event_count"])
        for s in sorted(truth, key=lambda s: (s["user_id"], s["start"])):
            w.writerow([s["user_id"], _iso_utc(s["start"]), _iso_utc(s["end"]), s["count"]])
    with open(exp / "expected_rejects.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["row_number", "reject_reason"])
        w.writerows(expected_rejects)

    by_reason: Dict[str, int] = {}
    for _, reason in expected_rejects:
        by_reason[reason] = by_reason.get(reason, 0) + 1
    manifest = {"seed": seed, "rows": rows, "format": fmt, "gap_minutes": gap_minutes,
                "users": len(users), "expected_sessions": len(truth), "valid_unique_events": len(real),
                "expected_rejects": len(expected_rejects), "expected_rejects_by_reason": dict(sorted(by_reason.items())),
                "events_file": events_path.as_posix()}
    (exp / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
