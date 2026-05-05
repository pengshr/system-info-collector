# System Info Collector - 安装脚本
# 此脚本会自动从 GitHub 克隆仓库并设置好所有文件

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "System Info Collector - 安装脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$repoUrl = "https://github.com/pengshr/system-info-collector.git"
$installPath = "$env:USERPROFILE\system-info-collector"

# 检查 Git
if (!(Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 错误: 未找到 Git，请先安装 Git" -ForegroundColor Red
    Write-Host "   下载: https://git-scm.com/download/win" -ForegroundColor Yellow
    exit 1
}

# 克隆仓库
if (Test-Path $installPath) {
    Write-Host "⚠️  目录已存在，正在更新..." -ForegroundColor Yellow
    Set-Location $installPath
    git pull origin main
} else {
    Write-Host "📥 正在克隆仓库..." -ForegroundColor Green
    git clone $repoUrl $installPath
    Set-Location $installPath
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ 安装完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "安装路径: $installPath" -ForegroundColor White
Write-Host ""
Write-Host "使用方法:" -ForegroundColor Yellow
Write-Host "  cd $installPath" -ForegroundColor White
Write-Host "  python collector.py" -ForegroundColor White
Write-Host ""
Write-Host "查看帮助:" -ForegroundColor Yellow
Write-Host "  python collector.py --help" -ForegroundColor White
Write-Host ""
