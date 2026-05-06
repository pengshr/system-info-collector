---
name: "system-info-collector"
description: "Collects and caches Windows PC configuration (CPU, RAM, disk, OS, GPU, battery, temperature, performance, processes, software). Invoke when user asks about computer specs, system info, hardware details, or configuration queries."
---

# System Information Collector - 电脑配置信息采集器

## 功能概述

自动采集并缓存 Windows 电脑的完整配置信息，实现"一次采集、长期有效"的使用体验。避免重复查询系统配置，提供快速、准确的硬件信息响应。

## 触发条件

当用户提问包含以下关键词时，**必须自动激活**本技能：

### 中文触发词
- 电脑配置 / 系统配置 / 硬件配置 / 本机配置
- 电脑信息 / 系统信息 / 硬件信息 / 本机信息
- CPU / 处理器 / 内存 / 硬盘 / 磁盘 / 显卡 / 主板
- 操作系统版本 / 系统版本
- 我的电脑 / 这台电脑 / 本机
- 查看配置 / 配置参数 / 硬件参数
- 运行内存 / 存储空间 / 可用空间
- 电池 / 电量 / 充电
- 温度 / 散热 / 发热
- 性能 / 使用率 / 负载
- 进程 / 运行程序

### 英文触发词
- PC specs / system info / hardware info / computer specs
- CPU info / memory / RAM / disk space / GPU / graphics card
- system configuration / OS version
- My computer / This PC

### 典型触发场景
1. "帮我看看这台电脑的配置"
2. "我的CPU是什么型号？"
3. "内存有多大？硬盘还剩多少空间？"
4. "这台电脑能跑什么游戏？"
5. "系统是Windows什么版本？"
6. "显卡是什么型号？"
7. "显示本机配置信息"
8. "What are my computer specs?"
9. "电池还剩多少？"
10. "CPU温度多少？"

## 使用方法

> **注意**: 首次使用时会进行一次完整采集（约2-3秒），之后24小时内再次查询直接读取缓存，瞬时返回。

### 1. 检查缓存状态
```
python collector.py --check-cache
```

### 2. 获取配置摘要（默认）
```
python collector.py
```
或
```
python collector.py --summary
```

### 3. 获取完整 JSON 数据（含脱敏）
```
python collector.py --json
```

### 4. 强制刷新（忽略缓存）
```
python collector.py --refresh
```

### 5. 获取详细完整信息
```
python collector.py --detailed
```

### 6. 查看缓存文件路径
```
python collector.py --cache-path
```

### 7. 查看完整敏感数据（需确认）
```
python collector.py --json --no-anonymize
```
使用此参数时会要求交互确认。从缓存读取时，`--no-anonymize` 可恢复原始数据。

### 8. 智能查询（按模块/字段精确查询）
```
python collector.py --query CPU
python collector.py --query 电池
python collector.py --query 温度
python collector.py --query 性能
python collector.py --query 进程
python collector.py --query 软件
python collector.py --query 内存.total_gb
python collector.py --query 显卡.gpus.0.name
python collector.py --query os
```
支持中英文模块别名（如 `cpu`/`CPU`/`处理器`、`os`/`操作系统`、`gpu`/`显卡` 等），支持点号分隔的嵌套路径和数组索引。

### 9. 系统健康评估
```
python collector.py --health
```
综合评估磁盘空间、内存容量、CPU 核心数、显卡显存、系统运行时间、实时性能、温度、电池等指标，给出 0-100 分评分和改进建议。

### 10. 保存配置快照
```
python collector.py --snapshot
python collector.py --snapshot before_upgrade
```
保存当前配置为带时间戳的快照文件，可指定标签名。快照可用于硬件升级前后对比。

### 11. 列出所有快照
```
python collector.py --list-snapshots
```

### 12. 启用详细日志
```
python collector.py --verbose
```

### 13. 导出为 TXT 报告
```
python collector.py --export-txt
```
生成人类可读的纯文本配置报告，适合打印和分享。

### 14. 导出为 CSV 表格
```
python collector.py --export-csv
```
生成 CSV 格式文件，可直接用 Excel 打开或导入数据库。

### 15. 配置对比
```
python collector.py --compare old_config.json
```
对比当前缓存与指定历史配置文件，列出所有硬件和系统变更。

### 16. 导入配置
```
python collector.py --import config_backup.json
```
从 JSON 文件导入配置到缓存，可用于配置恢复或迁移。

### 17. 批量查询
```
python collector.py --query-multi CPU 内存.total_gb 显卡.gpus.0.name
```
一次性查询多个配置字段，每个字段单独显示结果。

## 采集数据范围

