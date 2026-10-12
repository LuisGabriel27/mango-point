param(
    [switch]$CheckOnly,
    [switch]$ForceDeploy,
    [switch]$StartServer,
    [switch]$UseTailscale,
    [switch]$RememberConnection,
    [string]$PublicApiUrl
)

$ErrorActionPreference = 'Stop'
$previousProgressPreference = $ProgressPreference
$ProgressPreference = 'SilentlyContinue'
$startupTimer = [System.Diagnostics.Stopwatch]::StartNew()
$projectFolder = Split-Path $PSScriptRoot -Parent
$frontendFolder = Join-Path $projectFolder 'frontend'
$siteUrl = 'https://mango-point-projects.vercel.app'
$localApi = 'http://127.0.0.1:8000'
. (Join-Path $PSScriptRoot 'remote_access_helpers.ps1')
. (Join-Path $PSScriptRoot 'stable_access_helpers.ps1')
$connectionConfigPath = Join-Path $projectFolder 'outputs\remote-access\connection.json'
$frontendCheckCachePath = Join-Path $projectFolder 'outputs\remote-access\frontend-check.json'

function Get-LiveApiUrl {
    return Get-MangoPointLiveApiBase -SiteUrl $siteUrl -CachePath $frontendCheckCachePath -CheckOnly $CheckOnly -Refresh $ForceDeploy
}

function Get-RunningTunnelUrls {
    $ports = @(20241..20245)
    $processes = @(Get-Process cloudflared -ErrorAction SilentlyContinue)
    foreach ($process in $processes) {
        $ports += @(Get-NetTCPConnection -OwningProcess $process.Id -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -in @('127.0.0.1', '::1') } |
            Select-Object -ExpandProperty LocalPort)
    }
    foreach ($port in ($ports | Select-Object -Unique)) {
        try {
            $metrics = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/metrics" -TimeoutSec 1
            foreach ($match in [regex]::Matches($metrics.Content, 'userHostname="(https://[a-z0-9-]+\.trycloudflare\.com)"')) {
                $match.Groups[1].Value
            }
        } catch { }
    }
}

function Assert-TunnelReady([string]$Url, [int]$TimeoutSeconds = 90) {
    Wait-MangoPointApiReady $Url -TimeoutSeconds $TimeoutSeconds
    $headers = @{ Origin = $siteUrl; 'Access-Control-Request-Method' = 'POST'; 'Access-Control-Request-Headers' = 'content-type' }
    $cors = Invoke-WebRequest -UseBasicParsing -Method Options -Uri "$Url/auth/login" -Headers $headers -TimeoutSec 20
    if ($cors.Headers['Access-Control-Allow-Origin'] -ne $siteUrl) {
        throw 'The API CORS_ORIGINS setting must include https://mango-point-projects.vercel.app.'
    }
}

function Invoke-Vercel([string[]]$VercelArgs) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& npx.cmd --yes vercel@63.1.2 @VercelArgs --non-interactive --no-color 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    $message = ($output | ForEach-Object { "$_" }) -join "`n"
    if ($exitCode -ne 0) { throw "Vercel command failed. $message" }
    return $message
}

function Start-MangoPointServer {
    if (Test-MangoPointApiReady $localApi) { return }
    if (-not $StartServer) { throw 'Start the API and database first, or run .\start_production.bat to start them together.' }
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
        Write-Host '[INFO] An API is already listening; waiting for its database readiness...'
        Wait-MangoPointApiReady $localApi
        return
    }
    $python = Join-Path $projectFolder '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
    $databaseCheck = @'
import sys
try:
    import psycopg2
    from api.core.config import settings
    connection = psycopg2.connect(settings.DATABASE_URL, connect_timeout=3)
    connection.close()
except Exception:
    sys.exit(1)
