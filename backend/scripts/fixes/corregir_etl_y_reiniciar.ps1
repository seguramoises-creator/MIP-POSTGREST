net stop MSM-Backend
Start-Sleep -Seconds 3
net start MSM-Backend
Get-Service -Name MSM-Backend
