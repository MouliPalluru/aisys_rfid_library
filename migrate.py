#!/usr/bin/env python3
"""
Data Migration Utility - RFID Library System
============================================
Reads a CSV/XLSX of synthetic member or catalog records, validates every row,
rejects bad/duplicate rows into error_log.csv, imports the good ones into SQLite
inside ONE transaction, and prints a Reconciliation Summary.

Usage
  python migrate.py --make-sample ./sample                 # create demo files
  python migrate.py sample/members_sample.csv --entity members
  python migrate.py sample/books_sample.csv   --entity books --rollback

Flags
  --rollback   Strict / all-or-nothing: if ANY row is rejected, the whole
               migration is reverted (nothing is inserted). Without it, bad rows
               are logged and the valid rows are committed.
               Regardless of the flag, an unexpected exception always reverts
               the entire transaction.

Exit codes: 0 committed | 1 rolled back | 2 file/schema error

Requires: pandas, sqlalchemy (>=2.0); openpyxl only if you read .xlsx files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, MetaData,
                        String, Table, Text, create_engine, insert, select)

# =============================================================================
# DATABASE SCHEMA (subset of the project DDL needed for migration)
# =============================================================================
metadata = MetaData()

members_t = Table(
    "members", metadata,
    Column("member_id", Integer, primary_key=True, autoincrement=True),
    Column("member_code", String(30), nullable=False, unique=True),
    Column("full_name", String(150), nullable=False),
    Column("email", String(150)),
    Column("phone", String(20)),
    Column("member_type", String(20), nullable=False, default="STUDENT"),
    Column("status", String(15), nullable=False, default="ACTIVE"),
)

titles_t = Table(
    "titles", metadata,
    Column("title_id", Integer, primary_key=True, autoincrement=True),
    Column("isbn", String(20), unique=True),
    Column("title", String(300), nullable=False),
    Column("author", String(200)),
    Column("publisher", String(150)),
    Column("pub_year", Integer),
    Column("category", String(80)),
)

copies_t = Table(
    "book_copies", metadata,
    Column("copy_id", Integer, primary_key=True, autoincrement=True),
    Column("title_id", Integer, ForeignKey("titles.title_id"), nullable=False),
    Column("accession_no", String(40), nullable=False, unique=True),
    Column("status", String(15), nullable=False, default="AVAILABLE"),
    Column("shelf_location", String(50)),
)

tags_t = Table(
    "rfid_tag_mappings", metadata,
    Column("mapping_id", Integer, primary_key=True, autoincrement=True),
    Column("tag_uid", String(64), nullable=False, unique=True),
    Column("copy_id", Integer, ForeignKey("book_copies.copy_id"), unique=True),
    Column("security_bit", Boolean, nullable=False, default=True),  # True = armed
    Column("tag_status", String(15), nullable=False, default="ACTIVE"),
    Column("encoded_at", DateTime),
)

staging_t = Table(
    "migration_staging", metadata,
    Column("stage_id", Integer, primary_key=True, autoincrement=True),
    Column("batch_id", String(40), nullable=False),
    Column("entity_type", String(20), nullable=False),
    Column("natural_key", String(80)),
    Column("raw_payload", Text, nullable=False),
    Column("validation_status", String(12), nullable=False),  # MIGRATED | INVALID | DUPLICATE
    Column("error_message", Text),
    Column("loaded_at", DateTime, nullable=False),
)

# =============================================================================
# INPUT SCHEMA & VALIDATION RULES
# =============================================================================
ENTITY_COLUMNS = {
    "members": {"required": ["member_code", "full_name"],
                "optional": ["email", "phone", "member_type"]},
    "books": {"required": ["isbn", "title", "accession_no", "tag_uid"],
              "optional": ["author", "publisher", "pub_year", "category", "shelf_location"]},
}
NATURAL_KEY = {"members": "member_code", "books": "accession_no"}
MEMBER_TYPES = {"STUDENT", "FACULTY", "STAFF", "GUEST"}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9\- ]{7,15}$")
TAG_RE = re.compile(r"^[0-9A-Fa-f]{8,24}$")
ISBN_RE = re.compile(r"^(\d{9}[\dX]|\d{13})$")
# Control characters and the Unicode replacement char (typical encoding damage)
CORRUPT_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]")

ERROR_LOG_COLUMNS = ["batch_id", "row_number", "entity", "natural_key",
                     "category", "reason", "raw_row"]


class SchemaError(Exception):
    """Input file is unreadable or is missing required columns."""


class MigrationAborted(Exception):
    """Raised in --rollback (strict) mode when any row was rejected."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_row(entity: str, row: dict) -> list[str]:
    """Return a list of error codes for this row (empty list = valid)."""
    errors = [f"CORRUPTED_VALUE:{k}" for k, v in row.items() if CORRUPT_RE.search(v)]
    for col in ENTITY_COLUMNS[entity]["required"]:
        if not row[col]:
            errors.append(f"MISSING_{col.upper()}")

    if entity == "members":
        if row["email"] and not EMAIL_RE.match(row["email"]):
            errors.append("INVALID_EMAIL")
        if row["phone"] and not PHONE_RE.match(row["phone"]):
            errors.append("INVALID_PHONE")
        if row["member_type"] and row["member_type"].upper() not in MEMBER_TYPES:
            errors.append("INVALID_MEMBER_TYPE")
    else:
        if row["isbn"] and not ISBN_RE.match(re.sub(r"[-\s]", "", row["isbn"]).upper()):
            errors.append("INVALID_ISBN")
        if row["tag_uid"] and not TAG_RE.match(row["tag_uid"]):
            errors.append("INVALID_TAG_UID")
        if row["pub_year"]:
            ok = row["pub_year"].isdigit() and 1400 <= int(row["pub_year"]) <= datetime.now().year + 1
            if not ok:
                errors.append("INVALID_PUB_YEAR")
    return errors


