from __future__ import annotations

from html import escape
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.charts import make_chart
from src.rag_agent import HospitalKnowledgeBase
from src.report_generator import HospitalReportGenerator
from src.risk_scoring import MedicalInsuranceRiskScorer
from src.router import route_question
from src.sql_agent import HospitalSQLAgent
from src.auth import AuthStore, Principal, allowed_pages, require_page
from src.auth_ui import require_login, logout
from src.access import hospital_connection


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data/hospital.db"

UI_TOKENS = {
    "bg": "#07110f",
    "card": "#111a17",
    "border": "#24372f",
    "text": "#edf6f1",
    "muted": "#8fa39a",
    "green": "#34d66f",
    "green_soft": "#143626",
    "blue": "#4f8cff",
    "cyan": "#58d4d8",
    "yellow": "#f6c85f",
    "red": "#ff6370",
    "purple": "#9b7cff",
    "radius": "8px",
}
GREEN = UI_TOKENS["green"]
BLUE = UI_TOKENS["blue"]
CYAN = UI_TOKENS["cyan"]
YELLOW = UI_TOKENS["yellow"]
RED = UI_TOKENS["red"]
TEXT = UI_TOKENS["text"]
CHART_COLORS = [GREEN, BLUE, CYAN, YELLOW, RED, UI_TOKENS["purple"]]

PAGE_REGISTRY = [
    {
        "label": "运营总览",
        "module": "dashboard",
        "purpose": "管理层首屏，集中查看 KPI、风险和关键趋势",
    },
    {
        "label": "浮窗问答",
        "module": "floating_qa",
        "purpose": "页面内轻量 AI 入口，输入后再展开图表结果",
    },
    {
        "label": "智能问答",
        "module": "qa",
        "purpose": "自然语言查询、知识库解释和报告生成",
    },
    {
        "label": "趋势分析",
        "module": "trends",
        "purpose": "按时间观察门诊、收入、床位和手术变化",
    },
    {
        "label": "科室绩效",
        "module": "departments",
        "purpose": "横向比较科室收入、工作量、床位和费用结构",
    },
    {
        "label": "医保控费观察",
        "module": "insurance_risk",
        "purpose": "用模拟 DRG/DIP 数据观察科室经营与控费风险",
    },
    {
        "label": "运营简报",
        "module": "report",
        "purpose": "生成管理层可读的月度运营简报",
    },
    {
        "label": "医管知识库",
        "module": "knowledge",
        "purpose": "解释指标口径、医保控费、DRG/DIP 和绩效规则",
    },
    {
        "label": "改动记录",
        "module": "change_log",
        "purpose": "展示产品升级过程、页面骨架和差异对比",
    },
]
PAGE_LABELS = [page["label"] for page in PAGE_REGISTRY]

EXAMPLES = [
    "本月本科室门诊量是多少？",
    "统计2026年5月本科室收入。",
    "最近7天本科室床位使用率是多少？",
    "本月药占比是多少？",
    "本月本科室耗材收入占比是多少？",
    "本月医疗服务收入占比是多少？",
    "2026年5月本科室平均住院日是多少？",
    "本月本科室住院人数是多少？",
    "本月本科室床位周转次数是多少？",
    "本月手术量按手术级别怎么分布？",
    "哪个医生上周接诊人数最多？",
    "DRG/DIP支付下医院运营应关注哪些指标？",
    "医保控费中药品、耗材和检查费用要关注什么？",
    "科室绩效考核通常包含哪些指标？",
    "生成本月医院运营简报。",
]

COLUMN_LABELS = {
    "department_name": "科室",
    "doctor_name": "医生",
    "title": "职称",
    "visit_count": "门诊量",
    "total_income": "总收入",
    "bill_count": "收费记录数",
    "drug_income": "药品收入",
    "drug_ratio": "药占比",
    "item_income": "项目收入",
    "item_ratio": "项目占比",
    "medical_service_income": "医疗服务收入",
    "medical_service_income_ratio": "医疗服务收入占比",
    "avg_bed_occupancy_rate": "平均床位使用率",
    "max_bed_occupancy_rate": "最高床位使用率",
    "stat_days": "统计天数",
    "avg_length_of_stay": "平均住院日",
    "inpatient_count": "住院人数",
    "discharged_count": "出院人数",
    "inpatient_total_cost": "住院总费用",
    "avg_open_beds": "平均开放床位",
    "bed_turnover_times": "床位周转次数",
    "surgery_level": "手术级别",
    "surgery_count": "手术量",
    "avg_duration_minutes": "平均手术时长",
    "item_type": "费用类别",
    "amount": "金额",
    "ratio": "占比",
    "risk_score": "风险分",
    "risk_level": "风险等级",
    "triggered_risks": "命中风险项",
    "suggested_action": "建议动作",
    "case_count": "模拟病例数",
    "simulated_drg_loss": "模拟DRG/DIP亏损",
    "overrun_case_count": "费用超支病例数",
    "high_risk_case_count": "高风险病例数",
    "drg_code": "病组编码",
    "drg_name": "模拟病组",
    "avg_total_cost": "平均总费用",
    "avg_estimated_payment": "平均模拟支付",
    "simulated_profit_loss": "模拟盈亏",
}

CHANGE_LOG = [
    {
        "阶段": "1. 视觉框架",
        "参考界面特征": "左侧导航、深色医疗后台、绿色状态色",
        "本项目改动": "重构为侧边栏多页面后台，统一深色主题和卡片样式",
        "效果": "从单页 Demo 变成可展示的医管驾驶舱",
    },
    {
        "阶段": "2. 内容驾驶舱",
        "参考界面特征": "顶部 KPI 卡片、实时状态、关键发现",
        "本项目改动": "新增门诊量、收入、床位使用率、药占比、手术量、住院人数 KPI",
        "效果": "管理层进入页面即可看到核心运营状态",
    },
    {
        "阶段": "3. 图表分析",
        "参考界面特征": "趋势图、分布图、风险图、结构图",
        "本项目改动": "新增门诊/收入趋势、收入结构、床位风险、手术级别、科室绩效图",
        "效果": "数据从表格结果升级为可解释的运营图谱",
    },
    {
        "阶段": "4. AI 助手侧栏",
        "参考界面特征": "右侧 AI 助手给出结论和下一步行动",
        "本项目改动": "新增关键发现、风险提示、建议动作和智能问答解释区",
        "效果": "页面不只展示数据，还能辅助决策",
    },
    {
        "阶段": "5. 管理表格",
        "参考界面特征": "患者/样本/用户管理表格",
        "本项目改动": "新增科室绩效明细表、床位风险表、问答结果中文列名",
        "效果": "便于筛查、比较和面试演示",
    },
    {
        "阶段": "6. 项目包装",
        "参考界面特征": "专业产品级后台而不是脚本输出",
        "本项目改动": "新增改动记录页和文档化过程表",
        "效果": "方便写简历、讲项目升级路径",
    },
    {
        "阶段": "7. 前端骨架化",
        "参考界面特征": "先定风格、技术方案、模块边界和组件复用规则，再让 AI 写页面",
        "本项目改动": "沉淀页面注册表、设计 token、组件规则和前端骨架文档",
        "效果": "页面扩展时更容易保持同一套医管后台风格",
    },
    {
        "阶段": "8. 医保控费观察",
        "参考界面特征": "风险评分、科室排行、病组盈亏和边界说明",
        "本项目改动": "新增模拟 DRG/DIP 数据、科室风险评分和医保控费观察页",
        "效果": "从运营看板升级为能解释控费风险的产品原型",
    },
]


