"""Reading input files (CSV or JSON Lines) into RawRecord objects.

Responsibilities:
  * file-level checks  -> raise SchemaError (the whole file is unusable)
  * row-level problems -> return a Reject (malformed_row), keep going
Row numbers are 1-based physical line numbers (the CSV header is line 1),
so a reject can be located by opening the file at that line.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from .models import RawRecord, Reject
from .schema import CANONICAL_COLUMNS, REQUIRED_COLUMNS, Reason, SchemaError


@dataclass
class IngestResult:
    records: List[RawRecord] = field(default_factory=list)
    rejects: List[Reject] = field(default_factory=list)
    extra_columns: Set[str] = field(default_factory=set)
    rows_read: int = 0  # records examined (good + malformed); blank lines are not counted


def _norm(name: str, column_map: Dict[str, str]) -> str:
    key = str(name).strip().lstrip("\ufeff").lower()
    return column_map.get(key, key)


def _lower_map(column_map: Optional[Dict[str, str]]) -> Dict[str, str]:
    return {str(k).strip().lower(): str(v).strip().lower() for k, v in (column_map or {}).items()}


def _check_header(columns: List[str], path: str) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise SchemaError(f"schema_mismatch: {path} is missing required column(s) {missing}; found {columns}")
    duplicates = sorted({c for c in columns if columns.count(c) > 1})
    if duplicates:
        raise SchemaError(f"schema_mismatch: {path} has duplicate column(s) after mapping: {duplicates}")


def read_csv(path: str, column_map: Optional[Dict[str, str]] = None) -> IngestResult:
    cmap = _lower_map(column_map)
    result = IngestResult()
    source = Path(path).as_posix()
    try:
        # utf-8-sig silently drops the byte-order mark that Excel on Windows adds.
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                return result  # zero-byte file == empty batch
            columns = [_norm(h, cmap) for h in header]
            _check_header(columns, source)
            result.extra_columns = {c for c in columns if c not in CANONICAL_COLUMNS}
            for row in reader:
                if not row:  # blank line
                    continue
                line_no = reader.line_num
                result.rows_read += 1
                if len(row) != len(columns):
                    result.rejects.append(
                        Reject(source, line_no, Reason.MALFORMED_ROW,
                               f"expected {len(columns)} fields, found {len(row)}",
                               json.dumps(row, ensure_ascii=False))
                    )
                    continue
                data = dict(zip(columns, row))
                result.records.append(
                    RawRecord(source, line_no, data, json.dumps(dict(zip(header, row)), ensure_ascii=False))
                )
    except UnicodeDecodeError as exc:
        raise SchemaError(f"not_valid_utf8: {source} is not UTF-8 text ({exc.reason})")
    except csv.Error as exc:
        raise SchemaError(f"csv_parse_error: {source}: {exc}")
    return result


def read_jsonl(path: str, column_map: Optional[Dict[str, str]] = None) -> IngestResult:
    cmap = _lower_map(column_map)
    result = IngestResult()
    source = Path(path).as_posix()
    keys_seen: Set[str] = set()
    objects = 0
    try:
        with open(path, encoding="utf-8-sig") as fh:
            for line_no, line in enumerate(fh, start=1):
                text = line.strip()
                if not text:
                    continue
                result.rows_read += 1
                try:
                    obj = json.loads(text)
                except ValueError as exc:
                    result.rejects.append(Reject(source, line_no, Reason.MALFORMED_ROW, f"invalid JSON: {exc}", text))
                    continue
                if not isinstance(obj, dict):
                    result.rejects.append(
                        Reject(source, line_no, Reason.MALFORMED_ROW, "line is not a JSON object", text))
                    continue
                if any(isinstance(v, (dict, list)) for v in obj.values()):
                    result.rejects.append(
                        Reject(source, line_no, Reason.MALFORMED_ROW, "nested objects/arrays are not supported", text))
                    continue
                data = {_norm(k, cmap): (None if v is None else str(v)) for k, v in obj.items()}
                objects += 1
                keys_seen.update(data)
                result.records.append(RawRecord(source, line_no, data, text))
    except UnicodeDecodeError as exc:
        raise SchemaError(f"not_valid_utf8: {source} is not UTF-8 text ({exc.reason})")
    if objects:
        missing = [c for c in REQUIRED_COLUMNS if c not in keys_seen]
        if missing:
            raise SchemaError(
                f"schema_mismatch: {source} has no record containing required field(s) {missing}; "
                f"keys seen: {sorted(keys_seen)}")
    result.extra_columns = {c for c in keys_seen if c not in CANONICAL_COLUMNS}
    return result


def read_source(path: str, column_map: Optional[Dict[str, str]] = None) -> IngestResult:
    """Pick a reader by file extension."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"input_not_found: {path}")
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return read_csv(path, column_map)
    if ext in (".jsonl", ".ndjson"):
        return read_jsonl(path, column_map)
    raise SchemaError(f"unsupported_file_type: {path} (use .csv, .jsonl or .ndjson)")


def read_user_ids(path: str) -> List[str]:
    """Read the reference users file (CSV with a user_id column)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"input_not_found: {path}")
    ids: List[str] = []
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                return ids
            cols = [str(h).strip().lower() for h in header]
            if "user_id" not in cols:
                raise SchemaError(f"schema_mismatch: users file {path} must have a user_id column; found {cols}")
            idx = cols.index("user_id")
            for row in reader:
                if len(row) > idx and row[idx].strip():
                    ids.append(row[idx].strip())
    except UnicodeDecodeError as exc:
        raise SchemaError(f"not_valid_utf8: {path} is not UTF-8 text ({exc.reason})")
    return ids
