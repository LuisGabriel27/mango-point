function Get-MangoPointCompanionStartArgs([bool]$Prepare) {
    $arguments = @('compose', 'up', '-d', '--wait', '--wait-timeout', '120')
    if ($Prepare) { return $arguments + @('--build') }
    return $arguments + @('--no-build', '--pull', 'never')
}

function Add-MangoPointCompanionOrigin([string]$EnvPath, [string]$SiteUrl) {
    if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
        throw 'This laptop has no .env file. Create its local configuration before repairing CORS.'
    }
    $contents = [System.IO.File]::ReadAllText($EnvPath)
    $lines = [regex]::Matches($contents, '(?im)^[ \t]*(?:export[ \t]+)?CORS_ORIGINS[ \t]*=[^\r\n]*')
    if ($lines.Count -gt 1) { throw 'Multiple CORS_ORIGINS definitions exist. Keep one valid definition in .env, then retry.' }
    $origins = @('http://localhost:3000', 'http://127.0.0.1:3000', 'http://localhost:5173', 'http://127.0.0.1:5173')
    $comment = ''
    if ($lines.Count -eq 1) {
        $parts = [regex]::Match($lines[0].Value, '^(?<prefix>[^=]*=)(?<value>.*)$')
        $value = $parts.Groups['value'].Value.Trim()
        $commentMatch = [regex]::Match($value, '[ \t]+#.*$')
        if ($commentMatch.Success) {
            $comment = $commentMatch.Value
            $value = $value.Substring(0, $commentMatch.Index).Trim()
        }
        if ($value.Length -ge 2 -and ($value[0] -eq [char]39 -or $value[0] -eq [char]34) -and $value[0] -eq $value[$value.Length - 1]) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($value.StartsWith('[')) {
            try {
                $parsed = ConvertFrom-Json -InputObject ('{"origins":' + $value + '}') -ErrorAction Stop
                $origins = @($parsed.origins)
            } catch { throw 'CORS_ORIGINS is not a valid JSON array. Correct that setting before retrying; .env was not changed.' }
        } else {
            $origins = @($value.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        }
        if (@($origins | Where-Object { $_ -isnot [string] }).Count) {
            throw 'CORS_ORIGINS must contain only origin strings; .env was not changed.'
        }
    }
    if ($origins -ccontains $SiteUrl) { return $false }
    $json = ConvertTo-Json -InputObject @($origins + $SiteUrl) -Compress
    if ($lines.Count -eq 1) {
        $replacement = $parts.Groups['prefix'].Value + $json + $comment
        $updated = $contents.Substring(0, $lines[0].Index) + $replacement + $contents.Substring($lines[0].Index + $lines[0].Length)
    } else {
        $newline = if ($contents.Contains("`r`n")) { "`r`n" } else { "`n" }
        $separator = if ($contents -and -not $contents.EndsWith("`n")) { $newline } else { '' }
        $updated = $contents + $separator + 'CORS_ORIGINS=' + $json + $newline
    }
    $backupDirectory = Join-Path (Split-Path $EnvPath -Parent) 'outputs/offline-companion'
    [System.IO.Directory]::CreateDirectory($backupDirectory) | Out-Null
    $backupPath = Join-Path $backupDirectory ('.env-before-cors-' + [guid]::NewGuid().ToString('N'))
    [System.IO.File]::Copy($EnvPath, $backupPath, $false)
    $bytes = [System.IO.File]::ReadAllBytes($EnvPath)
    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191
    [System.IO.File]::WriteAllText($EnvPath, $updated, (New-Object System.Text.UTF8Encoding($hasBom)))
    return $true
}

function Assert-MangoPointCompanionBrowserAccess([string]$ApiUrl, [string]$SiteUrl) {
    $message = 'The local API does not allow the deployed MangoPoint site. For this project''s running Docker API, run start_offline_companion.bat -RepairCors. Or add https://mango-point-projects.vercel.app to CORS_ORIGINS in this laptop''s .env, preserving its other origins, then recreate the API container: docker compose up -d --no-build --pull never --force-recreate api. If the API runs outside Docker, restart that API instead.'
    try {
        $health = Invoke-WebRequest -UseBasicParsing -Uri "$ApiUrl/health" -Headers @{ Origin = $SiteUrl } -TimeoutSec 5
        $login = Invoke-WebRequest -UseBasicParsing -Method Options -Uri "$ApiUrl/auth/login" -Headers @{
            Origin = $SiteUrl
            'Access-Control-Request-Method' = 'POST'
            'Access-Control-Request-Headers' = 'authorization,content-type'
        } -TimeoutSec 5
    } catch { throw $message }
    if ($health.Headers['Access-Control-Allow-Origin'] -ne $SiteUrl -or
        $login.Headers['Access-Control-Allow-Origin'] -ne $SiteUrl -or
        $login.StatusCode -ne 200) { throw $message }
}
