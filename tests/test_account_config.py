from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.auth import AuthStore
from src.account_config import apply_account_config, load_account_file
from tests.auth_fixtures import make_hospital, make_accounts, PASSWORD


class TestAccountConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        self.hospital = self.root / "data/hospital.db"
        make_hospital(self.hospital)
        self.store = AuthStore(self.root / "data/auth.db")

    def settings(self, username="director", password=PASSWORD):
        return {"director": {"username": username, "password": password}}

    def test_empty_cloud_can_initialize_both_roles_and_recreate_accounts(self):
        config = self.settings()
        config["doctor"] = {"username": "doctor", "password": PASSWORD}
        for store in (self.store, AuthStore(self.root / "recreated.db")):
            apply_account_config(store, config, self.hospital)
            principal = store.get_session(store.authenticate("doctor", PASSWORD))
            self.assertEqual((principal.role, principal.department_id, principal.doctor_id), ("doctor", 1, 11))

    def test_saved_file_changes_revoke_old_login_and_preserve_scope(self):
        make_accounts(self.store, self.hospital)
        path = self.root / "账号密码配置.toml"
        path.write_text('[accounts.director]\nusername="director"\npassword="'+PASSWORD+'"\n', encoding="utf-8")
        self.store._use_local_config = True
        with patch("src.auth.ROOT", self.root):
            token = self.store.authenticate("director", PASSWORD)
            before = self.store.get_session(token)
            path.write_text('[accounts.director]\nusername="renamed"\npassword="New-private-password"\n', encoding="utf-8")
            self.assertIsNone(self.store.get_session(token))
            self.assertIsNone(self.store.authenticate("director", PASSWORD))
            after = self.store.get_session(self.store.authenticate("renamed", "New-private-password"))
            self.assertEqual(after.user_id, before.user_id)
            self.assertEqual((after.role, after.department_id), (before.role, before.department_id))

    def test_unchanged_config_preserves_sessions_throttling_and_disabled_accounts(self):
        apply_account_config(self.store, self.settings(), self.hospital)
        token = self.store.authenticate("director", PASSWORD)
        for i in range(5):
            self.store.authenticate("director", "wrong", now=100+i)
        apply_account_config(self.store, self.settings(), self.hospital)
        self.assertIsNotNone(self.store.get_session(token))
        self.assertIsNone(self.store.authenticate("director", PASSWORD, now=110))
        self.store.disable_user("director")
        apply_account_config(self.store, self.settings(), self.hospital)
        self.assertIsNone(self.store.authenticate("director", PASSWORD))

    def test_collision_rolls_back_entire_update(self):
        make_accounts(self.store, self.hospital)
        apply_account_config(self.store, self.settings(), self.hospital)
        config = self.settings("renamed", "New-private-password")
        config["doctor"] = {"username": "director2", "password": PASSWORD}
        with self.assertRaises(ValueError):
            apply_account_config(self.store, config, self.hospital)
        self.assertIsNotNone(self.store.authenticate("director", PASSWORD))
        self.assertIsNone(self.store.authenticate("renamed", "New-private-password"))

    def test_bad_file_never_exposes_password_or_falls_back_to_old_session(self):
        apply_account_config(self.store, self.settings(), self.hospital)
        token = self.store.authenticate("director", PASSWORD)
        path = self.root / "账号密码配置.toml"
        path.write_text('[accounts.director]\npassword="PRIVATE-DO-NOT-PRINT', encoding="utf-8")
        self.store._use_local_config = True
        with patch("src.auth.ROOT", self.root), self.assertRaises(ValueError) as caught:
            self.store.get_session(token)
        self.assertNotIn("PRIVATE-DO-NOT-PRINT", str(caught.exception))
        path.write_text('[wrong_section]\nusername="director"', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_account_file(path)
