"""Exercise production route planning and readiness without external writes."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="Windows startup helper")


def run_helper(code):
    helper = str(ROOT / "scripts" / "remote_access_helpers.ps1").replace("'", "''")
    stable_helper = str(ROOT / "scripts" / "stable_access_helpers.ps1").replace("'", "''")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
         f"$ErrorActionPreference='Stop'; . '{helper}'; . '{stable_helper}'; {code}"],
        capture_output=True, text=True, timeout=15, check=True,
    )
    return json.loads(result.stdout)


def test_new_tunnel_edits_route_and_same_tunnel_requires_no_publication():
    result = run_helper("""
        $state = [pscustomobject]@{
            version = @{ isStaging = $false }
            routes = @([pscustomobject]@{
                id = 'route-one'; name = 'MangoPoint API'; enabled = $true
                rawSrc = '^/api/(.*)$'; rawDest = 'https://old.trycloudflare.com/$1'
                route = @{ headers = @{ 'Cache-Control' = 'no-store' } }
            })
        }
        @(
            (Get-MangoPointRoutePlan $state 'https://new.trycloudflare.com/'),
            (Get-MangoPointRoutePlan $state 'https://old.trycloudflare.com')
        ) | ConvertTo-Json -Compress
    """)
    assert result[0] == {"action": "edit", "destination": "https://new.trycloudflare.com/$1", "id": "route-one"}
    assert result[1]["action"] == "none"


def test_first_start_adds_route_and_never_publishes_unrelated_staging():
    result = run_helper("""
        $new = Get-MangoPointRoutePlan ([pscustomobject]@{ routes = @(); version = $null }) 'https://api.example.test'
        try {
            Get-MangoPointRoutePlan ([pscustomobject]@{ routes = @(); version = @{ isStaging = $true } }) 'https://api.example.test' | Out-Null
            $blocked = $false
        } catch { $blocked = $true }
        @{ new = $new; blocked = $blocked } | ConvertTo-Json -Compress
    """)
    assert result["new"] == {"action": "add", "destination": "https://api.example.test/$1"}
    assert result["blocked"] is True


def test_database_disconnection_and_spa_html_cannot_pass_readiness():
    result = run_helper("""
        function Invoke-RestMethod { return $script:healthResponse }
        $script:healthResponse = @{ status = 'healthy'; database = 'error' }
        $disconnected = Test-MangoPointApiReady 'http://example.test'
        $script:healthResponse = '<html>SPA fallback</html>'
        $html = Test-MangoPointApiReady 'http://example.test'
        $script:healthResponse = @{ status = 'healthy'; database = 'connected' }
        $connected = Test-MangoPointApiReady 'http://example.test'
        @{ disconnected = $disconnected; html = $html; connected = $connected } | ConvertTo-Json -Compress
    """)
    assert result == {"disconnected": False, "html": False, "connected": True}


def test_readiness_wait_handles_initial_unavailability():
    result = run_helper("""
        $script:attempts = 0
        function Test-MangoPointApiReady { $script:attempts += 1; return $script:attempts -ge 3 }
        function Start-Sleep { }
        Wait-MangoPointApiReady 'http://example.test' -TimeoutSeconds 5
        @{ attempts = $script:attempts } | ConvertTo-Json -Compress
    """)
    assert result["attempts"] == 3


def test_published_api_response_shape_is_idempotent_and_staging_is_rejected():
    result = run_helper("""
        $state = [pscustomobject]@{
            version = @{ id = 'live-version' }
            hasStagingChanges = $false
            routes = @(@{
                id = 'route-one'; name = 'MangoPoint API'; enabled = $true
                route = @{ src = '/api/(.*)$'; dest = 'https://api.example.test/$1'; headers = @{ 'Cache-Control' = 'no-store' } }
            })
        }
        $plan = Get-MangoPointRoutePlan $state 'https://api.example.test'
        $state.hasStagingChanges = $true
        try { Get-MangoPointRoutePlan $state 'https://api.example.test' | Out-Null; $blocked = $false }
        catch { $blocked = $true }
        @{ plan = $plan; blocked = $blocked } | ConvertTo-Json -Compress
    """)
    assert result["plan"]["action"] == "none"
    assert result["blocked"] is True


def test_unused_api_fallback_cannot_hide_an_explicit_stale_build_setting():
    result = run_helper("""
        @{
            stale = Get-MangoPointBundleApiBase '{VITE_API_BASE:"https://old.trycloudflare.com"},fallback="/api";'
            current = Get-MangoPointBundleApiBase '{VITE_API_BASE:"/api"}'
            default = Get-MangoPointBundleApiBase 'fallback="/api";'
        } | ConvertTo-Json -Compress
    """)
    assert result == {"stale": "https://old.trycloudflare.com", "current": "/api", "default": "/api"}


def test_saved_stable_address_is_reused_and_invalid_settings_cannot_fall_back():
    result = run_helper("""
        $saved = [pscustomobject]@{ version = 1; provider = 'tailscale'; publicApiUrl = 'https://server.tail123.ts.net/' }
        $remembered = Get-MangoPointConnectionPlan -SavedConnection $saved
        $explicit = Get-MangoPointConnectionPlan -PublicApiUrl 'https://api.example.test/' -SavedConnection $saved
        $fresh = Get-MangoPointConnectionPlan -UseTailscale $true -SavedConnection $saved
        $saved.version = 2
        try { Get-MangoPointConnectionPlan -SavedConnection $saved | Out-Null; $blocked = $false }
        catch { $blocked = $true }
        @{ remembered = $remembered; explicit = $explicit; fresh = $fresh; blocked = $blocked } | ConvertTo-Json -Compress
    """)
    assert result["remembered"] == {"provider": "tailscale", "publicApiUrl": "https://server.tail123.ts.net"}
    assert result["explicit"] == {"provider": "external", "publicApiUrl": "https://api.example.test"}
    assert result["fresh"] == {"provider": "tailscale", "publicApiUrl": None}
    assert result["blocked"] is True


@pytest.mark.parametrize("url", [
    "http://api.example.test", "https://localhost", "https://127.0.0.1",
    "https://user:secret@api.example.test", "https://api.example.test/api",
    "https://api.example.test/?token=secret", "https://api.example.test/#fragment",
    "https://temporary.trycloudflare.com", "not-an-address",
])
def test_stable_url_rejects_temporary_addresses_and_credential_or_path_settings(url):
    result = run_helper(f"""
        try {{ ConvertTo-MangoPointPublicUrl '{url}' | Out-Null; $blocked = $false }}
        catch {{ $blocked = $true }}
        @{{ blocked = $blocked }} | ConvertTo-Json -Compress
    """)
    assert result["blocked"] is True


def test_tailscale_readiness_requires_online_device_and_no_key_expiry():
    result = run_helper("""
        $states = @(
            @{ BackendState = 'NeedsLogin'; Self = $null },
            @{ BackendState = 'Running'; Self = @{ Online = $false; DNSName = 'server.tail123.ts.net.' } },
            @{ BackendState = 'Running'; Self = @{ Online = $true; DNSName = 'server.tail123.ts.net.'; KeyExpiry = '2027-04-01T00:00:00Z' } },
            @{ BackendState = 'Running'; Self = @{ Online = $true; DNSName = 'server.tail123.ts.net.'; Expired = $true } },
            @{ BackendState = 'Running'; Self = @{ Online = $true; DNSName = 'server.tail123.ts.net.' } }
        )
        @($states | ForEach-Object {
            try { @{ ready = $true; url = (Get-MangoPointTailscaleUrl $_) } }
            catch { @{ ready = $false } }
        }) | ConvertTo-Json -Compress
    """)
    assert [state["ready"] for state in result] == [False, False, False, False, True]
    assert result[4]["url"] == "https://server.tail123.ts.net"


FUNNEL_MOCK = """
    $script:statusJson = '{"BackendState":"Running","Self":{"Online":true,"DNSName":"server.tail123.ts.net."}}'
    $script:readyJson = '{"TCP":{"443":{"HTTPS":true}},"Web":{"server.tail123.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8000"}}}},"AllowFunnel":{"server.tail123.ts.net:443":true}}'
    $script:configJson = $script:readyJson
    $script:writes = @()
    function Invoke-MangoPointTailscale([string[]]$Arguments, [switch]$ShowProgress) {
        if ($Arguments[0] -eq 'status') { return $script:statusJson }
        if ($Arguments[0] -eq 'funnel' -and $Arguments[1] -eq 'status') { return $script:configJson }
        $script:writes += ($Arguments -join ' ')
        if ($Arguments[0] -eq 'funnel') { $script:configJson = $script:readyJson }
    }
