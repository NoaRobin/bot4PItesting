# Cree le raccourci « TIS Belges » sur le bureau, vers TIS_Belges.bat.
param([Parameter(Mandatory = $true)][string]$Target)

$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $desktop 'TIS Belges.lnk'))
$link.TargetPath = $Target
$link.WorkingDirectory = Split-Path -Parent $Target
$link.WindowStyle = 7   # fenetre de commande reduite : seule l'application s'affiche
$link.IconLocation = "$env:SystemRoot\System32\shell32.dll,44"
$link.Description = 'Ouvrir TIS Belges'
$link.Save()
Write-Output "Raccourci cree : $desktop\TIS Belges.lnk"
