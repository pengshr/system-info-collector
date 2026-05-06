# -*- coding: utf-8 -*-
"""
System Information Collector - 电脑配置信息采集器
策略: 1.PowerShell Get-CimInstance -> 2.wmic -> 3.platform 模块
"""

import argparse
import copy
import csv
import hashlib
import hmac
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

# Windows 专有模块，延迟导入以支持跨平台检查
msvcrt = None

logger = logging.getLogger(__name__)

TIMEOUT_POWERSHELL = 15
TIMEOUT_WMIC = 10
TIMEOUT_BATCH = 30
CACHE_EXPIRY_HOURS = 24
# HMAC 盐值：优先从环境变量读取，否则使用机器特定标识生成
def _get_hmac_salt() -> bytes:
    env_salt = os.getenv("SYSTEM_INFO_HMAC_SALT")
    if env_salt:
        return env_salt.encode()
    # 使用计算机名 + 用户名生成确定性盐值
    machine_id = f"{platform.node()}-{os.getlogin() if hasattr(os, 'getlogin') else 'default'}"
    return hashlib.sha256(machine_id.encode()).digest()

HMAC_SALT = _get_hmac_salt()
GB = 1024 ** 3
DT_FORMAT = "%Y-%m-%d %H:%M:%S"
HEALTH_SCORE_EXCELLENT = 90
HEALTH_SCORE_GOOD = 75
HEALTH_SCORE_FAIR = 60
DISK_USAGE_CRITICAL = 90
DISK_USAGE_WARNING = 80
DISK_USAGE_NOTICE = 70
DISK_DRIVE_NEARLY_FULL = 95
RAM_MINIMUM = 4
RAM_RECOMMENDED = 8
RAM_OPTIMAL = 16
CPU_CORES_MINIMUM = 4
GPU_VRAM_MINIMUM = 2
UPTIME_RESTART_DAYS = 30
SECURE_DELETE_OVERWRITE_BYTE = b"\x00"
TEMP_CRITICAL = 80
TEMP_WARNING = 70
CPU_USAGE_CRITICAL = 90
CPU_USAGE_WARNING = 80
MEM_USAGE_CRITICAL = 90
MEM_USAGE_WARNING = 80
BATTERY_DEGRADED_PCT = 50

SENSITIVE_FIELDS = frozenset({"serial_number", "mac_address"})

CACHE_DIR = Path(__file__).parent
CACHE_FILE = CACHE_DIR / "config.json"
SNAPSHOTS_DIR = CACHE_DIR / "snapshots"
CREATION_FLAGS = subprocess.CREATE_NO_WINDOW

IGNORED_COMPARE_KEYS = frozenset({"采集时间"})

MODULE_ALIASES = {
    "os": "操作系统", "操作系统": "操作系统", "系统": "操作系统",
    "cpu": "CPU", "处理器": "CPU", "processor": "CPU",
    "内存": "内存", "memory": "内存", "ram": "内存", "运存": "内存",
    "磁盘": "磁盘", "disk": "磁盘", "硬盘": "磁盘", "存储": "磁盘",
    "显卡": "显卡", "gpu": "显卡", "graphics": "显卡", "图形": "显卡",
    "主板": "主板", "motherboard": "主板", "baseboard": "主板",
    "bios": "BIOS",
    "网络": "网络适配器", "网卡": "网络适配器", "network": "网络适配器", "适配器": "网络适配器",
    "电池": "电池", "battery": "电池", "电源": "电池",
    "温度": "温度传感器", "temperature": "温度传感器", "传感器": "温度传感器", "temp": "温度传感器",
    "进程": "进程", "processes": "进程", "process": "进程", "processors": "进程",
    "软件": "已安装软件", "software": "已安装软件", "应用": "已安装软件", "apps": "已安装软件",
    "性能": "性能计数器", "performance": "性能计数器", "perf": "性能计数器",
    "摘要": "快速摘要", "summary": "快速摘要",
}

HARDWARE_CATEGORIES = frozenset({"CPU", "内存", "磁盘", "显卡", "主板", "BIOS", "网络适配器", "电池", "温度传感器"})
SYSTEM_CATEGORIES = frozenset({"操作系统", "计算机名", "进程", "已安装软件", "性能计数器"})

# [CONTENT_TRUNCATED_FULL_FILE_UPLOAD]