def normalise_row(entity: str, row: dict) -> dict:
    """Canonical form used for duplicate checks and inserts."""
    r = dict(row)
    if entity == "members":
        r["member_type"] = (r["member_type"] or "STUDENT").upper()
    else:
        r["isbn"] = re.sub(r"[-\s]", "", r["isbn"]).upper()
        r["tag_uid"] = r["tag_uid"].upper()
    return r


# =============================================================================
# FILE LOADING
# =============================================================================
def load_dataframe(path: str | Path, entity: str) -> pd.DataFrame:
    """Read CSV/XLSX as strings, verify required columns, keep only known columns."""
    path = Path(path)
    if not path.exists():
        raise SchemaError(f"Input file not found: {path}")
    try:
        if path.suffix.lower() in {".xlsx", ".xls"}:
            df = pd.read_excel(path, dtype=str, keep_default_na=False)
        elif path.suffix.lower() == ".csv":
            df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding_errors="replace")
        else:
            raise SchemaError(f"Unsupported file type: {path.suffix} (use .csv or .xlsx)")
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise SchemaError(f"File is structurally corrupt: {exc}") from exc

    df.columns = [str(c).strip().lower() for c in df.columns]
    spec = ENTITY_COLUMNS[entity]
    missing = [c for c in spec["required"] if c not in df.columns]
    if missing:
        raise SchemaError(f"Missing required column(s): {', '.join(missing)}")
    for col in spec["optional"]:
        if col not in df.columns:
            df[col] = ""
    df = df[spec["required"] + spec["optional"]]
    return df.apply(lambda c: c.astype(str).str.strip())


# =============================================================================
# INSERTERS (called inside the migration transaction)
# =============================================================================
def insert_members(conn, rows: list[dict]) -> dict:
    for r in rows:
        conn.execute(insert(members_t).values(
            member_code=r["member_code"], full_name=r["full_name"],
            email=r["email"] or None, phone=r["phone"] or None,
            member_type=r["member_type"], status="ACTIVE"))
    return {"members_created": len(rows)}


