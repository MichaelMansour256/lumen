# Starts a Cloudflare quick tunnel to the local API and prints the share link.
param([Parameter(Mandatory = $true)][string]$Cloudflared)
$ErrorActionPreference = "Stop"
# HTTP/2 (TCP) instead of QUIC (UDP): on networks that drop UDP, QUIC tunnels pass small
# replies but stall on images.
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$envFile = Join-Path $root "backend\.env.public"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$tunnelLog = Join-Path $logDir "tunnel.log"

$cfg = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $cfg[$Matches[1]] = $Matches[2].Trim('"', "'") }
}
$site = $cfg["LUMEN_SITE_URL"].TrimEnd("/")
$key = $cfg["ENHANCER_ACCESS_KEY"]

Write-Host "Waiting for the API on http://127.0.0.1:8000 ..."
$deadline = (Get-Date).AddSeconds(90)
while ($true) {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 3 | Out-Null; break }
    catch {
        if ((Get-Date) -gt $deadline) { Write-Host "The API did not start. Check the 'Lumen API (public)' window."; exit 1 }
        Start-Sleep -Seconds 2
    }
}

Write-Host "Opening the Cloudflare tunnel ..."
if (Test-Path $tunnelLog) { Remove-Item $tunnelLog -Force }
$proc = Start-Process -FilePath $Cloudflared `
    -ArgumentList @("tunnel", "--no-autoupdate", "--protocol", "http2", "--url", "http://127.0.0.1:8000") `
    -RedirectStandardError $tunnelLog -NoNewWindow -PassThru

$url = $null
$deadline = (Get-Date).AddSeconds(60)
while (-not $url -and (Get-Date) -lt $deadline -and -not $proc.HasExited) {
    Start-Sleep -Milliseconds 700
    if (Test-Path $tunnelLog) {
        $m = Select-String -LiteralPath $tunnelLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches |
             Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value }
    }
}
if (-not $url) {
    Write-Host "Could not get a tunnel address. See logs\tunnel.log"
    if (-not $proc.HasExited) { $proc | Stop-Process -Force }
    exit 1
}

$link = "$site/#api=$([uri]::EscapeDataString($url))&key=$([uri]::EscapeDataString($key))"
Set-Content -LiteralPath (Join-Path $logDir "share_link.txt") -Value $link
try { Set-Clipboard -Value $link } catch { }
Write-Host ""
Write-Host "  Public API : $url"
Write-Host "  Share link : $link"
Write-Host ""
Write-Host "  The link is copied to the clipboard and saved in logs\share_link.txt."
Write-Host "  Anyone with it can use your GPU. A new link is made every time you restart."
Write-Host "  Keep this window open; close it (or press Ctrl+C) to go offline."
Wait-Process -Id $proc.Id
Write-Host "The tunnel stopped."
