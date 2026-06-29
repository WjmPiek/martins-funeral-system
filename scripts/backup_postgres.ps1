param(
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$BackupFolder = ".\backups"
)
if (-not $DatabaseUrl) { throw "DATABASE_URL is required." }
New-Item -ItemType Directory -Force -Path $BackupFolder | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$out = Join-Path $BackupFolder "telesales_$stamp.dump"
pg_dump $DatabaseUrl --format=custom --file=$out
Write-Host "Backup created: $out"
