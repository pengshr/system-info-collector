# 合并 collector.py 部分的脚本
# 在 GitHub 上运行此脚本将合并所有部分

from pathlib import Path

# 读取所有部分
parts = []
for i in range(1, 10):
    part_file = Path(f"collector_part{i}.py")
    if part_file.exists():
        parts.append(part_file.read_text(encoding="utf-8"))
        print(f"✅ 读取 collector_part{i}.py")

if not parts:
    print("❌ 未找到任何部分文件")
    exit(1)

# 合并
full_content = "\n\n".join(parts)

# 写入完整文件
output = Path("collector.py")
output.write_text(full_content, encoding="utf-8")

print(f"\n✅ 已合并为 collector.py ({len(full_content)} bytes, {len(full_content.splitlines())} lines)")
