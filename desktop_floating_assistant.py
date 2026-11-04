from __future__ import annotations

import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.rag_agent import HospitalKnowledgeBase
from src.report_generator import HospitalReportGenerator
from src.router import route_question
from src.sql_agent import HospitalSQLAgent
from src.desktop_auth import sign_in, sign_out, check_session


EXAMPLES = [
    "最近7天床位使用率超过90%的科室有哪些？",
    "本月门诊量最高的5个科室是哪些？",
    "统计2026年5月各科室收入排名。",
    "本月耗材收入占比最高的科室有哪些？",
    "2026年5月平均住院日最高的科室有哪些？",
    "DRG/DIP支付下医院运营应关注哪些指标？",
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
}


class FloatingAssistant(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        sign_in(self)
        self.title("MedOps AI 桌面浮窗")
        self.geometry("460x620+980+120")
        self.minsize(390, 460)
        self.configure(bg="#07110f")
        self.attributes("-topmost", True)

        self.sql_agent = HospitalSQLAgent(ROOT / "data/hospital.db", ROOT / "data/hospital_schema.json", self.principal)
        self.kb = HospitalKnowledgeBase(ROOT / "hospital_docs")
        self.report_generator = HospitalReportGenerator(self.sql_agent) if self.principal.role == "director" else None
        self.examples = EXAMPLES if self.principal.role == "director" else ["本月本人门诊量是多少？", "本月本人手术量是多少？", "DRG/DIP支付下医院运营应关注哪些指标？"]

        self._configure_style()
        self._build_ui()

    def _configure_style(self) -> None:
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#07110f")
        self.style.configure("Card.TFrame", background="#111a17", borderwidth=1, relief="solid")
        self.style.configure("TLabel", background="#07110f", foreground="#edf6f1")
        self.style.configure("Muted.TLabel", background="#07110f", foreground="#8fa39a")
        self.style.configure("Title.TLabel", background="#07110f", foreground="#34d66f", font=("Microsoft YaHei UI", 15, "bold"))
        self.style.configure("TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=8)
        self.style.configure("Treeview", background="#0d1714", foreground="#edf6f1", fieldbackground="#0d1714", rowheight=28)
        self.style.configure("Treeview.Heading", background="#143626", foreground="#34d66f", font=("Microsoft YaHei UI", 9, "bold"))

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(16, 14, 16, 8))
        header.pack(fill="x")

        title_row = ttk.Frame(header)
        title_row.pack(fill="x")
        ttk.Label(title_row, text="MedOps AI", style="Title.TLabel").pack(side="left")
        self.topmost_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(title_row, text="置顶", variable=self.topmost_var, command=self._toggle_topmost).pack(side="right")

        ttk.Label(header, text=f"{self.principal.display_name} · {self.principal.role_label} · {self.principal.department_name}", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(self, padding=(16, 8, 16, 14))
        body.pack(fill="both", expand=True)

        input_card = ttk.Frame(body, style="Card.TFrame", padding=12)
        input_card.pack(fill="x")
        ttk.Label(input_card, text="快速问题").pack(anchor="w")
        self.example_var = tk.StringVar(value=self.examples[0])
        self.example_box = ttk.Combobox(input_card, textvariable=self.example_var, values=self.examples, state="readonly")
        self.example_box.pack(fill="x", pady=(4, 10))

        ttk.Label(input_card, text="自定义问题").pack(anchor="w")
        self.question_text = tk.Text(
            input_card,
            height=3,
            bg="#0d1714",
            fg="#edf6f1",
            insertbackground="#34d66f",
            relief="flat",
            font=("Microsoft YaHei UI", 10),
            wrap="word",
        )
        self.question_text.pack(fill="x", pady=(4, 10))

        buttons = ttk.Frame(input_card)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="发送", command=self.ask).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="用示例", command=self.use_example).pack(side="left", padx=8)
        ttk.Button(buttons, text="打开网页", command=lambda: webbrowser.open("http://localhost:8501")).pack(side="right")
        ttk.Button(buttons, text="退出登录", command=lambda: sign_out(self)).pack(side="right", padx=4)

        self.status_var = tk.StringVar(value="等待提问")
        ttk.Label(body, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(10, 4))

        self.output = tk.Text(
            body,
            height=9,
            bg="#0d1714",
            fg="#edf6f1",
            insertbackground="#34d66f",
            relief="flat",
            font=("Microsoft YaHei UI", 10),
            wrap="word",
        )
        self.output.pack(fill="x")
        self.output.insert("1.0", "输入问题后，这里会显示分析结论。\n")
        self.output.configure(state="disabled")

        table_card = ttk.Frame(body, style="Card.TFrame", padding=8)
        table_card.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Label(table_card, text="数据结果").pack(anchor="w")

        self.table = ttk.Treeview(table_card, show="headings", height=7)
        self.table.pack(fill="both", expand=True, pady=(6, 0))
        y_scroll = ttk.Scrollbar(self.table, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=y_scroll.set)
        y_scroll.pack(side="right", fill="y")

        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="清空", command=self.clear).pack(side="left")
        ttk.Button(footer, text="收起到小窗", command=self.compact).pack(side="right")

    def _toggle_topmost(self) -> None:
        self.attributes("-topmost", self.topmost_var.get())

    def use_example(self) -> None:
        self.question_text.delete("1.0", "end")
        self.question_text.insert("1.0", self.example_var.get())

    def clear(self) -> None:
        self.question_text.delete("1.0", "end")
        self._set_output("输入问题后，这里会显示分析结论。\n")
        self.status_var.set("等待提问")
        self._set_table([])

    def compact(self) -> None:
        self.geometry("360x260+1040+160")

    def ask(self) -> None:
        if not check_session(self):
            return
        question = self.question_text.get("1.0", "end").strip() or self.example_var.get()
        if not question:
            return

        self.status_var.set("分析中...")
        self.update_idletasks()

        try:
            decision = route_question(question)
            lines = [f"问题：{question}", f"任务类型：{decision.route}", ""]
            rows = []

            if decision.route in {"sql", "hybrid"}:
                result = self.sql_agent.ask(question, limit=8)
                rows = result.rows
                lines.append("分析结论：")
                lines.extend(f"- {note}" for note in result.analysis)

            if decision.route in {"rag", "hybrid"}:
                rag = self.kb.answer(question)
                lines.append("\n知识库回答：")
                lines.append(rag["answer"])

            if decision.route == "report":
                self.principal.require_director()
                lines.append(self.report_generator.generate_monthly_report(question))

            self._set_output("\n".join(lines))
            self._set_table(rows)
            self.status_var.set("完成")
        except Exception as exc:
            self._set_output(f"运行出错：{exc}")
            self.status_var.set("出错")

    def _set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def _set_table(self, rows: list[dict]) -> None:
        self.table.delete(*self.table.get_children())
        if not rows:
            self.table["columns"] = []
            return

        columns = list(rows[0].keys())
        self.table["columns"] = columns
        for column in columns:
            label = COLUMN_LABELS.get(column, column)
            self.table.heading(column, text=label)
            self.table.column(column, width=max(90, len(label) * 16), anchor="center", stretch=True)

        for row in rows:
            values = [row.get(column, "") for column in columns]
            self.table.insert("", "end", values=values)


if __name__ == "__main__":
    app = FloatingAssistant()
    app.mainloop()
