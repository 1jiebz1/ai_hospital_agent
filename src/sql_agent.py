from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from .analysis import analyze_metric_rows
from .sql_guard import add_default_limit, validate_select_sql
from .access import hospital_connection
from .auth import Principal


FIXED_TODAY = date(2026, 6, 7)


@dataclass
class QueryResult:
    question: str
    sql: str
    rows: list[dict]
    analysis: list[str]
    route_note: str = "deterministic-template"


class HospitalSQLAgent:
    def __init__(self, db_path: str | Path | None = None, schema_path: str | Path | None = None,
                 principal: Principal | None = None):
        load_dotenv()
        self.db_path = Path(db_path or os.getenv("DATABASE_PATH", "data/hospital.db"))
        self.schema_path = Path(schema_path or os.getenv("SCHEMA_PATH", "data/hospital_schema.json"))
        self.schema = self._load_schema()
        self.principal = principal

    def _load_schema(self) -> dict:
        if self.schema_path.exists():
            return json.loads(self.schema_path.read_text(encoding="utf-8"))
        return {}

    @staticmethod
    def _month_range(question: str) -> tuple[str, str]:
        month_match = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", question)
        if month_match:
            year = int(month_match.group(1))
            month = int(month_match.group(2))
        elif "上月" in question:
            year, month = 2026, 5
        else:
            year, month = FIXED_TODAY.year, FIXED_TODAY.month

        start = date(year, month, 1)
        end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        return start.isoformat(), end.isoformat()

    @staticmethod
    def _recent_days_range(question: str) -> tuple[str, str]:
        match = re.search(r"最近\s*(\d+)\s*天", question)
        days = int(match.group(1)) if match else 7
        start = FIXED_TODAY - timedelta(days=days - 1)
        return start.isoformat(), (FIXED_TODAY + timedelta(days=1)).isoformat()

    def generate_sql(self, question: str) -> str:
        start, end = self._month_range(question)
        recent_start, recent_end = self._recent_days_range(question)

        if "床位" in question and "床位周转" not in question and "病床周转" not in question:
            threshold = 90 if "90" in question or "紧张" in question or "异常" in question else 0
            having = f"HAVING avg_bed_occupancy_rate >= {threshold}" if threshold else ""
            return f"""
SELECT d.department_name,
       ROUND(AVG(b.occupied_beds * 100.0 / NULLIF(b.open_beds, 0)), 2) AS avg_bed_occupancy_rate,
       ROUND(MAX(b.occupied_beds * 100.0 / NULLIF(b.open_beds, 0)), 2) AS max_bed_occupancy_rate,
       COUNT(*) AS stat_days
FROM bed_daily_stats b
JOIN departments d ON b.department_id = d.department_id
WHERE b.stat_date >= '{recent_start}' AND b.stat_date < '{recent_end}'
GROUP BY d.department_name
{having}
ORDER BY avg_bed_occupancy_rate DESC
"""

        if "药占比" in question or ("药品" in question and "占比" in question):
            return f"""
SELECT d.department_name,
       ROUND(SUM(CASE WHEN b.item_type = '药品' THEN b.amount ELSE 0 END), 2) AS drug_income,
       ROUND(SUM(b.amount), 2) AS total_income,
       ROUND(SUM(CASE WHEN b.item_type = '药品' THEN b.amount ELSE 0 END) * 100.0 / NULLIF(SUM(b.amount), 0), 2) AS drug_ratio
FROM billing_records b
JOIN departments d ON b.department_id = d.department_id
WHERE b.bill_date >= '{start}' AND b.bill_date < '{end}'
GROUP BY d.department_name
ORDER BY drug_ratio DESC
"""

        if "医疗服务收入占比" in question:
            return f"""
SELECT d.department_name,
       ROUND(SUM(CASE WHEN b.item_type IN ('治疗', '手术', '床位', '挂号') THEN b.amount ELSE 0 END), 2) AS medical_service_income,
       ROUND(SUM(b.amount), 2) AS total_income,
       ROUND(SUM(CASE WHEN b.item_type IN ('治疗', '手术', '床位', '挂号') THEN b.amount ELSE 0 END) * 100.0 / NULLIF(SUM(b.amount), 0), 2) AS medical_service_income_ratio
FROM billing_records b
JOIN departments d ON b.department_id = d.department_id
WHERE b.bill_date >= '{start}' AND b.bill_date < '{end}'
GROUP BY d.department_name
ORDER BY medical_service_income_ratio DESC
"""

        item_ratio_map = {
            "耗材": "耗材",
            "检查": "检查",
            "检验": "检验",
            "治疗": "治疗",
            "手术": "手术",
        }
        for keyword, item_type in item_ratio_map.items():
            if keyword in question and "占比" in question:
                return f"""
SELECT d.department_name,
       ROUND(SUM(CASE WHEN b.item_type = '{item_type}' THEN b.amount ELSE 0 END), 2) AS item_income,
       ROUND(SUM(b.amount), 2) AS total_income,
       ROUND(SUM(CASE WHEN b.item_type = '{item_type}' THEN b.amount ELSE 0 END) * 100.0 / NULLIF(SUM(b.amount), 0), 2) AS item_ratio
FROM billing_records b
JOIN departments d ON b.department_id = d.department_id
WHERE b.bill_date >= '{start}' AND b.bill_date < '{end}'
GROUP BY d.department_name
ORDER BY item_ratio DESC
"""

        if "收入结构" in question or ("收入" in question and "占比" in question):
            return f"""
SELECT item_type,
       ROUND(SUM(amount), 2) AS amount,
       ROUND(SUM(amount) * 100.0 / (SELECT SUM(amount) FROM billing_records WHERE bill_date >= '{start}' AND bill_date < '{end}'), 2) AS ratio
FROM billing_records
WHERE bill_date >= '{start}' AND bill_date < '{end}'
GROUP BY item_type
ORDER BY amount DESC
"""

        if "收入" in question or "收费" in question:
            return f"""
SELECT d.department_name,
       ROUND(SUM(b.amount), 2) AS total_income,
       COUNT(*) AS bill_count
FROM billing_records b
JOIN departments d ON b.department_id = d.department_id
WHERE b.bill_date >= '{start}' AND b.bill_date < '{end}'
GROUP BY d.department_name
ORDER BY total_income DESC
"""

        if "床位周转" in question or "病床周转" in question:
            return f"""
WITH discharged AS (
    SELECT department_id, COUNT(*) AS discharged_count
    FROM inpatient_records
    WHERE discharge_date >= '{start}' AND discharge_date < '{end}'
      AND status = '已出院'
    GROUP BY department_id
),
beds AS (
    SELECT department_id, ROUND(AVG(open_beds), 2) AS avg_open_beds
    FROM bed_daily_stats
    WHERE stat_date >= '{start}' AND stat_date < '{end}'
    GROUP BY department_id
)
SELECT d.department_name,
       COALESCE(dis.discharged_count, 0) AS discharged_count,
       beds.avg_open_beds,
       ROUND(COALESCE(dis.discharged_count, 0) * 1.0 / NULLIF(beds.avg_open_beds, 0), 2) AS bed_turnover_times
FROM departments d
LEFT JOIN discharged dis ON d.department_id = dis.department_id
LEFT JOIN beds ON d.department_id = beds.department_id
WHERE d.open_beds > 0
ORDER BY bed_turnover_times DESC
"""

        if "医生" in question:
            return f"""
SELECT doc.doctor_name,
       d.department_name,
       doc.title,
       COUNT(v.visit_id) AS visit_count
FROM outpatient_visits v
JOIN doctors doc ON v.doctor_id = doc.doctor_id
JOIN departments d ON v.department_id = d.department_id
WHERE v.visit_date >= '{recent_start}' AND v.visit_date < '{recent_end}'
GROUP BY doc.doctor_name, d.department_name, doc.title
ORDER BY visit_count DESC
"""

        if "手术" in question:
            return f"""
SELECT d.department_name,
       s.surgery_level,
       COUNT(s.surgery_id) AS surgery_count,
       ROUND(AVG(s.duration_minutes), 1) AS avg_duration_minutes
FROM surgery_records s
JOIN departments d ON s.department_id = d.department_id
WHERE s.surgery_date >= '{start}' AND s.surgery_date < '{end}'
GROUP BY d.department_name, s.surgery_level
ORDER BY surgery_count DESC
"""

        if "平均住院日" in question or "住院日" in question:
            return f"""
SELECT d.department_name,
       ROUND(AVG(i.bed_days), 2) AS avg_length_of_stay,
       COUNT(*) AS discharged_count
FROM inpatient_records i
JOIN departments d ON i.department_id = d.department_id
WHERE i.discharge_date >= '{start}' AND i.discharge_date < '{end}'
  AND i.status = '已出院'
GROUP BY d.department_name
ORDER BY avg_length_of_stay DESC
"""

        if "住院" in question or "出院" in question:
            return f"""
SELECT d.department_name,
       COUNT(i.inpatient_id) AS inpatient_count,
       SUM(CASE WHEN i.status = '已出院' THEN 1 ELSE 0 END) AS discharged_count,
       ROUND(SUM(i.total_cost), 2) AS inpatient_total_cost
FROM inpatient_records i
JOIN departments d ON i.department_id = d.department_id
WHERE i.admission_date >= '{start}' AND i.admission_date < '{end}'
GROUP BY d.department_name
ORDER BY inpatient_count DESC
"""

        return f"""
SELECT d.department_name,
       COUNT(v.visit_id) AS visit_count
FROM outpatient_visits v
JOIN departments d ON v.department_id = d.department_id
WHERE v.visit_date >= '{start}' AND v.visit_date < '{end}'
GROUP BY d.department_name
ORDER BY visit_count DESC
"""

    def execute_sql(self, sql: str, limit: int = 10) -> list[dict]:
        safe_sql = add_default_limit(validate_select_sql(sql), limit=limit)
        with hospital_connection(self.db_path, self.principal) as conn:
            cursor = conn.execute(safe_sql)
            return [dict(row) for row in cursor.fetchall()]

    def ask(self, question: str, limit: int = 10) -> QueryResult:
        if self.principal and self.principal.role == "doctor":
            if any(word in question for word in ("收入", "费用", "收费", "医保", "床位", "绩效", "住院", "药占比", "耗材", "报告", "简报")):
                raise PermissionError("医生账号仅可查询本人门诊与手术工作量；制度说明请使用知识库。")
            if not any(word in question for word in ("门诊", "接诊", "手术", "工作量", "医生")):
                raise PermissionError("请选择本人门诊或手术工作量，或查询公共知识库。")
        sql = self.generate_sql(question)
        rows = self.execute_sql(sql, limit=limit)
        analysis = analyze_metric_rows(rows, question)
        return QueryResult(question=question, sql=add_default_limit(sql, limit=limit), rows=rows, analysis=analysis)