"""


def test_stable_funnel_reuse_and_read_only_checks_never_reconfigure_it():
    result = run_helper(FUNNEL_MOCK + """
        $url = Start-MangoPointTailscaleFunnel -CheckOnly $true -ExpectedUrl 'https://server.tail123.ts.net' 6>$null
        $script:configJson = '{}'
        try { Start-MangoPointTailscaleFunnel -CheckOnly $true 6>$null | Out-Null; $blocked = $false }
        catch { $blocked = $true }
        @{ url = $url; blocked = $blocked; writes = @($script:writes) } | ConvertTo-Json -Compress
    """)
    assert result == {"url": "https://server.tail123.ts.net", "blocked": True, "writes": []}


def test_stable_funnel_creation_persists_background_mapping_and_unattended_mode():
    result = run_helper(FUNNEL_MOCK + """
        $script:configJson = '{}'
        $url = Start-MangoPointTailscaleFunnel -ConfigureUnattended $true 6>$null
        @{ url = $url; writes = @($script:writes) } | ConvertTo-Json -Compress
    """)
    assert result["url"] == "https://server.tail123.ts.net"
    assert result["writes"] == [
        "funnel --bg --https=443 http://127.0.0.1:8000", "set --unattended=true",
    ]


def test_changed_hostname_and_other_services_cannot_be_silently_replaced():
    result = run_helper(FUNNEL_MOCK + """
        try { Start-MangoPointTailscaleFunnel -ExpectedUrl 'https://old.tail123.ts.net' 6>$null | Out-Null; $renamed = $false }
        catch { $renamed = $true }
        $script:configJson = '{"TCP":{"443":{"HTTPS":true}},"Web":{"server.tail123.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:3000"}}}}}'
        try { Start-MangoPointTailscaleFunnel 6>$null | Out-Null; $otherService = $false }
        catch { $otherService = $true }
        $script:configJson = '{"Services":{"svc:existing":{"TCP":{"443":{"HTTPS":true}}}}}'
        try { Start-MangoPointTailscaleFunnel 6>$null | Out-Null; $namedService = $false }
        catch { $namedService = $true }
        @{ renamed = $renamed; otherService = $otherService; namedService = $namedService; writes = @($script:writes) } | ConvertTo-Json -Compress
    """)
    assert result == {"renamed": True, "otherService": True, "namedService": True, "writes": []}


def test_funnel_requires_public_https_mapping_and_never_accepts_foreground_config():
    result = run_helper(FUNNEL_MOCK + """
        $private = $script:readyJson | ConvertFrom-Json
        $private.AllowFunnel.'server.tail123.ts.net:443' = $false
        $plain = $script:readyJson | ConvertFrom-Json
        $plain.TCP.'443'.HTTPS = $false
        $foreground = [pscustomobject]@{ Foreground = @{ session = ($script:readyJson | ConvertFrom-Json) } }
        @{
            private = Test-MangoPointTailscaleFunnel $private 'https://server.tail123.ts.net'
            plain = Test-MangoPointTailscaleFunnel $plain 'https://server.tail123.ts.net'
            foreground = Test-MangoPointTailscaleFunnel $foreground 'https://server.tail123.ts.net'
            missing = Test-MangoPointTailscaleFunnel ([pscustomobject]@{}) 'https://server.tail123.ts.net'
        } | ConvertTo-Json -Compress
    """)
    assert result == {"private": False, "plain": False, "foreground": False, "missing": False}
