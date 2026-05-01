param(
    [string]$PgUser = "postgres",
    [string]$PgHost = "localhost",
    [int]$PgPort = 5432,
    [string]$DbName = "mangopoint"
)

$ErrorActionPreference = "Stop"

$PgBin = "C:\Program Files\PostgreSQL\16\bin"
if (Test-Path "$PgBin\psql.exe") {
    $env:PATH = "$PgBin;$env:PATH"
    Write-Host "[OK] psql found at $PgBin" -ForegroundColor Green
} else {
    Write-Host "[FAIL] psql.exe not found at $PgBin" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "--- Checking PostgreSQL connectivity ---"

try {
    $ver = & psql -U $PgUser -h $PgHost -p $PgPort -c "SELECT version();" -t -A 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "psql exit code $LASTEXITCODE"
    }
    $verText = $ver.Trim()
    if ($verText.Length -gt 80) {
        $verText = $verText.Substring(0,80) + "..."
    }
    Write-Host "[OK] Connected: $verText" -ForegroundColor Green
}
catch {
    Write-Host "[FAIL] Cannot connect to PostgreSQL at $PgHost on port $PgPort" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "--- Creating database '$DbName' ---"

$dbExists = & psql -U $PgUser -h $PgHost -p $PgPort -tAc "SELECT 1 FROM pg_database WHERE datname='$DbName';" 2>&1
if ($dbExists.Trim() -eq "1") {
    Write-Host "[OK] Database '$DbName' already exists" -ForegroundColor Green
} else {
    & psql -U $PgUser -h $PgHost -p $PgPort -c "CREATE DATABASE $DbName;" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] Could not create database '$DbName'" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] Database '$DbName' created" -ForegroundColor Green
}

Write-Host ""
Write-Host "--- Enabling PostGIS extension ---"

$postgisAvail = & psql -U $PgUser -h $PgHost -p $PgPort -d $DbName -tAc "SELECT 1 FROM pg_available_extensions WHERE name='postgis';" 2>&1
if ($postgisAvail.Trim() -ne "1") {
    Write-Host "[FAIL] PostGIS is not available in this PostgreSQL installation" -ForegroundColor Red
    exit 1
}

& psql -U $PgUser -h $PgHost -p $PgPort -d $DbName -c "CREATE EXTENSION IF NOT EXISTS postgis;" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Could not enable PostGIS extension" -ForegroundColor Red
    exit 1
}

$pgVer = & psql -U $PgUser -h $PgHost -p $PgPort -d $DbName -tAc "SELECT postgis_version();" 2>&1
Write-Host "[OK] PostGIS enabled: $($pgVer.Trim())" -ForegroundColor Green

Write-Host ""
Write-Host "--- Applying schema (db/schema.sql) ---"

$schemaFile = Join-Path $PSScriptRoot "schema.sql"
if (-not (Test-Path $schemaFile)) {
    Write-Host "[FAIL] Schema file not found: $schemaFile" -ForegroundColor Red
    exit 1
}

& psql -U $PgUser -h $PgHost -p $PgPort -d $DbName -f $schemaFile 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Schema import failed" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Schema applied successfully" -ForegroundColor Green

Write-Host ""
Write-Host "--- Verifying tables ---"

$tables = & psql -U $PgUser -h $PgHost -p $PgPort -d $DbName -tAc "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;" 2>&1

$expectedTables = @(
    "alert",
    "environmental_condition",
    "infestation_record",
    "mango_stage",
    "orchard",
    "pest",
    "simulation_run",
    "spatial_ref_sys",
    "tree",
    "user_account",
    "weather_cache"
)

$tableList = $tables -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }

$missing = @()

foreach ($t in $expectedTables) {
    if ($tableList -contains $t) {
        Write-Host "  [OK] $t" -ForegroundColor Green
    } else {
        Write-Host "  [MISSING] $t" -ForegroundColor Red
        $missing += $t
    }
}

Write-Host ""
Write-Host "--- Verifying PostGIS geometry column on tree.geom ---"

$geomCol = & psql -U $PgUser -h $PgHost -p $PgPort -d $DbName -tAc "SELECT udt_name FROM information_schema.columns WHERE table_name='tree' AND column_name='geom';" 2>&1

if ($geomCol.Trim() -eq "geometry") {
    Write-Host "  [OK] tree.geom column type = geometry" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] tree.geom column not found or wrong type: $($geomCol.Trim())" -ForegroundColor Red
    $missing += "tree.geom"
}

Write-Host ""
if ($missing.Count -eq 0) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "ALL CHECKS PASSED - Setup complete" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Next: run 'python -m scripts.init_db' to provision the default admin account." -ForegroundColor Cyan
} else {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "SETUP INCOMPLETE - $($missing.Count) issue(s) found" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Missing: $($missing -join ', ')" -ForegroundColor Yellow
}
