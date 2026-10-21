# Runs as the Windows user who installed the task. No administrator required.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$configPath = Join-Path $PSScriptRoot 'config.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$destination = [IO.Path]::GetFullPath($config.Destination)
$null = New-Item -ItemType Directory -Force -Path $destination
$log = Join-Path $PSScriptRoot 'backup.log'
$lock = $null
$temporary = $null
$webSession = $null
$csrf = $null
$baseUrl = 'https://radar.clasure.com.br'

function Write-BackupLog([string]$message) {
    if ((Test-Path -LiteralPath $log) -and (Get-Item -LiteralPath $log).Length -gt 262144) {
        Move-Item -LiteralPath $log -Destination ($log + '.previous') -Force
    }
    Add-Content -LiteralPath $log -Value ('{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message) -Encoding UTF8
}

try {
    # Prevent a manual run and the scheduled task from pruning each other's files.
    $lock = [IO.File]::Open((Join-Path $PSScriptRoot 'backup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $credential = Import-Clixml -LiteralPath (Join-Path $PSScriptRoot 'credential.xml')
    $login = Invoke-WebRequest -Uri ($baseUrl + '/login') -SessionVariable webSession -UseBasicParsing -TimeoutSec 60
    $match = [regex]::Match($login.Content, 'name="csrf-token" content="([^"]+)"')
    if (-not $match.Success) { throw 'Nao foi possivel iniciar o login.' }
    $password = $credential.GetNetworkCredential().Password
    try {
        $panel = Invoke-WebRequest -Uri ($baseUrl + '/login') -Method Post -WebSession $webSession -UseBasicParsing -TimeoutSec 60 -Body @{
            email = $credential.UserName
            password = $password
            csrf_token = $match.Groups[1].Value
        }
    } finally { $password = $null }
    if ($panel.BaseResponse.ResponseUri.AbsolutePath -ne '/') { throw 'Login nao autorizado. Reinstale para atualizar a credencial.' }
    $match = [regex]::Match($panel.Content, 'name="csrf-token" content="([^"]+)"')
    if (-not $match.Success) { throw 'Sessao de backup invalida.' }
    $csrf = $match.Groups[1].Value
    $temporary = Join-Path $destination ('radar-download-' + [guid]::NewGuid().ToString('N') + '.partial')
    Invoke-WebRequest -Uri ($baseUrl + '/backup/banco') -WebSession $webSession -UseBasicParsing -TimeoutSec 180 -OutFile $temporary

    # Windows supplies SQLite; no Python or third-party executable is required.
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class RadarSqlite {
    [DllImport("winsqlite3.dll", CallingConvention=CallingConvention.Cdecl, CharSet=CharSet.Unicode)]
    static extern int sqlite3_open16(string path, out IntPtr db);
    [DllImport("winsqlite3.dll", CallingConvention=CallingConvention.Cdecl, CharSet=CharSet.Unicode)]
    static extern int sqlite3_prepare16_v2(IntPtr db, string sql, int bytes, out IntPtr statement, IntPtr tail);
    [DllImport("winsqlite3.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern int sqlite3_step(IntPtr statement);
    [DllImport("winsqlite3.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern IntPtr sqlite3_column_text16(IntPtr statement, int column);
    [DllImport("winsqlite3.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern int sqlite3_finalize(IntPtr statement);
    [DllImport("winsqlite3.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern int sqlite3_close(IntPtr db);
    public static void Validate(string path) {
        IntPtr db=IntPtr.Zero, stmt=IntPtr.Zero;
        try {
            if(sqlite3_open16(path,out db)!=0) throw new Exception("Nao foi possivel abrir o backup.");
            if(sqlite3_prepare16_v2(db,"PRAGMA integrity_check",-1,out stmt,IntPtr.Zero)!=0)
                throw new Exception("O arquivo recebido nao e um banco SQLite valido.");
            if(sqlite3_step(stmt)!=100 || Marshal.PtrToStringUni(sqlite3_column_text16(stmt,0))!="ok" || sqlite3_step(stmt)!=101)
                throw new Exception("O backup nao passou na verificacao de integridade.");
        } finally { if(stmt!=IntPtr.Zero) sqlite3_finalize(stmt); if(db!=IntPtr.Zero) sqlite3_close(db); }
    }
}
'@
    [RadarSqlite]::Validate($temporary)
    $filename = 'RADAR_banco_' + (Get-Date -Format 'yyyy-MM-dd_HH-mm-ss-fff') + '.db'
    Move-Item -LiteralPath $temporary -Destination (Join-Path $destination $filename)
    $temporary = $null
    # Only our own named backups are eligible. Historical and unrelated files stay intact.
    $backups = @(Get-ChildItem -LiteralPath $destination -File | Where-Object {
        $_.Name -match '^RADAR_banco_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:-\d{3})?\.db$'
    } | Sort-Object Name -Descending)
    foreach ($old in ($backups | Select-Object -Skip 7)) {
        Remove-Item -LiteralPath $old.FullName
    }
    Write-BackupLog ('OK: ' + $filename + '; copias mantidas: ' + [Math]::Min(7, $backups.Count))
} catch {
    # Do not log request bodies or credentials.
    Write-BackupLog ('FALHA: ' + $_.Exception.Message)
    exit 1
} finally {
    if ($temporary -and (Test-Path -LiteralPath $temporary)) { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }
    if ($webSession -and $csrf) {
        try { $null = Invoke-WebRequest -Uri ($baseUrl + '/logout') -Method Post -WebSession $webSession -UseBasicParsing -TimeoutSec 20 -Body @{csrf_token=$csrf} } catch { }
    }
    if ($lock) { $lock.Dispose() }
}
