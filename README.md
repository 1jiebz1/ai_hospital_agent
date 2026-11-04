# AI 医管智能体

面向医院管理层的智能数据查询、运营分析与报告生成系统。项目由原来的通用 Text-to-SQL 电商数据问答升级而来，重点从“能生成 SQL”升级为“能服务医院运营管理场景”。

> 所有患者、医生、收费和运营明细均为模拟数据，不涉及真实患者隐私，也不提供诊疗建议。

## 核心能力

- 自然语言查询医院运营数据：门诊量、科室收入、药品收入占比、床位使用率、平均住院日、手术量。
- SQL 安全校验：只允许单条 SELECT，禁止修改性 SQL，默认补 LIMIT。
- 医院管理知识库：解释指标口径、绩效管理、医保控费和手术分级。
- 医管后台驾驶舱：运营总览、趋势分析、科室绩效、智能问答、知识库和改动记录。
- 图表可视化：使用 Streamlit 和 Plotly 展示 KPI 卡片、表格、柱状图、饼图和趋势图。
- 医保控费观察：基于模拟 DRG/DIP 病组、模拟支付标准和病例费用记录，生成科室风险评分。
- 运营简报：自动生成月度医院运营分析报告和管理建议。
- 桌面小组件：支持置顶、拖动、折叠的 AI 医管桌面小拖件。
- 前端骨架治理：沉淀页面注册、设计 token、组件复用规则和 Vibe Coding 前端骨架说明。

## 项目结构

```text
ai_hospital_agent/
├── app.py
├── desktop_floating_assistant.py
├── desktop_widget_assistant.py
├── README.md
├── requirements.txt
├── data/
│   ├── hospital.db
│   └── hospital_schema.json
├── docs/
│   ├── frontend_skeleton.md
│   ├── optimization_comparison.md
│   ├── project_experience_updates.md
│   ├── product_landing_plan.md
│   ├── product_review_checklist.md
│   └── ui_upgrade_change_log.md
├── hospital_docs/
├── skills/
│   └── vibe-frontend-skeleton/
├── scripts/
│   └── generate_hospital_data.py
└── src/
    ├── analysis.py
    ├── charts.py
    ├── rag_agent.py
    ├── report_generator.py
    ├── router.py
    ├── sql_agent.py
    ├── sql_guard.py
    └── prompts.py
```

## 运行方式

使用 Python 3.11 或更高版本。新增登录与角色隔离：

| 账号角色 | 可用功能 | 数据范围 |
|---|---|---|
| 科室主任 | 运营总览、趋势、科室绩效、医保观察、问答、简报、公共知识库 | 账号绑定的本科室 |
| 医生 | 我的工作台、个人工作量、个人问答、公共知识库 | 账号绑定医生本人的门诊与手术工作量 |

角色与科室由管理员建号时分配，登录页不提供自行选择角色或注册。医生不可查看收入、住院明细、医保风险或管理简报。医生个人数据仅保留工作量需要的字段，不暴露患者标识、诊断或收费字段。网页与两个桌面入口共用账号。

```bash
pip install -r requirements.txt
python scripts/manage_users.py demo
streamlit run app.py
```

仓库已带模拟数据库，无需重新生成。`demo` 仅在没有账号时创建主任和医生各一个，绑定现有第一科室和医生，随机密码在终端显示；不会覆盖已有账号。请保存密码，使用打印的 `director` / `doctor` 账号登录。需要重建模拟数据时才运行 `python scripts/generate_hospital_data.py`，重建后需核对账号绑定。

### 账号管理

以下命令仅由系统管理员在服务器或本地终端运行：

```bash
# 查可绑定的科室和医生编号
python scripts/manage_users.py list-bindings
# 创建科室主任，按提示设置密码
python scripts/manage_users.py create --username director_neike --name 张主任 --role director --department-id 1
# 创建医生，医生档案必须属于指定科室
python scripts/manage_users.py create --username doctor_1 --name 医生 --role doctor --department-id 1 --doctor-id 1
# 重置密码，撤销该账号所有旧会话
python scripts/manage_users.py reset-password doctor_1
# 停用账号，旧会话同时失效
python scripts/manage_users.py disable doctor_1
```

密码采用随机盐与 PBKDF2-SHA256 保存；不提供固定默认密码。连续 5 次登录失败后锁定账号尝试 5 分钟。会话有效期 8 小时，退出会撤销服务端会话并清空界面状态；刷新或关闭页面后可能需要重新登录。登录不能持久保存到浏览器。

账号和会话保存在 `data/auth.db`（已排除提交），可通过服务端环境变量 `HOSPITAL_AUTH_DB` 指向持久磁盘。云端部署必须事先用相同管理脚本创建账号，并持久化该文件；没有配置账号时仅显示登录提示，不会开放自助主任注册。原模拟数据库不是账号数据库。

数据访问在服务端创建按角色裁剪的只读内存快照：主任只包含本科室记录；医生仅包含本人工作量所需表和列，原数据库不会挂载给查询连接。查询缓存包含账号范围，退出不影响其他用户。此实现针对当前小型模拟数据库；真实大规模院内数据应迁移到数据库授权视图或行级权限及统一身份服务。

验证登录、页面与数据隔离：

```bash
python -m unittest discover -s tests -v
```

## 在线部署

