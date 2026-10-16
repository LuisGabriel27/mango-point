# Production access helpers shared by the launcher and isolated tests.
function Get-MangoPointVercelLink([string]$ProjectFolder, [string]$ExpectedProjectName = 'mango-point') {
    $repairCommand = "npx.cmd --yes vercel@63.1.2 link --cwd frontend --project $ExpectedProjectName --yes"
    $linkPaths = @(
        (Join-Path $ProjectFolder 'frontend\.vercel\project.json'),
        (Join-Path $ProjectFolder '.vercel\project.json')
    )
    foreach ($linkPath in $linkPaths) {
        if (-not (Test-Path -LiteralPath $linkPath -PathType Leaf)) { continue }
        try {
            $link = Get-Content -LiteralPath $linkPath -Raw | ConvertFrom-Json
        } catch {
            throw "The local Vercel project link is invalid JSON: $linkPath. From the project folder, run: $repairCommand"
        }
        if (-not $link -or $link.projectId -notmatch '^prj_[A-Za-z0-9]+$' -or
            $link.orgId -notmatch '^(team|user)_[A-Za-z0-9]+$' -or
            $link.projectName -ne $ExpectedProjectName) {
            throw "The local Vercel link does not identify the $ExpectedProjectName app: $linkPath. From the project folder, run: $repairCommand"
        }
        return $link
    }
    throw "The local Vercel project link is missing. From the project folder, run: $repairCommand. This links the existing app; it does not deploy it."
}

