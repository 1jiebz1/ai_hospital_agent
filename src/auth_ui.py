"""Plan B login presentation with the existing account and permission model."""
from urllib.parse import quote
import streamlit as st
from .auth import AuthStore, Principal


def _icon(paths):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true">' + paths + '</svg>')


LOGO = _icon('<path d="M3 12h4l2-5 4 10 2-5h6"/>')
USER_ICON = quote(_icon('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>').replace('currentColor', '#6b7a72'))
LOCK_ICON = quote(_icon('<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>').replace('currentColor', '#6b7a72'))

LOGIN_CSS = """<style>
.stApp:has(#login-brand) {background:var(--bg);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;}
.stApp:has(#login-brand) [data-testid="stSidebar"],
.stApp:has(#login-brand) [data-testid="stHeader"],
.stApp:has(#login-brand) [data-testid="stToolbar"],
.stApp:has(#login-brand) footer {display:none!important;}
.stApp:has(#login-brand) [data-testid="stMainBlockContainer"] {max-width:none!important;min-height:100svh;padding:0 0 0 52vw!important;}
.stApp:has(#login-brand) [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {min-height:100svh;justify-content:center;gap:0;}
.stApp:has(#login-brand) [data-testid="stElementContainer"]:has(#login-brand) {height:0;margin:0;}
#login-brand {box-sizing:border-box;position:fixed;inset:0 auto 0 0;width:52vw;height:100svh;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:clamp(28px,4vw,54px);color:var(--text);border-right:1px solid var(--border);background:linear-gradient(160deg,var(--bg) 0%,#0c2a22 55%,#0b3a2e 100%);}
#login-brand::before {content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(237,246,241,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(237,246,241,.045) 1px,transparent 1px);background-size:44px 44px;pointer-events:none;}
#login-brand::after {content:"";position:absolute;width:560px;height:560px;top:-180px;right:-180px;background:radial-gradient(circle,rgba(52,214,111,.16),transparent 66%);pointer-events:none;}
#login-brand > * {position:relative;z-index:1;}
.login-logo {display:flex;align-items:center;gap:11px;font-size:16px;font-weight:700;}
.login-mark,.login-feature-icon {display:flex;align-items:center;justify-content:center;flex-shrink:0;width:34px;height:34px;background:var(--green-soft);border:1px solid var(--border);border-radius:9px;color:var(--green);}
.stApp:has(#login-brand) #login-brand h2 {font-size:28px!important;font-weight:700;line-height:1.42;max-width:420px;margin:0;padding:0;}
#login-brand h2 em {font-style:normal;color:var(--green);}
#login-brand .login-copy {font-size:13.2px;line-height:1.85;color:var(--muted);max-width:400px;margin:14px 0 0;}
.login-features {display:flex;flex-direction:column;gap:18px;margin-top:32px;}
.login-feature {display:flex;align-items:flex-start;gap:12px;max-width:430px;}
.login-feature-title {font-size:13.6px;font-weight:600;}
.login-feature-desc {font-size:12.4px;color:var(--muted);line-height:1.6;margin-top:3px;}
.login-copyright {font-size:12px;color:rgba(237,246,241,.5);margin-top:28px;}
.stApp:has(#login-brand) .st-key-login_panel {box-sizing:border-box;width:360px;max-width:calc(48vw - 64px);margin:40px auto;}
.login-mobile-brand {display:none;margin-bottom:28px;}
.login-welcome {font-size:22px;font-weight:700;line-height:1.4;color:var(--text);}
.login-subtitle {font-size:13.2px;color:var(--muted);margin:7px 0 24px;}
.stApp:has(#login-brand) [data-testid="stForm"] {padding:0;border:none;background:transparent;}
.stApp:has(#login-brand) [data-testid="stTextInput"] label p {font-size:12.8px!important;font-weight:600;}
.stApp:has(#login-brand) [data-testid="stTextInputRootElement"] {background:#0d1512;border:1px solid var(--border);border-radius:9px;}
.stApp:has(#login-brand) [data-testid="stTextInputRootElement"]:focus-within {border-color:var(--green);box-shadow:0 0 0 3px rgba(52,214,111,.18);}
.stApp:has(#login-brand) [data-testid="stTextInput"] input {height:42px;min-height:42px;font-size:14px;padding-left:38px;color:var(--text);background-color:transparent;background-repeat:no-repeat!important;background-position:12px center!important;background-size:16px 16px!important;}
.stApp:has(#login-brand) [data-testid="stTextInput"] input[aria-label="账号"] {background-image:url("data:image/svg+xml,__USER_ICON__")!important;}
.stApp:has(#login-brand) [data-testid="stTextInput"] input[aria-label="密码"] {background-image:url("data:image/svg+xml,__LOCK_ICON__")!important;}
.stApp:has(#login-brand) input::placeholder {color:#6b7a72!important;opacity:1;}
.stApp:has(#login-brand) [data-testid="stCheckbox"] label p {font-size:13px!important;color:var(--muted);}
.stApp:has(#login-brand) [data-testid="stPopover"] button {border:0;background:transparent;color:var(--green);font-size:13px;padding:0;min-height:0;}
.stApp:has(#login-brand) [data-testid="stPopover"] button p {color:var(--green);font-size:13px;}
.stApp:has(#login-brand) [data-testid="stPopover"] svg {display:none;}
.stApp:has(#login-brand) [data-testid="stFormSubmitButton"] button {height:44px;width:100%;border:0;border-radius:9px;background:var(--green);color:var(--bg);font-weight:600;}
.stApp:has(#login-brand) [data-testid="stFormSubmitButton"] button:hover {background:#2bbf60;color:var(--bg);}
.stApp:has(#login-brand) [data-testid="stFormSubmitButton"] button p {color:var(--bg);font-size:14px;font-weight:600;}
.stApp:has(#login-brand) [data-testid="stFormSubmitButton"] button:disabled {opacity:.65;}
.stApp:has(#login-brand) .st-key-login_error [data-testid="stAlert"] {background:#2a1513;border:1px solid #5c2a24;color:#ffb3ab;border-radius:8px;}
.stApp:has(#login-brand) .st-key-login_error [data-testid="stAlert"] p {color:#ffb3ab;font-size:12.8px;}
.login-footer {margin-top:22px;text-align:center;font-size:12px;line-height:1.7;color:var(--muted);}
@media(max-width:860px) {
 #login-brand {display:none;}
 .stApp:has(#login-brand) [data-testid="stMainBlockContainer"] {padding:0 24px!important;}
 .stApp:has(#login-brand) .st-key-login_panel {width:360px;max-width:100%;margin:40px auto;}
 .login-mobile-brand {display:flex;}
 .stApp:has(#login-brand) .st-key-login_panel [data-testid="stHorizontalBlock"] {flex-wrap:nowrap;}
 .stApp:has(#login-brand) .st-key-login_panel [data-testid="stColumn"] {min-width:0;flex:1 1 0;width:auto;}
}
@media(max-height:650px) and (min-width:861px) {
 #login-brand {overflow-y:auto;}
 #login-brand .login-features {gap:12px;margin-top:20px;}
 #login-brand .login-logo {margin-bottom:24px;}
}
</style>""".replace('__USER_ICON__', USER_ICON).replace('__LOCK_ICON__', LOCK_ICON)


