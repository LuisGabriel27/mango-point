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


def write_vercel_link(path, project_id="prj_main", project_name="mango-point"):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"projectId": project_id, "orgId": "team_test", "projectName": project_name}
    path.write_text(json.dumps(data))
    return data


def test_frontend_vercel_link_takes_precedence_over_another_root_project(tmp_path):
    expected = write_vercel_link(tmp_path / "frontend/.vercel/project.json", "prj_frontend")
    write_vercel_link(tmp_path / ".vercel/project.json", "prj_other", "mangopoint-access")
    folder = str(tmp_path).replace("'", "''")
    assert run_helper(f"Get-MangoPointVercelLink '{folder}' | ConvertTo-Json -Compress") == expected


def test_missing_frontend_link_reuses_root_metadata_without_writing(tmp_path):
    link_path = tmp_path / ".vercel/project.json"
    expected = write_vercel_link(link_path)
    before = link_path.read_bytes()
    folder = str(tmp_path).replace("'", "''")
    assert run_helper(f"Get-MangoPointVercelLink '{folder}' | ConvertTo-Json -Compress") == expected
    assert not (tmp_path / "frontend").exists()
    assert link_path.read_bytes() == before


def test_missing_vercel_links_explain_how_to_restore_the_existing_project(tmp_path):
    folder = str(tmp_path).replace("'", "''")
    result = run_helper(f"""
        try {{ Get-MangoPointVercelLink '{folder}' | Out-Null; $blocked = $false; $message = '' }}
        catch {{ $blocked = $true; $message = $_.Exception.Message }}
        @{{ blocked = $blocked; message = $message }} | ConvertTo-Json -Compress
    """)
    assert result["blocked"] is True
    assert "link --cwd frontend --project mango-point --yes" in result["message"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("contents", [
    "{bad-json",
    json.dumps({"projectId": "prj_main", "projectName": "mango-point"}),
    json.dumps({"projectId": "prj_other", "orgId": "team_test", "projectName": "mangopoint-access"}),
])
def test_invalid_frontend_links_fail_without_silently_selecting_the_root(tmp_path, contents):
    link_path = tmp_path / "frontend/.vercel/project.json"
    link_path.parent.mkdir(parents=True)
    link_path.write_text(contents)
    write_vercel_link(tmp_path / ".vercel/project.json")
    folder = str(tmp_path).replace("'", "''")
    result = run_helper(f"""
        try {{ Get-MangoPointVercelLink '{folder}' | Out-Null; $blocked = $false }}
        catch {{ $blocked = $true }}
        @{{ blocked = $blocked }} | ConvertTo-Json -Compress
    """)
    assert result == {"blocked": True}
    assert link_path.read_text() == contents


def test_missing_link_stops_production_startup_before_starting_services(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for filename in ("start_remote_access.ps1", "remote_access_helpers.ps1"):
        shutil.copyfile(ROOT / "scripts" / filename, scripts / filename)
    (scripts / "stable_access_helpers.ps1").write_text("")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(scripts / "start_remote_access.ps1"), "-StartServer"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 1
    assert "link --cwd frontend --project mango-point --yes" in result.stdout
    assert "Checking the local API and database" not in result.stdout
    assert not (tmp_path / "outputs").exists()


@pytest.mark.parametrize("link_folder", ["frontend", "root"])
@pytest.mark.parametrize("arguments", [
    ["env", "update", "VITE_API_BASE", "production", "--value", "/api", "--yes"],
    ["api", "/v1/projects/prj_main/routes?teamId=team_test"],
    ["--prod", "--yes", "--force", "--json"],
])
def test_vercel_calls_use_frontend_and_validated_ids_despite_root_bom_and_other_context(
    tmp_path, link_folder, arguments,
):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    root_link = tmp_path / ".vercel/project.json"
    if link_folder == "frontend":
        write_vercel_link(frontend / ".vercel/project.json")
        write_vercel_link(root_link, "prj_other", "mangopoint-access")
    else:
        write_vercel_link(root_link)
    root_link.write_bytes(b"\xef\xbb\xbf" + root_link.read_bytes())
    original_link = root_link.read_bytes()
    folder = str(tmp_path).replace("'", "''")
    working_folder = str(frontend).replace("'", "''")
    ps_arguments = ",".join(f"'{argument}'" for argument in arguments)
    result = run_helper(f"""
        $env:VERCEL_ORG_ID = 'team_other'
        $env:VERCEL_PROJECT_ID = 'prj_other'
        $script:vercelCalls = @()
        function npx.cmd {{
            $script:vercelCalls += @{{
                arguments = @($args); orgId = $env:VERCEL_ORG_ID;
                projectId = $env:VERCEL_PROJECT_ID
            }}
            $global:LASTEXITCODE = 0
            'Fixture Vercel success'
        }}
        Push-Location '{folder}'
        try {{
            $link = Get-MangoPointVercelLink '{folder}'
            $output = Invoke-MangoPointVercel -VercelArgs @({ps_arguments}) -ProjectLink $link -WorkingDirectory '{working_folder}'
            @{{
                output = $output; calls = @($script:vercelCalls);
                restoredOrg = $env:VERCEL_ORG_ID; restoredProject = $env:VERCEL_PROJECT_ID;
                restoredFolder = (Get-Location).Path; restoredPreference = "$ErrorActionPreference"
            }} | ConvertTo-Json -Depth 5 -Compress
        }} finally {{ Pop-Location }}
    """)
    assert result["output"] == "Fixture Vercel success"
    assert result["calls"] == [{
        "arguments": ["--yes", "vercel@63.1.2", *arguments, "--cwd", str(frontend),
                      "--scope", "team_test", "--non-interactive", "--no-color"],
        "orgId": "team_test", "projectId": "prj_main",
    }]
    assert result["restoredOrg"] == "team_other"
    assert result["restoredProject"] == "prj_other"
    assert result["restoredFolder"] == str(tmp_path)
    assert result["restoredPreference"] == "Stop"
    assert root_link.read_bytes() == original_link


@pytest.mark.parametrize("existing_context", [True, False])
def test_failed_vercel_command_restores_environment_and_reports_failure(existing_context):
    result = run_helper(f"""
        $env:VERCEL_ORG_ID = {'"team_other"' if existing_context else '$null'}
        $env:VERCEL_PROJECT_ID = {'"prj_other"' if existing_context else '$null'}
        function npx.cmd {{
            $global:LASTEXITCODE = 1
            'Fixture Vercel failure'
        }}
        $link = @{{ projectId = 'prj_main'; orgId = 'team_test'; projectName = 'mango-point' }}
        try {{
            Invoke-MangoPointVercel -VercelArgs @('env', 'ls') -ProjectLink $link -WorkingDirectory '.' | Out-Null
            $blocked = $false; $message = ''
        }} catch {{ $blocked = $true; $message = $_.Exception.Message }}
        @{{
            blocked = $blocked; message = $message;
            orgId = $env:VERCEL_ORG_ID; projectId = $env:VERCEL_PROJECT_ID;
            preference = "$ErrorActionPreference"
        }} | ConvertTo-Json -Compress
    """)
    assert result["blocked"] is True
    assert "Vercel command failed. Fixture Vercel failure" in result["message"]
    assert result["orgId"] == ("team_other" if existing_context else None)
    assert result["projectId"] == ("prj_other" if existing_context else None)
    assert result["preference"] == "Stop"


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


def test_unchanged_release_reuses_api_base_but_still_fetches_live_html(tmp_path):
    cache = str(tmp_path / 'frontend-check.json').replace("'", "''")
    result = run_helper(f"""
        $script:requests = @()
        $script:progress = @()
        function Invoke-WebRequest {{
            param($Uri)
            $script:requests += $Uri
            $script:progress += "$ProgressPreference"
            return @{{ Content = '<script src="/assets/index-current.js"></script>' }}
        }}
        function Get-MangoPointBundleText {{
            param($Url)
            $script:requests += $Url
            $script:progress += "$ProgressPreference"
            return '{{VITE_API_BASE:"/api"}}'
        }}
        $first = Get-MangoPointLiveApiBase 'https://app.example.test' '{cache}' $false $false 6>$null
        $second = Get-MangoPointLiveApiBase 'https://app.example.test' '{cache}' $false $false 6>$null
        @{{ first = $first; second = $second; requests = $script:requests; progress = $script:progress }} | ConvertTo-Json -Compress
    """)
    assert result['first'] == result['second'] == '/api'
    assert len(result['requests']) == 3
    assert 'connection_check=' in result['requests'][0]
    assert result['requests'][1].endswith('/assets/index-current.js')
    assert 'connection_check=' in result['requests'][2]
    assert result['progress'] == ['SilentlyContinue'] * 3
    saved = json.loads((tmp_path / 'frontend-check.json').read_text(encoding='utf-8-sig'))
    assert saved == {
        'version': 1, 'siteUrl': 'https://app.example.test',
        'assetUrl': 'https://app.example.test/assets/index-current.js', 'apiBase': '/api',
    }


@pytest.mark.parametrize('reason', ['release-changed', 'site-changed', 'refresh'])
def test_changed_release_site_or_explicit_refresh_cannot_reuse_cache(tmp_path, reason):
    cache_file = tmp_path / 'frontend-check.json'
    cache_file.write_text(json.dumps({
        'version': 1,
        'siteUrl': 'https://other.example.test' if reason == 'site-changed' else 'https://app.example.test',
        'assetUrl': 'https://app.example.test/assets/index-old.js' if reason == 'release-changed' else 'https://app.example.test/assets/index-current.js',
        'apiBase': '/api',
    }))
    cache = str(cache_file).replace("'", "''")
    result = run_helper(f"""
        $script:bundleRequests = 0
        function Invoke-WebRequest {{
            param($Uri)
            return @{{ Content = '<script src="/assets/index-current.js"></script>' }}
        }}
        function Get-MangoPointBundleText {{
            $script:bundleRequests += 1
            return '{{VITE_API_BASE:"https://stale.trycloudflare.com"}},fallback="/api";'
        }}
        $base = Get-MangoPointLiveApiBase 'https://app.example.test' '{cache}' $false ${str(reason == 'refresh').lower()} 6>$null
        @{{ base = $base; downloads = $script:bundleRequests }} | ConvertTo-Json -Compress
    """)
    assert result == {'base': 'https://stale.trycloudflare.com', 'downloads': 1}


@pytest.mark.parametrize('existing', [None, '{bad-json'])
def test_read_only_cache_miss_fetches_bundle_without_writing(tmp_path, existing):
    cache_file = tmp_path / 'frontend-check.json'
    if existing is not None:
        cache_file.write_text(existing)
    cache = str(cache_file).replace("'", "''")
    result = run_helper(f"""
        function Invoke-WebRequest {{
            param($Uri)
            return @{{ Content = '<script src="/assets/index-current.js"></script>' }}
        }}
        function Get-MangoPointBundleText {{ return '{{VITE_API_BASE:"/api"}}' }}
        @{{ base = (Get-MangoPointLiveApiBase 'https://app.example.test' '{cache}' $true $false 6>$null) }} | ConvertTo-Json -Compress
    """)
    assert result == {'base': '/api'}
    if existing is None:
        assert not cache_file.exists()
    else:
        assert cache_file.read_text() == existing


def test_cached_configuration_does_not_mask_a_failed_live_page_check(tmp_path):
    cache_file = tmp_path / 'frontend-check.json'
    cache_file.write_text(json.dumps({
        'version': 1, 'siteUrl': 'https://app.example.test',
        'assetUrl': 'https://app.example.test/assets/index-current.js', 'apiBase': '/api',
    }))
    cache = str(cache_file).replace("'", "''")
    result = run_helper(f"""
        function Invoke-WebRequest {{ throw 'Fixture internet failure' }}
        try {{ Get-MangoPointLiveApiBase 'https://app.example.test' '{cache}' $true $false 6>$null | Out-Null; $blocked = $false }}
        catch {{ $blocked = $true }}
        @{{ blocked = $blocked }} | ConvertTo-Json -Compress
    """)
    assert result == {'blocked': True}
