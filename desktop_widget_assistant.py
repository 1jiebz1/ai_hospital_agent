from __future__ import annotations

import sys
import tkinter as tk
import webbrowser
from pathlib import Path


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
    "DRG/DIP支付下医院运营应关注哪些指标？",
]

COLUMN_LABELS = {
    "department_name": "科室",
    "doctor_name": "医生",
    "title": "职称",
    "visit_count": "门诊量",
    "total_income": "总收入",
    "drug_ratio": "药占比",
    "item_ratio": "项目占比",
    "avg_bed_occupancy_rate": "床位使用率",
    "max_bed_occupancy_rate": "最高使用率",
    "avg_length_of_stay": "平均住院日",
    "inpatient_count": "住院人数",
    "bed_turnover_times": "床位周转",
    "surgery_level": "手术级别",
    "surgery_count": "手术量",
}


class DesktopWidget(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        sign_in(self)
        self.title("AI 医管小拖件")
        self.geometry("420x560+980+120")
        self.configure(bg="#07110f")
        self.attributes("-topmost", True)
        self.overrideredirect(True)

        self.drag_x = 0
        self.drag_y = 0
        self.expanded = True

        self.sql_agent = HospitalSQLAgent(ROOT / "data/hospital.db", ROOT / "data/hospital_schema.json", self.principal)
        self.kb = HospitalKnowledgeBase(ROOT / "hospital_docs")
        self.report_generator = HospitalReportGenerator(self.sql_agent) if self.principal.role == "director" else None
        self.examples = EXAMPLES if self.principal.role == "director" else ["本月本人门诊量是多少？", "本月本人手术量是多少？", "DRG/DIP支付下医院运营应关注哪些指标？"]

        self._build()

    def _build(self) -> None:
        self.shell = tk.Frame(self, bg="#0d1714", highlightbackground="#2c4638", highlightthickness=1)
        self.shell.pack(fill="both", expand=True)

        self.header = tk.Frame(self.shell, bg="#123322", height=44)
        self.header.pack(fill="x")
        self.header.bind("<ButtonPress-1>", self._start_drag)
        self.header.bind("<B1-Motion>", self._drag)

        self.title_label = tk.Label(
            self.header,
            text=f"{self.principal.role_label} · {self.principal.department_name}",
            bg="#123322",
            fg="#34d66f",
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.title_label.pack(side="left", padx=12)
        self.title_label.bind("<ButtonPress-1>", self._start_drag)
        self.title_label.bind("<B1-Motion>", self._drag)

        tk.Button(
            self.header,
            text="×",
            command=lambda: sign_out(self),
            bg="#123322",
            fg="#edf6f1",
            activebackground="#1c4a32",
            activeforeground="#ffffff",
            bd=0,
            font=("Microsoft YaHei UI", 12, "bold"),
            width=3,
        ).pack(side="right")
        tk.Button(
            self.header,
            text="－",
            command=self.toggle,
            bg="#123322",
            fg="#edf6f1",
            activebackground="#1c4a32",
            activeforeground="#ffffff",
            bd=0,
            font=("Microsoft YaHei UI", 12, "bold"),
            width=3,
        ).pack(side="right")

        self.body = tk.Frame(self.shell, bg="#07110f")
        self.body.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(
            self.body,
            text="拖动顶部可移动；输入问题后显示结果",
            bg="#07110f",
            fg="#8fa39a",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w")

        self.example_var = tk.StringVar(value=self.examples[0])
        self.example_menu = tk.OptionMenu(self.body, self.example_var, *self.examples)
        self.example_menu.configure(bg="#111a17", fg="#edf6f1", activebackground="#143626", activeforeground="#34d66f", bd=0)
        self.example_menu.pack(fill="x", pady=(8, 8))

        self.question = tk.Text(
            self.body,
            height=3,
            bg="#0d1714",
            fg="#edf6f1",
            insertbackground="#34d66f",
            relief="flat",
            font=("Microsoft YaHei UI", 10),
            wrap="word",
        )
        self.question.pack(fill="x")

        btn_row = tk.Frame(self.body, bg="#07110f")
        btn_row.pack(fill="x", pady=8)
        self._button(btn_row, "发送", self.ask).pack(side="left", fill="x", expand=True)
        self._button(btn_row, "用示例", self.use_example).pack(side="left", padx=6)
        self._button(btn_row, "网页", lambda: webbrowser.open("http://localhost:8501")).pack(side="right")
        self._button(btn_row, "退出", lambda: sign_out(self)).pack(side="right", padx=4)

        self.status = tk.Label(self.body, text="等待提问", bg="#07110f", fg="#8fa39a", font=("Microsoft YaHei UI", 9))
        self.status.pack(anchor="w", pady=(2, 6))

        self.output = tk.Text(
            self.body,
            height=16,
            bg="#0d1714",
            fg="#edf6f1",
            insertbackground="#34d66f",
            relief="flat",
            font=("Microsoft YaHei UI", 10),
            wrap="word",
        )
        self.output.pack(fill="both", expand=True)
        self._set_output("这里会显示分析结论和简要数据。\n")

    def _button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg="#34d66f",
            fg="#04100b",
            activebackground="#63ef94",
            activeforeground="#04100b",
            bd=0,
            padx=10,
            pady=7,
            font=("Microsoft YaHei UI", 9, "bold"),
        )

    def _start_drag(self, event: tk.Event) -> None:
        self.drag_x = event.x
        self.drag_y = event.y

    def _drag(self, event: tk.Event) -> None:
        x = self.winfo_x() + event.x - self.drag_x
        y = self.winfo_y() + event.y - self.drag_y
        self.geometry(f"+{x}+{y}")

    def toggle(self) -> None:
        if self.expanded:
            self.body.pack_forget()
            self.geometry("230x44")
            self.expanded = False
        else:
            self.body.pack(fill="both", expand=True, padx=12, pady=12)
            self.geometry("420x560")
            self.expanded = True

    def use_example(self) -> None:
        self.question.delete("1.0", "end")
        self.question.insert("1.0", self.example_var.get())

    def ask(self) -> None:
        if not check_session(self):
            return
        question = self.question.get("1.0", "end").strip() or self.example_var.get()
        self.status.configure(text="分析中...")
        self.update_idletasks()
        try:
            decision = route_question(question)
            lines = [f"问题：{question}", f"类型：{decision.route}", ""]

            if decision.route in {"sql", "hybrid"}:
                result = self.sql_agent.ask(question, limit=6)
                lines.append("分析结论：")
                lines.extend(f"- {note}" for note in result.analysis)
                if result.rows:
                    lines.append("\n数据结果：")
                    lines.extend(self._format_rows(result.rows))

            if decision.route in {"rag", "hybrid"}:
                rag = self.kb.answer(question)
                lines.append("\n知识库回答：")
                lines.append(rag["answer"])

            if decision.route == "report":
                self.principal.require_director()
                lines.append(self.report_generator.generate_monthly_report(question))

            self._set_output("\n".join(lines))
            self.status.configure(text="完成")
        except Exception as exc:
            self._set_output(f"运行出错：{exc}")
            self.status.configure(text="出错")

    def _format_rows(self, rows: list[dict]) -> list[str]:
        formatted = []
        for row in rows[:6]:
            parts = []
            for key, value in row.items():
                label = COLUMN_LABELS.get(key, key)
                parts.append(f"{label}: {value}")
            formatted.append("；".join(parts))
        return formatted

    def _set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")


if __name__ == "__main__":
    widget = DesktopWidget()
    widget.mainloop()
