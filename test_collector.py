# -*- coding: utf-8 -*-
"""
System Information Collector - 单元测试模块

Tests for core functionality: parsing, caching, sanitization, formatting, export, compare.
Run with: python test_collector.py
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock


sys.path.insert(0, str(Path(__file__).parent))
import collector


class TestSafeInt(unittest.TestCase):

    def test_valid_int_string(self):
        self.assertEqual(collector.safe_int("42"), 42)

    def test_valid_int(self):
        self.assertEqual(collector.safe_int(42), 42)

    def test_none_returns_default(self):
        self.assertIsNone(collector.safe_int(None))

    def test_empty_string_returns_default(self):
        self.assertIsNone(collector.safe_int(""))

    def test_invalid_string_returns_default(self):
        self.assertIsNone(collector.safe_int("abc"))

    def test_custom_default(self):
        self.assertEqual(collector.safe_int("invalid", -1), -1)

    def test_float_string_returns_default(self):
        self.assertIsNone(collector.safe_int("42.5"))

    def test_bool_input(self):
        self.assertEqual(collector.safe_int(True), 1)
        self.assertEqual(collector.safe_int(False), 0)

    def test_negative(self):
        self.assertEqual(collector.safe_int("-5"), -5)


class TestParseWmiDate(unittest.TestCase):

    def test_wmi_date_format(self):
        result = collector.parse_wmi_date("/Date(1708747200000)/")
        self.assertIsNotNone(result)
        self.assertIn("2024", result)

    def test_iso_format_long(self):
        result = collector.parse_wmi_date("2024-02-27T08:00:00.000000+480")
        self.assertEqual(result, "2024-02-27T08:00:00")

    def test_iso_format_short(self):
        result = collector.parse_wmi_date("2024-02-27")
        self.assertEqual(result, "2024-02-27")

    def test_none_input(self):
        self.assertIsNone(collector.parse_wmi_date(None))

    def test_empty_string(self):
        self.assertIsNone(collector.parse_wmi_date(""))

    def test_invalid_format(self):
        result = collector.parse_wmi_date("invalid")
        self.assertEqual(result, "invalid")


class TestHashMacAddress(unittest.TestCase):

    def test_deterministic(self):
        mac = "58:11:22:82:F5:2F"
        hash1 = collector.hash_mac_address(mac)
        hash2 = collector.hash_mac_address(mac)
        self.assertEqual(hash1, hash2)

    def test_full_length(self):
        result = collector.hash_mac_address("00:11:22:33:44:55")
        self.assertEqual(len(result), 64)

    def test_different_inputs(self):
        h1 = collector.hash_mac_address("AA:BB:CC:DD:EE:FF")
        h2 = collector.hash_mac_address("11:22:33:44:55:66")
        self.assertNotEqual(h1, h2)

    def test_uses_hmac(self):
        import hashlib
        plain_hash = hashlib.sha256("AA:BB:CC:DD:EE:FF".encode()).hexdigest()
        hmac_hash = collector.hash_mac_address("AA:BB:CC:DD:EE:FF")
        self.assertNotEqual(plain_hash, hmac_hash)


class TestFilterSensitiveData(unittest.TestCase):

    def setUp(self):
        self.sample_data = {
            "采集时间": "2026-04-29 00:00:00",
            "计算机名": "TEST-PC",
            "主板": {"serial_number": "SECRET123", "product": "GA503RW"},
            "网络适配器": {
                "adapters": [
                    {"name": "Ethernet", "mac_address": "AA:BB:CC:DD:EE:FF"}
                ]
            },
            "BIOS": {"manufacturer": "AMI", "version": "1.0", "serial_number": "BIOS-SN-999"},
        }

    def test_anonymize_mac_and_serial(self):
        result = collector.filter_sensitive_data(self.sample_data, anonymize=True)
        self.assertEqual(result["主板"]["serial_number"], "已脱敏")
        self.assertEqual(result["网络适配器"]["adapters"][0]["mac_address"], "已脱敏")
        self.assertIn("mac_address_hash", result["网络适配器"]["adapters"][0])

    def test_bios_serial_anonymized_not_deleted(self):
        result = collector.filter_sensitive_data(self.sample_data, anonymize=True)
        self.assertIn("BIOS", result)
        self.assertEqual(result["BIOS"]["serial_number"], "已脱敏")
        self.assertEqual(result["BIOS"]["manufacturer"], "AMI")
        self.assertEqual(result["BIOS"]["version"], "1.0")

    def test_anonymize_disabled(self):
        result = collector.filter_sensitive_data(self.sample_data, anonymize=False)
        self.assertEqual(result["主板"]["serial_number"], "SECRET123")
        self.assertEqual(result["网络适配器"]["adapters"][0]["mac_address"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(result["BIOS"]["serial_number"], "BIOS-SN-999")

    def test_preserves_other_data(self):
        result = collector.filter_sensitive_data(self.sample_data, anonymize=True)
        self.assertEqual(result["计算机名"], "TEST-PC")
        self.assertEqual(result["主板"]["product"], "GA503RW")

    def test_missing_keys_no_crash(self):
        data = {"采集时间": "2026-04-29"}
        result = collector.filter_sensitive_data(data, anonymize=True)
        self.assertIn("采集时间", result)

    def test_deep_copy_no_mutation(self):
        original_serial = self.sample_data["主板"]["serial_number"]
        collector.filter_sensitive_data(self.sample_data, anonymize=True)
        self.assertEqual(self.sample_data["主板"]["serial_number"], original_serial)

    def test_mac_hash_not_overwritten_on_double_filter(self):
        result1 = collector.filter_sensitive_data(self.sample_data, anonymize=True)
        correct_hash = result1["网络适配器"]["adapters"][0]["mac_address_hash"]
        result2 = collector.filter_sensitive_data(result1, anonymize=True)
        self.assertEqual(result2["网络适配器"]["adapters"][0]["mac_address_hash"], correct_hash)
        self.assertEqual(result2["网络适配器"]["adapters"][0]["mac_address"], "已脱敏")

    def test_anonymize_disabled_returns_deep_copy(self):
        result1 = collector.filter_sensitive_data(self.sample_data, anonymize=False)
        result2 = collector.filter_sensitive_data(self.sample_data, anonymize=False)
        self.assertIsNot(result1, result2)

    def test_uses_sensitive_fields_constant(self):
        self.assertIn("serial_number", collector.SENSITIVE_FIELDS)
        self.assertIn("mac_address", collector.SENSITIVE_FIELDS)


class TestFormatSpeed(unittest.TestCase):

    def test_gbps(self):
        self.assertEqual(collector.format_speed(2_500_000_000), "2.5 Gbps")

    def test_exact_1gbps(self):
        self.assertEqual(collector.format_speed(1_000_000_000), "1.0 Gbps")

    def test_mbps(self):
        self.assertEqual(collector.format_speed(500_000_000), "500.0 Mbps")

    def test_bps(self):
        self.assertEqual(collector.format_speed(1000), "1000 bps")

    def test_zero(self):
        self.assertEqual(collector.format_speed(0), "未知")

    def test_none(self):
        self.assertEqual(collector.format_speed(None), "未知")


class TestParseWmicTable(unittest.TestCase):

    def test_valid_csv(self):
        text = "Header1,Header2\nValue1,Value2"
        result = collector.parse_wmic_table(text)
        self.assertEqual(result, [{"Header1": "Value1", "Header2": "Value2"}])

    def test_empty_input(self):
        self.assertEqual(collector.parse_wmic_table(""), [])
        self.assertEqual(collector.parse_wmic_table(None), [])

    def test_single_line(self):
        self.assertEqual(collector.parse_wmic_table("Header1,Header2"), [])

    def test_mismatched_columns(self):
        text = "H1,H2,H3\nV1,V2"
        result = collector.parse_wmic_table(text)
        self.assertEqual(result, [])


class TestParseBatchedFunctions(unittest.TestCase):

    def test_parse_os_batched_with_data(self):
        data = {
            "Caption": "Microsoft Windows 11 Pro",
            "Version": "10.0.22631",
            "BuildNumber": "22631",
            "OSArchitecture": "64-bit",
            "InstallDate": "/Date(1708747200000)/",
            "LastBootUpTime": "/Date(1714348800000)/",
        }
        os_info = {"system": "Windows", "release": "10", "version": "10.0.22631", "architecture": "AMD64"}
        result = collector._parse_os_batched(data, "TEST-PC", os_info)
        self.assertEqual(result["caption"], "Microsoft Windows 11 Pro")
        self.assertEqual(result["cpu_arch"], "AMD64")
        self.assertEqual(result["os_arch"], "64-bit")
        self.assertIn("install_date", result)

    def test_parse_os_batched_none_data(self):
        os_info = {"system": "Windows", "release": "10", "version": "10.0", "architecture": "AMD64"}
        result = collector._parse_os_batched(None, "TEST-PC", os_info)
        self.assertEqual(result["cpu_arch"], "AMD64")
        self.assertNotIn("architecture", result)

    def test_parse_cpu_batched_with_data(self):
        data = {"Name": "Intel i7-12700H", "NumberOfCores": 14, "NumberOfLogicalProcessors": 20, "MaxClockSpeed": 2300}
        result = collector._parse_cpu_batched(data, "Intel Processor")
        self.assertEqual(result["name"], "Intel i7-12700H")
        self.assertEqual(result["cores"], 14)
        self.assertEqual(result["logical_processors"], 20)

    def test_parse_cpu_batched_none(self):
        result = collector._parse_cpu_batched(None, "Test CPU")
        self.assertEqual(result["processor"], "Test CPU")

    def test_parse_memory_batched_with_data(self):
        data = [
            {"Capacity": 17179869184, "Speed": 4800, "Manufacturer": "Samsung", "PartNumber": "M425R2GA3BB0"},
            {"Capacity": 17179869184, "Speed": 4800, "Manufacturer": "Samsung", "PartNumber": "M425R2GA3BB0"},
        ]
        result = collector._parse_memory_batched(data)
        self.assertEqual(result["total_gb"], 32.0)
        self.assertEqual(len(result["sticks"]), 2)

    def test_parse_memory_batched_none(self):
        result = collector._parse_memory_batched(None)
        self.assertEqual(result["sticks"], [])

    def test_parse_disk_batched_with_data(self):
        data = [{"DeviceID": "C:", "Size": 999653638144, "FreeSpace": 499826819072, "FileSystem": "NTFS", "VolumeName": "OS"}]
        result = collector._parse_disk_batched(data)
        self.assertEqual(len(result["drives"]), 1)
        self.assertEqual(result["drives"][0]["drive"], "C:")
        self.assertGreater(result["total_size_gb"], 0)

    def test_parse_gpu_batched_with_data(self):
        data = [{"Name": "RTX 3070 Ti", "AdapterRAM": 4294967296, "DriverVersion": "31.0.15.9579", "VideoProcessor": "NVIDIA", "VideoModeDescription": "1920 x 1080"}]
        result = collector._parse_gpu_batched(data)
        self.assertEqual(result["gpus"][0]["name"], "RTX 3070 Ti")
        self.assertEqual(result["gpus"][0]["vram_gb"], 4.0)
        self.assertEqual(result["gpus"][0]["video_mode"], "1920 x 1080")

    def test_parse_motherboard_batched_with_data(self):
        data = {"Manufacturer": "ASUS", "Product": "GA503RW", "SerialNumber": "SECRET", "Version": "1.0"}
        result = collector._parse_motherboard_batched(data)
        self.assertEqual(result["manufacturer"], "ASUS")
        self.assertEqual(result["serial_number"], "SECRET")

    def test_parse_bios_batched_with_data(self):
        data = {"Manufacturer": "AMI", "Name": "BIOS", "Version": "1.0", "ReleaseDate": "/Date(1708747200000)/", "SerialNumber": "SN123"}
        result = collector._parse_bios_batched(data)
        self.assertEqual(result["manufacturer"], "AMI")
        self.assertIsNotNone(result["release_date"])

    def test_parse_network_batched_with_data(self):
        data = [{"Name": "Ethernet", "MACAddress": "AA:BB:CC:DD:EE:FF", "Speed": 1000000000, "AdapterType": "Ethernet 802.3"}]
        result = collector._parse_network_batched(data)
        self.assertEqual(len(result["adapters"]), 1)
        self.assertEqual(result["adapters"][0]["speed"], "1.0 Gbps")


class TestBuildSummaryFromInfo(unittest.TestCase):

    def test_builds_from_collected_data(self):
        info = {
            "CPU": {"name": "Test CPU", "cores": 8, "logical_processors": 16, "processor": "Test"},
            "内存": {"total_gb": 32.0, "sticks": []},
            "磁盘": {"total_size_gb": 512.0, "total_free_gb": 256.0, "drives": []},
            "显卡": {"gpus": [{"name": "GPU1"}, {"name": "GPU2"}]},
        }
        os_info = {"system": "Windows", "release": "10", "version": "10.0", "architecture": "AMD64"}
        result = collector._build_summary_from_info(info, "TEST-PC", os_info)
        self.assertEqual(result["cpu"], "Test CPU")
        self.assertEqual(result["ram_gb"], 32.0)
        self.assertEqual(result["gpu"], "GPU1 / GPU2")

    def test_handles_empty_info(self):
        result = collector._build_summary_from_info({}, "PC", {"system": "Win", "release": "10", "version": "1", "architecture": "x64"})
        self.assertEqual(result["cpu"], "N/A")
        self.assertEqual(result["gpu"], "N/A")


class TestCompareConfigs(unittest.TestCase):

    def test_identical_configs(self):
        config = {"a": 1, "b": {"c": 2}}
        result = collector.compare_configs(config, copy.deepcopy(config))
        self.assertEqual(result, [])

    def test_different_values(self):
        c1 = {"a": 1, "b": "old"}
        c2 = {"a": 1, "b": "new"}
        result = collector.compare_configs(c1, c2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["old"], "old")
        self.assertEqual(result[0]["new"], "new")

    def test_new_key(self):
        c1 = {"a": 1}
        c2 = {"a": 1, "b": 2}
        result = collector.compare_configs(c1, c2)
        self.assertTrue(any("新增" in str(d["old"]) for d in result))

    def test_deleted_key(self):
        c1 = {"a": 1, "b": 2}
        c2 = {"a": 1}
        result = collector.compare_configs(c1, c2)
        self.assertTrue(any("删除" in str(d["new"]) for d in result))

    def test_list_length_change(self):
        c1 = {"items": [1, 2, 3]}
        c2 = {"items": [1, 2]}
        result = collector.compare_configs(c1, c2)
        self.assertTrue(any("长度" in str(d["old"]) for d in result))

    def test_list_extra_items_reported(self):
        c1 = {"items": [1]}
        c2 = {"items": [1, 2]}
        result = collector.compare_configs(c1, c2)
        self.assertTrue(any("新增" in str(d["old"]) for d in result))

    def test_max_depth_limit(self):
        nested = {"a": {}}
        current = nested
        for _ in range(25):
            current["a"] = {"a": {}}
            current = current["a"]
        c1 = copy.deepcopy(nested)
        c2 = copy.deepcopy(nested)
        result = collector.compare_configs(c1, c2, max_depth=5)
        self.assertTrue(any("超限" in str(d["old"]) for d in result))

    def test_empty_dicts(self):
        result = collector.compare_configs({}, {})
        self.assertEqual(result, [])


class TestFormatComparison(unittest.TestCase):

    def test_no_differences(self):
        result = collector.format_comparison([], "t1", "t2")
        self.assertIn("一致", result)

    def test_categorizes_hardware_diffs(self):
        diffs = [{"path": "root.CPU.name", "old": "i5", "new": "i7"}]
        result = collector.format_comparison(diffs, "t1", "t2")
        self.assertIn("硬件变更", result)

    def test_ignores_collection_time(self):
        diffs = [{"path": "root.采集时间", "old": "t1", "new": "t2"}]
        result = collector.format_comparison(diffs, "t1", "t2")
        self.assertIn("元数据变化", result)


class TestValidateComparePath(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        collector.CACHE_DIR = Path(self.test_dir.name)

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        self.test_dir.cleanup()

    def test_valid_path_in_cache_dir(self):
        test_file = Path(self.test_dir.name) / "test.json"
        test_file.write_text("{}")
        result = collector.validate_compare_path(str(test_file))
        self.assertIsNotNone(result)

    def test_path_outside_cache_dir(self):
        result = collector.validate_compare_path("C:\\Windows\\System32\\config.json")
        self.assertIsNone(result)

    def test_prefix_collision_blocked(self):
        evil_dir = self.test_dir.name + "_evil"
        os.makedirs(evil_dir, exist_ok=True)
        evil_file = Path(evil_dir) / "config.json"
        evil_file.write_text("{}")
        result = collector.validate_compare_path(str(evil_file))
        self.assertIsNone(result)
        evil_file.unlink(missing_ok=True)
        os.rmdir(evil_dir)

    def test_non_json_file(self):
        test_file = Path(self.test_dir.name) / "test.txt"
        test_file.write_text("hello")
        result = collector.validate_compare_path(str(test_file))
        self.assertIsNone(result)

    def test_nonexistent_file(self):
        result = collector.validate_compare_path(str(Path(self.test_dir.name) / "nonexistent.json"))
        self.assertIsNone(result)


class TestValidateExportPath(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        collector.CACHE_DIR = Path(self.test_dir.name)

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        self.test_dir.cleanup()

    def test_path_in_cache_dir_allowed(self):
        result = collector._validate_export_path(str(Path(self.test_dir.name) / "output.txt"))
        self.assertIsNotNone(result)

    def test_path_in_home_dir_allowed(self):
        result = collector._validate_export_path(str(Path.home() / "output.txt"))
        self.assertIsNotNone(result)

    def test_path_in_restricted_dir_blocked(self):
        result = collector._validate_export_path("C:\\Windows\\System32\\output.txt")
        self.assertIsNone(result)


class TestDeleteAllData(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        collector.CACHE_DIR = Path(self.test_dir.name)

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        self.test_dir.cleanup()

    def test_deletes_cache_files(self):
        (Path(self.test_dir.name) / "config.json").write_text("{}")
        (Path(self.test_dir.name) / "config_old.json").write_text("{}")
        deleted = collector.delete_all_data()
        self.assertGreaterEqual(deleted, 2)
        self.assertFalse((Path(self.test_dir.name) / "config.json").exists())

    def test_no_files_to_delete(self):
        deleted = collector.delete_all_data()
        self.assertEqual(deleted, 0)


class TestSecureDeleteFile(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_secure_delete_overwrites_then_deletes(self):
        test_file = Path(self.test_dir.name) / "secret.json"
        test_file.write_text('{"secret": "data123"}')
        self.assertTrue(test_file.exists())
        result = collector._secure_delete_file(test_file)
        self.assertTrue(result)
        self.assertFalse(test_file.exists())

    def test_secure_delete_nonexistent_file(self):
        test_file = Path(self.test_dir.name) / "nonexistent.txt"
        result = collector._secure_delete_file(test_file)
        self.assertFalse(result)


class TestLoadCache(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        self.original_cache_file = collector.CACHE_FILE
        collector.CACHE_DIR = Path(self.test_dir.name)
        collector.CACHE_FILE = collector.CACHE_DIR / "config.json"

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        collector.CACHE_FILE = self.original_cache_file
        self.test_dir.cleanup()

    def test_no_cache_file(self):
        self.assertIsNone(collector.load_cache())

    def test_valid_cache(self):
        data = {
            "采集时间": (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "计算机名": "TEST-PC",
        }
        with open(collector.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = collector.load_cache()
        self.assertIsNotNone(result)
        self.assertEqual(result["计算机名"], "TEST-PC")

    def test_expired_cache(self):
        data = {
            "采集时间": (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S"),
            "计算机名": "TEST-PC",
        }
        with open(collector.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = collector.load_cache()
        self.assertIsNone(result)

    def test_corrupted_cache(self):
        with open(collector.CACHE_FILE, "w", encoding="utf-8") as f:
            f.write("{invalid json")
        result = collector.load_cache()
        self.assertIsNone(result)
        self.assertFalse(collector.CACHE_FILE.exists())

    def test_cache_without_timestamp_uses_mtime(self):
        data = {"计算机名": "TEST-PC"}
        with open(collector.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = collector.load_cache()
        self.assertIsNotNone(result)
        self.assertEqual(result["计算机名"], "TEST-PC")


class TestSaveCache(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        self.original_cache_file = collector.CACHE_FILE
        collector.CACHE_DIR = Path(self.test_dir.name)
        collector.CACHE_FILE = collector.CACHE_DIR / "config.json"

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        collector.CACHE_FILE = self.original_cache_file
        self.test_dir.cleanup()

    def test_save_valid_data(self):
        data = {"采集时间": "2026-04-29 00:00:00", "计算机名": "TEST-PC"}
        result = collector.save_cache(data)
        self.assertTrue(result)
        self.assertTrue(collector.CACHE_FILE.exists())

    def test_save_stores_raw_data(self):
        data = {
            "采集时间": "2026-04-29",
            "主板": {"serial_number": "SECRET123"},
            "网络适配器": {"adapters": [{"mac_address": "AA:BB:CC:DD:EE:FF"}]},
            "BIOS": {"serial_number": "BIOS-SN"},
        }
        collector.save_cache(data)
        with open(collector.CACHE_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        self.assertEqual(stored["主板"]["serial_number"], "SECRET123")
        self.assertEqual(stored["网络适配器"]["adapters"][0]["mac_address"], "AA:BB:CC:DD:EE:FF")

    def test_save_none_returns_false(self):
        result = collector.save_cache(None)
        self.assertFalse(result)

    def test_atomic_write(self):
        data = {"采集时间": "2026-04-29 00:00:00"}
        collector.save_cache(data)
        self.assertTrue(collector.CACHE_FILE.exists())
        self.assertFalse(collector.CACHE_FILE.with_suffix(".tmp").exists())


class TestGetConfigIntegration(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        self.original_cache_file = collector.CACHE_FILE
        collector.CACHE_DIR = Path(self.test_dir.name)
        collector.CACHE_FILE = collector.CACHE_DIR / "config.json"

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        collector.CACHE_FILE = self.original_cache_file
        self.test_dir.cleanup()

    @patch("collector.load_cache")
    def test_returns_cached_data_anonymized(self, mock_load):
        mock_load.return_value = {
            "采集时间": (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "计算机名": "TEST-PC",
            "主板": {"serial_number": "SECRET"},
            "网络适配器": {"adapters": [{"mac_address": "AA:BB:CC:DD:EE:FF"}]},
        }
        result = collector.get_config()
        self.assertEqual(result["计算机名"], "TEST-PC")
        self.assertEqual(result["主板"]["serial_number"], "已脱敏")

    @patch("collector.load_cache")
    def test_returns_cached_data_no_anonymize(self, mock_load):
        mock_load.return_value = {
            "采集时间": (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "计算机名": "TEST-PC",
            "主板": {"serial_number": "SECRET"},
            "网络适配器": {"adapters": [{"mac_address": "AA:BB:CC:DD:EE:FF"}]},
        }
        result = collector.get_config(anonymize=False)
        self.assertEqual(result["主板"]["serial_number"], "SECRET")
        self.assertEqual(result["网络适配器"]["adapters"][0]["mac_address"], "AA:BB:CC:DD:EE:FF")

    @patch("collector.load_cache", return_value=None)
    @patch("collector.collect_all")
    def test_collects_and_caches_when_no_cache(self, mock_collect, mock_load):
        mock_collect.return_value = {
            "采集时间": "2026-04-29 00:00:00",
            "计算机名": "TEST-PC",
            "主板": {},
            "网络适配器": {"adapters": []},
        }
        result = collector.get_config()
        self.assertIsNotNone(result)
        mock_collect.assert_called_once()

    @patch("collector.load_cache", return_value=None)
    @patch("collector.collect_all", return_value=None)
    def test_raises_on_complete_failure(self, mock_collect, mock_load):
        with self.assertRaises(RuntimeError):
            collector.get_config()

    @patch("collector.load_cache", return_value=None)
    @patch("collector.collect_all")
    def test_force_refresh_bypasses_cache(self, mock_collect, mock_load):
        mock_collect.return_value = {
            "采集时间": "2026-04-29 00:00:00",
            "计算机名": "TEST-PC",
            "主板": {},
            "网络适配器": {"adapters": []},
        }
        result = collector.get_config(force_refresh=True)
        self.assertIsNotNone(result)
        mock_load.assert_not_called()

    @patch("collector.load_cache")
    def test_double_filter_preserves_hash(self, mock_load):
        mock_load.return_value = {
            "采集时间": (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "网络适配器": {"adapters": [{"mac_address": "AA:BB:CC:DD:EE:FF"}]},
        }
        result1 = collector.get_config(anonymize=True)
        correct_hash = result1["网络适配器"]["adapters"][0]["mac_address_hash"]
        mock_load.return_value = {
            "采集时间": (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "网络适配器": {"adapters": [{"mac_address": "AA:BB:CC:DD:EE:FF"}]},
        }
        result2 = collector.get_config(anonymize=True)
        self.assertEqual(result2["网络适配器"]["adapters"][0]["mac_address_hash"], correct_hash)


class TestFormatSummary(unittest.TestCase):

    def test_complete_data(self):
        info = {
            "采集时间": "2026-04-29 00:00:00",
            "快速摘要": {
                "hostname": "TEST-PC",
                "os": "Windows",
                "cpu": "Test CPU",
                "cpu_cores": 8,
                "cpu_threads": 16,
                "ram_gb": 32.0,
                "disk_total_gb": 512.0,
                "disk_free_gb": 256.0,
                "gpu": "Test GPU",
            },
        }
        result = collector.format_summary(info)
        self.assertIn("TEST-PC", result)
        self.assertIn("Test CPU", result)
        self.assertIn("32.0 GB", result)

    def test_empty_data(self):
        info = {}
        result = collector.format_summary(info)
        self.assertIn("N/A", result)


class TestCheckPlatform(unittest.TestCase):

    @patch.object(sys, "platform", "linux")
    def test_non_windows_exits(self):
        with self.assertRaises(SystemExit) as cm:
            collector.check_platform()
        self.assertEqual(cm.exception.code, 1)

    @patch.object(sys, "platform", "win32")
    def test_windows_continues(self):
        try:
            collector.check_platform()
        except SystemExit:
            self.fail("check_platform() raised SystemExit on Windows")


class TestExportTxt(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        collector.CACHE_DIR = Path(self.test_dir.name)

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        self.test_dir.cleanup()

    def test_export_creates_file(self):
        info = {
            "采集时间": "2026-04-29",
            "计算机名": "TEST-PC",
            "操作系统": {"caption": "Windows 11", "version": "10.0", "os_arch": "64-bit"},
            "CPU": {"name": "Test CPU", "cores": 8, "logical_processors": 16},
            "内存": {"total_gb": 32.0, "sticks": []},
            "磁盘": {"total_size_gb": 512, "total_free_gb": 256, "drives": []},
            "显卡": {"gpus": []},
        }
        output = collector.export_txt(info, os.path.join(self.test_dir.name, "test.txt"))
        self.assertTrue(os.path.exists(output))
        with open(output, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Test CPU", content)
        self.assertIn("32.0 GB", content)

    def test_export_rejects_invalid_path(self):
        info = {"采集时间": "2026-04-29"}
        with self.assertRaises(ValueError):
            collector.export_txt(info, "C:\\Windows\\System32\\test.txt")


class TestExportCsv(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        collector.CACHE_DIR = Path(self.test_dir.name)

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        self.test_dir.cleanup()

    def test_export_creates_csv(self):
        info = {
            "采集时间": "2026-04-29",
            "计算机名": "TEST-PC",
            "操作系统": {"caption": "Windows 11"},
            "CPU": {"name": "Test CPU"},
            "内存": {"total_gb": 32.0, "sticks": []},
            "磁盘": {"total_size_gb": 512, "total_free_gb": 256, "drives": []},
            "显卡": {"gpus": []},
        }
        output = collector.export_csv(info, os.path.join(self.test_dir.name, "test.csv"))
        self.assertTrue(os.path.exists(output))
        with open(output, "r", encoding="utf-8-sig") as f:
            content = f.read()
        self.assertIn("Test CPU", content)

    def test_export_rejects_invalid_path(self):
        info = {"采集时间": "2026-04-29"}
        with self.assertRaises(ValueError):
            collector.export_csv(info, "C:\\Windows\\System32\\test.csv")


class TestQueryConfig(unittest.TestCase):

    def setUp(self):
        self.data = {
            "采集时间": "2026-04-29",
            "计算机名": "TEST-PC",
            "CPU": {"name": "Intel i7", "cores": 8, "logical_processors": 16},
            "内存": {"total_gb": 32.0, "sticks": [{"capacity_gb": 16.0, "speed_mhz": 4800}]},
            "显卡": {"gpus": [{"name": "RTX 3070", "vram_gb": 8.0}]},
            "操作系统": {"caption": "Windows 11", "version": "10.0"},
        }

    def test_query_top_level_by_alias(self):
        result = collector.query_config(self.data, "cpu")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Intel i7")

    def test_query_top_level_chinese(self):
        result = collector.query_config(self.data, "内存")
        self.assertIsNotNone(result)
        self.assertEqual(result["total_gb"], 32.0)

    def test_query_nested_field(self):
        result = collector.query_config(self.data, "CPU.name")
        self.assertEqual(result, "Intel i7")

    def test_query_deep_nested(self):
        result = collector.query_config(self.data, "内存.total_gb")
        self.assertEqual(result, 32.0)

    def test_query_list_by_index(self):
        result = collector.query_config(self.data, "显卡.gpus.0.name")
        self.assertEqual(result, "RTX 3070")

    def test_query_nonexistent(self):
        result = collector.query_config(self.data, "不存在的字段")
        self.assertIsNone(result)

    def test_query_empty_string(self):
        result = collector.query_config(self.data, "")
        self.assertIsNone(result)

    def test_query_os_alias(self):
        result = collector.query_config(self.data, "os")
        self.assertIsNotNone(result)
        self.assertEqual(result["caption"], "Windows 11")


class TestFormatQueryResult(unittest.TestCase):

    def test_none_result(self):
        result = collector.format_query_result("test", None)
        self.assertIn("未找到", result)

    def test_dict_result(self):
        result = collector.format_query_result("CPU", {"name": "i7", "cores": 8})
        self.assertIn("i7", result)
        self.assertIn("cores", result)

    def test_list_result(self):
        result = collector.format_query_result("gpus", [{"name": "RTX 3070"}])
        self.assertIn("RTX 3070", result)
        self.assertIn("1 项", result)

    def test_scalar_result(self):
        result = collector.format_query_result("CPU.name", "Intel i7")
        self.assertIn("Intel i7", result)


class TestSnapshot(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_snapshots_dir = collector.SNAPSHOTS_DIR
        collector.SNAPSHOTS_DIR = Path(self.test_dir.name) / "snapshots"

    def tearDown(self):
        collector.SNAPSHOTS_DIR = self.original_snapshots_dir
        self.test_dir.cleanup()

    def test_save_snapshot_no_label(self):
        data = {"采集时间": "2026-04-29", "计算机名": "TEST-PC"}
        path = collector.save_snapshot(data)
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            stored = json.load(f)
        self.assertEqual(stored["计算机名"], "TEST-PC")
        self.assertIn("快照时间", stored)

    def test_save_snapshot_with_label(self):
        data = {"采集时间": "2026-04-29", "计算机名": "TEST-PC"}
        path = collector.save_snapshot(data, label="before_upgrade")
        self.assertIn("before_upgrade", path)
        with open(path, "r", encoding="utf-8") as f:
            stored = json.load(f)
        self.assertEqual(stored["快照标签"], "before_upgrade")

    def test_save_snapshot_sanitizes_label(self):
        data = {"采集时间": "2026-04-29"}
        path = collector.save_snapshot(data, label="test/evil\\path")
        self.assertNotIn("/", path.split("\\")[-1])

    def test_list_snapshots_empty(self):
        result = collector.list_snapshots()
        self.assertEqual(result, [])

    def test_list_snapshots_with_data(self):
        data = {"采集时间": "2026-04-29", "计算机名": "TEST-PC"}
        collector.save_snapshot(data, label="test")
        snapshots = collector.list_snapshots()
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["label"], "test")

    def test_format_snapshots_empty(self):
        result = collector.format_snapshots_list([])
        self.assertIn("没有", result)

    def test_format_snapshots_with_data(self):
        data = {"采集时间": "2026-04-29", "计算机名": "TEST-PC"}
        collector.save_snapshot(data, label="v1")
        snapshots = collector.list_snapshots()
        result = collector.format_snapshots_list(snapshots)
        self.assertIn("v1", result)


class TestSystemHealth(unittest.TestCase):

    def test_healthy_system(self):
        data = {
            "磁盘": {"total_size_gb": 1000, "total_free_gb": 500, "drives": [
                {"drive": "C:", "total_gb": 1000, "free_gb": 500}
            ]},
            "内存": {"total_gb": 32},
            "CPU": {"cores": 8},
            "显卡": {"gpus": [{"name": "RTX 3070", "vram_gb": 8.0}]},
            "操作系统": {},
        }
        health = collector.assess_system_health(data)
        self.assertGreaterEqual(health["score"], 90)
        self.assertEqual(len(health["warnings"]), 0)

    def test_low_disk_space(self):
        data = {
            "磁盘": {"total_size_gb": 1000, "total_free_gb": 50, "drives": [
                {"drive": "C:", "total_gb": 1000, "free_gb": 50}
            ]},
            "内存": {"total_gb": 32},
            "CPU": {"cores": 8},
            "显卡": {"gpus": []},
            "操作系统": {},
        }
        health = collector.assess_system_health(data)
        self.assertLess(health["score"], 90)
        self.assertTrue(any("磁盘" in w for w in health["warnings"]))

    def test_critical_disk_space(self):
        data = {
            "磁盘": {"total_size_gb": 1000, "total_free_gb": 10, "drives": [
                {"drive": "C:", "total_gb": 1000, "free_gb": 10}
            ]},
            "内存": {"total_gb": 32},
            "CPU": {"cores": 8},
            "显卡": {"gpus": []},
            "操作系统": {},
        }
        health = collector.assess_system_health(data)
        self.assertLessEqual(health["score"], 80)
        self.assertTrue(any("严重" in w for w in health["warnings"]))

    def test_low_ram(self):
        data = {
            "磁盘": {"total_size_gb": 1000, "total_free_gb": 500, "drives": []},
            "内存": {"total_gb": 2},
            "CPU": {"cores": 8},
            "显卡": {"gpus": []},
            "操作系统": {},
        }
        health = collector.assess_system_health(data)
        self.assertTrue(any("内存" in w for w in health["warnings"]))

    def test_few_cpu_cores(self):
        data = {
            "磁盘": {"total_size_gb": 1000, "total_free_gb": 500, "drives": []},
            "内存": {"total_gb": 32},
            "CPU": {"cores": 2},
            "显卡": {"gpus": []},
            "操作系统": {},
        }
        health = collector.assess_system_health(data)
        self.assertTrue(any("核心" in i for i in health["info"]))

    def test_empty_data(self):
        health = collector.assess_system_health({})
        self.assertEqual(health["score"], 100)

    def test_score_bounded(self):
        data = {
            "磁盘": {"total_size_gb": 100, "total_free_gb": 1, "drives": [
                {"drive": "C:", "total_gb": 100, "free_gb": 1}
            ]},
            "内存": {"total_gb": 1},
            "CPU": {"cores": 1},
            "显卡": {"gpus": [{"name": "Old", "vram_gb": 0.5}]},
            "操作系统": {},
        }
        health = collector.assess_system_health(data)
        self.assertGreaterEqual(health["score"], 0)
        self.assertLessEqual(health["score"], 100)


class TestFormatHealthReport(unittest.TestCase):

    def test_excellent_score(self):
        health = {"score": 95, "warnings": [], "info": [], "details": {"磁盘使用率": "50.0%"}}
        result = collector.format_health_report(health)
        self.assertIn("优秀", result)
        self.assertIn("95", result)

    def test_good_score(self):
        health = {"score": 80, "warnings": [], "info": ["内存充足"], "details": {}}
        result = collector.format_health_report(health)
        self.assertIn("良好", result)

    def test_warning_display(self):
        health = {"score": 70, "warnings": ["磁盘空间紧张"], "info": [], "details": {}}
        result = collector.format_health_report(health)
        self.assertIn("磁盘空间紧张", result)

    def test_no_issues(self):
        health = {"score": 100, "warnings": [], "info": [], "details": {}}
        result = collector.format_health_report(health)
        self.assertIn("良好", result)


class TestImportConfig(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        self.original_cache_file = collector.CACHE_FILE
        collector.CACHE_DIR = Path(self.test_dir.name)
        collector.CACHE_FILE = collector.CACHE_DIR / "config.json"

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        collector.CACHE_FILE = self.original_cache_file
        self.test_dir.cleanup()

    def test_import_valid_config(self):
        data = {
            "采集时间": "2026-04-29 00:00:00",
            "计算机名": "TEST-PC",
            "CPU": {"name": "Test CPU"},
        }
        import_file = Path(self.test_dir.name) / "import_test.json"
        with open(import_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = collector.import_config(str(import_file))
        self.assertTrue(result)
        cached_file = collector.CACHE_DIR / "config.json"
        self.assertTrue(cached_file.exists())
        with open(cached_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        self.assertEqual(cached["计算机名"], "TEST-PC")

    def test_import_nonexistent_file(self):
        result = collector.import_config("nonexistent.json")
        self.assertFalse(result)

    def test_import_invalid_format(self):
        import_file = Path(self.test_dir.name) / "invalid.json"
        with open(import_file, "w", encoding="utf-8") as f:
            f.write("{invalid json")
        result = collector.import_config(str(import_file))
        self.assertFalse(result)

    def test_import_non_json_file(self):
        import_file = Path(self.test_dir.name) / "test.txt"
        import_file.write_text("hello")
        result = collector.import_config(str(import_file))
        self.assertFalse(result)

    def test_import_missing_required_fields(self):
        data = {"foo": "bar"}
        import_file = Path(self.test_dir.name) / "empty.json"
        with open(import_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = collector.import_config(str(import_file))
        self.assertFalse(result)

    def test_import_list_instead_of_dict(self):
        import_file = Path(self.test_dir.name) / "list.json"
        with open(import_file, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
        result = collector.import_config(str(import_file))
        self.assertFalse(result)


class TestResolveAlias(unittest.TestCase):

    def test_resolve_cpu_alias(self):
        result = collector._resolve_alias("cpu")
        self.assertEqual(result, "CPU")

    def test_resolve_memory_alias(self):
        result = collector._resolve_alias("memory")
        self.assertEqual(result, "内存")

    def test_resolve_unknown_alias(self):
        result = collector._resolve_alias("unknown")
        self.assertEqual(result, "unknown")

    def test_resolve_chinese_alias(self):
        result = collector._resolve_alias("处理器")
        self.assertEqual(result, "CPU")

    def test_resolve_os_alias(self):
        result = collector._resolve_alias("os")
        self.assertEqual(result, "操作系统")


class TestQueryConfigEdgeCases(unittest.TestCase):

    def setUp(self):
        self.data = {
            "采集时间": "2026-04-29",
            "计算机名": "TEST-PC",
            "CPU": {"name": "Intel i7", "cores": 8},
            "内存": {"total_gb": 32.0, "sticks": [{"capacity_gb": 16.0}]},
            "显卡": {"gpus": [{"name": "RTX 3070"}]},
        }

    def test_query_with_spaces_in_path(self):
        result = collector.query_config(self.data, "CPU. name ")
        self.assertEqual(result, "Intel i7")

    def test_query_empty_segments(self):
        result = collector.query_config(self.data, "CPU..name")
        self.assertEqual(result, "Intel i7")

    def test_query_invalid_list_index(self):
        result = collector.query_config(self.data, "显卡.gpus.abc")
        self.assertIsNone(result)

    def test_query_out_of_bounds_index(self):
        result = collector.query_config(self.data, "显卡.gpus.10")
        self.assertIsNone(result)

    def test_query_negative_index(self):
        result = collector.query_config(self.data, "显卡.gpus.-1")
        self.assertEqual(result, {"name": "RTX 3070"})

    def test_query_path_to_scalar(self):
        result = collector.query_config(self.data, "CPU.name.length")
        self.assertIsNone(result)


class TestConstants(unittest.TestCase):

    def test_sensitive_fields_immutable(self):
        self.assertIsInstance(collector.SENSITIVE_FIELDS, frozenset)

    def test_hardware_categories_immutable(self):
        self.assertIsInstance(collector.HARDWARE_CATEGORIES, frozenset)

    def test_system_categories_immutable(self):
        self.assertIsInstance(collector.SYSTEM_CATEGORIES, frozenset)

    def test_module_aliases_has_required_keys(self):
        for key in ["cpu", "内存", "os", "gpu", "磁盘"]:
            self.assertIn(key, collector.MODULE_ALIASES)

    def test_health_score_constants_order(self):
        self.assertGreater(collector.HEALTH_SCORE_EXCELLENT, collector.HEALTH_SCORE_GOOD)
        self.assertGreater(collector.HEALTH_SCORE_GOOD, collector.HEALTH_SCORE_FAIR)

    def test_disk_usage_constants_order(self):
        self.assertGreater(collector.DISK_USAGE_CRITICAL, collector.DISK_USAGE_WARNING)
        self.assertGreater(collector.DISK_USAGE_WARNING, collector.DISK_USAGE_NOTICE)


if __name__ == "__main__":
    unittest.main()
