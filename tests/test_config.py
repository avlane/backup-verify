import json
import os
import tempfile
import unittest

from backup_verify.config import Config, ConfigError, load_config, parse_config


class ParseConfigTest(unittest.TestCase):
    def test_empty_config_uses_defaults(self):
        cfg = parse_config({})
        self.assertEqual(cfg.defaults.full_max_age_hours, 26.0)
        self.assertIsNone(cfg.defaults.diff_max_age_hours)
        self.assertEqual(cfg.exclude, ["tempdb"])

    def test_database_overrides_inherit_defaults(self):
        cfg = parse_config({
            "defaults": {"full_max_age_hours": 30, "log_max_age_minutes": 15},
            "databases": {"Sales": {"diff_max_age_hours": 12}},
        })
        sales = cfg.policy_for("SALES")
        self.assertEqual(sales.full_max_age_hours, 30)
        self.assertEqual(sales.log_max_age_minutes, 15)
        self.assertEqual(sales.diff_max_age_hours, 12)
        self.assertIsNone(cfg.policy_for("Other").diff_max_age_hours)

    def test_null_disables_a_check(self):
        cfg = parse_config({"databases": {"Archive": {"log_max_age_minutes": None}}})
        self.assertIsNone(cfg.policy_for("archive").log_max_age_minutes)

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"defaults": {"full_max_age": 1}})
        with self.assertRaises(ConfigError):
            parse_config({"default": {}})

    def test_non_positive_values_are_rejected(self):
        for bad in (0, -5, "12", True):
            with self.assertRaises(ConfigError):
                parse_config({"defaults": {"full_max_age_hours": bad}})

    def test_exclude_is_case_insensitive(self):
        cfg = parse_config({"exclude": ["TempDB", "model"]})
        self.assertTrue(cfg.is_excluded("tempdb"))
        self.assertTrue(cfg.is_excluded("MODEL"))
        self.assertFalse(cfg.is_excluded("Sales"))


class LoadConfigTest(unittest.TestCase):
    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cfg.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"defaults": {"full_max_age_hours": 48}}, fh)
            self.assertEqual(load_config(path).defaults.full_max_age_hours, 48)

    def test_missing_file(self):
        with self.assertRaises(ConfigError):
            load_config("/nonexistent/backup-verify.json")

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            with self.assertRaises(ConfigError):
                load_config(path)