| 模块 | 采集内容 |
|------|---------|
| 操作系统 | 版本号、架构、安装日期、启动时间、主机名、Build号 |
| CPU | 型号、核心数、线程数、主频、L2/L3缓存 |
| 内存 | 总容量、每条内存的容量/频率/品牌/型号 |
| 磁盘 | 各分区容量/可用空间/文件系统/类型 |
| 显卡 | 型号、显存、驱动版本、视频处理器、分辨率模式 |
| 主板 | 制造商、型号、序列号(默认脱敏)、版本 |
| BIOS | 制造商、名称、版本、发布日期、序列号(默认脱敏) |
| 网络适配器 | 名称、MAC地址(默认脱敏)、速度、类型 |
| 🆕 电池 | 设备名、化学类型、剩余电量、充电状态、设计容量 |
| 🆕 温度传感器 | 传感器名称、当前温度(°C) |
| 🆕 性能计数器 | CPU使用率、内存使用率、磁盘活动时间、磁盘队列 |
| 🆕 运行进程 | Top 20 内存占用进程(PID/内存/CPU时间) |
| 🆕 已安装软件 | 软件名称、版本、发行商、安装日期 |

## 隐私与安全

- **默认脱敏**: MAC地址和序列号默认被脱敏为"已脱敏"，保留完整的 HMAC-SHA256 哈希值用于唯一标识
- **缓存保护**: `config.json` 已加入 `.gitignore`，防止意外提交到版本控制系统
- **缓存存储原始数据**: 缓存文件存储原始数据，仅在返回给用户时进行脱敏，`--no-anonymize` 可恢复原始值
- **脚本完整性**: 批量采集脚本使用 SHA-256 哈希校验，防止被篡改
- **安全删除**: 使用 `--delete-data` 时会先覆写再删除，防止数据恢复
- **文件锁**: 读写缓存时使用文件锁，防止并发访问导致数据损坏
- **路径验证**: 导出和对比功能限制文件路径范围，防止路径遍历攻击
- **查看原始数据**: 使用 `--no-anonymize` 参数可查看未脱敏的完整数据（需交互确认）

## 缓存策略

- **缓存文件**: `.trae/skills/system-info-collector/config.json`
- **有效期**: 24小时（无时间戳时使用文件修改时间判断）
- **过期后**: 下次查询时自动重新采集
- **原子写入**: 使用临时文件+重命名机制，防止并发写入损坏
- **文件锁**: 使用 msvcrt 文件锁保护读写操作

## 实现原理

1. 使用 `platform` 内置模块获取基础系统信息
2. **主采集方式**: 使用 PowerShell `Get-CimInstance` 批量获取详细硬件信息
3. **备用方案**: 当批量采集失败时，回退到逐项采集（PowerShell单条查询 + wmic）
4. 所有数据缓存为 JSON 文件，后续查询直接读取
5. 仅使用 Python 标准库，无需安装任何第三方依赖
6. 完整的异常分类处理和结构化日志记录

## 输出格式示例

```
═══════════════════════════════════════
          电脑配置信息摘要
═══════════════════════════════════════
  计算机: DESKTOP-ABC123
  操作系统: Microsoft Windows 11 专业版
  CPU: Intel(R) Core(TM) i7-12700H
      核心数: 14 / 线程数: 20
      CPU 使用率: 12%
  内存: 32.0 GB
  磁盘: 总计 512.0 GB / 可用 256.5 GB
  显卡: NVIDIA GeForce RTX 3060
  电池: 95%（接入电源）
  进程: 128 个运行中
  软件: 245 个已安装
  温度: ACPI\ThermalZone = 45.3°C
  采集时间: 2026-05-06 12:00:00
───────────────────────────────────────
  提示: 刷新配置请使用 --refresh 参数
═══════════════════════════════════════
```

## 注意事项

1. **Windows 专属**: 本技能仅适用于 Windows 操作系统，在其他平台会自动退出并提示
2. **管理员权限**: 部分硬件信息（如主板序列号）可能需要管理员权限
3. **缓存有效性**: 硬件配置一般不会频繁变化，24小时缓存策略适用于绝大多数场景
4. **零依赖**: 无需安装任何第三方 Python 包
5. **轻量快速**: 首次采集约2-3秒（批量PowerShell调用），缓存读取<0.1秒
6. **隐私保护**: 默认启用敏感字段脱敏，使用 `--no-anonymize` 可查看原始数据
7. **安全增强**: HMAC Salt 支持环境变量配置，导入功能路径遍历保护
8. **温度采集**: 需 ACPI 支持，部分台式机可能不支持 `MSAcpi_ThermalZoneTemperature`
9. **软件列表**: 从注册表 Uninstall 键读取，可能包含系统组件