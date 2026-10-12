param(
    [switch]$Prepare,
    [switch]$CheckOnly,
    [switch]$RepairCors
)

$ErrorActionPreference = 'Stop'
$projectFolder = Split-Path $PSScriptRoot -Parent
$localApi = 'http://127.0.0.1:8000'
$siteUrl = 'https://mango-point-projects.vercel.app'
. (Join-Path $PSScriptRoot 'remote_access_helpers.ps1')
. (Join-Path $PSScriptRoot 'offline_companion_helpers.ps1')

Push-Location $projectFolder
try {
    if (@($Prepare, $CheckOnly, $RepairCors | Where-Object { $_ }).Count -gt 1) {
        throw 'Use -Prepare, -CheckOnly or -RepairCors separately.'
    }
    if ($RepairCors) {
        $browserAccessReady = $false
        if (Test-MangoPointApiReady $localApi) {
            try {
                Assert-MangoPointCompanionBrowserAccess -ApiUrl $localApi -SiteUrl $siteUrl
                $browserAccessReady = $true
            } catch { }
        }
        if ($browserAccessReady) {
            Write-Host '[OK] The running API already allows Vercel; no repair is needed.'
        } else {
            Get-Command docker -ErrorAction Stop | Out-Null
            try { & docker info --format '{{.ServerVersion}}' *> $null }
            catch { throw 'Docker Desktop is not running. Start it, then retry -RepairCors.' }
            if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not running. Start it, then retry -RepairCors.' }
            $apiContainer = & docker compose ps --status running --quiet api
            if ($LASTEXITCODE -ne 0 -or -not $apiContainer) {
                throw 'No running API container was found for this project. Start its Docker companion first. If your healthy API runs directly in Python, edit CORS_ORIGINS in .env and restart that API instead; no configuration was changed.'
            }
            $changed = Add-MangoPointCompanionOrigin -EnvPath (Join-Path $projectFolder '.env') -SiteUrl $siteUrl
            if ($changed) {
                Write-Host '[OK] Added the Vercel origin to .env. Other settings were retained; a private backup is in outputs/offline-companion/.'
            }
            Write-Host '[INFO] Recreating only the API container from its existing image to apply CORS...'
            & docker compose up -d --no-deps --no-build --pull never --force-recreate --wait --wait-timeout 120 api
            if ($LASTEXITCODE -ne 0) { throw 'API recreation failed. The .env change is retained; inspect docker compose logs --tail 50 api, then retry -RepairCors.' }
            Wait-MangoPointApiReady $localApi -TimeoutSeconds 60
        }
    }
    $localReady = Test-MangoPointApiReady $localApi
    if (-not $localReady) {
        if ($CheckOnly) {
            throw 'The local API/database is not ready at http://127.0.0.1:8000/health. Start Docker Desktop and run start_offline_companion.bat. If images are missing, prepare while online with -Prepare.'
        }
        if (-not (Test-Path -LiteralPath (Join-Path $projectFolder '.env'))) {
            throw 'Create .env from .env.example for this laptop before first setup. Keep an existing .env and its credentials.'
        }
        Get-Command docker -ErrorAction Stop | Out-Null
        try { & docker info --format '{{.ServerVersion}}' *> $null }
        catch { throw 'Docker Desktop is not running. Start it, then retry.' }
        if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not running. Start it, then retry.' }
        if ($Prepare) {
            Write-Host '[INFO] Preparing Docker images while online and waiting for API/database health...'
        } else {
            Write-Host '[INFO] Starting prepared Docker images without builds/downloads and waiting for API/database health...'
        }
        $startArguments = @(Get-MangoPointCompanionStartArgs -Prepare $Prepare)
        & docker @startArguments
        if ($LASTEXITCODE -ne 0) {
            throw 'Docker startup failed. Check Docker Desktop and ports 8000/55432. If images are missing/outdated, run start_offline_companion.bat -Prepare while online. Inspect docker compose ps and docker compose logs --tail 50 api on this laptop.'
        }
        Wait-MangoPointApiReady $localApi -TimeoutSeconds 60
    } else {
        Write-Host '[OK] A healthy local MangoPoint API and connected database are already running.'
        if ($Prepare) {
            Write-Host '[INFO] Existing healthy services were reused. To update Docker code deliberately, run docker compose up -d --build --wait --wait-timeout 120 while online.'
        }
    }
    Assert-MangoPointCompanionBrowserAccess -ApiUrl $localApi -SiteUrl $siteUrl
    Write-Host '[OK] Local API/database health and Vercel CORS/login preflight passed.'
    Write-Host "Health check: $localApi/health"
    Write-Host "Open: $siteUrl"
    Write-Host 'In current Chrome/Edge, allow this site Local network access, then reload while online.'
    Write-Host 'Sign in with an account in this laptop''s database. Confirm Local-first mode before disconnecting.'
    Write-Host 'Keep this browser profile, the API/database and Docker Desktop running; use Custom Weather offline.'
    Write-Host 'These checks cannot verify browser permissions or its PWA cache. Run -CheckOnly on the affected laptop to diagnose its server settings.'
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally { Pop-Location }