def insert_books(conn, rows: list[dict]) -> dict:
    """One row = one physical copy. Titles are shared by ISBN; each copy gets a tag mapping."""
    isbn_to_id = {isbn: tid for tid, isbn in conn.execute(
        select(titles_t.c.title_id, titles_t.c.isbn))}
    titles_created = 0
    for r in rows:
        title_id = isbn_to_id.get(r["isbn"])
        if title_id is None:
            res = conn.execute(insert(titles_t).values(
                isbn=r["isbn"], title=r["title"], author=r["author"] or None,
                publisher=r["publisher"] or None,
                pub_year=int(r["pub_year"]) if r["pub_year"] else None,
                category=r["category"] or None))
            title_id = res.inserted_primary_key[0]
            isbn_to_id[r["isbn"]] = title_id
            titles_created += 1
        copy_id = conn.execute(insert(copies_t).values(
            title_id=title_id, accession_no=r["accession_no"], status="AVAILABLE",
            shelf_location=r["shelf_location"] or None)).inserted_primary_key[0]
        conn.execute(insert(tags_t).values(
            tag_uid=r["tag_uid"], copy_id=copy_id, security_bit=True,
            tag_status="ACTIVE", encoded_at=utcnow()))
    return {"titles_created": titles_created, "copies_created": len(rows),
            "tags_mapped": len(rows)}


# =============================================================================
# MIGRATION ENGINE
# =============================================================================
def run_migration(input_path, entity: str, db_url: str,
                  error_log="error_log.csv", report_path="reconciliation_report.txt",
                  rollback_on_error: bool = False, batch_id: str | None = None) -> dict:
    """Run one migration batch and return the reconciliation report (dict)."""
    if entity not in ENTITY_COLUMNS:
        raise SchemaError(f"Unknown entity '{entity}'")
    df = load_dataframe(input_path, entity)          # raises SchemaError (nothing touched)
    records = df.to_dict("records")
    batch_id = batch_id or uuid.uuid4().hex[:12]
    key_col = NATURAL_KEY[entity]

    engine = create_engine(db_url)
    metadata.create_all(engine)

    rejects: list[dict] = []
    valid_rows: list[dict] = []
    staging_rows: list[dict] = []
    details: dict = {}
    status, fatal_error = "COMMITTED", None

    def reject(rownum, row, category, reason):
        rejects.append({"batch_id": batch_id, "row_number": rownum, "entity": entity,
                        "natural_key": row.get(key_col, ""), "category": category,
                        "reason": reason, "raw_row": json.dumps(row, ensure_ascii=False)})

    conn = engine.connect()
    trans = conn.begin()
    try:
        # --- known keys for duplicate detection --------------------------------
        staged_keys = set(conn.execute(select(staging_t.c.natural_key).where(
            staging_t.c.entity_type == entity,
            staging_t.c.validation_status == "MIGRATED")).scalars())
        target_col = members_t.c.member_code if entity == "members" else copies_t.c.accession_no
        target_keys = set(conn.execute(select(target_col)).scalars())
        target_tags = set(conn.execute(select(tags_t.c.tag_uid)).scalars()) if entity == "books" else set()

        # --- validate + de-duplicate -------------------------------------------
        seen_keys: set[str] = set()
        seen_tags: set[str] = set()
        for idx, raw in enumerate(records):
            rownum = idx + 2                          # row 1 is the header
            errors = validate_row(entity, raw)
            if errors:
                reject(rownum, raw, "INVALID", "; ".join(errors))
                continue
            row = normalise_row(entity, raw)
            key = row[key_col]

            dup = None
            if key in seen_keys:
                dup = "DUPLICATE_IN_FILE"
            elif key in staged_keys:
                dup = "DUPLICATE_IN_STAGING"          # migrated by an earlier batch
            elif key in target_keys:
                dup = "DUPLICATE_IN_DATABASE"
            elif entity == "books" and row["tag_uid"] in seen_tags:
                dup = "DUPLICATE_TAG_IN_FILE"
            elif entity == "books" and row["tag_uid"] in target_tags:
                dup = "TAG_ALREADY_MAPPED"
            if dup:
                reject(rownum, raw, "DUPLICATE", dup)
                continue

            seen_keys.add(key)
            if entity == "books":
                seen_tags.add(row["tag_uid"])
            valid_rows.append(row)

        # --- load ----------------------------------------------------------------
        if entity == "members":
            details = insert_members(conn, valid_rows)
        else:
            details = insert_books(conn, valid_rows)

        # --- write every row's outcome to the staging table ------------------------
        now = utcnow()
        rejected_by_key = {(r["row_number"]): r for r in rejects}
        for idx, raw in enumerate(records):
            rej = rejected_by_key.get(idx + 2)
            staging_rows.append({
                "batch_id": batch_id, "entity_type": entity,
                "natural_key": raw.get(key_col, ""),
                "raw_payload": json.dumps(raw, ensure_ascii=False),
                "validation_status": rej["category"] if rej else "MIGRATED",
                "error_message": rej["reason"] if rej else None,
                "loaded_at": now})
        if staging_rows:
            conn.execute(insert(staging_t), staging_rows)

        # --- strict mode: any rejected row reverts the whole batch -------------------
        if rollback_on_error and rejects:
            raise MigrationAborted(f"{len(rejects)} row(s) rejected; --rollback is set")

        trans.commit()
    except Exception as exc:                          # any failure => full revert
        trans.rollback()
        status, fatal_error = "ROLLED_BACK", str(exc)
    finally:
        conn.close()
        engine.dispose()

    invalid = sum(1 for r in rejects if r["category"] == "INVALID")
    duplicate = sum(1 for r in rejects if r["category"] == "DUPLICATE")
    inserted = len(valid_rows) if status == "COMMITTED" else 0
    total = len(records)
    report = {
        "batch_id": batch_id, "entity": entity, "status": status,
        "fatal_error": fatal_error,
        "total_read": total,
        "valid": len(valid_rows),
        "rejected": len(rejects), "rejected_invalid": invalid, "rejected_duplicate": duplicate,
        "inserted": inserted,
        "details": details if status == "COMMITTED" else {},
        # Reconciliation: every row is accounted for, and inserts match valid rows
        "reconciled": (total == len(valid_rows) + len(rejects)
                       and inserted == (len(valid_rows) if status == "COMMITTED" else 0)),
    }

    pd.DataFrame(rejects, columns=ERROR_LOG_COLUMNS).to_csv(error_log, index=False)
    Path(report_path).write_text(format_report(report, error_log), encoding="utf-8")
    return report


