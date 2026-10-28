# Installs Python 3.12.10 for the current user only, into <project>\tools\python312 (no admin rights, nothing global).
# Pinned size and sha256 are the same as manifests\runtime.json (adapted from Qasem processing-server/downloads/voice.json).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$sha = "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"
$cache = Join-Path $root "data\downloads\cache"
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$exe = Join-Path $cache "python-3.12.10-amd64.exe"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not (Test-Path $exe)) {
    Write-Host "  Downloading Python 3.12.10 (about 26 MB) ..."
    Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
}
$got = (Get-FileHash -Algorithm SHA256 $exe).Hash.ToLower()
if ($got -ne $sha) {
    Move-Item -Force $exe ($exe + ".bad")
    Write-Host "  The downloaded installer failed verification and was moved aside."
    exit 1
}
$target = Join-Path $root "tools\python312"
Write-Host "  Installing (about a minute) ..."
$p = Start-Process -FilePath $exe -ArgumentList @("/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=0", "Include_test=0", "Include_doc=0", "Shortcuts=0", "TargetDir=$target") -Wait -PassThru
exit $p.ExitCode
