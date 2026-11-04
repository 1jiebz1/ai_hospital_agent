"""Streamlit sign-in gate. No business data is read before authentication."""
import streamlit as st

from .auth import AuthStore, Principal


def logout(store: AuthStore) -> None:
    store.logout(st.session_state.get("auth_token"))
    st.session_state.clear()
    st.rerun()


def require_login(store: AuthStore) -> Principal:
    principal = store.get_session(st.session_state.get("auth_token"))
    if principal:
        return principal
    if "auth_token" in st.session_state:
        st.session_state.clear()
        st.session_state["login_notice"] = "登录已过期，请重新登录。"

    st.markdown("""<style>
    [data-testid="stSidebar"] {display:none;}
    .login-brand {font-size:17px;font-weight:800;letter-spacing:2px;color:#34d66f;margin-bottom:38px;}
    .login-title {font-size:42px;line-height:1.25;font-weight:800;color:#edf6f1;margin:0 0 18px;}
    .login-copy {color:#9db4a8;font-size:16px;line-height:1.9;max-width:440px;}
    .login-role {border:1px solid #24372f;background:#111e18;border-radius:12px;padding:18px 22px;margin-top:18px;}
    .login-role strong {color:#edf6f1;display:block;margin-bottom:7px;}
    .login-role span {color:#9db4a8;font-size:14px;}
    [data-testid="stForm"] {border:1px solid #2c4638;border-radius:18px;padding:30px;background:#101c16;}
    [data-testid="stFormSubmitButton"] button {background:#34d66f;color:#04100b;border:1px solid #34d66f;font-weight:800;border-radius:8px;}
    [data-testid="stFormSubmitButton"] button:hover {background:#63ef94;color:#04100b;border-color:#63ef94;}
    input::placeholder {color:#8fa39a !important;opacity:1 !important;}
    </style>""", unsafe_allow_html=True)
    st.write("")
    st.write("")
    _, content, _ = st.columns([0.2, 5, 0.2])
    with content:
        left, gap, right = st.columns([1.15, 0.18, 1])
        with left:
            st.markdown("""<div class="login-brand">MEDOPS AI · 医管工作空间</div>
            <div class="login-title">连接数据与决策，<br>从你的工作台开始。</div>
            <p class="login-copy">登录后进入专属工作空间，查看与你职责相关的数据与分析。</p>
            <div class="login-role"><strong>科室主任</strong><span>本科室运营概况、绩效分析、医保控费与运营简报</span></div>
            <div class="login-role"><strong>医生</strong><span>本人门诊与手术工作量、个人趋势和公共知识库</span></div>""", unsafe_allow_html=True)
        with right:
            st.write("")
            st.write("")
            with st.form("login_form", clear_on_submit=True):
                st.subheader("欢迎登录")
                st.caption("使用管理员分配的账号，进入对应角色的工作台。")
                username = st.text_input("账号", placeholder="请输入账号", max_chars=80)
                password = st.text_input("密码", type="password", placeholder="请输入密码", max_chars=256)
                submitted = st.form_submit_button("登录工作台", type="primary", width="stretch")
            if notice := st.session_state.pop("login_notice", None):
                st.info(notice)
            if not store.has_users():
                st.info("账号尚未开通，请联系系统管理员完成首次账号配置。")
            if submitted:
                token = store.authenticate(username, password) if username and password else None
                if token:
                    # Clears any old account's page, text input and result objects.
                    st.session_state.clear()
                    st.session_state["auth_token"] = token
                    st.rerun()
                st.error("账号或密码不正确；多次失败后请等待 5 分钟再试。")
            st.caption("角色由账号确定，无需手动选择。忘记密码请联系管理员。")
    st.divider()
    st.caption("当前为模拟数据演示系统 · 登录后按账号权限展示数据")
    st.stop()
