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


class LoadTomlTest(unittest.TestCase):
    def write(self, text, name="policy.toml"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_toml_file(self):
        path = self.write("""
exclude = ["tempdb", "model"]

[defaults]
full_max_age_hours = 30

[databases.Sales]
log_max_age_minutes = 10
""")
        cfg = load_config(path)
        self.assertEqual(cfg.defaults.full_max_age_hours, 30)
        self.assertEqual(cfg.policy_for("sales").log_max_age_minutes, 10)
        self.assertEqual(cfg.exclude, ["tempdb", "model"])

    def test_invalid_toml(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(self.write("[defaults\nfull = 1"))
        self.assertIn("not valid TOML", str(ctx.exception))

    def test_false_switches_a_check_off(self):
        cfg = load_config(self.write("[defaults]\nlog_max_age_minutes = false\n"))
        self.assertIsNone(cfg.defaults.log_max_age_minutes)
        self.assertEqual(cfg.defaults.full_max_age_hours, 26)


class WildcardTest(unittest.TestCase):
    def cfg(self):
        return parse_config({
            "databases": {
                "Stage_*": {"full_max_age_hours": 72},
                "Stage_Orders": {"full_max_age_hours": 12},
                "*_Archive": {"log_max_age_minutes": None},
            },
            "exclude": ["tempdb", "ReportServer*"],
        })

    def test_pattern_matches_case_insensitively(self):
        self.assertEqual(self.cfg().policy_for("STAGE_billing").full_max_age_hours, 72)

    def test_exact_name_beats_pattern_even_when_listed_later(self):
        self.assertEqual(self.cfg().policy_for("stage_orders").full_max_age_hours, 12)

    def test_unmatched_names_use_the_defaults(self):
        self.assertEqual(self.cfg().policy_for("Sales").full_max_age_hours, 26)

    def test_second_pattern(self):
        self.assertIsNone(self.cfg().policy_for("Sales_Archive").log_max_age_minutes)

    def test_exclude_patterns(self):
        cfg = self.cfg()
        self.assertTrue(cfg.is_excluded("ReportServerTempDB"))
        self.assertTrue(cfg.is_excluded("TEMPDB"))
        self.assertFalse(cfg.is_excluded("Reporting"))


class RestoreSettingsTest(unittest.TestCase):
    def test_defaults_are_unset(self):
        cfg = parse_config({})
        self.assertIsNone(cfg.restore_dir)
        self.assertIsNone(cfg.restore_prefix)

    def test_settings_are_read(self):
        cfg = parse_config({"restore_test_dir": "E:\\RT", "restore_test_prefix": "rt_"})
        self.assertEqual((cfg.restore_dir, cfg.restore_prefix), ("E:\\RT", "rt_"))

    def test_empty_values_are_rejected(self):
        for bad in ("", "  ", 5):
            with self.assertRaises(ConfigError):
                parse_config({"restore_test_prefix": bad})
