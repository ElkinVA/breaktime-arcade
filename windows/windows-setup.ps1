#Requires -RunAsAdministrator
param([string[]]$ExtraHosts = @())
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
Write-Host "BREAKTIME ARCADE - настройка Windows" -ForegroundColor Cyan

$ca = Join-Path $dir 'rootCA.pem'
if (Test-Path $ca) {
  Import-Certificate -FilePath $ca -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
  Write-Host "OK: локальный сертификат доверенный" -ForegroundColor Green
} else { Write-Host "! rootCA.pem не найден рядом со скриптом" -ForegroundColor Yellow }

$hosts = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
Copy-Item $hosts "$hosts.bak" -Force
$raw = Get-Content $hosts -Raw -ErrorAction SilentlyContinue
$names = @('portal.test','demo.games.test','dont-drop-it.games.test') + $ExtraHosts
$add = @()
foreach ($n in $names) {
  if ($raw -notmatch "(?m)^\s*127\.0\.0\.1\s+$([regex]::Escape($n))\s*$") { $add += "127.0.0.1 $n" }
}
if ($add.Count -gt 0) {
  Add-Content -Path $hosts -Encoding ASCII -Value ("`r`n# BREAKTIME ARCADE dev`r`n" + ($add -join "`r`n"))
  Write-Host ("OK: в hosts добавлено " + $add.Count + " имён") -ForegroundColor Green
} else { Write-Host "OK: hosts уже настроен" -ForegroundColor Green }

$wslcfg = Join-Path $env:USERPROFILE '.wslconfig'
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1)
Write-Host ("ОЗУ компьютера: {0} ГБ" -f $ram)
if (-not (Test-Path $wslcfg)) {
  $mem = [int][math]::Max(4, [math]::Min(8, [math]::Floor($ram*0.6)))
  $ans = Read-Host ("Создать .wslconfig с memory=${mem}GB? [y/N]")
  if ($ans -eq 'y') {
    "[wsl2]`r`nmemory=${mem}GB`r`nprocessors=4`r`nswap=4GB`r`nlocalhostForwarding=true" | Set-Content $wslcfg -Encoding ASCII
    Write-Host "OK: .wslconfig создан" -ForegroundColor Green
  }
} else { Write-Host "OK: .wslconfig уже есть, не меняю" -ForegroundColor Green }
Write-Host "`nДальше выполните:  wsl --shutdown" -ForegroundColor Cyan
Write-Host "Затем откройте Ubuntu и запустите проверку окружения." -ForegroundColor Cyan