'@
    & $python -c $databaseCheck
    if ($LASTEXITCODE -ne 0) {
        Get-Command docker -ErrorAction Stop | Out-Null
        Write-Host '[INFO] Starting the Docker database and API; waiting for readiness...'
        & docker compose up -d --build --wait --wait-timeout 120
        if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed. Start Docker Desktop and check ports 8000/55432, then run this command again.' }
        Wait-MangoPointApiReady $localApi
        return
    }
    $logFolder = Join-Path $projectFolder 'outputs\remote-access'
    New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
    $logPrefix = Join-Path $logFolder (Get-Date -Format 'yyyyMMdd-HHmmss-api')
    $apiProcess = Start-Process -FilePath $python -WorkingDirectory $projectFolder -ArgumentList @('-u', 'run_server.py', '--host', '127.0.0.1', '--port', '8000') -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logPrefix.stdout.log" -RedirectStandardError "$logPrefix.stderr.log"
    Write-Host "[INFO] Started the API in the background (PID $($apiProcess.Id)); waiting for its database..."
    Wait-MangoPointApiReady -Url $localApi -Process $apiProcess
}

function Set-MangoPointApiRoute([string]$ApiUrl) {
    Write-Host '[INFO] Checking the published Vercel /api route...'
    $link = Get-Content (Join-Path $frontendFolder '.vercel\project.json') -Raw | ConvertFrom-Json
    $endpoint = "/v1/projects/$($link.projectId)/routes?teamId=$($link.orgId)"
    $state = Convert-VercelJson (Invoke-Vercel -VercelArgs @('api', $endpoint))
    $versions = Convert-VercelJson (Invoke-Vercel -VercelArgs @('api', "/v1/projects/$($link.projectId)/routes/versions?teamId=$($link.orgId)"))
    $state | Add-Member -NotePropertyName hasStagingChanges -NotePropertyValue (@($versions.versions | Where-Object { $_.isStaging }).Count -gt 0)
    $plan = Get-MangoPointRoutePlan -State $state -ApiUrl $ApiUrl
    if ($plan.action -eq 'none') {
        Write-Host '[OK] The published /api route already uses this server.'
        return
    }
    if ($CheckOnly) { throw 'The published /api route needs updating. Run .\start_production.bat.' }
    $routeArgs = @('routes', $plan.action)
    $routeArgs += if ($plan.action -eq 'add') { 'MangoPoint API' } else { $plan.id }
    $routeArgs += @('--project', $link.projectId, '--src', '^/api/(.*)$', '--src-syntax', 'regex', '--action', 'rewrite', '--dest', $plan.destination, '--set-response-header', 'Cache-Control=no-store', '--yes')
    if ($plan.action -eq 'add') { $routeArgs += @('--position', 'start') }
    Invoke-Vercel -VercelArgs $routeArgs | Out-Null
    $previousRoute = $state.routes | Where-Object { $_.id -eq $plan.id } | Select-Object -First 1
    if ($plan.action -eq 'edit' -and -not $previousRoute.enabled) {
        Invoke-Vercel -VercelArgs @('routes', 'enable', $plan.id, '--project', $link.projectId) | Out-Null
    }
    Invoke-Vercel -VercelArgs @('routes', 'publish', '--project', $link.projectId, '--yes') | Out-Null
    Write-Host '[OK] Published the current server at the fixed /api address.'
}

function Convert-VercelJson([string]$Output) {
    $jsonStart = [regex]::Match($Output, '(?m)^\{')
    if (-not $jsonStart.Success) { throw 'Vercel did not return the expected JSON result.' }
    return $Output.Substring($jsonStart.Index) | ConvertFrom-Json
}