def _brand_html():
    features = [
        ('<path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 5-6"/>',
         "运营总览 · 一句话查数", "门诊量、床位使用率、药占比，开口即得"),
        ('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
         "医保控费 · 风险观察", "科室风险评分，异常尽早发现"),
        ('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
         "运营简报 · 自动生成", "月度分析与管理建议，管理层可直接读"),
    ]
    items = ''.join(f'<div class="login-feature"><div class="login-feature-icon">{_icon(icon)}</div>'
                    f'<div><div class="login-feature-title">{title}</div>'
                    f'<div class="login-feature-desc">{description}</div></div></div>'
                    for icon, title, description in features)
    return (f'<section id="login-brand" aria-label="产品介绍">'
            f'<div class="login-logo"><span class="login-mark">{LOGO}</span>AI 医管智能体</div>'
            '<div><h2>让医院运营数据<br><em>开口说话</em></h2>'
            '<p class="login-copy">自然语言查询、医保控费观察与管理简报，一站完成。所有患者与运营数据均为演示模拟数据。</p>'
            f'<div class="login-features">{items}</div></div>'
            '<div class="login-copyright">© 2026 AI 医管智能体 · 内部演示</div></section>')


def logout(store: AuthStore) -> None:
    remembered = st.session_state.get("remembered_username")
    store.logout(st.session_state.get("auth_token"))
    st.session_state.clear()
    if remembered:
        st.session_state["remembered_username"] = remembered
    st.rerun()


