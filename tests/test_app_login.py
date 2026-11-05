"""End-to-end Streamlit runs through sign-in, role navigation and sign-out."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from src.auth import AuthStore
from tests.auth_fixtures import PASSWORD

ROOT = Path(__file__).resolve().parents[1]


class TestLoginApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.auth_path = Path(self.tmp.name)/"auth.db"
        self.environment = patch.dict(os.environ,{"HOSPITAL_AUTH_DB":str(self.auth_path)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.store = AuthStore(self.auth_path)
        hospital = ROOT/"data/hospital.db"
        with closing(sqlite3.connect(hospital)) as conn:
            doctors = conn.execute("SELECT doctor_id,department_id,doctor_name FROM doctors ORDER BY doctor_id LIMIT 2").fetchall()
            self.department_name = conn.execute("SELECT department_name FROM departments WHERE department_id=?",(doctors[0][1],)).fetchone()[0]
        self.store.create_user("director",PASSWORD,"测试主任","director",doctors[0][1],hospital)
        self.store.create_user("doctor",PASSWORD,doctors[0][2],"doctor",doctors[0][1],hospital,doctors[0][0])
        self.doctor_id = doctors[0][0]
        self.at = AppTest.from_file(str(ROOT/"app.py"),default_timeout=30)

    def login(self,username):
        self.at.run()
        self.assertFalse(self.at.exception)
        self.at.text_input[0].set_value(username)
        self.at.text_input[1].set_value(PASSWORD)
        self.at.button[0].click().run()
        self.assertFalse(self.at.exception)

    def test_unauthenticated_gate_and_wrong_password(self):
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertFalse(self.at.dataframe)
        self.assertFalse(self.at.sidebar.radio)
        self.at.text_input[0].set_value("doctor")
        self.at.text_input[1].set_value("wrong")
        self.at.button[0].click().run()
        self.assertTrue(self.at.error)
        self.assertFalse(self.at.sidebar.radio)

    def test_director_all_pages_and_question_report_stay_scoped(self):
        self.login("director")
        pages = self.at.sidebar.radio[0].options
        self.assertIn("运营简报",pages)
        self.assertNotIn("我的工作台",pages)
        for page in pages:
            self.at.sidebar.radio[0].set_value(page).run()
            self.assertFalse(self.at.exception, page)
            if page == "科室绩效":
                frame = self.at.dataframe[-1].value
                self.assertEqual(frame["科室"].tolist(),[self.department_name])
            elif page == "运营简报":
                self.assertTrue(any(self.department_name+"运营月度简报" in item.value for item in self.at.markdown))
        self.at.sidebar.radio[0].set_value("智能问答").run()
        [button for button in self.at.button if button.label == "开始分析"][0].click().run()
        self.assertFalse(self.at.exception)

    def test_doctor_pages_and_logout_switch_clear_previous_results(self):
        self.login("director")
        self.at.session_state["float_result"] = {"secret":"previous account"}
        self.at.sidebar.button[0].click().run()
        self.assertFalse(self.at.exception)
        self.assertFalse(self.at.dataframe)
        with self.assertRaises(KeyError):
            self.at.session_state["float_result"]
        self.at.text_input[0].set_value("doctor")
        self.at.text_input[1].set_value(PASSWORD)
        self.at.button[0].click().run()
        self.assertFalse(self.at.exception)
        self.assertEqual(self.at.sidebar.radio[0].options,["我的工作台","个人工作量","智能问答","医管知识库"])
        for page in self.at.sidebar.radio[0].options:
            self.at.sidebar.radio[0].set_value(page).run()
            self.assertFalse(self.at.exception,page)
        self.at.sidebar.radio[0].set_value("智能问答").run()
        [b for b in self.at.button if b.label == "开始查询"][0].click().run()
        self.assertFalse(self.at.exception)
        self.assertTrue(self.at.dataframe)

    def test_revoked_session_returns_to_login(self):
        self.login("doctor")
        self.store.disable_user("doctor")
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertFalse(self.at.dataframe)
        self.assertFalse(self.at.sidebar.radio)
        self.assertIn("账号",[item.label for item in self.at.text_input])

    def test_cloud_secrets_initialize_accounts_and_password_change_revokes_login(self):
        with closing(self.store._connect()) as conn, conn:
            conn.execute("DELETE FROM users")
        self.at.secrets["accounts"] = {
            "director": {"username": "director", "password": PASSWORD},
            "doctor": {"username": "doctor", "password": PASSWORD},
        }
        self.login("doctor")
        self.assertIn("我的工作台", self.at.sidebar.radio[0].options)
        self.at.secrets["accounts"]["doctor"]["password"] = "Updated-cloud-password"
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertFalse(self.at.sidebar.radio)
        self.at.text_input[0].set_value("doctor")
        self.at.text_input[1].set_value("Updated-cloud-password")
        self.at.button[0].click().run()
        self.assertFalse(self.at.exception)
        self.assertIn("我的工作台", self.at.sidebar.radio[0].options)


if __name__ == "__main__":
    unittest.main()
