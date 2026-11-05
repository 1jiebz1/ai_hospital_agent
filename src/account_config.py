"""Administrator-controlled credentials from a private local file or cloud Secrets."""
from contextlib import closing
import hmac
from pathlib import Path
import secrets
import sqlite3
import tomllib

from .auth import Principal, _hash_password, _valid_password


CONFIG_ERROR = "账号配置无效，请检查账号密码配置文件；密码至少 6 位，两个账号不能重名。"


def load_account_file(path):
    try:
        config = tomllib.loads(Path(path).read_text(encoding="utf-8-sig")).get("accounts")
        if not isinstance(config, dict) or not config:
            raise ValueError
        return config
    except (ValueError, OSError):
        raise ValueError(CONFIG_ERROR) from None


def apply_account_config(store, config, hospital_db):
    """Apply both slots atomically; stable bindings preserve identity and data scope."""
    if not config:
        return
    try:
        if set(config) - {"director", "doctor"}:
            raise ValueError
        entries = []
        for role, settings in config.items():
            username = settings["username"].strip().lower()
            password = settings["password"]
            if not username or len(username) > 80 or not isinstance(password, str):
                raise ValueError
            _valid_password(password)
            entries.append((role, username, password))
        if len({entry[1] for entry in entries}) != len(entries):
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError(CONFIG_ERROR) from None

    with closing(sqlite3.connect(Path(hospital_db).resolve().as_uri() + "?mode=ro", uri=True)) as hospital:
        default = hospital.execute("""SELECT d.department_id,d.department_name,d.director_name,
            doc.doctor_id,doc.doctor_name FROM departments d JOIN doctors doc USING(department_id)
            ORDER BY d.department_id,doc.doctor_id LIMIT 1""").fetchone()
    if default is None:
        raise ValueError("没有可绑定的模拟科室和医生。")
    try:
        with closing(store._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE IF NOT EXISTS account_config_bindings (
                slot TEXT PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE)""")
            for role, username, password in entries:
                user = conn.execute("""SELECT u.* FROM users u JOIN account_config_bindings b
                    USING(user_id) WHERE b.slot=?""", (role,)).fetchone()
                if user is None:
                    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
                if user is None:
                    # Existing unmanaged identities require explicit adoption, never a duplicate privileged account.
                    if conn.execute("SELECT 1 FROM users WHERE role=?", (role,)).fetchone():
                        raise ValueError(CONFIG_ERROR)
                    doctor_id = default[3] if role == "doctor" else None
                    display_name = default[4] if role == "doctor" else default[2]
                    Principal(1, username, display_name, role, default[0], default[1], doctor_id)
                    salt = secrets.token_hex(16)
                    cursor = conn.execute("""INSERT INTO users
                        (username,display_name,role,department_id,department_name,doctor_id,salt,password_hash)
                        VALUES (?,?,?,?,?,?,?,?)""", (username, display_name, role, default[0], default[1],
                                                    doctor_id, salt, _hash_password(password, salt)))
                    user_id = cursor.lastrowid
                else:
                    if user["role"] != role:
                        raise ValueError(CONFIG_ERROR)
                    user_id = user["user_id"]
                    changed = user["username"] != username or not hmac.compare_digest(
                        user["password_hash"], _hash_password(password, user["salt"]))
                    if changed:
                        salt = secrets.token_hex(16)
                        conn.execute("UPDATE users SET username=?,salt=?,password_hash=? WHERE user_id=?",
                                     (username, salt, _hash_password(password, salt), user_id))
                        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                        conn.execute("DELETE FROM attempts WHERE username IN (?,?)", (user["username"], username))
                conn.execute("INSERT OR IGNORE INTO account_config_bindings VALUES (?,?)", (role, user_id))
    except sqlite3.IntegrityError:
        raise ValueError(CONFIG_ERROR) from None
