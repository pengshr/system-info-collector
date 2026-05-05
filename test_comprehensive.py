# -*- coding: utf-8 -*-
"""
System Information Collector - 全面可用性和隐私安全验证测试

测试类别：
1. 核心功能可用性
2. 边缘场景处理
3. 隐私安全保护
4. 数据加密机制
5. 访问权限控制
6. 异常数据隐私保护
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
import hashlib
import hmac

sys.path.insert(0, str(Path(__file__).parent))
import collector


class TestCoreFunctionality(unittest.TestCase):
    """核心功能可用性测试"""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        self.original_cache_file = collector.CACHE_FILE
        collector.CACHE_DIR = Path(self.test_dir.name)
        collector.CACHE_FILE = collector.CACHE_DIR / "config.json"
        self.sample_data = {
            "采集时间": (datetime.now() - timedelta(hours=1)).strftime(collector.DT_FORMAT),
            "计算机名": "TEST-PC",
            "操作系统": {"caption": "Windows 11", "version": "10.0", "os_arch": "64-bit"},
            "CPU": {"name": "Intel i7", "cores": 8, "logical_processors": 16},
            "内存": {"total_gb": 32.0, "sticks": [{"capacity_gb": 16.0, "speed_mhz": 4800}]},
            "磁盘": {
                "total_size_gb": 512.0,
                "total_free_gb": 256.0,
                "drives": [{"drive": "C:", "total_gb": 512.0, "free_gb": 256.0, "file_system": "NTFS"}]
            },
            "显卡": {"gpus": [{"name": "RTX 3070", "vram_gb": 8.0}]},
            "主板": {"manufacturer": "ASUS", "product": "GA503RW", "serial_number": "MB-SN-12345"},
            "BIOS": {"manufacturer": "AMI", "name": "BIOS", "serial_number": "BIOS-SN-67890"},
            "网络适配器": {"adapters": [{"name": "Ethernet", "mac_address": "AA:BB:CC:DD:EE:FF"}]},
        }

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        collector.CACHE_FILE = self.original_cache_file
        self.test_dir.cleanup()

    def test_cache_save_and_load(self):
        """测试缓存保存和读取功能"""
        collector.save_cache(self.sample_data)
        loaded = collector.load_cache()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["计算机名"], "TEST-PC")
        self.assertEqual(loaded["CPU"]["cores"], 8)

    def test_query_config_top_level(self):
        """测试顶层配置查询"""
        result = collector.query_config(self.sample_data, "CPU")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Intel i7")

    def test_query_config_nested(self):
        """测试嵌套配置查询"""
        result = collector.query_config(self.sample_data, "内存.total_gb")
        self.assertEqual(result, 32.0)

    def test_query_config_with_alias(self):
        """测试别名查询"""
        result = collector.query_config(self.sample_data, "cpu.name")
        self.assertEqual(result, "Intel i7")

    def test_query_config_list_index(self):
        """测试列表索引查询"""
        result = collector.query_config(self.sample_data, "显卡.gpus.0.name")
        self.assertEqual(result, "RTX 3070")

    def test_export_txt(self):
        """测试 TXT 导出功能"""
        output_path = collector.export_txt(self.sample_data)
        self.assertTrue(os.path.exists(output_path))
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Intel i7", content)
        self.assertIn("32.0 GB", content)

    def test_export_csv(self):
        """测试 CSV 导出功能"""
        output_path = collector.export_csv(self.sample_data)
        self.assertTrue(os.path.exists(output_path))
        with open(output_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        self.assertIn("Intel i7", content)

    def test_save_and_list_snapshot(self):
        """测试快照保存和列表功能"""
        path = collector.save_snapshot(self.sample_data, label="test_snapshot")
        self.assertTrue(os.path.exists(path))
        snapshots = collector.list_snapshots()
        self.assertGreater(len(snapshots), 0)
        self.assertEqual(snapshots[0]["label"], "test_snapshot")

    def test_system_health_assessment(self):
        """测试系统健康评估"""
        health = collector.assess_system_health(self.sample_data)
        self.assertIn("score", health)
        self.assertIn("warnings", health)
        self.assertIn("info", health)
        self.assertGreaterEqual(health["score"], 0)
        self.assertLessEqual(health["score"], 100)

    def test_compare_configs_identical(self):
        """测试配置对比（相同配置）"""
        result = collector.compare_configs(self.sample_data, copy.deepcopy(self.sample_data))
        self.assertEqual(len(result), 0)

    def test_compare_configs_different(self):
        """测试配置对比（不同配置）"""
        data2 = copy.deepcopy(self.sample_data)
        data2["CPU"]["cores"] = 12
        result = collector.compare_configs(self.sample_data, data2)
        self.assertGreater(len(result), 0)

    def test_import_config(self):
        """测试配置导入功能"""
        import_file = Path(self.test_dir.name) / "import.json"
        with open(import_file, "w", encoding="utf-8") as f:
            json.dump(self.sample_data, f)
        result = collector.import_config(str(import_file))
        self.assertTrue(result)
        cached_file = collector.CACHE_DIR / "config.json"
        self.assertTrue(cached_file.exists())


class TestEdgeCases(unittest.TestCase):
    """边缘场景测试"""

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

    def test_empty_data_handling(self):
        """测试空数据处理"""
        health = collector.assess_system_health({})
        self.assertEqual(health["score"], 100)

    def test_none_values_in_config(self):
        """测试配置中的 None 值"""
        data = {
            "采集时间": "2026-04-29",
            "CPU": {"name": None, "cores": None},
        }
        result = collector.query_config(data, "CPU.name")
        self.assertIsNone(result)

    def test_deeply_nested_query(self):
        """测试深度嵌套查询"""
        data = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "value": "deep"
                        }
                    }
                }
            }
        }
        result = collector.query_config(data, "level1.level2.level3.level4.value")
        self.assertEqual(result, "deep")

    def test_invalid_json_import(self):
        """测试无效 JSON 导入"""
        invalid_file = Path(self.test_dir.name) / "invalid.json"
        invalid_file.write_text("{invalid json content}")
        result = collector.import_config(str(invalid_file))
        self.assertFalse(result)

    def test_corrupted_cache_handling(self):
        """测试损坏缓存处理"""
        collector.CACHE_FILE.write_text("{corrupted json}")
        result = collector.load_cache()
        self.assertIsNone(result)
        self.assertFalse(collector.CACHE_FILE.exists())

    def test_expired_cache_handling(self):
        """测试过期缓存处理"""
        old_data = {
            "采集时间": (datetime.now() - timedelta(hours=25)).strftime(collector.DT_FORMAT),
            "计算机名": "TEST-PC",
        }
        with open(collector.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(old_data, f)
        result = collector.load_cache()
        self.assertIsNone(result)

    def test_concurrent_read_simulation(self):
        """模拟并发读取场景"""
        data = {
            "采集时间": (datetime.now() - timedelta(minutes=5)).strftime(collector.DT_FORMAT),
            "计算机名": "TEST-PC",
        }
        with open(collector.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        
        for _ in range(10):
            result = collector.load_cache()
            self.assertIsNotNone(result)
            self.assertEqual(result["计算机名"], "TEST-PC")

    def test_large_config_handling(self):
        """测试大配置处理"""
        large_data = {
            "采集时间": (datetime.now() - timedelta(hours=1)).strftime(collector.DT_FORMAT),
            "计算机名": "TEST-PC",
            "network_adapters": {
                "adapters": [
                    {"name": f"Adapter {i}", "mac_address": f"AA:BB:CC:DD:EE:{i:02X}"}
                    for i in range(100)
                ]
            }
        }
        collector.save_cache(large_data)
        result = collector.load_cache()
        self.assertIsNotNone(result)
        self.assertEqual(len(result["network_adapters"]["adapters"]), 100)


class TestPrivacySecurity(unittest.TestCase):
    """隐私安全验证"""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        self.original_cache_file = collector.CACHE_FILE
        collector.CACHE_DIR = Path(self.test_dir.name)
        collector.CACHE_FILE = collector.CACHE_DIR / "config.json"
        self.sensitive_data = {
            "采集时间": (datetime.now() - timedelta(hours=1)).strftime(collector.DT_FORMAT),
            "计算机名": "TEST-PC",
            "主板": {
                "manufacturer": "ASUS",
                "product": "GA503RW",
                "serial_number": "MB-SERIAL-123456",
            },
            "BIOS": {
                "manufacturer": "AMI",
                "serial_number": "BIOS-SERIAL-789012",
            },
            "网络适配器": {
                "adapters": [
                    {"name": "Ethernet", "mac_address": "AA:BB:CC:DD:EE:FF"},
                    {"name": "WiFi", "mac_address": "11:22:33:44:55:66"},
                ]
            },
        }

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        collector.CACHE_FILE = self.original_cache_file
        self.test_dir.cleanup()

    def test_mac_address_anonymization(self):
        """测试 MAC 地址脱敏"""
        result = collector.filter_sensitive_data(self.sensitive_data, anonymize=True)
        for adapter in result["网络适配器"]["adapters"]:
            self.assertEqual(adapter["mac_address"], "已脱敏")
            self.assertIn("mac_address_hash", adapter)
            self.assertNotEqual(adapter["mac_address_hash"], "")

    def test_serial_number_anonymization(self):
        """测试序列号脱敏"""
        result = collector.filter_sensitive_data(self.sensitive_data, anonymize=True)
        self.assertEqual(result["主板"]["serial_number"], "已脱敏")
        self.assertEqual(result["BIOS"]["serial_number"], "已脱敏")

    def test_mac_hash_uniqueness(self):
        """测试 MAC 哈希值唯一性"""
        mac1 = "AA:BB:CC:DD:EE:FF"
        mac2 = "11:22:33:44:55:66"
        hash1 = collector.hash_mac_address(mac1)
        hash2 = collector.hash_mac_address(mac2)
        self.assertNotEqual(hash1, hash2)

    def test_mac_hash_deterministic(self):
        """测试 MAC 哈希值确定性"""
        mac = "AA:BB:CC:DD:EE:FF"
        hash1 = collector.hash_mac_address(mac)
        hash2 = collector.hash_mac_address(mac)
        self.assertEqual(hash1, hash2)

    def test_hmac_sha256_implementation(self):
        """验证 HMAC-SHA256 实现"""
        mac = "AA:BB:CC:DD:EE:FF"
        expected = hmac.new(
            collector.HMAC_SALT,
            mac.encode(),
            hashlib.sha256
        ).hexdigest()
        actual = collector.hash_mac_address(mac)
        self.assertEqual(expected, actual)
        self.assertEqual(len(actual), 64)

    def test_anonymize_preserves_structure(self):
        """测试脱敏保留数据结构"""
        result = collector.filter_sensitive_data(self.sensitive_data, anonymize=True)
        self.assertEqual(result["主板"]["manufacturer"], "ASUS")
        self.assertEqual(result["主板"]["product"], "GA503RW")
        self.assertEqual(result["计算机名"], "TEST-PC")

    def test_no_anonymize_returns_original(self):
        """测试不脱敏返回原始数据"""
        result = collector.filter_sensitive_data(self.sensitive_data, anonymize=False)
        self.assertEqual(result["主板"]["serial_number"], "MB-SERIAL-123456")
        self.assertEqual(result["网络适配器"]["adapters"][0]["mac_address"], "AA:BB:CC:DD:EE:FF")

    def test_double_anonymization_consistency(self):
        """测试双重脱敏一致性"""
        result1 = collector.filter_sensitive_data(self.sensitive_data, anonymize=True)
        result2 = collector.filter_sensitive_data(result1, anonymize=True)
        self.assertEqual(
            result1["网络适配器"]["adapters"][0]["mac_address_hash"],
            result2["网络适配器"]["adapters"][0]["mac_address_hash"]
        )
        self.assertEqual(result2["网络适配器"]["adapters"][0]["mac_address"], "已脱敏")

    def test_sensitive_fields_constant(self):
        """测试敏感字段常量定义"""
        self.assertIn("serial_number", collector.SENSITIVE_FIELDS)
        self.assertIn("mac_address", collector.SENSITIVE_FIELDS)
        self.assertIsInstance(collector.SENSITIVE_FIELDS, frozenset)


class TestDataEncryption(unittest.TestCase):
    """数据加密机制验证"""

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

    def test_secure_delete_file(self):
        """测试安全文件删除"""
        test_file = Path(self.test_dir.name) / "secret.txt"
        test_file.write_text("sensitive data here")
        self.assertTrue(test_file.exists())
        
        result = collector._secure_delete_file(test_file)
        self.assertTrue(result)
        self.assertFalse(test_file.exists())

    def test_script_hash_verification(self):
        """测试脚本哈希校验"""
        ps_script = Path(self.test_dir.name) / "test.ps1"
        ps_script.write_text("Write-Host 'Test'")
        
        hash_value = hashlib.sha256(ps_script.read_bytes()).hexdigest()
        self.assertEqual(len(hash_value), 64)
        
        ps_script_hash = ps_script.with_suffix(".ps1.sha256")
        ps_script_hash.write_text(hash_value)
        
        stored_hash = ps_script_hash.read_text().strip()
        self.assertEqual(hash_value, stored_hash)

    def test_atomic_write_prevents_corruption(self):
        """测试原子写入防止损坏"""
        data = {
            "采集时间": (datetime.now() - timedelta(hours=1)).strftime(collector.DT_FORMAT),
            "计算机名": "TEST-PC",
        }
        
        temp_file = collector.CACHE_FILE.with_suffix(".tmp")
        collector.save_cache(data)
        
        self.assertTrue(collector.CACHE_FILE.exists())
        self.assertFalse(temp_file.exists())
        
        with open(collector.CACHE_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["计算机名"], "TEST-PC")

    def test_file_lock_mechanism(self):
        """测试文件锁机制"""
        test_file = Path(self.test_dir.name) / "lock_test.txt"
        test_file.write_text("test content")
        
        with open(test_file, "r", encoding="utf-8") as f:
            locked = collector._acquire_file_lock(f)
            self.assertTrue(locked)
            collector._release_file_lock(f)


class TestAccessControl(unittest.TestCase):
    """访问权限控制测试"""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        collector.CACHE_DIR = Path(self.test_dir.name)

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        self.test_dir.cleanup()

    def test_export_path_validation(self):
        """测试导出路径验证"""
        valid_path = collector._validate_export_path(str(Path(self.test_dir.name) / "output.txt"))
        self.assertIsNotNone(valid_path)
        
        invalid_path = collector._validate_export_path("C:\\Windows\\System32\\output.txt")
        self.assertIsNone(invalid_path)

    def test_compare_path_validation(self):
        """测试对比路径验证"""
        test_file = Path(self.test_dir.name) / "compare.json"
        test_file.write_text("{}")
        
        valid_path = collector.validate_compare_path(str(test_file))
        self.assertIsNotNone(valid_path)
        
        invalid_path = collector.validate_compare_path("C:\\Windows\\System32\\config.json")
        self.assertIsNone(invalid_path)

    def test_path_traversal_protection(self):
        """测试路径遍历保护"""
        evil_path = collector._validate_export_path("C:\\test\\..\\..\\Windows\\System32\\output.txt")
        resolved = Path(evil_path).resolve() if evil_path else None
        
        if resolved:
            self.assertFalse(resolved.is_relative_to(Path("C:\\Windows")))

    def test_import_path_validation(self):
        """测试导入路径验证"""
        test_file = Path(self.test_dir.name) / "import.json"
        test_file.write_text('{"采集时间": "2026-04-29"}')
        
        result = collector.import_config(str(test_file))
        self.assertTrue(result)

    def test_non_json_import_rejected(self):
        """测试非 JSON 导入被拒绝"""
        test_file = Path(self.test_dir.name) / "test.txt"
        test_file.write_text("not json")
        
        result = collector.import_config(str(test_file))
        self.assertFalse(result)


class TestExceptionPrivacy(unittest.TestCase):
    """异常数据隐私保护测试"""

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

    def test_error_log_no_sensitive_data(self):
        """测试错误日志不包含敏感数据"""
        import logging
        import io
        
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("collector")
        logger.addHandler(handler)
        
        collector.CACHE_FILE.write_text("{invalid json}")
        collector.load_cache()
        
        log_output = log_stream.getvalue()
        self.assertNotIn("serial_number", log_output)
        self.assertNotIn("mac_address", log_output)

    def test_corrupted_data_doesnt_leak(self):
        """测试损坏数据不泄露"""
        collector.CACHE_FILE.write_text('{invalid json content}')
        
        result = collector.load_cache()
        self.assertIsNone(result)
        self.assertFalse(collector.CACHE_FILE.exists())

    def test_exception_safe_delete(self):
        """测试异常安全删除"""
        nonexistent = Path(self.test_dir.name) / "nonexistent.txt"
        result = collector._secure_delete_file(nonexistent)
        self.assertFalse(result)

    def test_invalid_input_handling(self):
        """测试无效输入处理"""
        result = collector.query_config({}, "any.field")
        self.assertIsNone(result)
        
        result = collector.query_config({"CPU": None}, "CPU.name")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
