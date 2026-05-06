# System Information Collector

Windows 系统信息采集器 - 快速、安全、智能的电脑配置管理工具

## 🌟 功能特性

### 核心功能
- **自动采集**: PowerShell 批量获取硬件信息，单次调用完成采集
- **智能缓存**: 24 小时缓存策略，避免重复查询
- **隐私保护**: MAC 地址和序列号默认脱敏，HMAC-SHA256 哈希保护
- **健康评估**: 综合评估磁盘、内存、CPU、显卡、温度、电池状态，给出评分和建议
- **配置对比**: 对比历史配置，追踪硬件变更
- **快照管理**: 保存配置快照，支持硬件升级前后对比
- **多格式导出**: 支持 TXT 和 CSV 格式导出配置报告

### 高级功能
- **智能查询**: 支持中英文别名、嵌套路径、数组索引查询
- **批量查询**: 一次查询多个配置字段
- **配置导入**: 从 JSON 文件恢复配置
- **安全删除**: 文件覆写机制防止数据恢复
- **文件锁保护**: 防止并发访问导致数据损坏

## 📦 快速开始

### 环境要求
- **操作系统**: Windows 10/11
- **Python**: 3.8+
- **依赖**: 仅使用 Python 标准库，零第三方依赖

### 安装
```bash
# 克隆仓库
git clone https://github.com/pengshr/system-info-collector.git
cd system-info-collector

# 或直接下载 ZIP 文件并解压
```

### 使用方法

#### 1. 查看配置摘要
```bash
python collector.py
```

#### 2. 获取完整 JSON 数据
```bash
python collector.py --json
```

#### 3. 强制刷新采集
```bash
python collector.py --refresh
```

#### 4. 智能查询
```bash
# 查询 CPU 信息
python collector.py --query CPU

# 查询电池状态
python collector.py --query 电池

# 查询温度传感器
python collector.py --query 温度

# 查询实时性能
python collector.py --query 性能

# 查询运行进程
python collector.py --query 进程

# 查询已安装软件
python collector.py --query 软件

# 查询内存大小
python collector.py --query 内存.total_gb

# 查询显卡型号
python collector.py --query 显卡.gpus.0.name
```

#### 5. 批量查询
```bash
python collector.py --query-multi CPU 内存.total_gb 显卡.gpus.0.name
```

#### 6. 系统健康评估
```bash
python collector.py --health
```

#### 7. 保存配置快照
```bash
python collector.py --snapshot
python collector.py --snapshot before_upgrade
```

#### 8. 导出配置报告
```bash
# 导出为 TXT
python collector.py --export-txt

# 导出为 CSV
python collector.py --export-csv
```

#### 9. 配置对比
```bash
python collector.py --compare old_config.json
```

#### 10. 导入配置
```bash
python collector.py --import config_backup.json
```

## 🔒 隐私与安全

### 默认脱敏
- **MAC 地址**: 自动脱敏为"已脱敏"，保留 HMAC-SHA256 哈希值
- **序列号**: 主板和 BIOS 序列号自动脱敏

### 查看原始数据
```bash
python collector.py --json --no-anonymize
```
> ⚠️ 需要交互确认，确保用户知情

### 安全特性
- ✅ 文件锁保护，防止并发损坏
- ✅ 原子写入，确保数据完整性
- ✅ 安全删除，覆写后删除防止恢复
- ✅ 路径遍历保护，限制导出/导入路径
- ✅ 脚本完整性校验，SHA-256 哈希验证

## 📊 采集数据范围

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

## 🧪 测试

### 运行测试
```bash
# 运行单元测试
python test_collector.py

# 运行综合测试
python test_comprehensive.py

# 运行所有测试
python -m unittest discover -s . -p "test_*.py" -v
```

### 测试覆盖
- ✅ 193 个测试用例
- ✅ 100% 通过率
- ✅ 覆盖核心功能、边缘场景、隐私安全

## 📈 性能

| 操作 | 耗时 | 优化 |
|------|------|------|
| 首次采集 | 2-3秒 | PowerShell 批量采集 |
| 缓存读取 | <10ms | 24小时缓存策略 |
| 别名查询 | <1ms | LRU 缓存优化 |
| 脱敏处理 | <5ms | 高效递归算法 |

## 🛠️ 技术实现

### 采集策略
1. **主采集方式**: PowerShell `Get-CimInstance` 批量获取
2. **备用方案**: WMIC 逐项采集（批量失败时回退）
3. **基础信息**: Python `platform` 模块

### 缓存策略
- **格式**: JSON
- **有效期**: 24 小时
- **保护**: 文件锁 + 原子写入
- **位置**: 与脚本同目录

### 脱敏算法
- **MAC 地址**: HMAC-SHA256(盐值 + MAC)
- **序列号**: 直接替换为"已脱敏"

## 📖 完整文档

详细使用说明请参考 [SKILL.md](SKILL.md)

## 📝 更新日志

### v3.1 (2026-05-06)
- ✨ 新增电池信息采集（剩余电量、充电状态、设计容量）
- ✨ 新增温度传感器采集（MSAcpi_ThermalZoneTemperature）
- ✨ 新增性能计数器（CPU/内存/磁盘实时使用率）
- ✨ 新增运行进程采集（Top 20 内存占用）
- ✨ 新增已安装软件采集（从注册表 Uninstall 键）
- 🔒 健康评估增强：加入温度、实时性能、电池健康检测
- 📊 TXT/CSV 导出增强：包含全部新增模块数据
- 📊 摘要面板增强：显示电池、CPU使用率、进程/软件数量、温度

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
- 📊 提取魔法数字为常量

### v1.0 (2026-04-29)
- 🎉 初始版本发布
- ✅ 基础采集、缓存、查询功能
- ✅ 健康评估、快照、导出功能

## 🤝 贡献

欢迎提交 Issues 和 Pull Requests！

### 贡献指南
1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件