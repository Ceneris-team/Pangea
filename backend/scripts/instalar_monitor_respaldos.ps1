param([string]$Python = "", [string]$EnvironmentFile = "", [string]$TaskName = "Pangea-Monitor-Respaldos-Local")
$ErrorActionPreference = "Stop"
$backend = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) { $Python = Join-Path $backend "venv\Scripts\python.exe" }
$Python = (Resolve-Path -LiteralPath $Python).Path
$argumentos = "-m scripts.gestionar_respaldos vigilar"
if ($EnvironmentFile) {
    $EnvironmentFile = (Resolve-Path -LiteralPath $EnvironmentFile).Path
    $argumentos = '-m scripts.gestionar_respaldos --env-file "' + $EnvironmentFile + '" vigilar'
}
$action = New-ScheduledTaskAction -Execute $Python -Argument $argumentos -WorkingDirectory $backend
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "Monitor $TaskName instalado cada hora mientras el usuario tenga una sesion abierta."
