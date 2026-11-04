from contextlib import closing
from pathlib import Path
import sqlite3

from scripts.generate_hospital_data import create_tables
from src.auth import AuthStore


PASSWORD = "Test-Only-Password-2026"


def make_hospital(path: Path):
    with closing(sqlite3.connect(path)) as conn, conn:
        create_tables(conn)
        conn.executemany("INSERT INTO departments VALUES (?,?,?,?,?)", [
            (1,"内科","住院科室","张主任",10), (2,"外科","住院科室","李主任",20)])
        conn.executemany("INSERT INTO doctors VALUES (?,?,?,?)", [
            (11,"甲医生",1,"主治医师"), (12,"乙医生",1,"住院医师"), (21,"丙医生",2,"主治医师")])
        conn.executemany("INSERT INTO outpatient_visits VALUES (?,?,?,?,?,?,?)", [
            (1,101,11,1,"2026-06-07",10,"模拟诊断"),
            (2,102,12,1,"2026-06-07",10,"模拟诊断"),
            (3,103,21,2,"2026-06-07",10,"模拟诊断")])
        conn.executemany("INSERT INTO billing_records VALUES (?,?,?,?,?,?,?)", [
            (1,101,1,"2026-06-07","药品","项目",100),
            (2,103,2,"2026-06-07","治疗","项目",900)])
        conn.executemany("INSERT INTO surgery_records VALUES (?,?,?,?,?,?,?,?,?)", [
            (1,101,1,11,"2026-06-07","模拟手术","一级",30,"完成"),
            (2,102,1,12,"2026-06-07","模拟手术","二级",60,"完成"),
            (3,103,2,21,"2026-06-07","模拟手术","三级",90,"完成")])
        conn.executemany("INSERT INTO bed_daily_stats VALUES (?,?,?,?,?)", [
            (1,1,"2026-06-07",10,9), (2,2,"2026-06-07",20,10)])
        conn.executemany("INSERT INTO drg_groups VALUES (?,?,?,?,?,?,?)", [
            ("A","内科病组","内科",100,100,3,"低"), ("B","外科病组","外科",100,100,3,"低")])


def make_accounts(store: AuthStore, hospital: Path):
    store.create_user("director",PASSWORD,"张主任","director",1,hospital)
    store.create_user("director2",PASSWORD,"李主任","director",2,hospital)
    store.create_user("doctor",PASSWORD,"甲医生","doctor",1,hospital,11)
    store.create_user("doctor2",PASSWORD,"乙医生","doctor",1,hospital,12)


def principal_for(store, username):
    return store.get_session(store.authenticate(username, PASSWORD))
