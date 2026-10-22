# start-headless-edge.ps1 —— 启动一个可被 puppeteer connect 的无头 Edge（固定调试端口）
#
# 为什么需要它：本机 DSH 沙箱禁止「用管道捕获子进程 stdio」的 spawn（EPERM），
# puppeteer.launch() 内部正是用管道读 DevTools URL，因此必须在外部先把 Edge 拉起来，
# 再让 verify.mjs 用 puppeteer.connect({browserURL}) 连上去。
#
# 用法（**必须**在后台作业里跑，否则会话结束时子进程可能被回收）：
#   pwsh -File tools\web\start-headless-edge.ps1 -Port 9333 -KeepAliveSeconds 900
#   powershell -NoProfile -File tools\web\start-headless-edge.ps1 -Port 9333
#
# 临时目录铁律：profile 与 TEMP 全部落在 .scratch\web 下，绝不落 C 盘。

param(
  [int]$Port = 9333,
  [string]$Url = 'about:blank',
  [int]$Width = 1280,
  [int]$Height = 800,
  [switch]$Headful,
  [int]$KeepAliveSeconds = 0
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $here)
$scratch = Join-Path $root '.scratch\web'
$profile = Join-Path $scratch 'profile'
$tmp = Join-Path $scratch 'tmp'
New-Item -ItemType Directory -Force -Path $profile, $tmp | Out-Null

$env:TEMP = $tmp
$env:TMP = $tmp

$candidates = @(
  'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
  'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
)
$edge = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw '找不到 msedge.exe' }

# 复用已在跑的实例（同端口）
try {
  $probe = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
} catch { $probe = $null }
if ($probe) {
  Write-Output "ALREADY http://127.0.0.1:$Port"
  if ($KeepAliveSeconds -gt 0) { Start-Sleep -Seconds $KeepAliveSeconds }
  exit 0
}

$edgeArgs = @(
  "--remote-debugging-port=$Port",
  "--user-data-dir=$profile",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-background-networking",
  "--disable-features=Translate,BackForwardCache,MediaRouter",
  "--disable-dev-shm-usage",
  "--disable-extensions",
  "--enable-unsafe-swiftshader",
  "--use-angle=swiftshader",
  "--autoplay-policy=no-user-gesture-required",
  "--window-size=$Width,$Height",
  "--lang=zh-CN"
)
if (-not $Headful) { $edgeArgs += '--headless=new' }
$edgeArgs += $Url

$log = Join-Path $scratch 'edge.log'
$err = Join-Path $scratch 'edge.err.log'
$p = Start-Process -FilePath $edge -ArgumentList $edgeArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $err
$p.Id | Set-Content (Join-Path $scratch 'edge.pid')
Write-Output "PID $($p.Id)"

# 轮询调试端口（唯一可信判据）
$deadline = (Get-Date).AddSeconds(40)
$ok = $false
while ((Get-Date) -lt $deadline) {
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 2
    if ($r.webSocketDebuggerUrl) { $ok = $true; break }
  } catch {
    Start-Sleep -Milliseconds 400
  }
}
if ($ok) {
  Write-Output "READY http://127.0.0.1:$Port"
} else {
  Write-Output 'FAILED 调试端口未打开'
  if (Test-Path $err) { Get-Content $err -Tail 20 }
  exit 1
}

if ($KeepAliveSeconds -gt 0) {
  Start-Sleep -Seconds $KeepAliveSeconds
}
