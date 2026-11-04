"""Administrator-only local CLI; never exposed as public registration."""
from __future__ import annotations
import argparse
from contextlib import closing
import getpass
from pathlib import Path
import secrets
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.auth import AuthStore


def main():
    parser = argparse.ArgumentParser(description="医管系统账号管理（仅在服务器或本地终端操作）")
    parser.add_argument("--auth-db", type=Path, default=None)
    parser.add_argument("--hospital-db", type=Path, default=ROOT / "data/hospital.db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="首次创建内科主任和一位医生的演示账号，生成随机密码")
    create = commands.add_parser("create")
    create.add_argument("--username", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", choices=["director", "doctor"], required=True)
    create.add_argument("--department-id", type=int, required=True)
    create.add_argument("--doctor-id", type=int)
    reset = commands.add_parser("reset-password")
    reset.add_argument("username")
    disable = commands.add_parser("disable")
    disable.add_argument("username")
    commands.add_parser("list-bindings", help="列出可用于绑定账号的科室与医生档案")
    args = parser.parse_args()
    store = AuthStore(args.auth_db)
    try:
        if args.command == "demo":
            if store.has_users():
                parser.error("已有账号，未创建或覆盖任何演示账号。请用 create 新增或 reset-password 重置。")
            with closing(sqlite3.connect(args.hospital_db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                row = conn.execute("""SELECT d.department_id,d.department_name,d.director_name,
                    doc.doctor_id,doc.doctor_name FROM departments d JOIN doctors doc USING(department_id)
                    ORDER BY d.department_id,doc.doctor_id LIMIT 1""").fetchone()
            if not row:
                parser.error("没有可绑定的模拟医生档案。")
            for username, name, role, doctor_id in [("director", row[2], "director", None), ("doctor", row[4], "doctor", row[3])]:
                password = secrets.token_urlsafe(12)
                store.create_user(username, password, name, role, row[0], args.hospital_db, doctor_id)
                print(f"账号：{username} | 密码：{password} | 姓名：{name} | 角色：{'主任' if role == 'director' else '医生'} | 科室：{row[1]}")
            print("请妥善保存以上密码。登录页面不能自行选择或修改角色。")
        elif args.command == "create":
            password = getpass.getpass("设置密码（至少6位）：")
            if password != getpass.getpass("再次输入密码："):
                parser.error("两次密码不一致。")
            store.create_user(args.username, password, args.name, args.role, args.department_id, args.hospital_db, args.doctor_id)
            print("账号已创建。")
        elif args.command == "reset-password":
            password = getpass.getpass("新密码（至少6位）：")
            if password != getpass.getpass("再次输入密码："):
                parser.error("两次密码不一致。")
            store.reset_password(args.username, password)
            print("密码已更新；该账号的所有旧登录状态已失效。")
        elif args.command == "disable":
            store.disable_user(args.username)
            print("账号已停用，旧登录状态已失效。")
        else:
            with closing(sqlite3.connect(args.hospital_db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                for row in conn.execute("SELECT department_id,department_name FROM departments"):
                    print("科室", *row)
                for row in conn.execute("SELECT doctor_id,department_id,doctor_name FROM doctors"):
                    print("医生", *row)
    except (ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
