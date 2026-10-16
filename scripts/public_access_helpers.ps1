# Check the public path independently of this laptop's private Tailscale DNS.
function Get-MangoPointApiStatus([string]$Url) {
    if ($Url -match '^https://[a-z0-9-]+\.trycloudflare\.com$') {
        return Get-MangoPointPublicTunnelStatus $Url
    }
    try {
        $health = Invoke-RestMethod -Uri "$($Url.TrimEnd('/'))/health" -TimeoutSec 8 -Headers @{ 'Cache-Control' = 'no-cache' }
        if ($health.status -eq 'healthy' -and $health.database -eq 'connected') {
            return @{ ready = $true; kind = 'ready'; reason = '' }
        }
        if ($health.database -and $health.database -ne 'connected') {
            return @{ ready = $false; kind = 'database'; reason = 'The API reports a disconnected database.' }
        }
        return @{ ready = $false; kind = 'response'; reason = 'The route did not return healthy MangoPoint API/database JSON.' }
    } catch {
        $response = $_.Exception.Response
        $code = if ($response) { [int]$response.StatusCode } else { 0 }
        $gateway = if ($response) { "$($response.Headers['x-vercel-error'])" } else { '' }
        if ($gateway -notmatch '^[A-Z0-9_]+$') { $gateway = '' }
        $reason = if ($code) { "HTTP $code $gateway".Trim() } else { 'HTTPS connection or DNS lookup failed.' }
        return @{ ready = $false; kind = $(if ($code -in @(0, 502, 503, 504)) { 'transport' } else { 'response' }); reason = $reason }
    }
}

function Wait-MangoPointAccessStatus([scriptblock]$Probe, [int]$TimeoutSeconds = 15) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $result = & $Probe
        if ($result.ready -or $result.kind -ne 'transport') { return $result }
        if ((Get-Date) -ge $deadline) { return $result }
        Start-Sleep -Seconds 2
    } while ($true)
}

function Get-MangoPointPublicTunnelAddresses([string]$Url) {
    $hostName = ([uri]$Url).Host
    if ($Url -notmatch '^https://([a-z0-9-]+\.[a-z0-9-]+\.ts\.net|[a-z0-9-]+\.trycloudflare\.com)$') { throw 'Invalid public tunnel origin.' }
    $dns = Invoke-RestMethod -Uri "https://dns.google/resolve?name=$hostName&type=A" -TimeoutSec 5
    $addresses = @($dns.Answer | Where-Object { $_.type -eq 1 -and $_.data -match '^\d{1,3}(\.\d{1,3}){3}$' } | Select-Object -ExpandProperty data -Unique)
    if (-not $addresses.Count) { throw 'No public tunnel addresses.' }
    return $addresses
}

function Get-MangoPointPublicTunnelStatus([string]$Url) {
    $hostName = ([uri]$Url).Host
    try {
        # DNS over HTTPS avoids MagicDNS returning the device's private 100.x IP.
        $addresses = @(Get-MangoPointPublicTunnelAddresses $Url)
        foreach ($address in $addresses) {
            $previousPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = 'Continue'
                # --resolve changes only the destination IP; SNI, hostname and
                # certificate verification still use the original HTTPS URL.
                $output = @(& curl.exe --silent --show-error --fail --connect-timeout 5 --max-time 8 --resolve "${hostName}:443:$address" "$Url/health" 2>&1)
                $code = $LASTEXITCODE
            } finally { $ErrorActionPreference = $previousPreference }
            if ($code -ne 0) { throw 'Public relay HTTPS failed.' }
            $health = (($output | ForEach-Object { "$_" }) -join "`n") | ConvertFrom-Json
            if ($health.status -ne 'healthy' -or $health.database -ne 'connected') {
                return @{ ready = $false; kind = 'response'; reason = 'A public tunnel relay did not return healthy MangoPoint JSON.' }
            }
        }
        return @{ ready = $true; kind = 'ready'; reason = '' }
    } catch {
        return @{ ready = $false; kind = 'transport'; reason = 'Public tunnel HTTPS/DNS failed; private or stale local DNS access is insufficient.' }
    }
}

function Get-MangoPointPublicFunnelStatus([string]$Url) {
    if ($Url -notmatch '^https://[a-z0-9-]+\.[a-z0-9-]+\.ts\.net$') { throw 'Invalid public Funnel hostname.' }
    return Get-MangoPointPublicTunnelStatus $Url
}

function Assert-MangoPointPublicLoginCors([string]$Url, [string]$SiteUrl) {
    $hostName = ([uri]$Url).Host
    $addresses = @(Get-MangoPointPublicTunnelAddresses $Url)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& curl.exe --silent --show-error --fail --connect-timeout 5 --max-time 10 --resolve "${hostName}:443:$($addresses[0])" --request OPTIONS --header "Origin:$SiteUrl" --header 'Access-Control-Request-Method:POST' --header 'Access-Control-Request-Headers:content-type' --dump-header - --output NUL "$Url/auth/login" 2>&1)
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    $headers = ($output | ForEach-Object { "$_" }) -join "`n"
    if ($code -ne 0 -or $headers -notmatch ('(?im)^Access-Control-Allow-Origin:[ \t]*' + [regex]::Escape($SiteUrl) + '[ \t]*\r?$')) {
        throw 'The public backup does not allow this Vercel origin to access login. Check CORS_ORIGINS in the local API.'
    }
}

