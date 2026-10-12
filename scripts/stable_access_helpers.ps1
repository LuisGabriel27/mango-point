# Stable public access without changing the API or authentication boundary.
function Get-MangoPointConnectionPlan([bool]$UseTailscale, [string]$PublicApiUrl, $SavedConnection) {
    if ($UseTailscale -and $PublicApiUrl) { throw 'Choose -UseTailscale or -PublicApiUrl, not both.' }
    if ($UseTailscale) { return @{ provider = 'tailscale'; publicApiUrl = $null } }
    if ($PublicApiUrl) { return @{ provider = 'external'; publicApiUrl = (ConvertTo-MangoPointPublicUrl $PublicApiUrl) } }
    if ($SavedConnection) {
        if ($SavedConnection.version -ne 1 -or $SavedConnection.provider -notin @('tailscale', 'external')) {
            throw 'The saved stable connection is invalid. Repair outputs/remote-access/connection.json; no temporary tunnel was selected.'
        }
        return @{ provider = $SavedConnection.provider; publicApiUrl = (ConvertTo-MangoPointPublicUrl $SavedConnection.publicApiUrl) }
    }
    return @{ provider = 'quick'; publicApiUrl = $null }
}

function ConvertTo-MangoPointPublicUrl([string]$Url) {
    $uri = $null
    if (-not [uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or $uri.IsLoopback -or $uri.UserInfo -or
        $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/' -or
        $uri.Host.EndsWith('.trycloudflare.com')) {
        throw 'Use a stable HTTPS origin without credentials, path, query or fragment. Quick Tunnel addresses cannot be saved as permanent connections.'
    }
    return $uri.GetLeftPart([UriPartial]::Authority)
}

function Get-MangoPointTailscaleExecutable {
    $command = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $installedPath = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    if (Test-Path -LiteralPath $installedPath) { return $installedPath }
    throw 'Install Tailscale on this server laptop, sign in, then run .\setup_stable_access.bat.'
}

function Invoke-MangoPointTailscale([string[]]$Arguments, [switch]$ShowProgress) {
    $executable = Get-MangoPointTailscaleExecutable
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($ShowProgress) {
            # First-time Funnel setup prints a browser approval link. Display it
            # directly so the server operator can complete setup; never save it.
            & $executable @Arguments | Out-Host
            $output = @()
        } else {
            $output = @(& $executable @Arguments 2>&1)
        }
        $exitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($exitCode -ne 0) {
        # Never echo status/auth output containing account details or auth URLs.
        throw 'Tailscale is not ready. Sign in to the Tailscale application and enable Funnel for this laptop, then retry.'
    }
    return ($output | ForEach-Object { "$_" }) -join "`n"
}

function Get-MangoPointTailscaleUrl($Status) {
    if ($Status.BackendState -ne 'Running' -or -not $Status.Self.Online -or -not $Status.Self.DNSName) {
        throw 'Tailscale needs an online, signed-in server device. Sign in to Tailscale on this laptop, then retry.'
    }
    if ($Status.Self.Expired -or $Status.Self.KeyExpiry) {
        throw 'Disable Key Expiry for this server laptop in https://login.tailscale.com/admin/machines before switching to stable access.'
    }
    $hostName = $Status.Self.DNSName.TrimEnd('.')
    if ($hostName -notmatch '^[a-z0-9-]+\.[a-z0-9-]+\.ts\.net$') { throw 'Tailscale did not provide a valid server DNS name.' }
    return "https://$hostName"
}

function Test-MangoPointTailscaleFunnel($Config, [string]$Url) {
    if (-not $Config -or -not $Config.Web -or -not $Config.AllowFunnel -or -not $Config.TCP) { return $false }
    $hostPort = ([uri]$Url).Host + ':443'
    $webProperty = $Config.Web.PSObject.Properties[$hostPort]
    if (-not $webProperty -or -not $webProperty.Value.Handlers) { return $false }
    $rootProperty = $webProperty.Value.Handlers.PSObject.Properties['/']
    $publicProperty = $Config.AllowFunnel.PSObject.Properties[$hostPort]
    $tlsProperty = $Config.TCP.PSObject.Properties['443']
    return $rootProperty -and $publicProperty -and $tlsProperty -and
        $publicProperty.Value -eq $true -and $tlsProperty.Value.HTTPS -eq $true -and
        $rootProperty.Value.Proxy -eq 'http://127.0.0.1:8000'
}

function Start-MangoPointTailscaleFunnel([bool]$CheckOnly, [string]$ExpectedUrl, [bool]$ConfigureUnattended) {
    $status = Invoke-MangoPointTailscale -Arguments @('status', '--json') | ConvertFrom-Json
    $url = Get-MangoPointTailscaleUrl $status
    if ($ExpectedUrl -and $ExpectedUrl -ne $url) {
        throw 'The Tailscale device name changed. Restore its saved DNS name or explicitly run setup_stable_access.bat to register the new name. No temporary tunnel was selected.'
    }
    $config = Invoke-MangoPointTailscale -Arguments @('funnel', 'status', '--json') | ConvertFrom-Json
    if (-not (Test-MangoPointTailscaleFunnel $config $url)) {
        if ($CheckOnly) { throw 'The stable Funnel is not forwarding to MangoPoint. Run setup_stable_access.bat.' }
        if ($config.Web -or $config.TCP -or $config.Foreground -or $config.Services -or $config.AllowFunnel) {
            throw 'Tailscale already shares another service. Review its Serve/Funnel configuration before using HTTPS port 443 for MangoPoint.'
        }
        Write-Host '[INFO] Enabling persistent HTTPS access to MangoPoint through Tailscale...'
        Invoke-MangoPointTailscale -Arguments @('funnel', '--bg', '--https=443', 'http://127.0.0.1:8000') -ShowProgress | Out-Null
        $config = Invoke-MangoPointTailscale -Arguments @('funnel', 'status', '--json') | ConvertFrom-Json
        if (-not (Test-MangoPointTailscaleFunnel $config $url)) { throw 'Tailscale did not enable the expected public MangoPoint Funnel.' }
    }
    if ($ConfigureUnattended -and -not $CheckOnly) {
        Invoke-MangoPointTailscale -Arguments @('set', '--unattended=true') | Out-Null
    }
    Write-Host "[OK] Stable HTTPS server address: $url"
    return $url
}
