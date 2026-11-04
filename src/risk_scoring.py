from __future__ import annotations

from pathlib import Path
from .access import hospital_connection
from .auth import Principal


class MedicalInsuranceRiskScorer:
    """Lightweight operation-risk scorer for portfolio DRG/DIP observation.

    This is not a formal DRG/DIP settlement engine. It converts simulated
    operation and case-settlement data into department-level review priorities.
    """

    def __init__(self, db_path: str | Path = "data/hospital.db", principal: Principal | None = None):
        self.db_path = Path(db_path)
        if principal:
            principal.require_director()
        self.principal = principal

    def _fetch_rows(self, sql: str, params: tuple = ()) -> list[dict]:
        with hospital_connection(self.db_path, self.principal) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    @staticmethod
    def _month_key(month_start: str) -> str:
        return month_start[:7]

    @staticmethod
    def _risk_level(score: int) -> str:
        if score >= 6:
            return "高"
        if score >= 3:
            return "中"
        return "低"

    @staticmethod
    def _suggest_action(triggered: list[str]) -> str:
        if any("DRG/DIP" in item or "费用超支" in item for item in triggered):
            return "医保办牵头复核模拟亏损病例，联动科室核查费用结构、住院日和编码质量。"
        if any("床位" in item for item in triggered):
            return "运营办关注出入院节奏、床位周转和跨科调配。"
        if any("药占比" in item or "耗材" in item for item in triggered):
            return "运营办结合病种结构和诊疗路径复核费用结构。"
        return "持续观察核心运营指标，暂不触发专项复核。"

    def get_department_risk_scores(
        self,
        month_start: str,
        month_end: str,
        recent_start: str,
        recent_end: str,
        limit: int | None = None,
    ) -> list[dict]:
        rows = self._fetch_rows(
            """
            WITH bills AS (
                SELECT department_id,
                       SUM(amount) AS total_income,
                       SUM(CASE WHEN item_type='药品' THEN amount ELSE 0 END) AS drug_income,
                       SUM(CASE WHEN item_type='耗材' THEN amount ELSE 0 END) AS material_income
                FROM billing_records
                WHERE bill_date >= ? AND bill_date < ?
                GROUP BY department_id
            ),
            beds AS (
                SELECT department_id,
                       AVG(occupied_beds * 100.0 / NULLIF(open_beds, 0)) AS avg_bed_occupancy_rate
                FROM bed_daily_stats
                WHERE stat_date >= ? AND stat_date < ?
                GROUP BY department_id
            ),
            inpatients AS (
                SELECT department_id,
                       COUNT(*) AS inpatient_count,
                       AVG(CASE WHEN status='已出院' THEN bed_days END) AS avg_length_of_stay
                FROM inpatient_records
                WHERE (admission_date >= ? AND admission_date < ?)
                   OR (discharge_date >= ? AND discharge_date < ?)
                GROUP BY department_id
            ),
            drg AS (
                SELECT department_id,
                       COUNT(*) AS case_count,
                       SUM(CASE WHEN profit_loss < 0 THEN ABS(profit_loss) ELSE 0 END) AS simulated_drg_loss,
                       SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) AS overrun_case_count,
                       SUM(CASE WHEN risk_flag='高风险' THEN 1 ELSE 0 END) AS high_risk_case_count
                FROM case_drg_records
                WHERE settlement_month = ?
                GROUP BY department_id
            )
            SELECT d.department_id,
                   d.department_name,
                   ROUND(COALESCE(bills.total_income, 0), 2) AS total_income,
                   ROUND(COALESCE(bills.drug_income, 0) * 100.0 / NULLIF(bills.total_income, 0), 2) AS drug_ratio,
                   ROUND(COALESCE(bills.material_income, 0) * 100.0 / NULLIF(bills.total_income, 0), 2) AS material_ratio,
                   ROUND(COALESCE(beds.avg_bed_occupancy_rate, 0), 2) AS avg_bed_occupancy_rate,
                   COALESCE(inpatients.inpatient_count, 0) AS inpatient_count,
                   ROUND(COALESCE(inpatients.avg_length_of_stay, 0), 2) AS avg_length_of_stay,
                   COALESCE(drg.case_count, 0) AS case_count,
                   ROUND(COALESCE(drg.simulated_drg_loss, 0), 2) AS simulated_drg_loss,
                   COALESCE(drg.overrun_case_count, 0) AS overrun_case_count,
                   COALESCE(drg.high_risk_case_count, 0) AS high_risk_case_count
            FROM departments d
            LEFT JOIN bills ON d.department_id = bills.department_id
            LEFT JOIN beds ON d.department_id = beds.department_id
            LEFT JOIN inpatients ON d.department_id = inpatients.department_id
            LEFT JOIN drg ON d.department_id = drg.department_id
            """,
            (
                month_start,
                month_end,
                recent_start,
                recent_end,
                month_start,
                month_end,
                month_start,
                month_end,
                self._month_key(month_start),
            ),
        )

        scored: list[dict] = []
        for row in rows:
            score = 0
            triggered: list[str] = []
            if row["avg_bed_occupancy_rate"] >= 90:
                score += 2
                triggered.append("床位高位运行")
            if row["drug_ratio"] >= 30:
                score += 2
                triggered.append("药占比偏高")
            if row["material_ratio"] >= 20:
                score += 2
                triggered.append("耗材占比偏高")
            if row["avg_length_of_stay"] >= 9:
                score += 1
                triggered.append("平均住院日偏长")
            if row["simulated_drg_loss"] > 0:
                score += 3
                triggered.append("DRG/DIP模拟亏损")
            if row["overrun_case_count"] > 0:
                score += 2
                triggered.append("费用超支病例")
            if row["high_risk_case_count"] > 0:
                score += 1
                triggered.append("高风险病例")

            row["risk_score"] = score
            row["risk_level"] = self._risk_level(score)
            row["triggered_risks"] = "、".join(triggered) if triggered else "未触发重点风险"
            row["suggested_action"] = self._suggest_action(triggered)
            scored.append(row)

        scored.sort(key=lambda item: (item["risk_score"], item["simulated_drg_loss"]), reverse=True)
        return scored[:limit] if limit else scored

    def get_risk_summary(
        self,
        month_start: str,
        month_end: str,
        recent_start: str,
        recent_end: str,
    ) -> dict:
        scores = self.get_department_risk_scores(month_start, month_end, recent_start, recent_end)
        high_risk = [row for row in scores if row["risk_level"] == "高"]
        return {
            "department_count": len(scores),
            "high_risk_department_count": len(high_risk),
            "medium_risk_department_count": len([row for row in scores if row["risk_level"] == "中"]),
            "simulated_drg_loss": round(sum(row["simulated_drg_loss"] for row in scores), 2),
            "overrun_case_count": int(sum(row["overrun_case_count"] for row in scores)),
            "high_risk_case_count": int(sum(row["high_risk_case_count"] for row in scores)),
            "top_department": scores[0]["department_name"] if scores else "暂无",
        }

    def get_drg_group_summary(self, month_start: str, limit: int = 8) -> list[dict]:
        return self._fetch_rows(
            """
            SELECT g.drg_code,
                   g.drg_name,
                   g.risk_level,
                   COUNT(c.case_id) AS case_count,
                   ROUND(AVG(c.total_cost), 2) AS avg_total_cost,
                   ROUND(AVG(c.estimated_payment), 2) AS avg_estimated_payment,
                   ROUND(SUM(c.profit_loss), 2) AS simulated_profit_loss,
                   SUM(CASE WHEN c.profit_loss < 0 THEN 1 ELSE 0 END) AS overrun_case_count
            FROM case_drg_records c
            JOIN drg_groups g ON c.drg_code = g.drg_code
            WHERE c.settlement_month = ?
            GROUP BY g.drg_code, g.drg_name, g.risk_level
            ORDER BY simulated_profit_loss ASC
            LIMIT ?
            """,
            (self._month_key(month_start), limit),
        )