function Get-MangoPointBackupTunnel([string]$ProjectFolder, [bool]$CheckOnly) {
    $folder = Join-Path $ProjectFolder 'outputs\remote-access'
    $recordPath = Join-Path $folder 'backup-tunnel.json'
    if (Test-Path -LiteralPath $recordPath) {
        try {
            $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
            $existing = Get-Process -Id $record.processId -ErrorAction Stop
            $command = Get-CimInstance Win32_Process -Filter "ProcessId=$($existing.Id)"
            if ($record.version -eq 1 -and $record.url -match '^https://[a-z0-9-]+\.trycloudflare\.com$' -and
                $existing.ProcessName -eq 'cloudflared' -and
                $existing.StartTime.ToUniversalTime().ToString('o') -eq $record.startedAt -and
                $command.CommandLine -match '--url\s+"?http://127\.0\.0\.1:8000"?(\s|$)' -and
                (Get-MangoPointApiStatus $record.url).ready) {
                Write-Host '[OK] Reusing the verified MangoPoint backup tunnel.'
                return $record.url
            }
        } catch { }
    }
    if ($CheckOnly) { throw 'No healthy managed backup tunnel is available. Run .\start_production.bat to recover public access.' }
    $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cloudflared) { throw 'Public Tailscale access is unavailable. Install cloudflared for automatic backup, or repair the public Funnel connection.' }
    $executable = $cloudflared.Source
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $prefix = Join-Path $folder ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-backup-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    Write-Host '[INFO] Starting a Cloudflare backup for the MangoPoint API...'
    $process = Start-Process -FilePath $executable -ArgumentList @('tunnel', '--protocol', 'http2', '--url', 'http://127.0.0.1:8000') -WindowStyle Hidden -PassThru -RedirectStandardOutput "$prefix.stdout.log" -RedirectStandardError "$prefix.stderr.log"
    try {
        $deadline = (Get-Date).AddSeconds(60)
        do {
            $process.Refresh()
            if ($process.HasExited) { throw 'The backup tunnel exited. Check its logs in outputs/remote-access/.' }
            $log = if (Test-Path -LiteralPath "$prefix.stderr.log") { Get-Content -LiteralPath "$prefix.stderr.log" -Raw } else { '' }
            $url = [regex]::Match("$log", 'https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com').Value
            if ($url -and (Get-MangoPointApiStatus $url).ready) {
                $record = @{ version = 1; url = $url; processId = $process.Id; startedAt = $process.StartTime.ToUniversalTime().ToString('o') }
                [System.IO.File]::WriteAllText($recordPath, ($record | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
                return $url
            }
            Start-Sleep -Seconds 2
        } while ((Get-Date) -lt $deadline)
        throw 'Cloudflare backup public health verification failed. Check its logs in outputs/remote-access/ and public DNS/HTTPS connectivity.'
    } catch {
        # This is only the process created by this invocation, never another tunnel.
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
        throw
    }
}

function Confirm-MangoPointPublicAccess(
    [string]$Provider, [string]$PrimaryUrl, [string]$SiteUrl, [string]$ProjectFolder,
    [bool]$CheckOnly, [scriptblock]$PublishRoute, [scriptblock]$CheckBrowserAccess
) {
    $selectedUrl = $PrimaryUrl
    $reconnected = $false
    $usingBackup = $false
    while ($true) {
        $probe = {
            if ($Provider -eq 'tailscale' -and -not $usingBackup) { Get-MangoPointPublicFunnelStatus $selectedUrl }
            else { Get-MangoPointApiStatus $selectedUrl }
        }
        $result = if ($reconnected -and -not $usingBackup) { Wait-MangoPointAccessStatus -Probe $probe } else { & $probe }
        if ($result.ready) {
            & $CheckBrowserAccess $selectedUrl
            & $PublishRoute $selectedUrl
            $result = Wait-MangoPointAccessStatus -Probe { Get-MangoPointApiStatus "$SiteUrl/api" }
            if ($result.ready) {
                if ($usingBackup) { Write-Host '[WARN] Backup API connection is active. The shared website URL and saved Tailscale address are unchanged.' }
                else { Write-Host '[OK] Public API and deployed /api access are ready.' }
                return $selectedUrl
            }
        }
        if ($Provider -ne 'tailscale' -or $result.kind -ne 'transport' -or $usingBackup) {
            throw "Public API verification failed: $($result.reason) Endpoint: $SiteUrl/api/health"
        }
        if ($CheckOnly) {
            if ((Get-MangoPointApiStatus "$SiteUrl/api").ready) {
                $selectedUrl = Get-MangoPointBackupTunnel -ProjectFolder $ProjectFolder -CheckOnly $true
                $usingBackup = $true
                continue
            }
            throw "Local API access does not prove public Funnel access. $($result.reason) Run .\start_production.bat to recover; this read-only check changed nothing."
        }
        if (-not (Get-MangoPointApiStatus 'http://127.0.0.1:8000').ready) {
            throw 'The local API/database is not healthy; public tunnel recovery was stopped.'
        }
        if (-not $reconnected) {
            Restart-MangoPointTailscaleFunnel -ExpectedUrl $PrimaryUrl | Out-Null
            $reconnected = $true
            continue
        }
        Write-Host "[WARN] $($result.reason) Using a verified backup instead of repeating the failed connection."
        $selectedUrl = Get-MangoPointBackupTunnel -ProjectFolder $ProjectFolder -CheckOnly $false
        $usingBackup = $true
    }
}
