"""Produce a read-only, scoped database containing only this user's authorized rows.

The original database is never attached to the returned connection. Even raw SQL,
joins, subqueries or main-qualified names cannot reach another department's rows.
This in-memory snapshot approach targets the project's small simulated dataset.
"""
from contextlib import closing, contextmanager
from functools import lru_cache
from pathlib import Path
import sqlite3

from .auth import Principal

DEPARTMENT_TABLES = ("departments", "doctors", "outpatient_visits", "inpatient_records",
                     "billing_records", "bed_daily_stats", "surgery_records", "case_drg_records")
DOCTOR_COLUMNS = {
    "departments": ("department_id", "department_name"),
    "doctors": ("doctor_id", "department_id", "doctor_name", "title"),
    "outpatient_visits": ("visit_id", "doctor_id", "department_id", "visit_date"),
    "surgery_records": ("surgery_id", "doctor_id", "department_id", "surgery_date", "surgery_level", "duration_minutes"),
}


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@lru_cache(maxsize=32)
def _scoped_snapshot(path: str, version: tuple[int, int, int], principal: Principal) -> bytes:
    with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)) as source, \
            closing(sqlite3.connect(":memory:")) as target:
        source.row_factory = sqlite3.Row
        department = source.execute("SELECT 1 FROM departments WHERE department_id=?", (principal.department_id,)).fetchone()
        if department is None:
            raise PermissionError("账号绑定的科室不存在，请联系管理员。")
        if principal.role == "doctor" and source.execute(
            "SELECT 1 FROM doctors WHERE doctor_id=? AND department_id=?",
            (principal.doctor_id, principal.department_id),
        ).fetchone() is None:
            raise PermissionError("账号与医生档案不匹配，请联系管理员。")
        tables = DEPARTMENT_TABLES + ("drg_groups", "drg_risk_rules") if principal.role == "director" else tuple(DOCTOR_COLUMNS)
        available = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in tables:
            if table not in available:
                continue
            info = source.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
            if principal.role == "doctor":
                info = [r for r in info if r[1] in DOCTOR_COLUMNS[table]]
            columns = ','.join(_quote(r[1]) for r in info)
            if table == "drg_risk_rules":
                condition, params = "1=1", ()
            elif table == "drg_groups":
                condition, params = "department_name=(SELECT department_name FROM departments WHERE department_id=?)", (principal.department_id,)
            elif principal.role == "doctor" and table != "departments":
                condition, params = "department_id=? AND doctor_id=?", (principal.department_id, principal.doctor_id)
            else:
                condition, params = "department_id=?", (principal.department_id,)
            # Values are bound; names and types come exclusively from the trusted schema.
            schema = ','.join(f"{_quote(r[1])} {r[2]}" for r in info)
            target.execute(f"CREATE TABLE {_quote(table)} ({schema})")
            rows = source.execute(f"SELECT {columns} FROM {_quote(table)} WHERE {condition}", params).fetchall()
            target.executemany(f"INSERT INTO {_quote(table)} VALUES ({','.join('?' for _ in info)})", rows)
        target.commit()
        return target.serialize()


def _readonly_authorizer(action, arg1, arg2, database, source):
    return sqlite3.SQLITE_OK if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE} else sqlite3.SQLITE_DENY


@contextmanager
def hospital_connection(path: str | Path, principal: Principal | None = None):
    path = Path(path).resolve()
    if principal is None:
        # Offline scripts retain access to the simulated dataset; web entry points
        # always supply an authenticated principal.
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    else:
        stat = path.stat()
        wal = Path(str(path) + "-wal")
        version = (stat.st_mtime_ns, stat.st_size, wal.stat().st_mtime_ns if wal.exists() else 0)
        conn = sqlite3.connect(":memory:")
        try:
            conn.deserialize(_scoped_snapshot(str(path), version, principal))
        except BaseException:
            conn.close()
            raise
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.set_authorizer(_readonly_authorizer)
        yield conn
    finally:
        conn.close()
