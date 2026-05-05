# System Information Collector - Windows 系统信息采集器

## 概述

一个快速、安全的 Windows 系统配置信息采集工具，支持多种输出格式和隐私保护。

## 特性

- **一键采集**: 2-3 秒完成系统配置采集（PowerShell 批量模式）
- **隐私保护**: MAC 地址和序列号自动脱敏（HMAC-SHA256）
- **多种输出**: JSON、TXT、CSV 格式导出
- **配置对比**: 检测硬件变更和配置差异
- **快照管理**: 保存历史配置快照，支持标签和对比
- **健康评估**: 自动评估系统健康状态（磁盘、内存、CPU）
- **安全增强**: HMAC Salt 支持环境变量配置，导入功能路径遍历保护
- **跨平台检查**: 延迟导入 msvcrt，支持非 Windows 平台友好提示

## 快速开始

### 安装

```powershell
# 克隆仓库
git clone https://github.com/pengshr/system-info-collector.git
cd system-info-collector

# 或直接下载 collector.py 和 collect_all.ps1
```

### 使用

```powershell
# 显示配置摘要
python collector.py

# 输出完整 JSON
python collector.py --json

# 强制刷新配置
python collector.py --refresh

# 查询特定字段
python collector.py --query CPU
python collector.py --query 内存.total_gb

# 健康评估
python collector.py --health

# 保存快照
python collector.py --snapshot "before_update"

# 导出报告
python collector.py --export-txt
python collector.py --export-csv

# 对比配置
python collector.py --compare config_old.json

# 导入配置
python collector.py --import config_backup.json
```

## 更新日志

### v3.0 (2026-05-05)
- 🔒 安全增强：HMAC Salt 支持环境变量和机器特定生成
- 🔒 安全增强：import_config 添加路径遍历保护
- 🐛 修复：msvcrt 导入兼容性（支持跨平台检查）
- 🐛 修复：安全删除大文件内存溢出问题
- 🐛 修复：parse_wmi_date 非字符串类型处理
- 🐛 修复：format_speed 零值处理（0 bps 现在正确显示）
- 🐛 修复：compare_configs 循环引用检测
- 🐛 修复：_parse_disk_batched 负数值处理
- 🐛 修复：assess_system_health 磁盘容量为 0 边界情况
- 🚀 性能优化：文件锁重试机制（3 次重试，50ms 间隔）
- 🚀 性能优化：脚本 SHA-256 哈希缓存（基于修改时间）
- 🚀 性能优化：移除不必要的 lru_cache 装饰器
- 📝 代码质量：展开压缩的逐项采集函数，提高可读性
- 📝 代码质量：删除 MODULE_ALIASES 重复键
- 📝 代码质量：简化 __main__ 逻辑分支
- 📝 代码质量：使用 `is not` 替代 `!=` 比较 type()
- 🧪 测试增强：新增非字符串日期解析测试
- 🧪 测试覆盖：193 个测试用例全部通过（100%）

### v2.0 (2026-05-05)
- ✨ 新增配置导入功能
- ✨ 新增批量查询模式
- 🚀 性能优化：LRU 缓存别名解析
- 🔒 增强错误处理和用户提示
- 🧪 新增 42 个综合测试用例

## 测试

```bash
# 运行所有测试
python -m unittest discover -s . -p "test_*.py" -v
```

## 许可证

MIT License
