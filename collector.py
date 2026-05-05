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
import msvcrt
import os
import platform
import subprocess
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

TIMEOUT_POWERSHELL = 15
TIMEOUT_WMIC = 10
TIMEOUT_BATCH = 30
CACHE_EXPIRY_HOURS = 24
HMAC_SALT = b"system-info-collector-v2-salt"
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
    "bios": "BIOS", "BIOS": "BIOS",
    "网络": "网络适配器", "网卡": "网络适配器", "network": "网络适配器", "适配器": "网络适配器",
    "摘要": "快速摘要", "summary": "快速摘要",
}

HARDWARE_CATEGORIES = frozenset({"CPU", "内存", "磁盘", "显卡", "主板", "BIOS", "网络适配器"})
SYSTEM_CATEGORIES = frozenset({"操作系统", "计算机名"})


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def check_platform() -> None:
    if sys.platform != "win32":
        print(f"错误: 此技能仅支持 Windows 系统，当前平台: {sys.platform}")
        sys.exit(1)


def _run_subprocess(cmd: list[str], timeout: int) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, creationflags=CREATION_FLAGS,
        )
    except FileNotFoundError:
        logger.error("命令未找到: %s", cmd[0])
        return None
    except subprocess.TimeoutExpired:
        logger.warning("命令执行超时(%d秒): %s", timeout, cmd[0])
        return None
    except PermissionError:
        logger.error("权限不足: %s", cmd[0])
        return None
    except Exception as e:
        logger.error("执行异常 %s: %s", cmd[0], e)
        return None


def run_powershell(script: str) -> Optional[str]:
    result = _run_subprocess(["powershell", "-NoProfile", "-Command", script], TIMEOUT_POWERSHELL)
    if result is None or result.returncode != 0:
        if result:
            logger.warning("PowerShell 退出码 %d: %s", result.returncode, result.stderr.strip())
        return None
    return result.stdout.strip()


def run_powershell_json(script: str) -> Optional[Any]:
    text = run_powershell(f"{script} | ConvertTo-Json -Compress")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("PowerShell JSON 解析失败: %s", e)
        return None


def run_wmic(args: list[str]) -> Optional[str]:
    result = _run_subprocess(["wmic"] + args, TIMEOUT_WMIC)
    if result is None or result.returncode != 0:
        if result:
            logger.warning("WMIC 退出码 %d: %s", result.returncode, result.stderr.strip())
        return None
    return result.stdout.strip()


def parse_wmic_table(text: Optional[str]) -> list:
    if not text:
        return []
    lines = [s.strip() for s in text.split("\n") if s.strip()]
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].split(",")]
    rows = []
    for line in lines[1:]:
        values = [v.strip() for v in line.split(",")]
        if len(values) == len(headers):
            rows.append(dict(zip(headers, values)))
    return rows


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_wmi_date(wmi_date_str: Any) -> Optional[str]:
    if not wmi_date_str:
        return None
    if isinstance(wmi_date_str, str) and wmi_date_str.startswith("/Date("):
        try:
            timestamp_ms = int(wmi_date_str[6:-2])
            return datetime.fromtimestamp(timestamp_ms / 1000).strftime(DT_FORMAT)
        except (ValueError, IndexError, OSError):
            logger.debug("WMI 日期解析失败: %s", wmi_date_str)
            return None
    if isinstance(wmi_date_str, str) and len(wmi_date_str) >= 19:
        return wmi_date_str[:19]
    if isinstance(wmi_date_str, str) and len(wmi_date_str) >= 10:
        return wmi_date_str[:10]
    return str(wmi_date_str)


def hash_mac_address(mac: str) -> str:
    return hmac.new(HMAC_SALT, mac.encode(), hashlib.sha256).hexdigest()


def _anonymize_dict_recursive(data: dict) -> None:
    for key in list(data):
        if key in SENSITIVE_FIELDS:
            if key == "mac_address" and isinstance(data[key], str) and data[key] != "已脱敏":
                data["mac_address_hash"] = hash_mac_address(data[key])
                data[key] = "已脱敏"
            elif key == "serial_number":
                data[key] = "已脱敏"
        elif isinstance(data[key], dict):
            _anonymize_dict_recursive(data[key])
        elif isinstance(data[key], list):
            for item in data[key]:
                if isinstance(item, dict):
                    _anonymize_dict_recursive(item)


def filter_sensitive_data(data: dict, anonymize: bool = True) -> dict:
    if not anonymize:
        return copy.deepcopy(data)
    filtered = copy.deepcopy(data)
    _anonymize_dict_recursive(filtered)
    return filtered


def format_speed(speed_bps: Optional[int]) -> str:
    if not speed_bps:
        return "未知"
    if speed_bps >= 1_000_000_000:
        return f"{round(speed_bps / 1_000_000_000, 2)} Gbps"
    if speed_bps >= 1_000_000:
        return f"{round(speed_bps / 1_000_000, 1)} Mbps"
    return f"{speed_bps} bps"


def _bytes_to_gb(b: int) -> float:
    return round(b / GB, 2)


def _parse_os_batched(data: Optional[dict], hostname: str, os_info: dict) -> dict:
    base = {
        "system": os_info["system"],
        "release": os_info["release"],
        "version": os_info["version"],
        "cpu_arch": os_info["architecture"],
        "hostname": hostname,
    }
    if not data:
        return base
    return {
        **base,
        "os_arch": data.get("OSArchitecture", "N/A"),
        "caption": data.get("Caption", "N/A"),
        "build_number": data.get("BuildNumber", "N/A"),
        "install_date": parse_wmi_date(data.get("InstallDate")),
        "last_bootup": parse_wmi_date(data.get("LastBootUpTime")),
    }


def _parse_cpu_batched(data: Optional[dict], processor: str) -> dict:
    if not data:
        return {"processor": processor}
    return {
        "processor": processor,
        "name": (data.get("Name") or "N/A").strip(),
        "cores": safe_int(data.get("NumberOfCores")),
        "logical_processors": safe_int(data.get("NumberOfLogicalProcessors")),
        "max_clock_speed_mhz": data.get("MaxClockSpeed", "N/A"),
        "l2_cache_kb": data.get("L2CacheSize", "N/A"),
        "l3_cache_kb": data.get("L3CacheSize", "N/A"),
    }


