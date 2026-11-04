from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.access import hospital_connection
from src.auth import AuthStore
from src.sql_agent import HospitalSQLAgent
from src.report_generator import HospitalReportGenerator
from src.risk_scoring import MedicalInsuranceRiskScorer
from tests.auth_fixtures import make_hospital, make_accounts, principal_for


class TestDataAccess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name)/"hospital.db"
        make_hospital(self.db)
        self.store = AuthStore(Path(self.tmp.name)/"auth.db")
        make_accounts(self.store,self.db)
        self.director = principal_for(self.store,"director")
        self.doctor = principal_for(self.store,"doctor")

    def test_director_filters_joins_aggregates_and_raw_schema_names(self):
        with hospital_connection(self.db,self.director) as conn:
            self.assertEqual(conn.execute("SELECT SUM(amount) FROM main.billing_records").fetchone()[0],100)
            self.assertEqual([r[0] for r in conn.execute("SELECT department_id FROM departments")],[1])
            rows = conn.execute("SELECT DISTINCT v.department_id FROM outpatient_visits v JOIN doctors d USING(doctor_id)").fetchall()
            self.assertEqual([r[0] for r in rows],[1])
            self.assertEqual([r[0] for r in conn.execute("SELECT drg_code FROM drg_groups")],["A"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outpatient_visits WHERE department_id=2").fetchone()[0],0)

    def test_doctor_has_only_self_and_no_patient_or_financial_columns(self):
        with hospital_connection(self.db,self.doctor) as conn:
            self.assertEqual([r[0] for r in conn.execute("SELECT doctor_id FROM doctors")],[11])
            self.assertEqual([r[0] for r in conn.execute("SELECT doctor_id FROM outpatient_visits")],[11])
            self.assertEqual([r[0] for r in conn.execute("SELECT doctor_id FROM surgery_records")],[11])
            for query in ("SELECT * FROM billing_records","SELECT patient_id FROM outpatient_visits","SELECT registration_fee FROM outpatient_visits"):
                with self.assertRaises(sqlite3.DatabaseError):
                    conn.execute(query).fetchall()

    def test_scope_cache_does_not_mix_accounts(self):
        for username,expected in [("doctor",11),("doctor2",12),("doctor",11)]:
            with hospital_connection(self.db,principal_for(self.store,username)) as conn:
                self.assertEqual([r[0] for r in conn.execute("SELECT doctor_id FROM outpatient_visits")],[expected])
        with hospital_connection(self.db,principal_for(self.store,"director2")) as conn:
            self.assertEqual(conn.execute("SELECT SUM(amount) FROM billing_records").fetchone()[0],900)

    def test_readonly_and_no_attach_escape(self):
        with hospital_connection(self.db,self.director) as conn:
            for query in ("DELETE FROM doctors", "UPDATE billing_records SET amount=0", "ATTACH DATABASE ':memory:' AS other", "PRAGMA query_only=OFF"):
                with self.assertRaises(sqlite3.DatabaseError):
                    conn.execute(query)
        with hospital_connection(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0],3)

    def test_agent_risk_and_report_keep_director_scope(self):
        agent = HospitalSQLAgent(self.db,principal=self.director)
        self.assertEqual(agent.ask("本月各科室收入排名").rows[0]["total_income"],100)
        risk = MedicalInsuranceRiskScorer(self.db,self.director)
        scores = risk.get_department_risk_scores("2026-06-01","2026-07-01","2026-06-01","2026-06-08")
        self.assertEqual([r["department_name"] for r in scores],["内科"])
        report = HospitalReportGenerator(agent).generate_monthly_report()
        self.assertIn("内科运营月度简报",report)
        self.assertNotIn("外科",report)

    def test_doctor_cannot_use_management_tools(self):
        agent = HospitalSQLAgent(self.db,principal=self.doctor)
        self.assertEqual(agent.ask("本月门诊量").rows[0]["visit_count"],1)
        for question in ("本月收入", "本月医保费用", "生成简报"):
            with self.assertRaises(PermissionError):
                agent.ask(question)
        with self.assertRaises(PermissionError):
            HospitalReportGenerator(agent)
        with self.assertRaises(PermissionError):
            MedicalInsuranceRiskScorer(self.db,self.doctor)

    def test_source_update_refreshes_scoped_snapshot(self):
        with hospital_connection(self.db,self.doctor) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outpatient_visits").fetchone()[0],1)
        from contextlib import closing
        with closing(sqlite3.connect(self.db)) as source, source:
            source.execute("INSERT INTO outpatient_visits VALUES (4,104,11,1,'2026-06-07',10,'模拟诊断')")
        with hospital_connection(self.db,self.doctor) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outpatient_visits").fetchone()[0],2)


if __name__ == "__main__":
    unittest.main()
