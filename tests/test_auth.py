from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.auth import AuthStore, Principal, allowed_pages, require_page
from tests.auth_fixtures import PASSWORD, make_hospital, make_accounts, principal_for


class TestAuthentication(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hospital = Path(self.tmp.name)/"hospital.db"
        make_hospital(self.hospital)
        self.store = AuthStore(Path(self.tmp.name)/"auth.db")
        make_accounts(self.store, self.hospital)

    def test_identity_and_role_come_from_account(self):
        p = principal_for(self.store,"  DIRECTOR ")
        self.assertEqual((p.role,p.department_id,p.department_name),("director",1,"内科"))
        doctor = principal_for(self.store,"doctor")
        self.assertEqual((doctor.role,doctor.doctor_id),("doctor",11))
        self.assertNotIn("运营简报",allowed_pages(doctor))
        with self.assertRaises(PermissionError):
            require_page(doctor,"运营简报")
        with self.assertRaises(PermissionError):
            require_page(p,"不存在的页面")

    def test_invalid_login_and_persistent_lockout(self):
        for i in range(5):
            self.assertIsNone(self.store.authenticate("doctor","wrong",now=100+i))
        another_store = AuthStore(self.store.path)
        self.assertIsNone(another_store.authenticate("doctor",PASSWORD,now=110))
        self.assertIsNotNone(another_store.authenticate("doctor",PASSWORD,now=410))
        self.assertIsNone(self.store.authenticate("no-such-user",PASSWORD))

    def test_sessions_expire_and_logout_revokes_server_token(self):
        token = self.store.authenticate("doctor",PASSWORD,now=100)
        self.assertIsNotNone(self.store.get_session(token,now=101))
        self.assertIsNone(self.store.get_session(token,now=100+8*60*60))
        self.assertIsNone(self.store.get_session("made-up-token"))
        self.store.logout(token)
        self.assertIsNone(self.store.get_session(token,now=101))

    def test_password_reset_and_disable_revoke_sessions(self):
        token = self.store.authenticate("doctor",PASSWORD)
        self.store.reset_password("doctor","Changed-Password-2026")
        self.assertIsNone(self.store.get_session(token))
        self.assertIsNone(self.store.authenticate("doctor",PASSWORD))
        token = self.store.authenticate("doctor","Changed-Password-2026")
        self.assertIsNotNone(token)
        self.store.disable_user("doctor")
        self.assertIsNone(self.store.get_session(token))
        self.assertIsNone(self.store.authenticate("doctor","Changed-Password-2026"))

    def test_no_plaintext_password_or_token_stored(self):
        token = self.store.authenticate("doctor",PASSWORD)
        content = self.store.path.read_bytes()
        self.assertNotIn(PASSWORD.encode(),content)
        self.assertNotIn(token.encode(),content)

    def test_admin_can_set_requested_credentials_without_changing_scope(self):
        old = self.store.authenticate("director",PASSWORD)
        self.store.set_credentials("director","admin1","123123")
        self.store.set_credentials("doctor","admin2","123123")
        self.assertIsNone(self.store.get_session(old))
        self.assertIsNone(self.store.authenticate("director",PASSWORD))
        director = self.store.get_session(self.store.authenticate("admin1","123123"))
        doctor = self.store.get_session(self.store.authenticate("admin2","123123"))
        self.assertEqual((director.role,director.department_id),("director",1))
        self.assertEqual((doctor.role,doctor.department_id,doctor.doctor_id),("doctor",1,11))
        self.assertNotIn(b"123123",self.store.path.read_bytes())

    def test_invalid_binding_and_role_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create_user("bad",PASSWORD,"坏绑定","doctor",2,self.hospital,11)
        with self.assertRaises(ValueError):
            self.store.create_user("bad",PASSWORD,"坏角色","admin",1,self.hospital)
        with self.assertRaises(ValueError):
            Principal(1,"bad","坏角色","doctor",1,"内科")
        with self.assertRaises(ValueError):
            self.store.create_user("short","123","短密码","director",1,self.hospital)


if __name__ == "__main__":
    unittest.main()