def _parse_memory_batched(data: Optional[Any]) -> dict:
    if not data:
        return {"sticks": [], "total_gb": None}
    sticks_list = data if isinstance(data, list) else [data]
    sticks = []
    total_gb = 0.0
    for stick in sticks_list:
        cap = safe_int(stick.get("Capacity"), 0) or 0
        gb = _bytes_to_gb(cap)
        total_gb += gb
        sticks.append({
            "capacity_gb": gb,
            "speed_mhz": stick.get("Speed", "N/A"),
            "manufacturer": stick.get("Manufacturer", "N/A"),
            "part_number": (stick.get("PartNumber") or "N/A").strip(),
        })
    return {"total_gb": round(total_gb, 2), "sticks": sticks}


def _parse_disk_batched(data: Optional[Any]) -> dict:
    if not data:
        return {"drives": [], "total_size_gb": 0, "total_free_gb": 0}
    drives_list = data if isinstance(data, list) else [data]
    total_size = 0
    total_free = 0
    drives = []
    for drive in drives_list:
        size_bytes = safe_int(drive.get("Size"), 0) or 0
        free_bytes = safe_int(drive.get("FreeSpace"), 0) or 0
        total_size += size_bytes
        total_free += free_bytes
        drives.append({
            "drive": drive.get("DeviceID", "N/A"),
            "type": "本地磁盘",
            "file_system": drive.get("FileSystem", "N/A"),
            "total_gb": _bytes_to_gb(size_bytes) if size_bytes > 0 else 0,
            "free_gb": _bytes_to_gb(free_bytes) if free_bytes > 0 else 0,
            "volume_name": drive.get("VolumeName", ""),
        })
    return {
        "drives": drives,
        "total_size_gb": _bytes_to_gb(total_size),
        "total_free_gb": _bytes_to_gb(total_free),
    }


def _parse_gpu_batched(data: Optional[Any]) -> dict:
    if not data:
        return {"gpus": []}
    gpus_list = data if isinstance(data, list) else [data]
    gpus = []
    for gpu in gpus_list:
        vram = safe_int(gpu.get("AdapterRAM"), 0) or 0
        gpus.append({
            "name": (gpu.get("Name") or "N/A").strip(),
            "vram_gb": _bytes_to_gb(vram),
            "driver_version": gpu.get("DriverVersion", "N/A"),
            "video_processor": gpu.get("VideoProcessor", "N/A"),
            "video_mode": gpu.get("VideoModeDescription", "N/A"),
        })
    return {"gpus": gpus}


def _parse_motherboard_batched(data: Optional[dict]) -> dict:
    if not data:
        return {}
    return {
        "manufacturer": data.get("Manufacturer", "N/A"),
        "product": data.get("Product", "N/A"),
        "serial_number": data.get("SerialNumber", "N/A"),
        "version": data.get("Version", "N/A"),
    }


def _parse_bios_batched(data: Optional[dict]) -> dict:
    if not data:
        return {}
    return {
        "manufacturer": data.get("Manufacturer", "N/A"),
        "name": data.get("Name", "N/A"),
        "version": data.get("Version", "N/A"),
        "release_date": parse_wmi_date(data.get("ReleaseDate")),
        "serial_number": data.get("SerialNumber", "N/A"),
    }


def _parse_network_batched(data: Optional[Any]) -> dict:
    if not data:
        return {"adapters": []}
    nics_list = data if isinstance(data, list) else [data]
    adapters = []
    for nic in nics_list:
        adapters.append({
            "name": nic.get("Name", "N/A"),
            "mac_address": nic.get("MACAddress", "N/A"),
            "speed": format_speed(safe_int(nic.get("Speed"))),
            "adapter_type": nic.get("AdapterType", "N/A"),
        })
    return {"adapters": adapters}


def _now_str() -> str:
    return datetime.now().strftime(DT_FORMAT)


def collect_all_batched(hostname: str, processor: str, os_info: dict) -> Optional[dict]:
    ps_path = CACHE_DIR / "collect_all.ps1"
    if not ps_path.exists():
        logger.warning("批量采集脚本不存在: %s", ps_path)
        print(f"错误: 批量采集脚本缺失，请确保 collect_all.ps1 存在于 {CACHE_DIR}")
        return None

    hash_path = ps_path.with_suffix(".ps1.sha256")
    current_hash = hashlib.sha256(ps_path.read_bytes()).hexdigest()
    if hash_path.exists():
        expected = hash_path.read_text().strip()
        if current_hash != expected:
            logger.warning("脚本已被篡改! 预期: %s, 实际: %s", expected[:12], current_hash[:12])
            print("错误: 批量采集脚本校验失败，可能已被篡改。请使用 --refresh 重新生成校验和")
            return None
    else:
        logger.warning("首次运行，记录脚本哈希: %s", current_hash[:12])
        logger.warning("请手动验证 collect_all.ps1 内容后重新运行")
        hash_path.write_text(current_hash)

    result = _run_subprocess(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "RemoteSigned", "-File", str(ps_path)],
        TIMEOUT_BATCH,
    )
    if result is None:
        logger.error("批量脚本执行失败: PowerShell 未响应或超时（%d秒）", TIMEOUT_BATCH)
        print(f"错误: PowerShell 采集超时（{TIMEOUT_BATCH}秒限制），请检查系统性能")
        return None
    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.error("批量脚本执行失败 (退出码 %d): %s", result.returncode, stderr)
        print(f"错误: PowerShell 采集失败（退出码 {result.returncode}）")
        if "权限" in stderr or "permission" in stderr.lower():
            print("提示: 可能需要管理员权限，请尝试以管理员身份运行")
        elif "找不到" in stderr or "not found" in stderr.lower():
            print("提示: 系统命令缺失，请检查 Windows Management 服务是否正常运行")
        return None

    raw = result.stdout.strip()
    if not raw:
        logger.warning("批量脚本返回空输出")
        print("错误: PowerShell 脚本返回空输出，可能采集过程异常")
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("批量脚本 JSON 解析失败: %s", e)
        print(f"错误: PowerShell 输出格式异常，无法解析为 JSON")
        logger.debug("原始输出前200字符: %s", raw[:200])
        return None
    if not isinstance(parsed, dict):
        logger.error("批量脚本返回非对象: %s", type(parsed).__name__)
        print(f"错误: PowerShell 返回非预期数据结构（{type(parsed).__name__}）")
        return None

    d = parsed.get("data", {})
    s = parsed.get("summary", {})

    info = {
        "采集时间": _now_str(),
        "计算机名": hostname,
        "操作系统": _parse_os_batched(d.get("os"), hostname, os_info),
        "CPU": _parse_cpu_batched(d.get("cpu"), processor),
        "内存": _parse_memory_batched(d.get("memory")),
        "磁盘": _parse_disk_batched(d.get("disk")),
        "显卡": _parse_gpu_batched(d.get("gpu")),
        "主板": _parse_motherboard_batched(d.get("motherboard")),
        "BIOS": _parse_bios_batched(d.get("bios")),
        "网络适配器": _parse_network_batched(d.get("network")),
    }
    info["快速摘要"] = {
        "hostname": hostname,
        "os": platform.system(),
        "os_version": s.get("os_version", platform.version()),
        "cpu": (s.get("cpuName") or "N/A").strip(),
        "cpu_cores": s.get("cpuCores", "N/A"),
        "cpu_threads": s.get("cpuThreads", "N/A"),
        "ram_gb": s.get("ramGB", "N/A"),
        "disk_total_gb": s.get("diskTotalGB", 0),
        "disk_free_gb": s.get("diskFreeGB", 0),
        "gpu": " / ".join(s.get("gpuNames", [])) or "N/A",
    }
    return info


