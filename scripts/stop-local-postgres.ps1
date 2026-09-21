param([string]$PostgresBin = 'C:\Program Files\PostgreSQL\18\bin')
$projectRoot = Split-Path $PSScriptRoot -Parent
& "$PostgresBin\pg_ctl.exe" -D (Join-Path $projectRoot '.local\postgres-data') -m fast -w stop
if ($LASTEXITCODE -ne 0) { throw 'Unable to stop local PostgreSQL' }