st.set_page_config(page_title="AI 医管运营驾驶舱", page_icon="+", layout="wide")


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #07110f;
            --card: #111a17;
            --border: #24372f;
            --text: #edf6f1;
            --muted: #8fa39a;
            --green: #34d66f;
            --green-soft: #143626;
            --blue: #4f8cff;
            --cyan: #58d4d8;
            --yellow: #f6c85f;
            --red: #ff6370;
            --radius: 8px;
        }

        .stApp {
            background:
                radial-gradient(circle at 12% 10%, rgba(52,214,111,0.11), transparent 26%),
                radial-gradient(circle at 86% 12%, rgba(88,212,216,0.08), transparent 22%),
                var(--bg);
            color: var(--text);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0a1512 0%, #08110f 100%);
            border-right: 1px solid var(--border);
        }

        [data-testid="stSidebar"] * {
            color: var(--text);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 2rem;
            max-width: 1480px;
        }

        h1, h2, h3 {
            letter-spacing: 0;
            color: var(--text);
        }

        h1 {
            font-size: 34px !important;
            margin-bottom: 0.2rem !important;
        }

        h2 {
            font-size: 22px !important;
        }

        h3 {
            font-size: 18px !important;
        }

        p, li, label, .stMarkdown {
            color: var(--text);
            font-size: 15px;
            line-height: 1.65;
        }

        .muted {
            color: var(--muted);
        }

        .brand {
            padding: 18px 14px 22px 14px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 12px;
        }

        .brand-name {
            font-size: 22px;
            font-weight: 800;
            color: var(--green);
        }

        .brand-sub {
            font-size: 12px;
            color: var(--muted);
            margin-top: 2px;
        }

        .section-title {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 8px 0 14px 0;
        }

        .page-title {
            color: var(--text);
            font-size: 34px;
            line-height: 1;
            font-weight: 850;
        }

        .panel-title {
            color: var(--text);
            font-size: 22px;
            line-height: 1;
            font-weight: 800;
        }

        .section-title span {
            display: inline-flex;
            align-items: center;
            padding: 5px 10px;
            border-radius: 999px;
            background: var(--green-soft);
            color: var(--green);
            font-size: 13px;
            font-weight: 700;
        }

        .metric-card {
            min-height: 132px;
            padding: 18px 18px 14px 18px;
            border: 1px solid var(--border);
            border-radius: var(--radius);
            background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015)), var(--card);
            box-shadow: 0 18px 48px rgba(0,0,0,0.22);
        }

        .metric-label {
            color: var(--muted);
            font-size: 13px;
            margin-bottom: 10px;
        }

        .metric-value {
            color: var(--text);
            font-size: 30px;
            line-height: 1;
            font-weight: 800;
        }

        .metric-trend {
            margin-top: 12px;
            font-size: 13px;
            color: var(--muted);
        }

        .trend-up {
            color: var(--green);
            font-weight: 700;
        }

        .trend-down {
            color: var(--red);
            font-weight: 700;
        }

        .assistant-card {
            border: 1px solid var(--border);
            background: linear-gradient(180deg, rgba(52,214,111,0.08), rgba(17,26,23,0.96));
            border-radius: var(--radius);
            padding: 18px;
        }

        .float-stage {
            min-height: 560px;
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 22px;
            background:
                radial-gradient(circle at 18% 20%, rgba(52,214,111,0.18), transparent 32%),
                radial-gradient(circle at 80% 15%, rgba(79,140,255,0.14), transparent 28%),
                linear-gradient(180deg, rgba(17,26,23,0.68), rgba(7,17,15,0.96));
        }

        .float-window {
            border: 1px solid rgba(52,214,111,0.28);
            border-radius: var(--radius);
            padding: 18px;
            background: rgba(13,23,20,0.96);
            box-shadow: 0 24px 80px rgba(0,0,0,0.35);
        }

        .float-title {
            color: var(--green);
            font-size: 18px;
            font-weight: 850;
            margin-bottom: 6px;
        }

        .float-desc {
            color: var(--muted);
            font-size: 13px;
            margin-bottom: 14px;
        }

        .float-result {
            border: 1px solid rgba(52,214,111,0.18);
            border-radius: var(--radius);
            padding: 18px;
            background: rgba(17,26,23,0.92);
            box-shadow: 0 24px 80px rgba(0,0,0,0.28);
        }

        .assistant-title {
            color: var(--green);
            font-weight: 800;
            font-size: 17px;
            margin-bottom: 10px;
        }

        .assistant-bubble {
            border: 1px solid rgba(52,214,111,0.18);
            background: rgba(10,20,17,0.8);
            padding: 12px 14px;
            border-radius: var(--radius);
            margin: 10px 0;
        }

        .tag {
            display: inline-block;
            padding: 4px 9px;
            border-radius: 999px;
            background: rgba(52,214,111,0.12);
            color: var(--green);
            border: 1px solid rgba(52,214,111,0.22);
            font-size: 12px;
            margin: 3px 6px 3px 0;
        }

        .stButton > button {
            border-radius: var(--radius);
            border: 1px solid rgba(52,214,111,0.35);
            background: var(--green);
            color: #04100b;
            font-weight: 800;
        }

        .stButton > button:hover {
            border-color: var(--green);
            color: #04100b;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--border);
            border-radius: var(--radius);
            overflow: hidden;
            background: var(--card);
        }

        input, textarea {
            background: #0d1714 !important;
            color: var(--text) !important;
            border-color: var(--border) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def get_agents(identity: Principal):
    sql_agent = HospitalSQLAgent(DB_PATH, ROOT / "data/hospital_schema.json", identity)
    kb = HospitalKnowledgeBase(ROOT / "hospital_docs")
    report_generator = HospitalReportGenerator(sql_agent) if identity.role == "director" else None
    risk_scorer = MedicalInsuranceRiskScorer(DB_PATH, identity) if identity.role == "director" else None
    return sql_agent, kb, report_generator, risk_scorer


@st.cache_data(ttl=60)
def _query_df(sql: str, identity: Principal, version: int) -> pd.DataFrame:
    with hospital_connection(DB_PATH, identity) as conn:
        return pd.read_sql_query(sql, conn)


def query_df(sql: str) -> pd.DataFrame:
    return _query_df(sql, principal, DB_PATH.stat().st_mtime_ns)


def query_value(sql: str, default: float = 0.0) -> float:
    df = query_df(sql)
    if df.empty:
        return default
    value = df.iloc[0, 0]
    if value is None:
        return default
    return float(value)


def get_latest_date() -> date:
    df = query_df(
        """
        SELECT MAX(day) AS latest_day
        FROM (
            SELECT MAX(visit_date) AS day FROM outpatient_visits
            UNION ALL SELECT MAX(surgery_date) FROM surgery_records
        )
        """
    )
    value = df.loc[0, "latest_day"] if not df.empty else None
    if not value or pd.isna(value):
        return date(2026, 6, 7)
    return datetime.strptime(value, "%Y-%m-%d").date()


def month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def previous_month_bounds(day: date) -> tuple[date, date]:
    current_start, _ = month_bounds(day)
    previous_end = current_start
    if current_start.month == 1:
        previous_start = date(current_start.year - 1, 12, 1)
    else:
        previous_start = date(current_start.year, current_start.month - 1, 1)
    return previous_start, previous_end


inject_css()
auth_store = AuthStore()
try:
    # Streamlit stores this table privately; no default account or public registration.
    try:
        cloud_accounts = st.secrets.get("accounts", {})
    except FileNotFoundError:
        cloud_accounts = {}
    from src.account_config import apply_account_config
    from src.auth import ROOT as AUTH_ROOT
    if cloud_accounts and (AUTH_ROOT / "账号密码配置.toml").exists():
        raise ValueError("本地账号配置与云端 Secrets 同时存在，请仅保留一种账号配置来源。")
    apply_account_config(auth_store, cloud_accounts, DB_PATH)
    auth_store.has_users()
except (ValueError, OSError):
    st.error("账号配置无法读取或格式无效，请管理员检查本地账号配置或云端 Secrets。")
    st.stop()
principal = require_login(auth_store)
LATEST_DATE = get_latest_date()
MONTH_START, MONTH_END = month_bounds(LATEST_DATE)
PREV_START, PREV_END = previous_month_bounds(LATEST_DATE)
RECENT_START = LATEST_DATE - timedelta(days=6)
TREND_START = LATEST_DATE - timedelta(days=60)


def risk_date_window() -> tuple[str, str, str, str]:
    recent_end = LATEST_DATE + timedelta(days=1)
    return (
        MONTH_START.isoformat(),
        MONTH_END.isoformat(),
        RECENT_START.isoformat(),
        recent_end.isoformat(),
    )


def fmt_int(value: float) -> str:
    return f"{int(round(value)):,}"


def fmt_money(value: float) -> str:
    if value >= 10000:
        return f"{value / 10000:.1f}万"
    return f"{value:,.0f}"


def fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def pct_delta(current: float, previous: float) -> float:
    if not previous:
        return 0.0
    return (current - previous) * 100.0 / previous


def render_metric(label: str, value: str, delta: float, suffix: str = "较上月") -> None:
    cls = "trend-up" if delta >= 0 else "trend-down"
    sign = "+" if delta >= 0 else ""
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-trend">{suffix} <span class="{cls}">{sign}{delta:.1f}%</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_static_metric(label: str, value: str, caption: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-trend">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, badge: str = "实时监测") -> None:
    st.markdown(
        f"""<div class="section-title"><div class="panel-title">{title}</div><span>{badge}</span></div>""",
        unsafe_allow_html=True,
    )


