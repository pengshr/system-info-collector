# -*- coding: utf-8 -*-
import unittest
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import collector


class TestComprehensive(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = collector.CACHE_DIR
        collector.CACHE_DIR = Path(self.test_dir.name)
        collector.CACHE_FILE = collector.CACHE_DIR / "config.json"

    def tearDown(self):
        collector.CACHE_DIR = self.original_cache_dir
        collector.CACHE_FILE = collector.CACHE_DIR / "config.json"
        self.test_dir.cleanup()

    def test_full_workflow(self):
        data = {"采集时间": collector._now_str(), "计算机名": "test", "CPU": {"name": "Test CPU"}}
        self.assertTrue(collector.save_cache(data))
        cached = collector.load_cache()
        self.assertIsNotNone(cached)
        self.assertEqual(cached["计算机名"], "test")

    def test_import_config(self):
        test_file = Path(self.test_dir.name) / "import_test.json"
        test_file.write_text(json.dumps({"采集时间": collector._now_str(), "计算机名": "imported"}, ensure_ascii=False))
        self.assertTrue(collector.import_config(str(test_file)))
        cached = collector.load_cache()
        self.assertEqual(cached["计算机名"], "imported")

    def test_export_txt(self):
        data = {"采集时间": collector._now_str(), "计算机名": "test", "操作系统": {"caption": "Windows 11"}, "CPU": {"name": "Test CPU"}, "内存": {"total_gb": 16, "sticks": []}, "磁盘": {"total_size_gb": 500, "total_free_gb": 250, "drives": []}, "显卡": {"gpus": []}, "主板": {}}
        path = collector.export_txt(data)
        self.assertTrue(Path(path).exists())
        content = Path(path).read_text()
        self.assertIn("Windows 11", content)

    def test_empty_data_handling(self):
        health = collector.assess_system_health({})
        self.assertLessEqual(health["score"], 100)
        self.assertGreaterEqual(health["score"], 0)


if __name__ == "__main__":
    unittest.main()
