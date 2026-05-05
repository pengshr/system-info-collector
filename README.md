# System Information Collector

Windows 系统信息采集器 - 快速、安全、智能的电脑配置管理工具

## 🌟 功能特性

### 核心功能
- **自动采集**: PowerShell 批量获取硬件信息，单次调用完成采集
- **智能缓存**: 24 小时缓存策略，避免重复查询
- **隐私保护**: MAC 地址和序列号默认脱敏，HMAC-SHA256 哈希保护
- **健康评估**: 综合评估磁盘、内存、CPU、显卡状态，给出评分和建议
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
git clone https://github.com/YOUR_USERNAME/system-info-collector.git
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
- ✅ 192 个测试用例
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

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

感谢所有为这个项目贡献的用户！