def style_fig(fig: go.Figure, height: int = 330) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, size=12),
        margin=dict(l=24, r=18, t=42, b=26),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        colorway=CHART_COLORS,
    )
    fig.update_xaxes(gridcolor="rgba(143,163,154,0.12)", zerolinecolor="rgba(143,163,154,0.18)")
    fig.update_yaxes(gridcolor="rgba(143,163,154,0.12)", zerolinecolor="rgba(143,163,154,0.18)")
    return fig


def get_monthly_metrics() -> dict:
    visits = query_value(
        f"SELECT COUNT(*) FROM outpatient_visits WHERE visit_date >= '{MONTH_START}' AND visit_date < '{MONTH_END}'"
    )
    prev_visits = query_value(
        f"SELECT COUNT(*) FROM outpatient_visits WHERE visit_date >= '{PREV_START}' AND visit_date < '{PREV_END}'"
    )
    income = query_value(
        f"SELECT COALESCE(SUM(amount), 0) FROM billing_records WHERE bill_date >= '{MONTH_START}' AND bill_date < '{MONTH_END}'"
    )
    prev_income = query_value(
        f"SELECT COALESCE(SUM(amount), 0) FROM billing_records WHERE bill_date >= '{PREV_START}' AND bill_date < '{PREV_END}'"
    )
    bed_rate = query_value(
        f"""
        SELECT AVG(occupied_beds * 100.0 / NULLIF(open_beds, 0))
        FROM bed_daily_stats
        WHERE stat_date >= '{RECENT_START}' AND stat_date <= '{LATEST_DATE}'
        """
    )
    prev_bed_rate = query_value(
        f"""
        SELECT AVG(occupied_beds * 100.0 / NULLIF(open_beds, 0))
        FROM bed_daily_stats
        WHERE stat_date >= '{RECENT_START - timedelta(days=7)}' AND stat_date < '{RECENT_START}'
        """
    )
    drug_ratio = query_value(
        f"""
        SELECT SUM(CASE WHEN item_type='药品' THEN amount ELSE 0 END) * 100.0 / NULLIF(SUM(amount), 0)
        FROM billing_records
        WHERE bill_date >= '{MONTH_START}' AND bill_date < '{MONTH_END}'
        """
    )
    prev_drug_ratio = query_value(
        f"""
        SELECT SUM(CASE WHEN item_type='药品' THEN amount ELSE 0 END) * 100.0 / NULLIF(SUM(amount), 0)
        FROM billing_records
        WHERE bill_date >= '{PREV_START}' AND bill_date < '{PREV_END}'
        """
    )
    surgeries = query_value(
        f"SELECT COUNT(*) FROM surgery_records WHERE surgery_date >= '{MONTH_START}' AND surgery_date < '{MONTH_END}'"
    )
    prev_surgeries = query_value(
        f"SELECT COUNT(*) FROM surgery_records WHERE surgery_date >= '{PREV_START}' AND surgery_date < '{PREV_END}'"
    )
    inpatients = query_value(
        f"SELECT COUNT(*) FROM inpatient_records WHERE admission_date >= '{MONTH_START}' AND admission_date < '{MONTH_END}'"
    )
    prev_inpatients = query_value(
        f"SELECT COUNT(*) FROM inpatient_records WHERE admission_date >= '{PREV_START}' AND admission_date < '{PREV_END}'"
    )
    return {
        "visits": (visits, pct_delta(visits, prev_visits)),
        "income": (income, pct_delta(income, prev_income)),
        "bed_rate": (bed_rate, bed_rate - prev_bed_rate),
        "drug_ratio": (drug_ratio, drug_ratio - prev_drug_ratio),
        "surgeries": (surgeries, pct_delta(surgeries, prev_surgeries)),
        "inpatients": (inpatients, pct_delta(inpatients, prev_inpatients)),
    }


