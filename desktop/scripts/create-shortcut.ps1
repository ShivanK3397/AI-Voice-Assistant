$desktopProject = Split-Path -Parent $PSScriptRoot
$packagedExecutable = Join-Path $desktopProject 'out/Jarvis-win32-x64/Jarvis.exe'
if (-not (Test-Path -LiteralPath $packagedExecutable)) {
    throw 'Build Jarvis first: run npm run build in the desktop directory.'
}
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Jarvis.lnk'
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $packagedExecutable
$shortcut.WorkingDirectory = Split-Path -Parent $packagedExecutable
$shortcut.Description = 'Jarvis desktop voice assistant'
$shortcut.Save()
Write-Output "Created $shortcutPath"
