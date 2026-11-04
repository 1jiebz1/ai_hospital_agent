from __future__ import annotations

from datetime import date, timedelta

from .risk_scoring import MedicalInsuranceRiskScorer
from .sql_agent import HospitalSQLAgent


class HospitalReportGenerator:
    def __init__(self, sql_agent: HospitalSQLAgent | None = None):
        self.sql_agent = sql_agent or HospitalSQLAgent()
        self.risk_scorer = MedicalInsuranceRiskScorer(self.sql_agent.db_path, self.sql_agent.principal)

    @staticmethod
    def _report_windows() -> tuple[str, str, str, str]:
        latest = date(2026, 6, 7)
        month_start = latest.replace(day=1)
        month_end = date(latest.year, latest.month + 1, 1)
        recent_start = latest - timedelta(days=6)
        recent_end = latest + timedelta(days=1)
        return (
            month_start.isoformat(),
            month_end.isoformat(),
            recent_start.isoformat(),
            recent_end.isoformat(),
        )

    def generate_monthly_report(self, question: str = "生成本月医院运营简报") -> str:
        if self.sql_agent.principal:
            self.sql_agent.principal.require_director()
        outpatient = self.sql_agent.ask("本月门诊量最高的5个科室", limit=5)
        income = self.sql_agent.ask("本月各科室收入排名", limit=5)
        drug = self.sql_agent.ask("本月药占比是多少", limit=5)
        beds = self.sql_agent.ask("最近7天床位使用率超过90%的科室", limit=10)
        surgery = self.sql_agent.ask("本月各科室手术量", limit=6)
        month_start, month_end, recent_start, recent_end = self._report_windows()
        risk_scores = self.risk_scorer.get_department_risk_scores(
            month_start, month_end, recent_start, recent_end, limit=3
        )
        risk_summary = self.risk_scorer.get_risk_summary(month_start, month_end, recent_start, recent_end)

        def fmt_rows(rows: list[dict], key: str, value: str, unit: str = "") -> str:
            if not rows:
                return "暂无数据"
            return "；".join(f"{row.get(key)} {row.get(value)}{unit}" for row in rows)

        def fmt_money(value: float) -> str:
            return f"{value / 10000:.1f}万元" if value >= 10000 else f"{value:.0f}元"

        risk_notes = beds.analysis + drug.analysis
        risk_text = "\n".join(f"- {note}" for note in risk_notes)
        insurance_risk_text = "\n".join(
            f"- {row['department_name']}：风险分 {row['risk_score']}，命中{row['triggered_risks']}，"
            f"模拟亏损 {fmt_money(row['simulated_drg_loss'])}。"
            for row in risk_scores
        ) or "- 暂无重点医保控费观察风险。"

        scope_title = f"{self.sql_agent.principal.department_name}运营月度简报" if self.sql_agent.principal else "医院运营月度简报"
        return f"""# {scope_title}（模拟数据）

## 一、总体运营概况
本月门诊量排名靠前科室：{fmt_rows(outpatient.rows, "department_name", "visit_count", "人次")}。
本月收入排名靠前科室：{fmt_rows(income.rows, "department_name", "total_income", "元")}。

## 二、科室表现分析
门诊端建议关注高流量科室的排班、候诊时间和诊室资源；收入端建议结合病种结构、医保支付规则和成本结构判断，不宜只按收入高低评价科室。

## 三、收入结构分析
药品收入占比较高科室：{fmt_rows(drug.rows, "department_name", "drug_ratio", "%")}。
该指标用于内部合理用药和费用结构监测，不应作为单一考核指标。

## 四、床位使用情况
最近 7 天床位紧张科室：{fmt_rows(beds.rows, "department_name", "avg_bed_occupancy_rate", "%")}。

## 五、手术工作量
本月手术工作量概览：{fmt_rows(surgery.rows, "department_name", "surgery_count", "台")}。

## 六、异常风险提示
{risk_text}

## 七、医保控费与 DRG/DIP 观察（模拟）
本月模拟 DRG/DIP 亏损合计 {fmt_money(risk_summary["simulated_drg_loss"])}，费用超支病例 {risk_summary["overrun_case_count"]} 例，高风险病例 {risk_summary["high_risk_case_count"]} 例。
{insurance_risk_text}

说明：本节用于运营管理和控费观察，不代表正式 DRG/DIP 入组、结算或医保审核结果。

## 八、管理建议
- 对床位使用率持续超过 90% 的科室，优先评估出入院流程、床位周转和跨科调配。
- 对药品收入占比偏高科室，结合病种、诊疗路径和医保规则做二次核查。
- 对模拟亏损和费用超支病例较集中的科室，建议医保办、病案室和临床科室共同复核编码质量、住院日和费用结构。
- 对门诊量高峰科室，建议联动排班、预约号源和检查资源，降低患者等待时间。
- 后续可接入真实 HIS、财务和绩效系统，替换当前模拟明细数据。
"""
