# Batched system information collection script
# Runs all WMI queries in a single PowerShell session for maximum performance
# C-3: Changed from SilentlyContinue to Continue for proper error visibility

$ErrorActionPreference = "Continue"
$WarningPreference = "Continue"

$result = @{
    os = $null
    cpu = $null
    memory = $null
    disk = $null
    gpu = $null
    motherboard = $null
    bios = $null
    network = $null
    battery = $null
    temperature = $null
    processes = $null
    software = $null
    performance = $null
}

# C-3: Each query wrapped in try/catch for granular error handling
try {
    $result.os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture,InstallDate,LastBootUpTime
} catch {
    Write-Warning "Win32_OperatingSystem 查询失败: $_"
}

try {
    $result.cpu = Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,L2CacheSize,L3CacheSize
} catch {
    Write-Warning "Win32_Processor 查询失败: $_"
}

try {
    $result.memory = Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity,Speed,Manufacturer,PartNumber
} catch {
    Write-Warning "Win32_PhysicalMemory 查询失败: $_"
}

try {
    $result.disk = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,Size,FreeSpace,FileSystem,VolumeName
} catch {
    Write-Warning "Win32_LogicalDisk 查询失败: $_"
}

try {
    $result.gpu = Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion,VideoProcessor,VideoModeDescription
} catch {
    Write-Warning "Win32_VideoController 查询失败: $_"
}

try {
    $result.motherboard = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product,SerialNumber,Version
} catch {
    Write-Warning "Win32_BaseBoard 查询失败: $_"
}

try {
    $result.bios = Get-CimInstance Win32_BIOS | Select-Object Manufacturer,Name,Version,ReleaseDate,SerialNumber
} catch {
    Write-Warning "Win32_BIOS 查询失败: $_"
}

try {
    $result.network = Get-CimInstance Win32_NetworkAdapter -Filter 'NetEnabled=True' | Select-Object Name,MACAddress,Speed,AdapterType
} catch {
    Write-Warning "Win32_NetworkAdapter 查询失败: $_"
}

try {
    $result.battery = Get-CimInstance Win32_Battery | Select-Object Name,EstimatedChargeRemaining,EstimatedRunTime,BatteryStatus,DesignCapacity,Chemistry
} catch {
    Write-Warning "Win32_Battery 查询失败: $_"
}

try {
    $result.temperature = Get-CimInstance MSAcpi_ThermalZoneTemperature -Namespace "root/wmi" -ErrorAction SilentlyContinue | Select-Object InstanceName,CurrentTemperature
} catch {
    Write-Warning "温度传感器查询失败: $_"
}

try {
    $result.processes = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 20 Name,Id,WorkingSet64,CPU,ProcessName,StartTime
} catch {
    Write-Warning "进程查询失败: $_"
}

try {
    $result.software = Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*, HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* 2>$null | Where-Object { $_.DisplayName -and $_.DisplayName -ne '' } | Select-Object DisplayName,DisplayVersion,Publisher,InstallDate | Sort-Object DisplayName
} catch {
    Write-Warning "已安装软件查询失败: $_"
}

try {
    $cpuPerf = Get-CimInstance Win32_Processor | Select-Object LoadPercentage
    $osPerf = Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory,TotalVisibleMemorySize,FreeSpaceInPagingFiles,TotalVirtualMemorySize,FreeVirtualMemory
    $diskPerf = Get-CimInstance Win32_PerfFormattedData_PerfDisk_LogicalDisk | Where-Object Name -eq '_Total' | Select-Object PercentDiskTime,AvgDiskQueueLength
    $result.performance = @{
        cpu = $cpuPerf
        memory = $osPerf
        disk = $diskPerf
    }
} catch {
    Write-Warning "性能计数器查询失败: $_"
}

# L-5: Safe arithmetic with null checks for disk summary
$summary = @{
    cpuName = $null
    cpuCores = $null
    cpuThreads = $null
    ramGB = 0
    diskTotalGB = 0
    diskFreeGB = 0
    gpuNames = @()
}

if ($result.cpu) {
    $summary.cpuName = $result.cpu.Name
    $summary.cpuCores = $result.cpu.NumberOfCores
    $summary.cpuThreads = $result.cpu.NumberOfLogicalProcessors
}

if ($result.memory) {
    $memTotal = ($result.memory | Measure-Object -Property Capacity -Sum).Sum
    if ($memTotal -is [double] -or $memTotal -is [long]) {
        $summary.ramGB = [math]::Round($memTotal / 1GB, 2)
    }
}

if ($result.disk) {
    $disks = @($result.disk)
    $totalSize = 0
    $totalFree = 0
    foreach ($d in $disks) {
        $sizeVal = [double]$d.Size
        $freeVal = [double]$d.FreeSpace
        if ($sizeVal -gt 0) { $totalSize += $sizeVal }
        if ($freeVal -gt 0) { $totalFree += $freeVal }
    }
    $summary.diskTotalGB = [math]::Round($totalSize / 1GB, 2)
    $summary.diskFreeGB = [math]::Round($totalFree / 1GB, 2)
}

if ($result.gpu) {
    foreach ($g in $result.gpu) {
        if ($g.Name) {
            $summary.gpuNames += $g.Name
        }
    }
}

if ($result.battery) {
    $b = @($result.battery)
    if ($b.Count -gt 0 -and $b[0]) {
        $summary.batteryCharge = $b[0].EstimatedChargeRemaining
        $summary.batteryStatus = $b[0].BatteryStatus
        $summary.batteryChemistry = $b[0].Chemistry
    }
}

if ($result.processes) {
    $summary.runningProcesses = @($result.processes).Count
    $summary.memTopProcess = ($result.processes | Select-Object -First 1).ProcessName
    $summary.memTopProcessMB = if ($summary.memTopProcess) { [math]::Round(($result.processes | Select-Object -First 1).WorkingSet64 / 1MB, 1) } else { $null }
}

if ($result.software) {
    $summary.installedApps = @($result.software).Count
}

if ($result.performance -and $result.performance.cpu) {
    $summary.cpuUsage = $result.performance.cpu.LoadPercentage
}

$output = @{
    data = $result
    summary = $summary
}

$output | ConvertTo-Json -Depth 10 -Compress