def get_daily_trend() -> pd.DataFrame:
    return query_df(
        f"""
        WITH days AS (
            SELECT visit_date AS day FROM outpatient_visits
            WHERE visit_date >= '{TREND_START}' AND visit_date <= '{LATEST_DATE}'
            UNION
            SELECT bill_date AS day FROM billing_records
            WHERE bill_date >= '{TREND_START}' AND bill_date <= '{LATEST_DATE}'
        ),
        visits AS (
            SELECT visit_date AS day, COUNT(*) AS visit_count
            FROM outpatient_visits
            WHERE visit_date >= '{TREND_START}' AND visit_date <= '{LATEST_DATE}'
            GROUP BY visit_date
        ),
        income AS (
            SELECT bill_date AS day, SUM(amount) AS total_income
            FROM billing_records
            WHERE bill_date >= '{TREND_START}' AND bill_date <= '{LATEST_DATE}'
            GROUP BY bill_date
        )
        SELECT days.day,
               COALESCE(visits.visit_count, 0) AS visit_count,
               ROUND(COALESCE(income.total_income, 0), 2) AS total_income
        FROM days
        LEFT JOIN visits ON days.day = visits.day
        LEFT JOIN income ON days.day = income.day
        ORDER BY days.day
        """
    )


def get_income_structure() -> pd.DataFrame:
    return query_df(
        f"""
        SELECT item_type,
               ROUND(SUM(amount), 2) AS amount,
               ROUND(SUM(amount) * 100.0 / (
                   SELECT SUM(amount) FROM billing_records
                   WHERE bill_date >= '{MONTH_START}' AND bill_date < '{MONTH_END}'
               ), 2) AS ratio
        FROM billing_records
        WHERE bill_date >= '{MONTH_START}' AND bill_date < '{MONTH_END}'
        GROUP BY item_type
        ORDER BY amount DESC
        """
    )


def get_bed_risk() -> pd.DataFrame:
    return query_df(
        f"""
        SELECT d.department_name,
               ROUND(AVG(b.occupied_beds * 100.0 / NULLIF(b.open_beds, 0)), 2) AS avg_bed_occupancy_rate,
               ROUND(MAX(b.occupied_beds * 100.0 / NULLIF(b.open_beds, 0)), 2) AS max_bed_occupancy_rate,
               COUNT(*) AS stat_days
        FROM bed_daily_stats b
        JOIN departments d ON b.department_id = d.department_id
        WHERE b.stat_date >= '{RECENT_START}' AND b.stat_date <= '{LATEST_DATE}'
        GROUP BY d.department_name
        ORDER BY avg_bed_occupancy_rate DESC
        """
    )


def get_surgery_distribution() -> pd.DataFrame:
    return query_df(
        f"""
        SELECT d.department_name, s.surgery_level, COUNT(*) AS surgery_count
        FROM surgery_records s
        JOIN departments d ON s.department_id = d.department_id
        WHERE s.surgery_date >= '{MONTH_START}' AND s.surgery_date < '{MONTH_END}'
        GROUP BY d.department_name, s.surgery_level
        ORDER BY surgery_count DESC
        """
    )


def get_department_performance() -> pd.DataFrame:
    return query_df(
        f"""
        WITH visits AS (
            SELECT department_id, COUNT(*) AS visit_count
            FROM outpatient_visits
            WHERE visit_date >= '{MONTH_START}' AND visit_date < '{MONTH_END}'
            GROUP BY department_id
        ),
        income AS (
            SELECT department_id,
                   SUM(amount) AS total_income,
                   SUM(CASE WHEN item_type='药品' THEN amount ELSE 0 END) * 100.0 / NULLIF(SUM(amount), 0) AS drug_ratio,
                   SUM(CASE WHEN item_type='耗材' THEN amount ELSE 0 END) * 100.0 / NULLIF(SUM(amount), 0) AS material_ratio
            FROM billing_records
            WHERE bill_date >= '{MONTH_START}' AND bill_date < '{MONTH_END}'
            GROUP BY department_id
        ),
        beds AS (
            SELECT department_id, AVG(occupied_beds * 100.0 / NULLIF(open_beds, 0)) AS bed_rate
            FROM bed_daily_stats
            WHERE stat_date >= '{RECENT_START}' AND stat_date <= '{LATEST_DATE}'
            GROUP BY department_id
        ),
        inpatients AS (
            SELECT department_id,
                   COUNT(*) AS inpatient_count,
                   AVG(CASE WHEN status='已出院' THEN bed_days END) AS avg_los
            FROM inpatient_records
            WHERE (admission_date >= '{MONTH_START}' AND admission_date < '{MONTH_END}')
               OR (discharge_date >= '{MONTH_START}' AND discharge_date < '{MONTH_END}')
            GROUP BY department_id
        ),
        surgeries AS (
            SELECT department_id, COUNT(*) AS surgery_count
            FROM surgery_records
            WHERE surgery_date >= '{MONTH_START}' AND surgery_date < '{MONTH_END}'
            GROUP BY department_id
        )
        SELECT d.department_name,
               COALESCE(v.visit_count, 0) AS visit_count,
               ROUND(COALESCE(i.total_income, 0), 2) AS total_income,
               ROUND(COALESCE(i.drug_ratio, 0), 2) AS drug_ratio,
               ROUND(COALESCE(i.material_ratio, 0), 2) AS material_ratio,
               ROUND(COALESCE(b.bed_rate, 0), 2) AS avg_bed_occupancy_rate,
               COALESCE(ip.inpatient_count, 0) AS inpatient_count,
               ROUND(COALESCE(ip.avg_los, 0), 2) AS avg_length_of_stay,
               COALESCE(s.surgery_count, 0) AS surgery_count
        FROM departments d
        LEFT JOIN visits v ON d.department_id = v.department_id
        LEFT JOIN income i ON d.department_id = i.department_id
        LEFT JOIN beds b ON d.department_id = b.department_id
        LEFT JOIN inpatients ip ON d.department_id = ip.department_id
        LEFT JOIN surgeries s ON d.department_id = s.department_id
        ORDER BY total_income DESC
        """
    )