function Invoke-MangoPointVercel([string[]]$VercelArgs, $ProjectLink, [string]$WorkingDirectory) {
    $previousPreference = $ErrorActionPreference
    $previousOrgId = $env:VERCEL_ORG_ID
    $previousProjectId = $env:VERCEL_PROJECT_ID
    try {
        # Use the validated main-app link even when only root metadata exists,
        # or the caller's current folder/environment belongs to another site.
        $env:VERCEL_ORG_ID = $ProjectLink.orgId
        $env:VERCEL_PROJECT_ID = $ProjectLink.projectId
        $ErrorActionPreference = 'Continue'
        $output = @(& npx.cmd --yes vercel@63.1.2 @VercelArgs --cwd $WorkingDirectory --scope $ProjectLink.orgId --non-interactive --no-color 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
        $env:VERCEL_ORG_ID = $previousOrgId
        $env:VERCEL_PROJECT_ID = $previousProjectId
    }
    $message = ($output | ForEach-Object { "$_" }) -join "`n"
    if ($exitCode -ne 0) { throw "Vercel command failed. $message" }
    return $message
}

function Get-MangoPointBundleApiBase([string]$Bundle) {
    # An explicit build setting takes precedence over an unused /api fallback.
    $setting = [regex]::Match($Bundle, '["'']?VITE_API_BASE["'']?\s*:\s*["'']([^"'']*)["'']')
    if ($setting.Success -and $setting.Groups[1].Value) { return $setting.Groups[1].Value.TrimEnd('/') }
    if ([regex]::IsMatch($Bundle, '["'']/api["'']')) { return '/api' }
    return [regex]::Match($Bundle, 'https://[a-z0-9-]+\.trycloudflare\.com').Value
}

function Get-MangoPointBundleText([string]$Url) {
    # Read JavaScript as text, without Windows PowerShell's HTML/link parsing.
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(30)
    try {
        $response = $client.GetAsync($Url).GetAwaiter().GetResult()
        try {
            $response.EnsureSuccessStatusCode() | Out-Null
            return $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        } finally { $response.Dispose() }
    } finally { $client.Dispose() }
}

function Get-MangoPointLiveApiBase([string]$SiteUrl, [string]$CachePath, [bool]$CheckOnly, [bool]$Refresh) {
    # Windows PowerShell's byte-by-byte web progress is costly for the large
    # app bundle. Keep the launcher stage messages and silence that display.
    $ProgressPreference = 'SilentlyContinue'
    $page = Invoke-WebRequest -UseBasicParsing -Uri "$SiteUrl/login?connection_check=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())" -TimeoutSec 20 -Headers @{ 'Cache-Control' = 'no-cache' }
    $asset = [regex]::Match($page.Content, 'src="([^"]*/assets/index-[^"]+\.js)"').Groups[1].Value
    if (-not $asset) { throw 'Could not locate the deployed application script.' }
    $assetUrl = [uri]::new([uri]$SiteUrl, $asset).AbsoluteUri
    if (-not $Refresh -and (Test-Path -LiteralPath $CachePath -PathType Leaf)) {
        try {
            $cached = Get-Content -LiteralPath $CachePath -Raw | ConvertFrom-Json
            if ($cached.version -eq 1 -and $cached.siteUrl -eq $SiteUrl -and
                $cached.assetUrl -eq $assetUrl -and $cached.apiBase -eq '/api') {
                Write-Host '[OK] The deployed app is unchanged; reused its verified /api configuration.'
                return '/api'
            }
        } catch { }
    }
    Write-Host '[INFO] Checking the deployed app configuration (one bundle download per release)...'
    $bundle = Get-MangoPointBundleText $assetUrl
    $apiBase = Get-MangoPointBundleApiBase $bundle
    if (-not $CheckOnly -and $apiBase -eq '/api') {
        # Only cache the immutable asset URL and its verified fixed API base.
        # Every run still reads live HTML and checks API/database/login access.
        try {
            New-Item -ItemType Directory -Path (Split-Path $CachePath -Parent) -Force | Out-Null
            @{ version = 1; siteUrl = $SiteUrl; assetUrl = $assetUrl; apiBase = $apiBase } |
                ConvertTo-Json | Set-Content -LiteralPath $CachePath -Encoding UTF8
        } catch { Write-Host '[INFO] Could not save the app configuration cache; startup checks continue.' }
    }
    return $apiBase
}

function Test-MangoPointApiReady([string]$Url) {
    try {
        $health = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 5 -Headers @{ 'Cache-Control' = 'no-cache' }
        return $health.status -eq 'healthy' -and $health.database -eq 'connected'
    } catch { return $false }
}

function Wait-MangoPointApiReady([string]$Url, [int]$TimeoutSeconds = 90, $Process = $null) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-MangoPointApiReady $Url) { return }
        if ($Process) {
            $Process.Refresh()
            if ($Process.HasExited) { throw 'The server process exited before it was ready. Check outputs/remote-access/.' }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "MangoPoint API/database readiness timed out: $Url/health"
}

function Get-MangoPointRoutePlan($State, [string]$ApiUrl) {
    # Publishing applies the whole staged version. Never publish other edits.
    if ($State.hasStagingChanges -or ($State.version -and $State.version.isStaging)) {
        throw 'Vercel has unpublished routing changes. Review/publish or discard those changes in CDN > Routing Rules before running this helper.'
    }
    $matches = @($State.routes | Where-Object { $_.name -eq 'MangoPoint API' })
    if ($matches.Count -gt 1) { throw 'More than one MangoPoint API route exists. Resolve duplicate routes first.' }
    $route = $matches | Select-Object -First 1
    $destination = $ApiUrl.TrimEnd('/') + '/$1'
    if (-not $route) { return @{ action = 'add'; destination = $destination } }
    $configuredDestination = if ($route.rawDest) { $route.rawDest } else { $route.route.dest }
    $configuredSource = if ($route.rawSrc) { $route.rawSrc } else { $route.route.src }
    # Vercel normalizes regex sources by dropping the redundant leading ^.
    if ($configuredDestination -eq $destination -and $configuredSource.TrimStart('^') -eq '/api/(.*)$' -and
        $route.enabled -and $route.route.headers.'Cache-Control' -eq 'no-store') {
        return @{ action = 'none'; destination = $destination; id = $route.id }
    }
    return @{ action = 'edit'; destination = $destination; id = $route.id }
}