在线演示地址：<https://ai-hospital-agent.streamlit.app/>

### Streamlit Community Cloud

- Repository：`zhubojie703-maker/ai_hospital_agent`
- Branch：`main`
- Main file path：`app.py`
- Python dependencies：`requirements.txt`

### Render

项目已包含 `render.yaml`。在 Render 中选择从 GitHub 仓库创建 Web Service 或 Blueprint 后，会使用下面的启动命令：

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true
```

启动桌面小组件：

```bash
python desktop_widget_assistant.py
```

Windows 也可以双击：

```text
启动桌面小拖件.bat
```

如果想使用普通窗口版本，可以运行：

```bash
python desktop_floating_assistant.py
```

## 示例问题

- 本月门诊量最高的 5 个科室是哪些？
- 统计 2026 年 5 月各科室收入排名。
- 最近 7 天床位使用率超过 90% 的科室有哪些？
- 本月药占比是多少？
- 本月耗材收入占比最高的科室有哪些？
- 本月各科室床位周转次数是多少？
- DRG/DIP支付下医院运营应关注哪些指标？
- 药占比是什么意思？
- 生成本月医院运营简报。

## 页面模块

| 页面 | 主要内容 |
|---|---|
| 运营总览 | KPI 卡片、门诊/收入趋势、收入结构、床位风险、科室绩效明细、AI 医管助手 |
| 浮窗问答 | 页面内 AI 小浮窗，输入问题后再展开表格、图表和结论 |
| 智能问答 | 自然语言查询、RAG 指标解释、报告生成 |
| 趋势分析 | 近 60 天门诊与收入趋势、费用结构、床位排名、手术级别分布 |
| 科室绩效 | 科室工作量、收入、药品/耗材占比、床位效率对比 |
| 医保控费观察 | 模拟 DRG/DIP 病组、科室风险评分、费用超支病例和边界说明 |
| 运营简报 | 月度运营报告和管理建议 |
| 医管知识库 | 指标口径、医保控费、DRG/DIP、绩效考核文档 |
| 改动记录 | UI 和内容升级过程表 |

## 前端骨架优化

本项目根据 Vibe Coding “先定前端骨架，再让 AI 写页面”的方法做了二次整理，新增了：

- `UI_TOKENS`：集中管理颜色、圆角、文字色和图表色板。
- `PAGE_REGISTRY`：统一维护页面名称、模块名和页面用途。
- `render_current_page`：用页面渲染表替代分散的条件路由。
- `docs/frontend_skeleton.md`：记录设计风格、技术骨架、页面边界和组件复用规则。
- `skills/vibe-frontend-skeleton`：把参考视频蒸馏成可复用 Codex skill，项目下载后也能带走这套前端骨架方法。

## 公开依据与数据说明

本项目的指标口径参考了医院运营管理常见统计方式，并结合公开政策资料进行说明：

- 国家卫生健康委：《三级公立医院绩效监测操作手册（2025版）》通知：<https://www.nhc.gov.cn/yzygj/c100068/202506/6a97e937c58b413d8a0ffdcc23d325d4.shtml>
- 国务院办公厅：《关于加强三级公立医院绩效考核工作的意见》：<https://www.gov.cn/zhengce/content/2019-01/30/content_5362266.htm>
- 国家卫生健康委统计信息中心相关卫生健康统计公报入口：<https://www.nhc.gov.cn/guihuaxxs/s10748/>

由于真实 HIS、财务、医保和病案首页数据涉及隐私与机构授权，本 Demo 使用模拟数据生成器创建 `hospital.db`。模拟数据只用于展示系统逻辑，不能代表真实医院经营水平。

### DRG/DIP 边界说明

本项目新增的“医保控费观察”是轻量模拟模块：它使用模拟病组、模拟支付标准和模拟病例费用记录，展示如何把医院运营数据转化为风险评分和管理复核线索。它不做正式 DRG/DIP 入组、医保结算预测或医保审核判断。真实落地需要接入病案首页、医保结算清单、诊断/手术编码、本地分组规则、支付标准和病例成本。

## 优化对比

| 对比项 | 原 Text-to-SQL 项目 | 优化后的 AI 医管智能体 |
|---|---|---|
| 项目定位 | 通用电商数据问答 | 医院管理层运营分析助手 |
| 数据库 | `ecommerce.db`，用户/商品/订单 | `hospital.db`，科室/医生/门诊/住院/收费/床位/手术 |
| 问题类型 | 销售额、订单、库存 | 门诊量、科室收入、药品收入占比、床位使用率、平均住院日、手术量 |
| 安全约束 | Prompt 中要求只查数据 | 独立 SQL Guard 强制只允许 SELECT，拦截危险 SQL，自动补 LIMIT |
| 知识问答 | 无制度知识库 | `hospital_docs` 支持指标解释、政策和绩效制度问答 |
| 分析能力 | 主要返回查询结果 | 返回数据表、异常提示和管理建议 |
| 风险观察 | 无 | 模拟 DRG/DIP 病组 + 科室风险评分 + 控费边界说明 |
| 可视化 | 命令行输出 | Streamlit 表格 + Plotly 图表 |
| 报告能力 | 无 | 自动生成医院运营月度简报 |
| 简历表达 | Text-to-SQL Demo | Text-to-SQL + RAG + Router + SQL 安全 + 医管分析 + 医保控费观察 |