def render_assistant_panel(title: str, bullets: list[str], actions: list[str] | None = None) -> None:
    action_html = "".join(f"<span class='tag'>{item}</span>" for item in (actions or []))
    bullet_html = "".join(f"<li>{item}</li>" for item in bullets)
    st.markdown(
        f"""
        <div class="assistant-card">
            <div class="assistant-title">{title}</div>
            <div class="assistant-bubble">
                <ul>{bullet_html}</ul>
            </div>
            <div>{action_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str, badge: str = "实时监测") -> None:
    left, right = st.columns([2.1, 1])
    with left:
        st.markdown(
            f"""
            <div class="section-title">
                <div class="page-title">{title}</div><span>{badge}</span>
            </div>
            <p class="muted">{subtitle}</p>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.text_input("全局搜索", placeholder="搜索科室、指标或医管问题...", label_visibility="collapsed")


def render_dashboard() -> None:
    render_header("运营总览", f"数据时间范围：{MONTH_START} 至 {LATEST_DATE}；当前为模拟医院运营数据。")

    metrics = get_monthly_metrics()
    cols = st.columns(3)
    with cols[0]:
        render_metric("本月门诊量", fmt_int(metrics["visits"][0]), metrics["visits"][1])
    with cols[1]:
        render_metric("本月总收入", fmt_money(metrics["income"][0]), metrics["income"][1])
    with cols[2]:
        render_metric("近7天床位使用率", fmt_pct(metrics["bed_rate"][0]), metrics["bed_rate"][1], "较上周")
    cols = st.columns(3)
    with cols[0]:
        render_metric("药品收入占比", fmt_pct(metrics["drug_ratio"][0]), metrics["drug_ratio"][1])
    with cols[1]:
        render_metric("本月手术量", fmt_int(metrics["surgeries"][0]), metrics["surgeries"][1])
    with cols[2]:
        render_metric("本月住院人数", fmt_int(metrics["inpatients"][0]), metrics["inpatients"][1])

    st.write("")
    main, side = st.columns([2.25, 1])
    with main:
        section_title("关键指标趋势", "近60天")
        trend = get_daily_trend()
        fig = go.Figure()
        fig.add_bar(x=trend["day"], y=trend["visit_count"], name="门诊量", marker_color=GREEN)
        fig.add_scatter(
            x=trend["day"],
            y=trend["total_income"] / 1000,
            name="收入/千元",
            mode="lines",
            line=dict(color=BLUE, width=2.5),
            yaxis="y2",
        )
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)"))
        st.plotly_chart(style_fig(fig, 390), width="stretch")

    with side:
        bed = get_bed_risk()
        high_bed = bed[bed["avg_bed_occupancy_rate"] >= 90]
        bullets = [
            f"{row.department_name} 近7天平均床位使用率 {row.avg_bed_occupancy_rate:.1f}%，建议关注床位调配。"
            for row in high_bed.itertuples()
        ]
        if not bullets:
            bullets = ["近7天未发现床位使用率超过90%的科室。", "建议继续观察高峰日入院和出院节奏。"]
        render_assistant_panel("AI 医管助手", bullets, ["床位调配", "收入结构", "运营简报"])

    col_a, col_b, col_c = st.columns([1, 1, 1.2])
    with col_a:
        section_title("收入结构", "本月")
        income_df = get_income_structure()
        donut = px.pie(income_df, names="item_type", values="amount", hole=0.58)
        st.plotly_chart(style_fig(donut, 310), width="stretch")
    with col_b:
        section_title("床位风险", "近7天")
        bed_fig = px.bar(
            get_bed_risk().head(8),
            x="department_name",
            y="avg_bed_occupancy_rate",
            color="avg_bed_occupancy_rate",
            color_continuous_scale=["#2b6f4a", "#f6c85f", "#ff6370"],
            labels={"department_name": "科室", "avg_bed_occupancy_rate": "平均床位使用率"},
        )
        st.plotly_chart(style_fig(bed_fig, 310), width="stretch")
    with col_c:
        section_title("科室绩效明细", "本月")
        perf = get_department_performance()
        st.dataframe(perf.rename(columns=COLUMN_LABELS), width="stretch", hide_index=True, height=310)


def render_qa() -> None:
    if principal.role == "doctor":
        render_doctor_qa()
        return
    render_header("智能问答", "用自然语言查询运营数据、解释医管指标、生成管理报告。", "Text-to-SQL + RAG")
    left, right = st.columns([2, 1])
    with left:
        question = st.selectbox("示例问题", EXAMPLES, index=0)
        custom = st.text_input("自定义问题", placeholder="例如：本月耗材收入占比最高的科室有哪些？")
        final_question = custom.strip() or question
        submitted = st.button("开始分析", type="primary", width="stretch")

        if submitted:
            decision = route_question(final_question)
            if decision.route in {"sql", "hybrid"}:
                result = sql_agent.ask(final_question, limit=10)
                df = pd.DataFrame(result.rows).rename(columns=COLUMN_LABELS)
                st.dataframe(df, width="stretch", hide_index=True)
                chart = make_chart(result.rows, final_question)
                if chart is not None:
                    st.plotly_chart(style_fig(chart, 360), width="stretch")
                section_title("分析结论", "AI 摘要")
                for note in result.analysis:
                    st.write(f"- {note}")

            if decision.route in {"rag", "hybrid"}:
                rag_result = kb.answer(final_question)
                section_title("知识库回答", "RAG")
                st.write(rag_result["answer"])
                if rag_result["sources"]:
                    st.caption("来源：" + "、".join(item["title"] for item in rag_result["sources"]))

            if decision.route == "report":
                st.markdown(report_generator.generate_monthly_report(final_question))

    with right:
        render_assistant_panel(
            "提问建议",
            [
                "想看经营情况时，优先指定月份和指标，例如“2026年5月各科室收入排名”。",
                "想看风险时，优先问床位、药占比、耗材占比和平均住院日。",
                "想看制度解释时，可直接问 DRG/DIP、医保控费或绩效考核。",
            ],
            ["门诊量", "床位使用率", "DRG/DIP", "月度简报"],
        )


