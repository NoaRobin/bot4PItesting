# Cree le raccourci « TIS Belges » sur le bureau, qui lance Lancer.bat.
param([string]$Folder)

$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $desktop 'TIS Belges.lnk'))
$link.TargetPath = Join-Path $Folder 'Lancer.bat'
$link.WorkingDirectory = $Folder
$link.IconLocation = "$env:SystemRoot\System32\shell32.dll,44"
$link.Description = 'Ouvrir le dashboard TIS Belges'
$link.Save()
Write-Output "Raccourci cree : $desktop\TIS Belges.lnk"
