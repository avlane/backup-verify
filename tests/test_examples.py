import os
import unittest

from backup_verify.config import load_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ExampleConfigTest(unittest.TestCase):
    def test_example_policy_parses(self):
        cfg = load_config(os.path.join(ROOT, "examples", "backup-verify.toml"))
        self.assertEqual(cfg.defaults.full_max_age_hours, 26)
        self.assertEqual(cfg.policy_for("Sales").diff_max_age_hours, 14)
        self.assertEqual(cfg.policy_for("Reporting").log_max_age_minutes, 120)
        self.assertTrue(cfg.is_excluded("model"))

    def test_wildcard_section(self):
        cfg = load_config(os.path.join(ROOT, "examples", "backup-verify.toml"))
        self.assertEqual(cfg.policy_for("Stage_Orders").full_max_age_hours, 74)
        self.assertIsNone(cfg.policy_for("Stage_Orders").log_max_age_minutes)