def collect_all() -> Optional[dict]:
    print("正在收集系统配置信息...")

    hostname = platform.node()
    processor = platform.processor()
    os_info = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
    }

    batched = collect_all_batched(hostname, processor, os_info)
    if batched:
        logger.info("使用批量采集模式（单次 PowerShell 调用）")
        return batched

    logger.warning("批量采集失败，回退逐项模式")
    print("使用逐项采集模式")
    info: dict[str, Any] = {"采集时间": _now_str(), "计算机名": hostname}
    for label in ("操作系统", "CPU", "内存", "磁盘", "显卡", "主板", "BIOS", "网络适配器"):
        info[label] = {}

    for i, (label, collector_fn, *args) in enumerate([
        ("操作系统", _collect_os, os_info, hostname),
        ("CPU", _collect_cpu, processor),
        ("内存", _collect_memory,),
        ("磁盘", _collect_disk,),
        ("显卡", _collect_gpu,),
        ("主板", _collect_motherboard,),
        ("BIOS", _collect_bios,),
        ("网络适配器", _collect_network,),
    ], 1):
        print(f"[{i}/8] 正在采集{label}信息...")
        info[label] = collector_fn(*args)
    info["快速摘要"] = _build_summary_from_info(info, hostname, os_info)
    return info


def _collect_os(os_info: dict, hostname: str) -> dict:
    data = run_powershell_json("Get-CimInstance Win32_OperatingSystem | Select Caption,Version,BuildNumber,OSArchitecture,InstallDate,LastBootUpTime")
    return _parse_os_batched(data, hostname, os_info) if data else {"system": os_info["system"], "release": os_info["release"], "version": os_info["version"], "cpu_arch": os_info["architecture"], "hostname": hostname}


def _collect_cpu(processor: str) -> dict:
    data = run_powershell_json("Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,L2CacheSize,L3CacheSize")
    if data:
        return _parse_cpu_batched(data, processor)
    rows = parse_wmic_table(run_wmic(["cpu", "get", "Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,L2CacheSize,L3CacheSize", "/format:csv"]))
    if rows:
        r = rows[0]
        return {"processor": processor, "name": r.get("Name", "N/A").strip(), "cores": safe_int(r.get("NumberOfCores")), "logical_processors": safe_int(r.get("NumberOfLogicalProcessors")), "max_clock_speed_mhz": r.get("MaxClockSpeed", "N/A"), "l2_cache_kb": r.get("L2CacheSize", "N/A"), "l3_cache_kb": r.get("L3CacheSize", "N/A")}
    return {"processor": processor}


def _collect_memory() -> dict:
    data = run_powershell_json("Get-CimInstance Win32_PhysicalMemory | Select Capacity,Speed,Manufacturer,PartNumber")
    if data:
        return _parse_memory_batched(data)
    total_gb = None
    rows = parse_wmic_table(run_wmic(["ComputerSystem", "get", "TotalPhysicalMemory", "/format:csv"]))
    if rows:
        total_gb = _bytes_to_gb(safe_int(rows[0].get("TotalPhysicalMemory"), 0) or 0)
    sticks = parse_wmic_table(run_wmic(["memorychip", "get", "Capacity,Speed,Manufacturer,PartNumber,MemoryType", "/format:csv"]))
    return {"total_gb": total_gb, "sticks": [{"capacity_gb": _bytes_to_gb(safe_int(s.get("Capacity"), 0) or 0), "speed_mhz": s.get("Speed", "N/A"), "manufacturer": s.get("Manufacturer", "N/A"), "part_number": s.get("PartNumber", "N/A")} for s in sticks]}


def _collect_disk() -> dict:
    data = run_powershell_json("Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select DeviceID,Size,FreeSpace,FileSystem,VolumeName")
    if data:
        return _parse_disk_batched(data)
    type_map = {"2": "可移动磁盘", "3": "本地磁盘", "4": "网络驱动器", "5": "光盘"}
    rows = parse_wmic_table(run_wmic(["logicaldisk", "get", "Caption,Size,FreeSpace,FileSystem,DriveType,VolumeName", "/format:csv"]))
    drives, total_size, total_free = [], 0, 0
    for d in rows:
        dt = d.get("DriveType", "")
        size_b, free_b = safe_int(d.get("Size"), 0) or 0, safe_int(d.get("FreeSpace"), 0) or 0
        drives.append({"drive": d.get("Caption", "N/A"), "type": type_map.get(dt, f"类型{dt}"), "file_system": d.get("FileSystem", "N/A"), "total_gb": _bytes_to_gb(size_b), "free_gb": _bytes_to_gb(free_b), "volume_name": d.get("VolumeName", "")})
        if dt == "3":
            total_size += size_b
            total_free += free_b
    return {"drives": drives, "total_size_gb": _bytes_to_gb(total_size), "total_free_gb": _bytes_to_gb(total_free)}


