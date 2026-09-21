param([string]$PostgresBin = 'C:\Program Files\PostgreSQL\18\bin')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$localDir = Join-Path $projectRoot '.local'
$dataDir = Join-Path $localDir 'postgres-data'
$envPath = Join-Path $projectRoot '.env'
if (-not (Test-Path (Join-Path $PostgresBin 'initdb.exe'))) {
    throw 'PostgreSQL binaries not found. Pass -PostgresBin with the installed bin directory.'
}
New-Item -ItemType Directory -Force -Path $localDir | Out-Null
if (-not (Test-Path $envPath)) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $secretBytes = New-Object byte[] 48
    $rng.GetBytes($secretBytes)
    $jwtSecret = [Convert]::ToBase64String($secretBytes)
    $rng.GetBytes($secretBytes)
    $dbPassword = [Convert]::ToBase64String($secretBytes).Replace('+','a').Replace('/','b').TrimEnd('=')
    $rng.Dispose()
    $lines = @(
        'APP_ENV=development'
        "DATABASE_URL=postgresql+psycopg://eleven:${dbPassword}@127.0.0.1:55432/eleven"
        "TEST_DATABASE_URL=postgresql+psycopg://eleven:${dbPassword}@127.0.0.1:55432/eleven_test"
        "JWT_SECRET=$jwtSecret"
        'CORS_ORIGINS=["http://localhost:8081"]'
    )
    [IO.File]::WriteAllLines($envPath, $lines)
}
$databaseLine = Get-Content -LiteralPath $envPath | Where-Object { $_ -match '^DATABASE_URL=' }
$databaseUri = [Uri](($databaseLine -replace '^DATABASE_URL=', '') -replace '^postgresql\+psycopg:', 'postgresql:')
if ($databaseUri.Host -ne '127.0.0.1' -or $databaseUri.Port -ne 55432 -or $databaseUri.AbsolutePath -ne '/eleven') {
    throw 'Existing .env does not target the isolated local database on port 55432. It was preserved.'
}
$credentials = $databaseUri.UserInfo.Split(':', 2)
if ($credentials[0] -ne 'eleven') { throw 'Local bootstrap expects database user eleven.' }
$dbPassword = [Uri]::UnescapeDataString($credentials[1])
if (-not (Test-Path (Join-Path $dataDir 'PG_VERSION'))) {
    $passwordFile = Join-Path $localDir 'pg-init-password'
    try {
        [IO.File]::WriteAllText($passwordFile, $dbPassword)
        & "$PostgresBin\initdb.exe" -D $dataDir -U eleven --auth=scram-sha-256 --encoding=UTF8 --locale=C --pwfile=$passwordFile
        if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
        Add-Content -LiteralPath (Join-Path $dataDir 'postgresql.conf') -Value "`nlisten_addresses = '127.0.0.1'`nport = 55432"
    } finally {
        if (Test-Path $passwordFile) { Remove-Item -LiteralPath $passwordFile }
    }
}
& "$PostgresBin\pg_ctl.exe" -D $dataDir status *> $null
if ($LASTEXITCODE -ne 0) {
    & "$PostgresBin\pg_ctl.exe" -D $dataDir -l (Join-Path $localDir 'postgres.log') -w start
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL failed to start; inspect .local/postgres.log' }
}
$previousPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $dbPassword
    foreach ($databaseName in @('eleven', 'eleven_test')) {
        $exists = & "$PostgresBin\psql.exe" -h 127.0.0.1 -p 55432 -U eleven -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$databaseName'"
        if ($LASTEXITCODE -ne 0) { throw 'Database connection failed' }
        if ($exists -ne '1') {
            & "$PostgresBin\createdb.exe" -h 127.0.0.1 -p 55432 -U eleven $databaseName
            if ($LASTEXITCODE -ne 0) { throw "Could not create $databaseName" }
        }
    }
} finally { $env:PGPASSWORD = $previousPassword }
Write-Host 'Isolated PostgreSQL ready at 127.0.0.1:55432. Existing .env and databases preserved.'