Push-Location $projectFolder
try {
    if ($CheckOnly -and ($StartServer -or $RememberConnection -or $ForceDeploy)) {
        throw 'Use .\start_remote_access.bat -CheckOnly for a read-only check, without startup or setup options.'
    }
    $savedConnection = $null
    if (-not $UseTailscale -and -not $PublicApiUrl -and (Test-Path -LiteralPath $connectionConfigPath)) {
        $savedConnection = Get-Content -LiteralPath $connectionConfigPath -Raw | ConvertFrom-Json
        if (-not $savedConnection) { throw 'The saved stable connection is empty. Run setup_stable_access.bat to repair it.' }
    }
    $connection = Get-MangoPointConnectionPlan -UseTailscale $UseTailscale -PublicApiUrl $PublicApiUrl -SavedConnection $savedConnection
    if ($RememberConnection -and $connection.provider -eq 'quick') {
        throw 'Only a stable connection can be remembered. Use -UseTailscale or -PublicApiUrl.'
    }
    Write-Host '[INFO] Checking the local API and database...'
    Start-MangoPointServer
    Write-Host '[OK] Local API and database are ready.'
    Write-Host '[INFO] Checking the deployed app release...'
    $liveApi = Get-LiveApiUrl
    if ($connection.provider -eq 'tailscale') {
        $tunnelUrl = Start-MangoPointTailscaleFunnel -CheckOnly $CheckOnly -ExpectedUrl $connection.publicApiUrl -ConfigureUnattended $RememberConnection
    } elseif ($connection.provider -eq 'external') {
        $tunnelUrl = $connection.publicApiUrl
    } else {
        $runningUrls = @(Get-RunningTunnelUrls | Select-Object -Unique)
        $tunnelUrl = if ($runningUrls -contains $liveApi) { $liveApi } else { $runningUrls | Select-Object -First 1 }

        if (-not $tunnelUrl) {
            if ($CheckOnly) { throw 'No running Quick Tunnel was found.' }
            $cloudflared = (Get-Command cloudflared -ErrorAction Stop).Source
            $logFolder = Join-Path $projectFolder 'outputs\remote-access'
            New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
            $logPrefix = Join-Path $logFolder (Get-Date -Format 'yyyyMMdd-HHmmss')
            $tunnelProcess = Start-Process -FilePath $cloudflared -ArgumentList @('tunnel', '--protocol', 'http2', '--url', $localApi) -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logPrefix.stdout.log" -RedirectStandardError "$logPrefix.stderr.log"
            Write-Host "[INFO] Started the tunnel in the background (PID $($tunnelProcess.Id)). Logs: $logFolder"
            $deadline = (Get-Date).AddSeconds(45)
            do {
                $tunnelUrl = Get-RunningTunnelUrls | Select-Object -First 1
                if ($tunnelUrl) { break }
                $tunnelProcess.Refresh()
                if ($tunnelProcess.HasExited) { throw "cloudflared exited. Check $logPrefix.stderr.log" }
                Start-Sleep -Seconds 1
            } while ((Get-Date) -lt $deadline)
            if (-not $tunnelUrl) { throw "Tunnel startup timed out. Check $logPrefix.stderr.log" }
        }
    }

    $publicReadinessTimeout = if ($RememberConnection -and $connection.provider -eq 'tailscale') { 600 } else { 90 }
    if ($publicReadinessTimeout -eq 600) {
        Write-Host '[INFO] Checking stable HTTPS access; first-time DNS/certificate setup can take several minutes...'
    }
    Write-Host '[INFO] Checking public API health and browser access...'
    Assert-TunnelReady $tunnelUrl -TimeoutSeconds $publicReadinessTimeout
    Write-Host "[OK] Public API and browser access are ready: $tunnelUrl"
    Set-MangoPointApiRoute $tunnelUrl
    Write-Host '[INFO] Checking the deployed /api connection...'
    Wait-MangoPointApiReady "$siteUrl/api" -TimeoutSeconds $publicReadinessTimeout
    if ($liveApi -eq '/api' -and -not $ForceDeploy) {
        Write-Host '[OK] Vercel uses the fixed /api address. No deployment is needed.'
    } elseif ($CheckOnly) {
        throw "Vercel uses a different tunnel ($liveApi). Run .\start_remote_access.bat without -CheckOnly to update it."
    } else {
        Get-Command npx.cmd -ErrorAction Stop | Out-Null
        $link = Get-Content (Join-Path $frontendFolder '.vercel\project.json') -Raw | ConvertFrom-Json
        $projectName = $link.projectName
        $project = Convert-VercelJson (Invoke-Vercel -VercelArgs @('project', 'inspect', $projectName, '--json'))
        $previousRoot = $project.rootDirectory
        Write-Host '[INFO] Installing the fixed /api address in the frontend. This first rebuild may take a few minutes.'
        Invoke-Vercel -VercelArgs @('env', 'update', 'VITE_API_BASE', 'production', '--value', '/api', '--yes') | Out-Null
        Push-Location $frontendFolder
        try {
            Invoke-Vercel -VercelArgs @('project', 'update', $projectName, '--auto-detect', 'root-directory', '--yes') | Out-Null
            try {
                $deployment = Convert-VercelJson (Invoke-Vercel -VercelArgs @('--prod', '--yes', '--force'))
                if ($deployment.status -ne 'ok' -or $deployment.deployment.readyState -ne 'READY') {
                    throw 'The new Vercel deployment did not become ready.'
                }
            } finally {
                if ($previousRoot) {
                    Invoke-Vercel -VercelArgs @('project', 'update', $projectName, '--root-directory', $previousRoot, '--yes') | Out-Null
                } else {
                    Invoke-Vercel -VercelArgs @('project', 'update', $projectName, '--auto-detect', 'root-directory', '--yes') | Out-Null
                }
            }
            Invoke-Vercel -VercelArgs @('alias', 'set', $deployment.deployment.url, ([uri]$siteUrl).Host) | Out-Null
        } finally {
            Pop-Location
        }
        $frontendDeadline = (Get-Date).AddSeconds(60)
        do {
            if ((Get-LiveApiUrl) -eq '/api') { break }
            Start-Sleep -Seconds 2
        } while ((Get-Date) -lt $frontendDeadline)
        if ((Get-LiveApiUrl) -ne '/api') { throw 'The live frontend does not yet use /api. Check the deployment before sharing it.' }
        Write-Host '[OK] Vercel now uses the fixed /api address.'
    }
    if ($ForceDeploy -or $liveApi -ne '/api') {
        Wait-MangoPointApiReady "$siteUrl/api" -TimeoutSeconds $publicReadinessTimeout
    }
    # Confirm protected application routes also reach FastAPI, not the SPA fallback.
    $authCheck = Invoke-WebRequest -UseBasicParsing -Method Options -Uri "$siteUrl/api/auth/login" -Headers @{ Origin = $siteUrl; 'Access-Control-Request-Method' = 'POST'; 'Access-Control-Request-Headers' = 'content-type' } -TimeoutSec 20
    if ($authCheck.Headers['Access-Control-Allow-Origin'] -ne $siteUrl) { throw 'Vercel API login preflight failed.' }
    if ($RememberConnection -and -not $CheckOnly) {
        New-Item -ItemType Directory -Path (Split-Path $connectionConfigPath -Parent) -Force | Out-Null
        @{ version = 1; provider = $connection.provider; publicApiUrl = $tunnelUrl } | ConvertTo-Json | Set-Content -LiteralPath $connectionConfigPath -Encoding UTF8
        Write-Host '[OK] Saved the stable connection for future start_production.bat runs.'
    }
    Write-Host '[OK] Vercel API health, database and login access are ready.'
    Write-Host "[OK] Startup checks completed in $([math]::Round($startupTimer.Elapsed.TotalSeconds, 1)) seconds."
    Write-Host "[OK] Share $siteUrl"
    Write-Host 'Keep the laptop awake, online, and the MangoPoint API running.'
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
    $ProgressPreference = $previousProgressPreference
}