def _collect_gpu() -> dict:
    data = run_powershell_json("Get-CimInstance Win32_VideoController | Select Name,AdapterRAM,DriverVersion,VideoProcessor,VideoModeDescription")
    if data:
        return _parse_gpu_batched(data)
    rows = parse_wmic_table(run_wmic(["path", "win32_VideoController", "get", "Name,AdapterRAM,DriverVersion,VideoProcessor", "/format:csv"]))
    return {"gpus": [{"name": (g.get("Name", "N/A") or "").strip(), "vram_gb": _bytes_to_gb(safe_int(g.get("AdapterRAM"), 0) or 0), "driver_version": g.get("DriverVersion", "N/A"), "video_processor": g.get("VideoProcessor", "N/A")} for g in rows]}


def _collect_motherboard() -> dict:
    data = run_powershell_json("Get-CimInstance Win32_BaseBoard | Select Manufacturer,Product,SerialNumber,Version")
    if data:
        return _parse_motherboard_batched(data)
    rows = parse_wmic_table(run_wmic(["baseboard", "get", "Manufacturer,Product,SerialNumber,Version", "/format:csv"]))
    if rows:
        r = rows[0]
        return {"manufacturer": r.get("Manufacturer", "N/A"), "product": r.get("Product", "N/A"), "serial_number": r.get("SerialNumber", "N/A"), "version": r.get("Version", "N/A")}
    return {}


def _collect_bios() -> dict:
    data = run_powershell_json("Get-CimInstance Win32_BIOS | Select Manufacturer,Name,Version,ReleaseDate,SerialNumber")
    if data:
        return _parse_bios_batched(data)
    rows = parse_wmic_table(run_wmic(["bios", "get", "Manufacturer,Name,Version,ReleaseDate,SerialNumber", "/format:csv"]))
    if rows:
        r = rows[0]
        return {"manufacturer": r.get("Manufacturer", "N/A"), "name": r.get("Name", "N/A"), "version": r.get("Version", "N/A"), "release_date": parse_wmi_date(r.get("ReleaseDate")), "serial_number": r.get("SerialNumber", "N/A")}
    return {}


def _collect_network() -> dict:
    data = run_powershell_json("Get-CimInstance Win32_NetworkAdapter -Filter 'NetEnabled=True' | Select Name,MACAddress,Speed,AdapterType")
    if data:
        return _parse_network_batched(data)
    rows = parse_wmic_table(run_wmic(["nic", "where", "NetEnabled=True", "get", "Name,MACAddress,Speed,AdapterType", "/format:csv"]))
    return {"adapters": [{"name": n.get("Name", "N/A"), "mac_address": n.get("MACAddress", "N/A"), "speed": format_speed(safe_int(n.get("Speed"))), "adapter_type": n.get("AdapterType", "N/A")} for n in rows]}


def _build_summary_from_info(info: dict, hostname: str, os_info: dict) -> dict:
    cpu_info = info.get("CPU", {})
    mem_info = info.get("内存", {})
    disk_info = info.get("磁盘", {})
    gpu_info = info.get("显卡", {})
    gpu_names = [g.get("name", "").strip() for g in gpu_info.get("gpus", []) if g.get("name")]
    return {
        "hostname": hostname, "os": os_info["system"], "os_version": os_info["version"],
        "cpu": cpu_info.get("name", cpu_info.get("processor", "N/A")),
        "cpu_cores": cpu_info.get("cores", "N/A"),
        "cpu_threads": cpu_info.get("logical_processors", "N/A"),
        "ram_gb": mem_info.get("total_gb", "N/A"),
        "disk_total_gb": disk_info.get("total_size_gb", 0),
        "disk_free_gb": disk_info.get("total_free_gb", 0),
        "gpu": " / ".join(gpu_names) or "N/A",
    }


def _acquire_file_lock(file_obj) -> bool:
    try:
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except (OSError, IOError):
        return False


def _release_file_lock(file_obj) -> None:
    try:
        file_obj.seek(0)
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
    except (OSError, IOError):
        pass


def _parse_cache_time(t_str: str) -> Optional[datetime]:
    try:
        return datetime.strptime(t_str, DT_FORMAT)
    except (ValueError, TypeError):
        return None


def load_cache() -> Optional[dict]:
    if not CACHE_FILE.exists():
        logger.debug("缓存文件不存在")
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            if not _acquire_file_lock(f):
                logger.warning("缓存文件被锁定")
                return None
            try:
                data = json.load(f)
            finally:
                _release_file_lock(f)

        cached_dt = _parse_cache_time(data.get("采集时间", ""))
        if cached_dt:
            age = datetime.now() - cached_dt
            if age < timedelta(hours=CACHE_EXPIRY_HOURS):
                return data
            logger.info("缓存已过期（%.1f小时前）", age.total_seconds() / 3600)
        else:
            mtime = datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
            age = datetime.now() - mtime
            if age < timedelta(hours=CACHE_EXPIRY_HOURS):
                logger.info("缓存无时间戳，使用文件修改时间判断（%.1f小时前）", age.total_seconds() / 3600)
                return data
            logger.info("缓存已过期（基于文件修改时间）")
        return None

    except json.JSONDecodeError as e:
        logger.warning("缓存损坏: %s，已删除", e)
        try:
            CACHE_FILE.unlink()
        except OSError:
            pass
        return None
    except PermissionError:
        logger.error("无法读取缓存文件")
        return None
    except Exception as e:
        logger.error("读取缓存异常: %s", e)
        return None


def _secure_delete_file(file_path: Path) -> bool:
    try:
        size = file_path.stat().st_size
        with open(file_path, "wb") as f:
            f.write(SECURE_DELETE_OVERWRITE_BYTE * size)
            f.flush()
            os.fsync(f.fileno())
        file_path.unlink()
        return True
    except OSError as e:
        logger.warning("安全删除失败 %s: %s", file_path.name, e)
        try:
            file_path.unlink()
            return True
        except OSError:
            return False


