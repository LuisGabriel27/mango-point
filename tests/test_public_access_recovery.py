"""Isolated public-transport recovery; no real tunnels, routes or farm writes."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PS = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(not PS, reason="Windows production launcher")


def run_ps(code):
    imports = "; ".join(
        ". '" + str(ROOT / "scripts" / name).replace("'", "''") + "'"
        for name in ("remote_access_helpers.ps1", "stable_access_helpers.ps1", "public_access_helpers.ps1")
    )
    result = subprocess.run(
        [PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
         "$ErrorActionPreference='Stop'; " + imports + "; " + code],
        capture_output=True, text=True, timeout=15, check=True,
    )
    return json.loads(result.stdout)


FUNNEL = r'''
    $script:events = @()
    $script:config = '{"TCP":{"443":{"HTTPS":true}},"Web":{"server.tail123.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8000"}}}},"AllowFunnel":{"server.tail123.ts.net:443":true}}' | ConvertFrom-Json
    $script:disableFails = $false
    function Invoke-MangoPointTailscale([string[]]$Arguments) {
        if ($Arguments[0] -eq 'status') { return '{"BackendState":"Running","Self":{"Online":true,"DNSName":"server.tail123.ts.net."}}' }
        if ($Arguments[1] -eq 'status') { return ($script:config | ConvertTo-Json -Depth 8 -Compress) }
        $script:events += ($Arguments -join ' ')
        if ($Arguments[-1] -eq 'off' -and $script:disableFails) { throw 'Fixture disable failure' }
    }
'''


@pytest.mark.parametrize("disable_fails", [False, True])
def test_funnel_reconnect_restores_the_mapping_even_if_disable_reports_failure(disable_fails):
    result = run_ps(FUNNEL + f'''
        $script:disableFails = ${str(disable_fails).lower()}
        try {{ $url = Restart-MangoPointTailscaleFunnel 'https://server.tail123.ts.net' 6>$null; $blocked = $false }}
        catch {{ $blocked = $true }}
        @{{ events = @($script:events); blocked = $blocked }} | ConvertTo-Json -Compress
    ''')
    assert result["events"] == [
        "funnel --bg --https=443 off",
        "funnel --bg --https=443 http://127.0.0.1:8000",
    ]
    assert result["blocked"] is disable_fails


@pytest.mark.parametrize("change", [
    "$script:config.Web.'server.tail123.ts.net:443'.Handlers | Add-Member '/other' @{Proxy='http://127.0.0.1:3000'}",
    "$script:config.TCP | Add-Member '8443' @{HTTPS=$true}",
    "$script:config | Add-Member 'Services' @{other=@{}}",
    "$script:config.Web.'server.tail123.ts.net:443'.Handlers.'/'.Proxy = 'http://127.0.0.1:3000'",
])
def test_reconnect_does_not_replace_other_services(change):
    result = run_ps(FUNNEL + change + r'''
        try { Restart-MangoPointTailscaleFunnel 'https://server.tail123.ts.net' | Out-Null; $blocked=$false }
        catch { $blocked=$true }
        @{blocked=$blocked; events=@($script:events)} | ConvertTo-Json -Compress
    ''')
    assert result == {"blocked": True, "events": []}


@pytest.mark.parametrize("healthy", [True, False])
def test_public_funnel_probe_uses_public_dns_and_keeps_tls_verification(healthy):
    result = run_ps(f'''
        $script:curlArgs = @()
        function Invoke-RestMethod {{ return ('{{"Answer":[{{"type":1,"data":"203.0.113.8"}},{{"type":1,"data":"203.0.113.9"}}]}}' | ConvertFrom-Json) }}
        function curl.exe {{
            $script:curlArgs += ,@($args)
            $global:LASTEXITCODE = {0 if healthy else 35}
            '{{"status":"healthy","database":"connected"}}'
        }}
        $probe = Get-MangoPointPublicFunnelStatus 'https://server.tail123.ts.net'
        @{{probe=$probe; calls=@($script:curlArgs)}} | ConvertTo-Json -Depth 6 -Compress
    ''')
    assert result["probe"]["ready"] is healthy
    assert len(result["calls"]) == (2 if healthy else 1)
    for index, arguments in enumerate(result["calls"]):
        assert arguments[arguments.index("--resolve") + 1] == f"server.tail123.ts.net:443:203.0.113.{8 + index}"
        assert arguments[-1] == "https://server.tail123.ts.net/health"
        assert "--insecure" not in arguments and "-k" not in arguments


@pytest.mark.parametrize("health,kind", [
    ({"status": "healthy", "database": "connected"}, "ready"),
    ({"status": "healthy", "database": "error"}, "database"),
    ("<html>SPA fallback</html>", "response"),
])
def test_public_health_requires_api_json_and_a_connected_database(health, kind):
    value = json.dumps(health).replace("'", "''")
    result = run_ps(f'''
        function Invoke-RestMethod {{ return ('{value}' | ConvertFrom-Json) }}
        Get-MangoPointApiStatus 'https://app.example.test/api' | ConvertTo-Json -Compress
    ''')
    assert result["kind"] == kind
    assert result["ready"] is (kind == "ready")


def test_quick_tunnel_health_avoids_the_stale_system_dns_path():
    result = run_ps(r'''
        function Get-MangoPointPublicTunnelStatus([string]$Url) { @{ready=$true;kind='ready';reason=$Url} }
        function Invoke-RestMethod { throw 'The system resolver must not be used for this new backup hostname' }
        Get-MangoPointApiStatus 'https://backup.trycloudflare.com' | ConvertTo-Json -Compress
    ''')
    assert result["ready"] is True
    assert result["reason"] == "https://backup.trycloudflare.com"


@pytest.mark.parametrize("origin,exit_code,accepted", [
    ("https://mango-point-projects.vercel.app", 0, True),
    ("https://unrelated.example.test", 0, False),
    ("https://mango-point-projects.vercel.app", 35, False),
])
def test_backup_login_checks_real_origin_and_preserves_hostname_verification(origin, exit_code, accepted):
    result = run_ps(f'''
        function Get-MangoPointPublicTunnelAddresses {{ @('203.0.113.8') }}
        $script:arguments=@()
        function curl.exe {{
            $script:arguments=@($args); $global:LASTEXITCODE={exit_code}
            'HTTP/1.1 200 OK'
            'Access-Control-Allow-Origin: {origin}'
        }}
        try {{ Assert-MangoPointPublicLoginCors 'https://backup.trycloudflare.com' 'https://mango-point-projects.vercel.app'; $accepted=$true }}
        catch {{ $accepted=$false }}
        @{{accepted=$accepted;arguments=$script:arguments}} | ConvertTo-Json -Compress
    ''')
    assert result["accepted"] is accepted
    assert "--insecure" not in result["arguments"]
    assert "backup.trycloudflare.com:443:203.0.113.8" in result["arguments"]
    assert "Origin:https://mango-point-projects.vercel.app" in result["arguments"]


RECOVERY = r'''
    $script:events=@(); $script:primaryReady=$false; $script:deployedReady=$false
    $script:localReady=$true; $script:recoverPrimary=$false; $script:backupReady=$true
    $script:rejectPrimary=$false; $script:primaryKind='transport'
    function Get-MangoPointPublicFunnelStatus {
        @{ready=$script:primaryReady;kind=$(if ($script:primaryReady) {'ready'} else {$script:primaryKind});reason='Fixture public TLS failure'}
    }
    function Get-MangoPointApiStatus([string]$Url) {
        $ready = switch ($Url) {
            'http://127.0.0.1:8000' {$script:localReady}
            'https://backup.trycloudflare.com' {$script:backupReady}
            default {$script:deployedReady}
        }
        @{ready=$ready;kind=$(if ($ready) {'ready'} else {'transport'});reason='HTTP 502 ROUTER_EXTERNAL_TARGET_HANDSHAKE_ERROR'}
    }
    function Wait-MangoPointAccessStatus([scriptblock]$Probe) { & $Probe }
    function Restart-MangoPointTailscaleFunnel {
        $script:events += 'reconnect'; $script:primaryReady=$script:recoverPrimary
    }
    function Get-MangoPointBackupTunnel([string]$ProjectFolder,[bool]$CheckOnly) {
        $script:events += $(if ($CheckOnly) {'read-backup'} else {'start-backup'})
        return 'https://backup.trycloudflare.com'
    }
    $publish = { param($url)
        $script:events += "publish:$url"
        $script:deployedReady = if ($url -eq 'https://backup.trycloudflare.com') {$script:backupReady} else {$script:primaryReady -and -not $script:rejectPrimary}
    }
    $browser = { param($url) $script:events += "cors:$url" }
'''


def recover_result(extra="", check_only=False):
    return run_ps(RECOVERY + extra + f'''
        try {{
            $url=Confirm-MangoPointPublicAccess -Provider tailscale -PrimaryUrl 'https://server.tail123.ts.net' -SiteUrl 'https://app.example.test' -ProjectFolder '.' -CheckOnly ${str(check_only).lower()} -PublishRoute $publish -CheckBrowserAccess $browser 6>$null
            $blocked=$false; $message=''
        }} catch {{ $blocked=$true; $message=$_.Exception.Message }}
        @{{url=$url;blocked=$blocked;message=$message;events=@($script:events)}} | ConvertTo-Json -Compress
    ''')


def test_failed_public_funnel_reconnects_once_then_publishes_only_healthy_backup():
    result = recover_result()
    assert result["blocked"] is False
    assert result["url"] == "https://backup.trycloudflare.com"
    assert result["events"] == ["reconnect", "start-backup", "cors:https://backup.trycloudflare.com",
                                "publish:https://backup.trycloudflare.com"]


def test_recovered_primary_avoids_backup_and_returns_to_saved_stable_address():
    result = recover_result("$script:recoverPrimary=$true;")
    assert result["url"] == "https://server.tail123.ts.net"
    assert result["events"] == ["reconnect", "cors:https://server.tail123.ts.net", "publish:https://server.tail123.ts.net"]


def test_healthy_primary_never_restarts_a_tunnel():
    result = recover_result("$script:primaryReady=$true;")
    assert result["events"] == ["cors:https://server.tail123.ts.net", "publish:https://server.tail123.ts.net"]


def test_vercel_failure_after_a_successful_public_probe_also_uses_bounded_recovery():
    result = recover_result("$script:primaryReady=$true; $script:recoverPrimary=$true; $script:rejectPrimary=$true;")
    assert result["blocked"] is False
    assert result["events"].count("reconnect") == 1
    assert result["events"][-1] == "publish:https://backup.trycloudflare.com"


@pytest.mark.parametrize("extra", ["$script:localReady=$false;", "$script:primaryKind='database';"])
def test_local_database_and_response_failures_do_not_trigger_tunnel_recovery(extra):
    result = recover_result(extra)
    assert result["blocked"] is True
    assert result["events"] == []


def test_check_only_reports_failure_without_restarting_or_publishing():
    result = recover_result(check_only=True)
    assert result["blocked"] is True
    assert result["events"] == []
    assert "read-only" in result["message"]


def test_check_only_accepts_an_existing_healthy_managed_backup_without_starting_one():
    result = recover_result("$script:deployedReady=$true;", check_only=True)
    assert result["blocked"] is False
    assert result["events"] == ["read-backup", "cors:https://backup.trycloudflare.com", "publish:https://backup.trycloudflare.com"]


def test_failed_backup_is_not_published_and_recovery_does_not_loop():
    result = recover_result("$script:backupReady=$false;")
    assert result["blocked"] is True
    assert result["events"] == ["reconnect", "start-backup"]


@pytest.mark.parametrize("wrong_owner", [False, True])
def test_only_the_recorded_mangopoint_backup_process_is_reused(tmp_path, wrong_owner):
    folder = str(tmp_path).replace("'", "''")
    result = run_ps(f'''
        $folder='{folder}'; New-Item -ItemType Directory -Path "$folder/outputs/remote-access" -Force | Out-Null
        $started=[datetime]::UtcNow
        @{{version=1;url='https://backup.trycloudflare.com';processId=123;startedAt=$started.ToString('o')}} | ConvertTo-Json | Set-Content "$folder/outputs/remote-access/backup-tunnel.json"
        function Get-Process {{ @{{Id=123;ProcessName='cloudflared';StartTime=$started}} }}
        function Get-CimInstance {{ @{{CommandLine='cloudflared tunnel --url http://127.0.0.1:{3000 if wrong_owner else 8000}'}} }}
        function Get-MangoPointApiStatus {{ @{{ready=$true}} }}
        function Start-Process {{ throw 'Must not start a process in CheckOnly' }}
        try {{ $url=Get-MangoPointBackupTunnel $folder $true 6>$null; $blocked=$false }} catch {{ $blocked=$true }}
        @{{url=$url;blocked=$blocked}} | ConvertTo-Json -Compress
    ''')
    assert result["blocked"] is wrong_owner
    if not wrong_owner:
        assert result["url"] == "https://backup.trycloudflare.com"