def render_floating_qa() -> None:
    render_header("浮窗问答", "先显示一个 AI 小浮窗；输入问题后再展开结果图表。", "轻量模式")

    if "float_question" not in st.session_state:
        st.session_state.float_question = ""
    if "float_result" not in st.session_state:
        st.session_state.float_result = None

    st.markdown("<div class='float-stage'>", unsafe_allow_html=True)
    left, right = st.columns([1.45, 1])

    with left:
        section_title("浮窗交互预览", "输入后展开")
        st.markdown(
            """
            <div class="assistant-card">
                <div class="assistant-title">交互逻辑</div>
                <div class="assistant-bubble">
                    <ul>
                        <li>默认只保留右侧 AI 小浮窗，页面不会堆满图表。</li>
                        <li>用户输入医管问题后，系统判断 SQL / RAG / 报告任务。</li>
                        <li>如果是数据查询，会在下方结果浮层里显示表格、图表和分析结论。</li>
                    </ul>
                </div>
                <span class="tag">轻量入口</span>
                <span class="tag">按需出图</span>
                <span class="tag">适合演示</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            """
            <div class="float-window">
                <div class="float-title">AI 医管小浮窗</div>
                <div class="float-desc">输入问题后，系统会自动展开对应图表。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("floating_question_form", clear_on_submit=False):
            question = st.text_area(
                "输入问题",
                value=st.session_state.float_question,
                placeholder="例如：最近7天床位使用率超过90%的科室有哪些？",
                height=96,
            )
            quick = st.selectbox(
                "快速选择",
                [
                    "最近7天床位使用率超过90%的科室有哪些？",
                    "本月门诊量最高的5个科室是哪些？",
                    "本月耗材收入占比最高的科室有哪些？",
                    "2026年5月平均住院日最高的科室有哪些？",
                    "DRG/DIP支付下医院运营应关注哪些指标？",
                ],
            )
            use_quick = st.checkbox("使用快速选择", value=False)
            submitted = st.form_submit_button("发送并生成图表", type="primary", width="stretch")

        if submitted:
            final_question = quick if use_quick else question.strip()
            if final_question:
                st.session_state.float_question = final_question
                decision = route_question(final_question)
                payload: dict = {"question": final_question, "route": decision.route}
                if decision.route in {"sql", "hybrid"}:
                    payload["sql_result"] = sql_agent.ask(final_question, limit=10)
                if decision.route in {"rag", "hybrid"}:
                    payload["rag_result"] = kb.answer(final_question)
                if decision.route == "report":
                    payload["report"] = report_generator.generate_monthly_report(final_question)
                st.session_state.float_result = payload

        if st.button("清空浮窗结果", width="stretch"):
            st.session_state.float_result = None
            st.session_state.float_question = ""

    result = st.session_state.float_result
    if result:
        st.write("")
        st.markdown("<div class='float-result'>", unsafe_allow_html=True)
        section_title("浮窗结果", result["route"].upper())
        st.caption(f"问题：{result['question']}")

        if "sql_result" in result:
            sql_result = result["sql_result"]
            df = pd.DataFrame(sql_result.rows).rename(columns=COLUMN_LABELS)
            st.dataframe(df, width="stretch", hide_index=True)
            chart = make_chart(sql_result.rows, result["question"])
            if chart is not None:
                st.plotly_chart(style_fig(chart, 360), width="stretch")
            for note in sql_result.analysis:
                st.write(f"- {note}")

        if "rag_result" in result:
            st.write(result["rag_result"]["answer"])

        if "report" in result:
            st.markdown(result["report"])

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def render_trends() -> None:
    render_header("趋势分析", "观察运营指标随时间变化，定位高峰、风险和资源压力。")
    trend = get_daily_trend()
    col_a, col_b = st.columns([1.4, 1])
    with col_a:
        section_title("门诊与收入趋势", "近60天")
        fig = go.Figure()
        fig.add_scatter(x=trend["day"], y=trend["visit_count"], mode="lines+markers", name="门诊量", line=dict(color=GREEN))
        fig.add_scatter(x=trend["day"], y=trend["total_income"] / 1000, mode="lines", name="收入/千元", line=dict(color=BLUE))
        st.plotly_chart(style_fig(fig, 370), width="stretch")
    with col_b:
        section_title("收入结构占比", "本月")
        income_df = get_income_structure()
        bar = px.bar(
            income_df,
            x="ratio",
            y="item_type",
            orientation="h",
            text="ratio",
            labels={"ratio": "占比", "item_type": "费用类别"},
        )
        st.plotly_chart(style_fig(bar, 370), width="stretch")

    col_c, col_d = st.columns(2)
    with col_c:
        section_title("床位使用率排名", "近7天")
        bed_fig = px.bar(
            get_bed_risk(),
            x="department_name",
            y="avg_bed_occupancy_rate",
            labels={"department_name": "科室", "avg_bed_occupancy_rate": "平均床位使用率"},
        )
        st.plotly_chart(style_fig(bed_fig, 340), width="stretch")
    with col_d:
        section_title("手术级别分布", "本月")
        surgery = get_surgery_distribution()
        if surgery.empty:
            st.info("本月暂无手术数据。")
        else:
            fig = px.bar(
                surgery,
                x="department_name",
                y="surgery_count",
                color="surgery_level",
                barmode="stack",
                labels={"department_name": "科室", "surgery_count": "手术量", "surgery_level": "手术级别"},
            )
            st.plotly_chart(style_fig(fig, 340), width="stretch")


def render_department_page() -> None:
    render_header("科室绩效", "按科室对比工作量、收入、床位效率和费用结构。", "精细化运营")
    perf = get_department_performance()
    top = perf.head(6)
    col_a, col_b = st.columns([1.15, 1])
    with col_a:
        section_title("收入与门诊量对比", "本月")
        fig = px.scatter(
            perf,
            x="visit_count",
            y="total_income",
            size="inpatient_count",
            color="avg_bed_occupancy_rate",
            hover_name="department_name",
            color_continuous_scale=["#58d4d8", "#34d66f", "#f6c85f", "#ff6370"],
            labels={
                "visit_count": "门诊量",
                "total_income": "总收入",
                "inpatient_count": "住院人数",
                "avg_bed_occupancy_rate": "床位使用率",
            },
        )
        st.plotly_chart(style_fig(fig, 360), width="stretch")
    with col_b:
        section_title("费用结构风险", "药品/耗材")
        fig = go.Figure()
        fig.add_bar(x=top["department_name"], y=top["drug_ratio"], name="药占比", marker_color=GREEN)
        fig.add_bar(x=top["department_name"], y=top["material_ratio"], name="耗材占比", marker_color=YELLOW)
        fig.update_layout(barmode="group")
        st.plotly_chart(style_fig(fig, 360), width="stretch")

    section_title("科室运营明细", "管理表")
    st.dataframe(perf.rename(columns=COLUMN_LABELS), width="stretch", hide_index=True, height=420)


def render_insurance_risk() -> None:
    render_header(
        "医保控费观察",
        "基于模拟 DRG/DIP 病组和病例费用记录，观察科室经营风险；不做正式医保结算预测。",
        "轻量风控",
    )
    month_start, month_end, recent_start, recent_end = risk_date_window()
    summary = risk_scorer.get_risk_summary(month_start, month_end, recent_start, recent_end)
    scores = pd.DataFrame(
        risk_scorer.get_department_risk_scores(month_start, month_end, recent_start, recent_end)
    )
    groups = pd.DataFrame(risk_scorer.get_drg_group_summary(month_start, limit=8))

    cols = st.columns(4)
    with cols[0]:
        render_static_metric("高风险科室", fmt_int(summary["high_risk_department_count"]), "模拟评分 >= 6 分")
    with cols[1]:
        render_static_metric("模拟DRG/DIP亏损", fmt_money(summary["simulated_drg_loss"]), "仅用于控费观察")
    with cols[2]:
        render_static_metric("费用超支病例", fmt_int(summary["overrun_case_count"]), "支付金额低于病例费用")
    with cols[3]:
        render_static_metric("重点关注病例", fmt_int(summary["high_risk_case_count"]), "命中高风险规则")

    st.caption(
        "边界说明：本页使用模拟病组、模拟支付标准和模拟病例费用做风险观察，不代表正式 DRG/DIP 入组、结算或医保审核结果。"
    )

    left, right = st.columns([1.35, 1])
    with left:
        section_title("科室风险排行", "本月")
        if scores.empty:
            st.info("暂无医保控费观察数据。")
        else:
            risk_fig = px.bar(
                scores.head(8),
                x="department_name",
                y="risk_score",
                color="risk_level",
                color_discrete_map={"高": RED, "中": YELLOW, "低": GREEN},
                labels={"department_name": "科室", "risk_score": "风险分", "risk_level": "风险等级"},
            )
            st.plotly_chart(style_fig(risk_fig, 340), width="stretch")

    with right:
        if scores.empty:
            bullets = ["当前没有可展示的科室风险。"]
        else:
            top = scores.iloc[0]
            bullets = [
                f"{top.department_name} 当前风险分 {int(top.risk_score)}，命中：{top.triggered_risks}。",
                f"本月模拟 DRG/DIP 亏损合计 {fmt_money(summary['simulated_drg_loss'])}，建议优先复核费用超支病例。",
                "该模块用于展示产品落地思路，真实上线需接入病案首页、医保结算清单和本地分组规则。",
            ]
        render_assistant_panel(
            "控费观察解读",
            bullets,
            ["风险排行", "模拟亏损", "边界说明"],
        )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        section_title("DRG/DIP 病组模拟盈亏", "观察")
        if groups.empty:
            st.info("暂无模拟病组数据。")
        else:
            group_fig = px.bar(
                groups,
                x="drg_name",
                y="simulated_profit_loss",
                color="risk_level",
                color_discrete_map={"高": RED, "中": YELLOW, "低": GREEN},
                labels={"drg_name": "模拟病组", "simulated_profit_loss": "模拟盈亏", "risk_level": "病组风险"},
            )
            st.plotly_chart(style_fig(group_fig, 380), width="stretch")
    with col_b:
        section_title("病组观察明细", "模拟数据")
        if groups.empty:
            st.info("暂无模拟病组数据。")
        else:
            st.dataframe(groups.rename(columns=COLUMN_LABELS), width="stretch", hide_index=True, height=380)

    section_title("科室风险明细", "可评审表")
    if not scores.empty:
        display_cols = [
            "department_name",
            "risk_score",
            "risk_level",
            "triggered_risks",
            "simulated_drg_loss",
            "overrun_case_count",
            "high_risk_case_count",
            "drug_ratio",
            "material_ratio",
            "avg_bed_occupancy_rate",
            "avg_length_of_stay",
            "suggested_action",
        ]
        st.dataframe(
            scores[display_cols].rename(columns=COLUMN_LABELS),
            width="stretch",
            hide_index=True,
            height=360,
        )


def render_report() -> None:
    render_header("运营简报", "自动生成适合医院管理层阅读的月度运营报告。", "报告生成")
    report_col, assistant_col = st.columns([2, 1])
    with report_col:
        st.markdown(report_generator.generate_monthly_report())
    with assistant_col:
        render_assistant_panel(
            "报告解读",
            [
                "报告基于模拟医院运营数据库自动生成，不包含真实患者隐私。",
                "建议重点关注床位使用率高位科室、费用结构异常和门诊高峰科室。",
                "后续可接入 HIS、医保结算、病案首页和绩效系统，扩展 DRG/DIP 分析。",
            ],
            ["导出报告", "补充真实数据", "生成周报"],
        )


def render_knowledge() -> None:
    render_header("医管知识库", "解释指标口径、医保控费、DRG/DIP 和绩效考核制度。", "RAG")
    for doc in kb.documents:
        with st.expander(doc.title):
            st.markdown(doc.content)


def render_change_log() -> None:
    render_header("改动记录", "本次基于参考 UI 对项目做的页面和内容升级。", "过程表")
    st.dataframe(pd.DataFrame(CHANGE_LOG), width="stretch", hide_index=True, height=340)
    section_title("页面骨架", "Vibe Skeleton")
    page_df = pd.DataFrame(PAGE_REGISTRY).rename(
        columns={"label": "页面", "module": "模块名", "purpose": "页面职责"}
    )
    st.dataframe(page_df, width="stretch", hide_index=True, height=280)
    st.markdown(
        """
        ### 升级前后差异

        - 升级前：页面以问答、表格和简报为主，展示偏 Demo。
        - 升级后：增加运营总览、趋势分析、科室绩效、AI 助手、知识库和改动记录，整体更接近医管后台。
        - 数据边界：当前仍使用模拟数据库，适合演示系统能力；真实落地需要接入 HIS、财务、病案首页和医保结算数据。
        """
    )


def render_sidebar() -> str:
    st.sidebar.markdown(
        """
        <div class="brand">
            <div class="brand-name">MedOps AI</div>
            <div class="brand-sub">Hospital Management Intelligence</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(f"**{principal.display_name}**")
    st.sidebar.caption(f"{principal.role_label} · {principal.department_name}")
    st.sidebar.caption("数据范围：本科室" if principal.role == "director" else "数据范围：本人门诊与手术工作量")
    if st.sidebar.button("退出登录", width="stretch"):
        logout(auth_store)
    page = st.sidebar.radio(
        "导航",
        allowed_pages(principal),
        label_visibility="collapsed",
        key=f"navigation_{principal.user_id}",
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown("**系统状态**")
    st.sidebar.markdown("<span class='tag'>数据库正常</span><span class='tag'>SQL Guard 已启用</span>", unsafe_allow_html=True)
    st.sidebar.caption(f"最新数据日期：{LATEST_DATE}")
    return page


def render_current_page(page: str) -> None:
    require_page(principal, page)
    page_renderers = {
        "我的工作台": render_doctor_dashboard,
        "个人工作量": render_doctor_workload,
        "运营总览": render_dashboard,
        "浮窗问答": render_floating_qa,
        "智能问答": render_qa,
        "趋势分析": render_trends,
        "科室绩效": render_department_page,
        "医保控费观察": render_insurance_risk,
        "运营简报": render_report,
        "医管知识库": render_knowledge,
        "改动记录": render_change_log,
    }
    page_renderers[page]()


def render_doctor_dashboard() -> None:
    render_header("我的工作台", f"{escape(principal.display_name)}，欢迎回来。以下仅展示本人工作量，数据截至 {LATEST_DATE}。", "医生工作台")
    visits = query_value(f"SELECT COUNT(*) FROM outpatient_visits WHERE visit_date >= '{MONTH_START}' AND visit_date < '{MONTH_END}'")
    surgeries = query_value(f"SELECT COUNT(*) FROM surgery_records WHERE surgery_date >= '{MONTH_START}' AND surgery_date < '{MONTH_END}'")
    days = query_value(f"SELECT COUNT(DISTINCT visit_date) FROM outpatient_visits WHERE visit_date >= '{MONTH_START}' AND visit_date < '{MONTH_END}'")
    a, b, c = st.columns(3)
    with a:
        render_static_metric("本月接诊人次", fmt_int(visits), "本人门诊记录")
    with b:
        render_static_metric("本月参与手术", fmt_int(surgeries), "本人手术记录")
    with c:
        render_static_metric("本月有接诊记录天数", fmt_int(days), "按就诊日期去重")
    st.write("")
    render_doctor_workload(show_header=False)


def render_doctor_workload(show_header: bool = True) -> None:
    if show_header:
        render_header("个人工作量", f"仅包含 {escape(principal.display_name)} 本人的门诊与手术记录。", "本人数据")
    trend = query_df(f"""SELECT visit_date AS day,COUNT(*) AS visit_count FROM outpatient_visits
        WHERE visit_date >= '{TREND_START}' AND visit_date <= '{LATEST_DATE}' GROUP BY visit_date ORDER BY visit_date""")
    section_title("我的接诊趋势", "近60天")
    if trend.empty:
        st.info("当前范围内暂无本人门诊记录。")
    else:
        fig = px.line(trend, x="day", y="visit_count", markers=True,
                      labels={"day": "日期", "visit_count": "接诊人次"})
        st.plotly_chart(style_fig(fig, 300), width="stretch")
    left, right = st.columns(2)
    with left:
        section_title("每日接诊明细", "本人数据")
        st.dataframe(trend.rename(columns={"day": "日期", "visit_count": "接诊人次"}), width="stretch", hide_index=True)
    with right:
        section_title("本月手术工作量", "按级别汇总")
        surgery = query_df(f"""SELECT surgery_level,COUNT(*) AS surgery_count,
            ROUND(AVG(duration_minutes),1) AS avg_duration_minutes FROM surgery_records
            WHERE surgery_date >= '{MONTH_START}' AND surgery_date < '{MONTH_END}' GROUP BY surgery_level""")
        if surgery.empty:
            st.info("本月暂无本人手术记录。")
        else:
            st.dataframe(surgery.rename(columns=COLUMN_LABELS), width="stretch", hide_index=True)


def render_doctor_qa() -> None:
    render_header("智能问答", "查询本人工作量，或查阅公共医管知识。", "医生助手")
    mode = st.radio("查询内容", ("个人工作量查询", "公共知识问答"), horizontal=True)
    samples = ["本月本人门诊量是多少？", "本月本人手术量按级别分布。"] if mode == "个人工作量查询" else ["药占比是什么意思？", "DRG/DIP支付下医院运营应关注哪些指标？"]
    example = st.selectbox("示例问题", samples)
    question = st.text_input("自定义问题", placeholder="输入你想了解的问题")
    st.caption("数据查询始终限定本人，不提供科室收入、绩效、医保风险和管理报告。")
    if st.button("开始查询", type="primary"):
        question = question.strip() or example
        if mode == "公共知识问答":
            result = kb.answer(question)
            st.write(result["answer"])
            if result["sources"]:
                st.caption("来源：" + "、".join(item["title"] for item in result["sources"]))
        else:
            try:
                result = sql_agent.ask(question)
                st.dataframe(pd.DataFrame(result.rows).rename(columns=COLUMN_LABELS), width="stretch", hide_index=True)
                for note in result.analysis:
                    st.write(note)
            except PermissionError as exc:
                st.warning(str(exc))


sql_agent, kb, report_generator, risk_scorer = get_agents(principal)
page = render_sidebar()
st.caption(f"当前身份：{principal.role_label} · {principal.department_name} · " + ("本科室数据" if principal.role == "director" else "本人数据"))
render_current_page(page)
