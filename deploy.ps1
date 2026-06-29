$ErrorActionPreference = "Stop"

# Safe deployment helper:
# 1) commit changes
# 2) push to develop for Render test service
# 3) merge to main only after testing

git status
git add .
git commit -m "TeleSales update"
git push origin develop

Write-Host "Pushed to develop. Test on Render first, then merge develop into main when approved."
