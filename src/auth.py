"""Local account authentication. Roles and scope are assigned by an administrator."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time

ROOT = Path(__file__).resolve().parents[1]
PASSWORD_ROUNDS = 310_000
SESSION_SECONDS = 8 * 60 * 60
LOCK_SECONDS = 5 * 60


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    display_name: str
    role: str
    department_id: int
    department_name: str
    doctor_id: int | None = None

    def __post_init__(self):
        if self.role not in {"director", "doctor"} or self.department_id <= 0:
            raise ValueError("账号角色或科室无效。")
        if self.role == "doctor" and (self.doctor_id is None or self.doctor_id <= 0):
            raise ValueError("医生账号必须绑定医生档案。")

    @property
    def role_label(self) -> str:
        return "科室主任" if self.role == "director" else "医生"

    def require_director(self) -> None:
        if self.role != "director":
            raise PermissionError("该功能仅供科室主任使用。")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PASSWORD_ROUNDS
    ).hex()


def _valid_password(password: str) -> None:
    if not 6 <= len(password) <= 256:
        raise ValueError("密码长度须为 6 至 256 个字符。")


class AuthStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("HOSPITAL_AUTH_DB", str(ROOT / "data/auth.db")))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL, role TEXT NOT NULL,
                    department_id INTEGER NOT NULL, department_name TEXT NOT NULL,
                    doctor_id INTEGER, salt TEXT NOT NULL, password_hash TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    username TEXT PRIMARY KEY, failures INTEGER NOT NULL,
                    locked_until REAL NOT NULL DEFAULT 0, updated_at REAL NOT NULL
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def has_users(self) -> bool:
        with closing(self._connect()) as conn:
            return bool(conn.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def create_user(self, username: str, password: str, display_name: str, role: str,
                    department_id: int, hospital_db: str | Path,
                    doctor_id: int | None = None) -> None:
        username = username.strip().lower()
        if not username or len(username) > 80 or not display_name.strip():
            raise ValueError("请填写有效账号和姓名。")
        _valid_password(password)
        with closing(sqlite3.connect(Path(hospital_db).resolve().as_uri() + "?mode=ro", uri=True)) as hospital:
            department = hospital.execute(
                "SELECT department_name FROM departments WHERE department_id=?", (department_id,)
            ).fetchone()
            if department is None:
                raise ValueError("绑定科室不存在。")
            if role == "doctor" and hospital.execute(
                "SELECT 1 FROM doctors WHERE doctor_id=? AND department_id=?", (doctor_id, department_id)
            ).fetchone() is None:
                raise ValueError("医生档案不存在或不属于所选科室。")
        Principal(1, username, display_name, role, department_id, department[0], doctor_id)
        salt = secrets.token_hex(16)
        with closing(self._connect()) as conn, conn:
            conn.execute("""INSERT INTO users
                (username,display_name,role,department_id,department_name,doctor_id,salt,password_hash)
                VALUES (?,?,?,?,?,?,?,?)""",
                (username, display_name.strip(), role, department_id, department[0], doctor_id,
                 salt, _hash_password(password, salt)))

    def authenticate(self, username: str, password: str, now: float | None = None) -> str | None:
        username = username.strip().lower()[:80]
        now = time.time() if now is None else now
        with closing(self._connect()) as conn, conn:
            # Serialize the check/update so simultaneous attempts cannot bypass throttling.
            conn.execute("BEGIN IMMEDIATE")
            attempt = conn.execute("SELECT * FROM attempts WHERE username=?", (username,)).fetchone()
            if attempt and attempt["locked_until"] > now:
                return None
            user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            salt = user["salt"] if user else "00" * 16
            actual = _hash_password(password[:257], salt)
            valid = bool(user and user["active"] and hmac.compare_digest(actual, user["password_hash"]))
            if not valid:
                failures = attempt["failures"] if attempt and now - attempt["updated_at"] < LOCK_SECONDS else 0
                failures += 1
                conn.execute("INSERT OR REPLACE INTO attempts VALUES (?,?,?,?)",
                             (username, failures, now + LOCK_SECONDS if failures >= 5 else 0, now))
                return None
            conn.execute("DELETE FROM attempts WHERE username=?", (username,))
            conn.execute("DELETE FROM attempts WHERE updated_at<?", (now - LOCK_SECONDS,))
            conn.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO sessions VALUES (?,?,?)",
                         (hashlib.sha256(token.encode()).hexdigest(), user["user_id"], now + SESSION_SECONDS))
            return token

    def get_session(self, token: str | None, now: float | None = None) -> Principal | None:
        if not token:
            return None
        now = time.time() if now is None else now
        with closing(self._connect()) as conn:
            row = conn.execute("""SELECT u.* FROM users u JOIN sessions s USING(user_id)
                WHERE s.token_hash=? AND s.expires_at>? AND u.active=1""",
                (hashlib.sha256(token.encode()).hexdigest(), now)).fetchone()
        if row is None:
            return None
        return Principal(**{key: row[key] for key in Principal.__dataclass_fields__})

    def logout(self, token: str | None) -> None:
        if token:
            with closing(self._connect()) as conn, conn:
                conn.execute("DELETE FROM sessions WHERE token_hash=?",
                             (hashlib.sha256(token.encode()).hexdigest(),))

    def reset_password(self, username: str, password: str) -> None:
        _valid_password(password)
        salt = secrets.token_hex(16)
        with closing(self._connect()) as conn, conn:
            user = conn.execute("SELECT user_id FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
            if user is None:
                raise ValueError("账号不存在。")
            conn.execute("UPDATE users SET salt=?,password_hash=? WHERE user_id=?",
                         (salt, _hash_password(password, salt), user[0]))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user[0],))
            conn.execute("DELETE FROM attempts WHERE username=?", (username.strip().lower(),))

    def disable_user(self, username: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE users SET active=0 WHERE username=?", (username.strip().lower(),))
            conn.execute("DELETE FROM sessions WHERE user_id IN (SELECT user_id FROM users WHERE active=0)")

    def set_credentials(self, username: str, new_username: str, password: str) -> None:
        """Administrator operation: rename/reset an account without changing scope."""
        _valid_password(password)
        username, new_username = username.strip().lower(), new_username.strip().lower()
        if not new_username or len(new_username) > 80:
            raise ValueError("请填写有效账号。")
        salt = secrets.token_hex(16)
        with closing(self._connect()) as conn, conn:
            user = conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
            if user is None:
                raise ValueError("账号不存在。")
            conn.execute("UPDATE users SET username=?,salt=?,password_hash=? WHERE user_id=?",
                         (new_username,salt,_hash_password(password,salt),user[0]))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user[0],))
            conn.execute("DELETE FROM attempts WHERE username IN (?,?)", (username,new_username))


def allowed_pages(principal: Principal) -> tuple[str, ...]:
    if principal.role == "doctor":
        return ("我的工作台", "个人工作量", "智能问答", "医管知识库")
    return ("运营总览", "浮窗问答", "智能问答", "趋势分析", "科室绩效", "医保控费观察", "运营简报", "医管知识库")


def require_page(principal: Principal, page: str) -> None:
    if page not in allowed_pages(principal):
        raise PermissionError("当前账号无权访问此页面。")
