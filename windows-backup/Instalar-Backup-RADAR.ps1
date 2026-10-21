[CmdletBinding()]
param(
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Backups RADAR'),
    [string]$Time = '18:00'
)
$ErrorActionPreference = 'Stop'
$hour = [datetime]::ParseExact($Time, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture)
$install = Join-Path $env:LOCALAPPDATA 'RADAR Backup'
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$taskName = 'RADAR Backup Diario ' + $sid
$null = New-Item -ItemType Directory -Force -Path $install
$null = New-Item -ItemType Directory -Force -Path $Destination

# Restrict credentials/config/scripts to this user and SYSTEM.
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
foreach ($identity in @($sid, 'S-1-5-18')) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule(
        (New-Object Security.Principal.SecurityIdentifier($identity)), 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $install -AclObject $acl
Write-Host 'RADAR - backup diario do banco' -ForegroundColor Cyan
Write-Host ('Pasta: ' + $Destination)
Write-Host ('Horario: ' + $Time + ' (horario deste computador)')
Write-Host 'A senha fica protegida pelo Windows e so pode ser lida por este usuario neste PC.'
$email = Read-Host 'E-mail do RADAR'
$securePassword = Read-Host 'Senha do RADAR' -AsSecureString
$credential = New-Object Management.Automation.PSCredential($email, $securePassword)
$credential | Export-Clixml -LiteralPath (Join-Path $install 'credential.xml')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Backup-RADAR.ps1') -Destination (Join-Path $install 'Backup-RADAR.ps1') -Force
@{Destination=[IO.Path]::GetFullPath($Destination)} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $install 'config.json') -Encoding UTF8
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
Write-Host 'Baixando e validando o primeiro backup...'
& $powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $install 'Backup-RADAR.ps1')
if ($LASTEXITCODE -ne 0) {
    throw ('O teste falhou. Nenhum agendamento novo foi criado. Veja ' + (Join-Path $install 'backup.log'))
}
$action = New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $install 'Backup-RADAR.ps1') + '"')
$trigger = New-ScheduledTaskTrigger -Daily -At $hour
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Baixa o banco RADAR diariamente; valida integridade e mantem sete copias.' -Force | Out-Null
Write-Host 'Instalado! Primeiro backup validado e tarefa diaria criada.' -ForegroundColor Green
Write-Host 'O PC precisa estar ligado, com internet e este usuario conectado ao Windows.'
Write-Host 'Se perder o horario, o Windows tentara executar quando estiver disponivel.'
Write-Host ('Log: ' + (Join-Path $install 'backup.log'))
