"""Use the same accounts and scope for both local desktop entry points."""
import tkinter as tk
from tkinter import messagebox
from .auth import AuthStore


def sign_in(root):
    root.withdraw()
    store = AuthStore()
    dialog = tk.Toplevel(root)
    dialog.title("MedOps AI · 登录")
    dialog.geometry("380x350")
    dialog.resizable(False, False)
    dialog.configure(bg="#101c16")
    dialog.attributes("-topmost", True)
    tk.Label(dialog, text="登录医管工作空间", bg="#101c16", fg="#34d66f", font=("Microsoft YaHei UI", 17, "bold")).pack(pady=(25, 10))
    tk.Label(dialog, text="角色由管理员分配的账号确定", bg="#101c16", fg="#9db4a8").pack(pady=(0, 15))
    tk.Label(dialog, text="账号", bg="#101c16", fg="white").pack()
    username = tk.Entry(dialog, width=30)
    username.pack(pady=(4, 10))
    tk.Label(dialog, text="密码", bg="#101c16", fg="white").pack()
    password = tk.Entry(dialog, show="*", width=30)
    password.pack(pady=4)
    error = tk.StringVar()
    tk.Label(dialog, textvariable=error, bg="#101c16", fg="#ff6370", wraplength=340).pack(pady=8)
    result = []

    def submit(event=None):
        token = store.authenticate(username.get(), password.get())
        password.delete(0, "end")
        principal = store.get_session(token)
        if principal:
            result.extend((store, token, principal))
            dialog.destroy()
        else:
            error.set("账号或密码不正确；多次失败后请等待5分钟。")

    tk.Button(dialog, text="登录工作台", command=submit, bg="#34d66f", width=28).pack(pady=4)
    dialog.bind("<Return>", submit)
    username.focus_set()
    root.wait_window(dialog)
    if not result:
        root.destroy()
        raise SystemExit(0)
    root.auth_store, root.auth_token, root.principal = result
    root.deiconify()
    root.protocol("WM_DELETE_WINDOW", lambda: sign_out(root))


def sign_out(root):
    root.auth_store.logout(root.auth_token)
    root.destroy()


def check_session(root):
    if root.auth_store.get_session(root.auth_token) != root.principal:
        messagebox.showinfo("请重新登录", "登录已过期或账号权限发生变化，请重新打开并登录。", parent=root)
        sign_out(root)
        return False
    return True