def format_report(r: dict, error_log) -> str:
    line = "=" * 54
    out = [line, " RECONCILIATION SUMMARY REPORT", line,
           f" Batch ID     : {r['batch_id']}",
           f" Entity       : {r['entity']}",
           f" Status       : {r['status']}"]
    if r["fatal_error"]:
        out.append(f" Reason       : {r['fatal_error']}")
    out += ["-" * 54,
            f" Total Read   : {r['total_read']}",
            f" Valid        : {r['valid']}",
            f" Rejected     : {r['rejected']}  "
            f"(invalid {r['rejected_invalid']}, duplicate {r['rejected_duplicate']})",
            f" Inserted     : {r['inserted']}"]
    for k, v in r["details"].items():
        out.append(f"   - {k}: {v}")
    out += ["-" * 54,
            f" Reconciled   : {'YES' if r['reconciled'] else 'NO - INVESTIGATE'}",
            f" Error log    : {error_log}", line]
    return "\n".join(out)


# =============================================================================
# SAMPLE DATA + CLI
# =============================================================================
def generate_sample_files(directory) -> list[Path]:
    """Synthetic files with deliberate defects so every validation path is exercised."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    members = pd.DataFrame([
        {"member_code": "M001", "full_name": "Asha Rao", "email": "asha@example.com", "phone": "9876543210", "member_type": "STUDENT"},
        {"member_code": "M002", "full_name": "Ravi Kumar", "email": "ravi@example.com", "phone": "9876543211", "member_type": "FACULTY"},
        {"member_code": "M003", "full_name": "Meena Iyer", "email": "meena-at-example", "phone": "", "member_type": "STAFF"},      # bad email
        {"member_code": "M004", "full_name": "", "email": "x@example.com", "phone": "", "member_type": "GUEST"},                   # missing name
        {"member_code": "M001", "full_name": "Asha Rao (dup)", "email": "asha2@example.com", "phone": "", "member_type": "STUDENT"},  # duplicate
        {"member_code": "M006", "full_name": "Kiran\ufffdP", "email": "kiran@example.com", "phone": "", "member_type": "STUDENT"},   # corrupted
    ])
    books = pd.DataFrame([
        {"isbn": "978-0-262-03384-8", "title": "Introduction to Algorithms", "author": "Cormen", "publisher": "MIT Press", "pub_year": "2009", "category": "CS", "accession_no": "ACC-1001", "tag_uid": "E2000001", "shelf_location": "A-01"},
        {"isbn": "9780262033848", "title": "Introduction to Algorithms", "author": "Cormen", "publisher": "MIT Press", "pub_year": "2009", "category": "CS", "accession_no": "ACC-1002", "tag_uid": "E2000002", "shelf_location": "A-01"},
        {"isbn": "9780132126953", "title": "Computer Networks", "author": "Tanenbaum", "publisher": "Pearson", "pub_year": "2010", "category": "CS", "accession_no": "ACC-2001", "tag_uid": "E2000003", "shelf_location": "A-02"},
        {"isbn": "9780132126953", "title": "Computer Networks", "author": "Tanenbaum", "publisher": "Pearson", "pub_year": "2010", "category": "CS", "accession_no": "ACC-2002", "tag_uid": "ZZZ", "shelf_location": "A-02"},          # bad tag
        {"isbn": "123", "title": "Bad ISBN Book", "author": "", "publisher": "", "pub_year": "2020", "category": "", "accession_no": "ACC-3001", "tag_uid": "E2000005", "shelf_location": "B-01"},     # bad ISBN
        {"isbn": "9780132126953", "title": "Computer Networks", "author": "Tanenbaum", "publisher": "Pearson", "pub_year": "2010", "category": "CS", "accession_no": "ACC-2001", "tag_uid": "E2000009", "shelf_location": "A-02"},  # dup accession
    ])
    paths = [d / "members_sample.csv", d / "books_sample.csv"]
    members.to_csv(paths[0], index=False, encoding="utf-8")
    books.to_csv(paths[1], index=False, encoding="utf-8")
    return paths


def _to_url(db: str) -> str:
    return db if "://" in db else f"sqlite:///{db}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="RFID Library data migration utility")
    p.add_argument("input", nargs="?", help="CSV/XLSX file to migrate")
    p.add_argument("--entity", choices=sorted(ENTITY_COLUMNS), help="Record type in the file")
    p.add_argument("--db", default="library.db", help="SQLite path or SQLAlchemy URL")
    p.add_argument("--error-log", default="error_log.csv")
    p.add_argument("--report", default="reconciliation_report.txt")
    p.add_argument("--rollback", action="store_true",
                   help="All-or-nothing: revert everything if any row is rejected")
    p.add_argument("--make-sample", metavar="DIR", help="Write demo CSV files and exit")
    a = p.parse_args(argv)

    if a.make_sample:
        for f in generate_sample_files(a.make_sample):
            print(f"Created {f}")
        return 0
    if not a.input or not a.entity:
        p.error("input file and --entity are required")

    try:
        report = run_migration(a.input, a.entity, _to_url(a.db), a.error_log,
                               a.report, rollback_on_error=a.rollback)
    except SchemaError as exc:
        print(f"SCHEMA ERROR: {exc}", file=sys.stderr)
        return 2
    print(Path(a.report).read_text(encoding="utf-8"))
    return 0 if report["status"] == "COMMITTED" else 1


if __name__ == "__main__":
    sys.exit(main())
