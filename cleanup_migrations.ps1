# Cleanup broken duplicate migration files
$bad = "migrations\versions\auto_gross_method_by_agreement_v34.py"
if (Test-Path $bad) { Remove-Item $bad -Force; Write-Host "Removed duplicate bad migration: $bad" }
$cache = "migrations\versions\__pycache__"
if (Test-Path $cache) { Remove-Item $cache -Recurse -Force; Write-Host "Removed migration cache." }
Write-Host "Cleanup complete. Now run: flask db upgrade"