def save_cache(data: dict) -> bool:
    if data is None:
        logger.error("尝试保存 None 到缓存")
        return False

    temp_file = CACHE_FILE.with_suffix(".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            if not _acquire_file_lock(f):
                logger.warning("无法获取文件锁，跳过写入")
                return False
            try:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                _release_file_lock(f)
        temp_file.replace(CACHE_FILE)
        logger.info("配置已缓存: %s", CACHE_FILE)
        return True
    except (PermissionError, OSError) as e:
        logger.error("缓存写入失败: %s", e)
        return False
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass


def get_config(force_refresh: bool = False, anonymize: bool = True) -> dict:
    if not force_refresh:
        cached = load_cache()
        if cached:
            return filter_sensitive_data(cached, anonymize)

    data = collect_all()
    if data is None:
        raise RuntimeError("系统配置采集失败，请检查环境")

    save_cache(data)
    return filter_sensitive_data(data, anonymize)


def format_summary(info: dict) -> str:
    s = info.get("快速摘要", {})
    return (
        "═══════════════════════════════════════\n"
        "          电脑配置信息摘要\n"
        "═══════════════════════════════════════\n"
        f"  计算机: {s.get('hostname', 'N/A')}\n"
        f"  操作系统: {s.get('os', 'N/A')}\n"
        f"  CPU: {s.get('cpu', 'N/A')}\n"
        f"      核心数: {s.get('cpu_cores', 'N/A')} / 线程数: {s.get('cpu_threads', 'N/A')}\n"
        f"  内存: {s.get('ram_gb', 'N/A')} GB\n"
        f"  磁盘: 总计 {s.get('disk_total_gb', 'N/A')} GB / 可用 {s.get('disk_free_gb', 'N/A')} GB\n"
        f"  显卡: {s.get('gpu', 'N/A')}\n"
        f"  采集时间: {info.get('采集时间', 'N/A')}\n"
        "───────────────────────────────────────\n"
        "  提示: 刷新配置请使用 --refresh 参数\n"
        "═══════════════════════════════════════"
    )


def _validate_path(resolved: Path, allowed: list[Path]) -> Optional[str]:
    if any(resolved.is_relative_to(d) for d in allowed):
        return str(resolved)
    return None


def _validate_export_path(output_path: str) -> Optional[str]:
    resolved = Path(output_path).resolve()
    return _validate_path(resolved, [CACHE_DIR.resolve(), Path.cwd().resolve(), Path.home().resolve()])


def _export_build_lines(info: dict) -> list[str]:
    os_info = info.get("操作系统", {})
    cpu_info = info.get("CPU", {})
    mem_info = info.get("内存", {})
    disk_info = info.get("磁盘", {})
    gpu_info = info.get("显卡", {})
    mb_info = info.get("主板", {})

    lines = [
        "=" * 60, "              电脑配置信息报告", "=" * 60,
        f"采集时间: {info.get('采集时间', 'N/A')}", f"计算机名: {info.get('计算机名', 'N/A')}",
        "", "【操作系统】",
        f"  系统名称: {os_info.get('caption', os_info.get('system', 'N/A'))}",
        f"  版本号:   {os_info.get('version', 'N/A')}",
        f"  架构:     {os_info.get('os_arch', os_info.get('cpu_arch', 'N/A'))}",
        f"  Build号:  {os_info.get('build_number', 'N/A')}",
        f"  安装日期: {os_info.get('install_date', 'N/A')}",
        f"  启动时间: {os_info.get('last_bootup', 'N/A')}",
        "", "【处理器】",
        f"  型号:     {cpu_info.get('name', cpu_info.get('processor', 'N/A'))}",
        f"  核心数:   {cpu_info.get('cores', 'N/A')}",
        f"  线程数:   {cpu_info.get('logical_processors', 'N/A')}",
        f"  主频:     {cpu_info.get('max_clock_speed_mhz', 'N/A')} MHz",
        f"  L2缓存:   {cpu_info.get('l2_cache_kb', 'N/A')} KB",
        f"  L3缓存:   {cpu_info.get('l3_cache_kb', 'N/A')} KB",
        "", "【内存】", f"  总容量:   {mem_info.get('total_gb', 'N/A')} GB",
    ]
    for i, stick in enumerate(mem_info.get("sticks", []), 1):
        lines.append(f"  内存条{i}: {stick.get('capacity_gb', 'N/A')} GB / {stick.get('speed_mhz', 'N/A')} MHz / {stick.get('manufacturer', 'N/A')}")

    lines.extend([
        "", "【磁盘】",
        f"  总容量:   {disk_info.get('total_size_gb', 'N/A')} GB",
        f"  可用:     {disk_info.get('total_free_gb', 'N/A')} GB",
    ])
    for d in disk_info.get("drives", []):
        lines.append(f"  {d.get('drive', 'N/A')} {d.get('total_gb', 'N/A')} GB / 可用 {d.get('free_gb', 'N/A')} GB ({d.get('file_system', 'N/A')})")

    lines.extend(["", "【显卡】"])
    for gpu in gpu_info.get("gpus", []):
        lines.append(f"  型号:     {gpu.get('name', 'N/A')}")
        lines.append(f"  显存:     {gpu.get('vram_gb', 'N/A')} GB")
        lines.append(f"  驱动:     {gpu.get('driver_version', 'N/A')}")

    if mb_info:
        lines.extend([
            "", "【主板】",
            f"  制造商:   {mb_info.get('manufacturer', 'N/A')}",
            f"  型号:     {mb_info.get('product', 'N/A')}",
            f"  版本:     {mb_info.get('version', 'N/A')}",
        ])
    lines.extend(["", "=" * 60])
    return lines


def export_txt(info: dict, output_path: Optional[str] = None) -> str:
    if output_path is None:
        output_path = str(CACHE_DIR / f"config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    else:
        validated = _validate_export_path(output_path)
        if validated is None:
            raise ValueError(f"导出路径不合法: {output_path}")
        output_path = validated

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(_export_build_lines(info)))
    logger.info("TXT 报告已导出: %s", output_path)
    return output_path


def export_csv(info: dict, output_path: Optional[str] = None) -> str:
    if output_path is None:
        output_path = str(CACHE_DIR / f"config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    else:
        validated = _validate_export_path(output_path)
        if validated is None:
            raise ValueError(f"导出路径不合法: {output_path}")
        output_path = validated

    os_info = info.get("操作系统", {})
    cpu_info = info.get("CPU", {})
    mem_info = info.get("内存", {})
    disk_info = info.get("磁盘", {})
    gpu_info = info.get("显卡", {})
    mb_info = info.get("主板", {})

    rows = [["配置项", "值"],
            ["采集时间", info.get("采集时间", "N/A")], ["计算机名", info.get("计算机名", "N/A")],
            ["系统名称", os_info.get("caption", os_info.get("system", "N/A"))],
            ["系统版本", os_info.get("version", "N/A")],
            ["系统架构", os_info.get("os_arch", os_info.get("cpu_arch", "N/A"))],
            ["Build号", os_info.get("build_number", "N/A")],
            ["安装日期", os_info.get("install_date", "N/A")],
            ["启动时间", os_info.get("last_bootup", "N/A")],
            ["CPU型号", cpu_info.get("name", cpu_info.get("processor", "N/A"))],
            ["CPU核心数", cpu_info.get("cores", "N/A")],
            ["CPU线程数", cpu_info.get("logical_processors", "N/A")],
            ["CPU主频(MHz)", cpu_info.get("max_clock_speed_mhz", "N/A")],
            ["CPU L2缓存(KB)", cpu_info.get("l2_cache_kb", "N/A")],
            ["CPU L3缓存(KB)", cpu_info.get("l3_cache_kb", "N/A")],
            ["内存总容量(GB)", mem_info.get("total_gb", "N/A")]]

    for i, stick in enumerate(mem_info.get("sticks", []), 1):
        rows.extend([
            [f"内存条{i}_容量(GB)", stick.get("capacity_gb", "N/A")],
            [f"内存条{i}_频率(MHz)", stick.get("speed_mhz", "N/A")],
            [f"内存条{i}_品牌", stick.get("manufacturer", "N/A")],
            [f"内存条{i}_型号", stick.get("part_number", "N/A")],
        ])

    rows.extend([
        ["磁盘总容量(GB)", disk_info.get("total_size_gb", "N/A")],
        ["磁盘可用(GB)", disk_info.get("total_free_gb", "N/A")],
    ])
    for d in disk_info.get("drives", []):
        rows.extend([
            [f"磁盘_{d.get('drive', 'N/A')}_总容量(GB)", d.get("total_gb", "N/A")],
            [f"磁盘_{d.get('drive', 'N/A')}_可用(GB)", d.get("free_gb", "N/A")],
            [f"磁盘_{d.get('drive', 'N/A')}_文件系统", d.get("file_system", "N/A")],
        ])

    for i, gpu in enumerate(gpu_info.get("gpus", []), 1):
        rows.extend([
            [f"显卡{i}_型号", gpu.get("name", "N/A")],
            [f"显卡{i}_显存(GB)", gpu.get("vram_gb", "N/A")],
            [f"显卡{i}_驱动", gpu.get("driver_version", "N/A")],
        ])

    if mb_info:
        rows.extend([
            ["主板制造商", mb_info.get("manufacturer", "N/A")],
            ["主板型号", mb_info.get("product", "N/A")],
        ])

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    logger.info("CSV 报告已导出: %s", output_path)
    return output_path


def compare_configs(config1: dict, config2: dict, max_depth: int = 20) -> list:
    differences = []

    def _cmp(a: Any, b: Any, path: str = "root", depth: int = 0):
        if depth > max_depth:
            differences.append({"path": path, "old": "(超限)", "new": "(超限)"})
            return
        if type(a) != type(b):
            differences.append({"path": path, "old": a, "new": b})
            return
        if isinstance(a, dict):
            keys = a.keys() | b.keys()
            for k in keys:
                np = f"{path}.{k}"
                if k not in a:
                    differences.append({"path": np, "old": "N/A (新增)", "new": b.get(k)})
                elif k not in b:
                    differences.append({"path": np, "old": a.get(k), "new": "N/A (删除)"})
                else:
                    _cmp(a[k], b[k], np, depth + 1)
        elif isinstance(a, list):
            la, lb = len(a), len(b)
            if la != lb:
                differences.append({"path": path, "old": f"长度 {la}", "new": f"长度 {lb}"})
            for i in range(min(la, lb)):
                _cmp(a[i], b[i], f"{path}[{i}]", depth + 1)
            for i in range(min(la, lb), max(la, lb)):
                if i < lb:
                    differences.append({"path": f"{path}[{i}]", "old": "N/A (新增)", "new": b[i]})
                else:
                    differences.append({"path": f"{path}[{i}]", "old": a[i], "new": "N/A (删除)"})
        elif a != b:
            differences.append({"path": path, "old": a, "new": b})

    _cmp(config1, config2)
    return differences


def format_comparison(differences: list, t1: str, t2: str) -> str:
    if not differences:
        return "两次配置完全一致。"

    hw, sys_d, other = [], [], []
    for d in differences:
        p = d["path"].replace("root.", "")
        is_ignored = any(p.startswith(k) for k in IGNORED_COMPARE_KEYS)
        if is_ignored:
            continue
        e = {"path": p, "old_value": d["old"], "new_value": d["new"]}
        primaries = d["path"].split(".")
        cat = primaries[1] if len(primaries) > 1 else ""
        if cat in HARDWARE_CATEGORIES:
            hw.append(e)
        elif cat in SYSTEM_CATEGORIES:
            sys_d.append(e)
        else:
            other.append(e)

    all_d = hw + sys_d + other
    if not all_d:
        return "两次配置硬件和系统信息一致，仅有采集时间等元数据变化。"

    lines = [f"配置对比: {t1} vs {t2}", f"{len(all_d)} 处差异", "-" * 50]
    sections = [("硬件变更", hw), ("系统变更", sys_d), ("其他变更", other)]
    for title, items in sections:
        if items:
            lines.extend(["", f"【{title}】"])
            for d in items:
                lines.append(f"  {d['path']}")
                lines.append(f"    旧: {d['old_value']}")
                lines.append(f"    新: {d['new_value']}")
    return "\n".join(lines)


def delete_all_data() -> int:
    deleted = 0
    for pat in ("config.json", "config_*.txt", "config_*.csv", "config_*.json", "*.tmp", "collect_all.ps1.sha256"):
        for f in CACHE_DIR.glob(pat):
            if _secure_delete_file(f):
                deleted += 1
    return deleted


def validate_compare_path(compare_path: str) -> Optional[str]:
    resolved = Path(compare_path).resolve()
    cache_resolved = CACHE_DIR.resolve()
    if not resolved.is_relative_to(cache_resolved):
        logger.error("对比文件必须在缓存目录: %s", cache_resolved)
        return None
    if not resolved.exists():
        logger.error("对比文件不存在: %s", compare_path)
        return None
    if resolved.suffix != ".json":
        logger.error("对比文件必须是 .json 格式")
        return None
    return str(resolved)


def import_config(import_path: str) -> bool:
    resolved = Path(import_path).resolve()
    if not resolved.exists():
        print(f"错误: 导入文件不存在: {import_path}")
        return False
    if resolved.suffix != ".json":
        print("错误: 导入文件必须是 .json 格式")
        return False

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print("错误: 导入文件格式错误，必须是 JSON 对象")
            return False
        if "采集时间" not in data and "计算机名" not in data:
            print("错误: 导入文件缺少必需的配置字段")
            return False

        save_cache(data)
        logger.info("配置已从 %s 导入", resolved)
        print(f"配置已从 {resolved} 导入到缓存")
        return True
    except json.JSONDecodeError as e:
        print(f"错误: 导入文件格式无效: {e}")
        return False
    except PermissionError:
        print(f"错误: 无权限读取文件: {import_path}")
        return False
    except Exception as e:
        print(f"错误: 导入配置失败: {e}")
        return False


@lru_cache(maxsize=128)
def _resolve_alias(key: str) -> Optional[str]:
    key_lower = key.lower()
    return MODULE_ALIASES.get(key_lower, key)


def query_config(data: dict, query: str) -> Optional[Any]:
    keys = [k.strip() for k in query.split(".") if k.strip()]
    if not keys:
        return None

    first = keys[0]
    resolved = _resolve_alias(first)
    current = data.get(resolved) if resolved else None
    if current is None:
        current = next((v for k, v in data.items() if k.lower() == first.lower()), None)
    if current is None:
        return None

    for key in keys[1:]:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            try:
                idx = int(key)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


def format_query_result(query: str, result: Any) -> str:
    if result is None:
        return f"未找到: {query}"
    if isinstance(result, dict):
        parts = [f"── {query} ──"]
        for k, v in result.items():
            v_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
            parts.append(f"  {k}: {v_str}")
        return "\n".join(parts)
    if isinstance(result, list):
        parts = [f"── {query} ({len(result)} 项) ──"]
        for i, item in enumerate(result):
            if isinstance(item, dict):
                parts.append(f"  [{i}]")
                parts.extend(f"    {k}: {v}" for k, v in item.items())
            else:
                parts.append(f"  [{i}] {item}")
        return "\n".join(parts)
    return f"{query}: {result}"


def save_snapshot(data: dict, label: Optional[str] = None) -> str:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_lbl = "" if not label else "_" + "".join(c for c in label if c.isalnum() or c in "_-")
    path = SNAPSHOTS_DIR / f"snapshot_{ts}{safe_lbl}.json"
    snap = copy.deepcopy(data)
    snap["快照标签"] = label or ""
    snap["快照时间"] = _now_str()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    logger.info("快照已保存: %s", path)
    return str(path)


def list_snapshots() -> list:
    if not SNAPSHOTS_DIR.exists():
        return []
    snapshots = []
    for f in sorted(SNAPSHOTS_DIR.glob("snapshot_*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            snapshots.append({
                "file": f.name, "path": str(f),
                "time": d.get("快照时间", d.get("采集时间", "未知")),
                "label": d.get("快照标签", ""),
                "hostname": d.get("计算机名", "N/A"),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return snapshots


def format_snapshots_list(snapshots: list) -> str:
    if not snapshots:
        return "没有已保存的快照。使用 --snapshot 保存。"
    lines = [f"已保存 {len(snapshots)} 个快照:", ""]
    for i, s in enumerate(snapshots, 1):
        lbl = f" [{s['label']}]" if s["label"] else ""
        lines.append(f"  {i}. {s['time']}{lbl} - {s['hostname']} ({s['file']})")
    return "\n".join(lines)


def assess_system_health(data: dict) -> dict:
    health = {"score": 100, "warnings": [], "info": [], "details": {}}
    disk_info = data.get("磁盘", {})
    total_disk = disk_info.get("total_size_gb", 0)
    free_disk = disk_info.get("total_free_gb", 0)

    if total_disk and total_disk > 0:
        pct = ((total_disk - free_disk) / total_disk) * 100
        health["details"]["磁盘使用率"] = f"{pct:.1f}%"
        if pct > DISK_USAGE_CRITICAL:
            health["score"] -= 20
            health["warnings"].append(f"磁盘严重不足! 使用率 {pct:.1f}%，仅剩 {free_disk:.1f} GB")
        elif pct > DISK_USAGE_WARNING:
            health["score"] -= 10
            health["warnings"].append(f"磁盘空间紧张 {pct:.1f}%，剩余 {free_disk:.1f} GB")
        elif pct > DISK_USAGE_NOTICE:
            health["score"] -= 3
            health["info"].append(f"磁盘使用率 {pct:.1f}%")

        for drive in disk_info.get("drives", []):
            dt, df = drive.get("total_gb", 0), drive.get("free_gb", 0)
            if dt and dt > 0 and ((dt - df) / dt) * 100 > DISK_DRIVE_NEARLY_FULL:
                health["warnings"].append(
                    f"驱动器 {drive.get('drive', '?')} 几乎已满 ({((dt-df)/dt)*100:.1f}%)，仅剩 {df:.1f} GB"
                )

    total_ram = data.get("内存", {}).get("total_gb", 0)
    if total_ram:
        health["details"]["内存容量"] = f"{total_ram} GB"
        if total_ram < RAM_MINIMUM:
            health["score"] -= 15
            health["warnings"].append(f"内存过低 ({total_ram} GB)，建议 {RAM_RECOMMENDED} GB+")
        elif total_ram < RAM_RECOMMENDED:
            health["score"] -= 5
            health["info"].append(f"内存偏小 ({total_ram} GB)")
        elif total_ram >= RAM_OPTIMAL:
            health["info"].append(f"内存充足 ({total_ram} GB)")

    cores = data.get("CPU", {}).get("cores")
    if cores:
        health["details"]["CPU核心数"] = cores
        if cores < CPU_CORES_MINIMUM:
            health["score"] -= 5
            health["info"].append(f"CPU 核心数较少 ({cores} 核)")

    for gpu in data.get("显卡", {}).get("gpus", []):
        vram = gpu.get("vram_gb", 0)
        if vram and vram < GPU_VRAM_MINIMUM:
            health["score"] -= 5
            health["info"].append(f"显卡 {gpu.get('name', '?')} 显存过小 ({vram} GB)")

    boot = data.get("操作系统", {}).get("last_bootup")
    if boot:
        t = _parse_cache_time(boot) if isinstance(boot, str) else None
        if t:
            days = (datetime.now() - t).total_seconds() / 86400
            health["details"]["系统运行时间"] = f"{days:.1f} 天"
            if days > UPTIME_RESTART_DAYS:
                health["score"] -= 3
                health["info"].append(f"系统已运行 {days:.0f} 天，建议重启")

    health["score"] = max(0, min(100, health["score"]))
    return health


def format_health_report(health: dict) -> str:
    score = health["score"]
    if score >= HEALTH_SCORE_EXCELLENT:
        grade, indicator = "优秀", "🟢"
    elif score >= HEALTH_SCORE_GOOD:
        grade, indicator = "良好", "🟡"
    elif score >= HEALTH_SCORE_FAIR:
        grade, indicator = "一般", "🟠"
    else:
        grade, indicator = "需关注", "🔴"

    lines = [
        "═══════════════════════════════════════",
        "          系统健康评估报告",
        "═══════════════════════════════════════",
        f"  综合评分: {score}/100 {indicator} {grade}",
        "───────────────────────────────────────",
    ]
    if health["details"]:
        lines.append("  【系统指标】")
        lines.extend(f"    {k}: {v}" for k, v in health["details"].items())

    if health["warnings"]:
        lines.append("")
        lines.append("  【警告】")
        lines.extend(f"    ⚠ {w}" for w in health["warnings"])

    if health["info"]:
        lines.append("")
        lines.append("  【建议】")
        lines.extend(f"    💡 {i}" for i in health["info"])

    if not health["warnings"] and not health["info"]:
        lines.extend(["", "  系统状态良好，无需特别关注。"])

    lines.append("═══════════════════════════════════════")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="System Information Collector - 电脑配置信息采集器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python collector.py                        # 配置摘要\n"
               "  python collector.py --json                 # 完整 JSON\n"
               "  python collector.py --refresh              # 强制刷新\n"
               "  python collector.py --query CPU            # 查询 CPU\n"
               "  python collector.py --query 内存.total_gb  # 查询内存\n"
               "  python collector.py --health               # 健康评估\n"
               "  python collector.py --snapshot before      # 快照\n"
               "  python collector.py --list-snapshots       # 快照列表\n"
               "  python collector.py --export-txt           # TXT\n"
               "  python collector.py --compare old.json     # 对比\n",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--detailed", action="store_true", help="摘要 + 详细")
    parser.add_argument("--refresh", "--force", action="store_true", help="强制刷新")
    parser.add_argument("--check-cache", action="store_true", help="检查缓存")
    parser.add_argument("--cache-path", action="store_true", help="缓存路径")
    parser.add_argument("--no-anonymize", action="store_true", help="显示未脱敏（需确认）")
    parser.add_argument("--export-txt", action="store_true", help="导出 TXT")
    parser.add_argument("--export-csv", action="store_true", help="导出 CSV")
    parser.add_argument("--compare", metavar="FILE", help="对比历史配置")
    parser.add_argument("--import", metavar="FILE", dest="import_config", help="从 JSON 导入配置")
    parser.add_argument("--query", metavar="KEY", help="精确查询（支持多个，用空格分隔）")
    parser.add_argument("--query-multi", metavar="KEY", nargs="+", help="批量查询多个字段")
    parser.add_argument("--health", action="store_true", help="健康评估")
    parser.add_argument("--snapshot", metavar="LABEL", nargs="?", const="", help="保存快照")
    parser.add_argument("--list-snapshots", action="store_true", help="快照列表")
    parser.add_argument("--delete-data", action="store_true", help="删除缓存")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    args = parser.parse_args()

    setup_logging(args.verbose)
    check_platform()

    anonymize = not args.no_anonymize
    if args.no_anonymize:
        print("⚠ 警告: --no-anonymize 将显示未脱敏数据（MAC、序列号等）")
        try:
            if input("确认继续? (y/N): ").strip().lower() != "y":
                print("已取消")
                sys.exit(0)
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            sys.exit(0)

    if args.refresh:
        (CACHE_DIR / "collect_all.ps1.sha256").unlink(missing_ok=True)
        logger.debug("已清除脚本哈希缓存")

    try:
        if args.delete_data:
            print(f"已安全删除 {delete_all_data()} 个文件")
            sys.exit(0)
        if args.list_snapshots:
            print(format_snapshots_list(list_snapshots()))
            sys.exit(0)
        if args.import_config:
            success = import_config(args.import_config)
            sys.exit(0 if success else 1)

        # --compare reads cache directly, doesn't need get_config
        if args.compare:
            cached = load_cache()
            if not cached:
                print("错误: 缓存不存在，请先采集")
                sys.exit(1)
            vp = validate_compare_path(args.compare)
            if not vp:
                sys.exit(1)
            with open(vp, "r", encoding="utf-8") as f:
                compare_data = json.load(f)
            diffs = compare_configs(cached, compare_data)
            print(format_comparison(diffs, cached.get("采集时间", "未知"), compare_data.get("采集时间", "未知")))
            sys.exit(0)

        # --check-cache only reads cache, no get_config needed
        data = None

        if args.check_cache:
            cached = load_cache()
            if cached:
                print(f"缓存有效: {cached.get('采集时间', 'N/A')}")
                print(format_summary(cached))
            else:
                print("缓存无效或不存在")

        if args.cache_path:
            print(CACHE_FILE)

        # All modes requiring full config
        need_config = any([args.json, args.detailed, args.query, args.query_multi, args.health,
                          args.snapshot is not None, args.export_txt, args.export_csv])
        need_config = need_config or (not args.check_cache and not args.cache_path)

        if not need_config:
            sys.exit(0)

        data = get_config(force_refresh=args.refresh, anonymize=anonymize)

        if args.query_multi:
            for q in args.query_multi:
                result = query_config(data, q)
                print(format_query_result(q, result))
        elif args.query:
            print(format_query_result(args.query, query_config(data, args.query)))
        elif args.health:
            print(format_health_report(assess_system_health(data)))
        elif args.snapshot is not None:
            label = args.snapshot or None
            print(f"快照已保存: {save_snapshot(data, label=label)}")
        elif args.export_txt:
            print(f"TXT 报告: {export_txt(data)}")
        elif args.export_csv:
            print(f"CSV 报告: {export_csv(data)}")
        else:
            print(format_summary(data))
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            elif args.detailed:
                print("\n--- 详细配置 ---\n")
                print(json.dumps(data, ensure_ascii=False, indent=2))

    except RuntimeError as e:
        print(f"错误: {e}")
        sys.exit(1)
