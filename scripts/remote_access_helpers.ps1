# Read-only readiness checks and route planning, shared by the launcher and tests.
function Get-MangoPointBundleApiBase([string]$Bundle) {
    # An explicit build setting takes precedence over an unused /api fallback.
    $setting = [regex]::Match($Bundle, '["'']?VITE_API_BASE["'']?\s*:\s*["'']([^"'']*)["'']')
    if ($setting.Success -and $setting.Groups[1].Value) { return $setting.Groups[1].Value.TrimEnd('/') }
    if ([regex]::IsMatch($Bundle, '["'']/api["'']')) { return '/api' }
    return [regex]::Match($Bundle, 'https://[a-z0-9-]+\.trycloudflare\.com').Value
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