def require_login(store: AuthStore) -> Principal:
    principal = store.get_session(st.session_state.get("auth_token"))
    if principal:
        return principal
    if "auth_token" in st.session_state:
        remembered = st.session_state.get("remembered_username")
        st.session_state.clear()
        if remembered:
            st.session_state["remembered_username"] = remembered
        st.session_state["login_notice"] = "登录已过期，请重新登录。"

    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    st.markdown(_brand_html(), unsafe_allow_html=True)
    busy = "_login_request" in st.session_state
    with st.container(key="login_panel"):
        st.markdown(f'<div class="login-logo login-mobile-brand"><span class="login-mark">{LOGO}</span>AI 医管智能体</div>'
                    '<div class="login-welcome" role="heading" aria-level="1">欢迎回来</div>'
                    '<div class="login-subtitle">请使用管理员分配的账号登录工作台</div>', unsafe_allow_html=True)
        if error := st.session_state.pop("login_error", None):
            with st.container(key="login_error"):
                st.error(error)
        if notice := st.session_state.pop("login_notice", None):
            st.info(notice)
        if not store.has_users():
            st.info("账号尚未开通，请联系系统管理员完成首次账号配置。")
        with st.form("login_form", clear_on_submit=True, border=False):
            username = st.text_input("账号", value=st.session_state.get("remembered_username", ""),
                                     placeholder="工号或用户名", max_chars=80, disabled=busy)
            password = st.text_input("密码", type="password", placeholder="请输入密码", max_chars=256, disabled=busy)
            remember_col, forgot_col = st.columns([1, 1], vertical_alignment="center")
            with remember_col:
                remember = st.checkbox("记住账号", value=bool(st.session_state.get("remembered_username")),
                                       help="仅在当前浏览器会话记住账号，不保存密码或延长登录有效期。", disabled=busy)
            with forgot_col:
                with st.popover("忘记密码？", use_container_width=True):
                    st.info("请联系系统管理员重置密码。")
            submitted = st.form_submit_button("登录中…" if busy else "登录", type="primary", width="stretch", disabled=busy)
        st.markdown('<div class="login-footer">演示环境 · 模拟数据 · 按账号权限访问</div>', unsafe_allow_html=True)

    if submitted and not busy:
        if not username.strip() or not password:
            st.session_state["login_error"] = "请输入账号和密码"
        else:
            # One rerun presents the disabled loading state before authentication.
            st.session_state["_login_request"] = (username.strip(), password, remember)
        st.rerun()
    if busy:
        username, password, remember = st.session_state.pop("_login_request")
        with st.spinner("登录中…"):
            token = store.authenticate(username, password)
        if token:
            st.session_state.clear()
            st.session_state["auth_token"] = token
            if remember:
                st.session_state["remembered_username"] = username
        else:
            st.session_state["login_error"] = "账号或密码不正确"
        st.rerun()
    st.stop()
