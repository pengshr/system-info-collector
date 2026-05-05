# -*- coding: utf-8 -*-
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import collector


class TestFormatSpeed(unittest.TestCase):
    def test_none(self):
        self.assertEqual(collector.format_speed(None), "未知")

    def test_negative(self):
        self.assertEqual(collector.format_speed(-1), "未知")

    def test_zero(self):
        self.assertEqual(collector.format_speed(0), "0 bps")

    def test_bps(self):
        self.assertEqual(collector.format_speed(1000), "1000 bps")

    def test_mbps(self):
        self.assertEqual(collector.format_speed(1000000), "1.0 Mbps")

    def test_gbps(self):
        self.assertEqual(collector.format_speed(1000000000), "1.0 Gbps")


class TestParseWmiDate(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(collector.parse_wmi_date(None))

    def test_empty(self):
        self.assertIsNone(collector.parse_wmi_date(""))

    def test_timestamp_format(self):
        result = collector.parse_wmi_date("/Date(1708747200000)/")
        self.assertIsNotNone(result)
        self.assertIn("2024", result)

    def test_long_string(self):
        result = collector.parse_wmi_date("2024-01-01T12:00:00.000000+000")
        self.assertEqual(result, "2024-01-01T12:00:00")

    def test_short_string(self):
        result = collector.parse_wmi_date("2024-01-01")
        self.assertEqual(result, "2024-01-01")

    def test_invalid_format(self):
        result = collector.parse_wmi_date("invalid")
        self.assertIsNone(result)

    def test_non_string_returns_none(self):
        self.assertIsNone(collector.parse_wmi_date(12345))
        self.assertIsNone(collector.parse_wmi_date(None))
        self.assertIsNone(collector.parse_wmi_date([]))


class TestSafeInt(unittest.TestCase):
    def test_valid_int(self):
        self.assertEqual(collector.safe_int("123"), 123)

    def test_invalid(self):
        self.assertIsNone(collector.safe_int("abc"))

    def test_default(self):
        self.assertEqual(collector.safe_int("abc", 0), 0)

    def test_none(self):
        self.assertIsNone(collector.safe_int(None))


class TestBytesToGb(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(collector._bytes_to_gb(0), 0.0)

    def test_one_gb(self):
        self.assertEqual(collector._bytes_to_gb(1024**3), 1.0)


class TestDeleteAllData(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(collector.CACHE_DIR)

    def test_deletes_cache_files(self):
        (self.test_dir / "config.json").write_text("{}")
        (self.test_dir / "config_old.txt").write_text("{}")
        deleted = collector.delete_all_data()
        self.assertGreaterEqual(deleted, 2)
        self.assertFalse((self.test_dir / "config.json").exists())


class TestValidateComparePath(unittest.TestCase):
    def test_valid_path(self):
        result = collector.validate_compare_path(str(collector.CACHE_FILE))
        self.assertIsNotNone(result)

    def test_nonexistent(self):
        result = collector.validate_compare_path("nonexistent.json")
        self.assertIsNone(result)

    def test_wrong_extension(self):
        result = collector.validate_compare_path("test.txt")
        self.assertIsNone(result)


class TestAssessSystemHealth(unittest.TestCase):
    def test_empty_data(self):
        health = collector.assess_system_health({})
        self.assertLess(health["score"], 100)
        self.assertGreaterEqual(health["score"], 0)

    def test_good_system(self):
        data = {
            "磁盘": {"total_size_gb": 500, "total_free_gb": 250, "drives": []},
            "内存": {"total_gb": 16},
            "CPU": {"cores": 8},
            "显卡": {"gpus": [{"name": "Test GPU", "vram_gb": 8}]},
        }
        health = collector.assess_system_health(data)
        self.assertGreaterEqual(health["score"], 90)


class TestCompareConfigs(unittest.TestCase):
    def test_identical(self):
        c1 = {"a": 1, "b": 2}
        c2 = {"a": 1, "b": 2}
        result = collector.compare_configs(c1, c2)
        self.assertEqual(len(result), 0)

    def test_different(self):
        c1 = {"a": 1}
        c2 = {"a": 2}
        result = collector.compare_configs(c1, c2)
        self.assertEqual(len(result), 1)

    def test_nested(self):
        c1 = {"a": {"b": 1}}
        c2 = {"a": {"b": 2}}
        result = collector.compare_configs(c1, c2)
        self.assertEqual(len(result), 1)

    def test_same_object_in_both(self):
        shared = {"x": 1}
        c1 = {"a": shared, "b": shared}
        c2 = {"a": shared, "b": shared}
        result = collector.compare_configs(c1, c2)
        self.assertEqual(len(result), 0)


class TestResolveAlias(unittest.TestCase):
    def test_os(self):
        self.assertEqual(collector._resolve_alias("os"), "操作系统")

    def test_cpu(self):
        self.assertEqual(collector._resolve_alias("cpu"), "CPU")

    def test_unknown(self):
        self.assertEqual(collector._resolve_alias("unknown"), "unknown")


if __name__ == "__main__":
    unittest.main()
