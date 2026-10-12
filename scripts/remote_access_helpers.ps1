# Read-only readiness checks and route planning, shared by the launcher and tests.
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
