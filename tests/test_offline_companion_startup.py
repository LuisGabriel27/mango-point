"""Verify offline startup and browser access without modifying Docker services."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")


def run_ps(code):
    if not POWERSHELL:
        pytest.skip("Windows startup helper")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", code],
        capture_output=True, text=True, timeout=15, check=True,
    )
    return json.loads(result.stdout)


def test_offline_starts_wait_for_health_without_builds_or_downloads():
    helper = str(ROOT / "scripts/offline_companion_helpers.ps1").replace("'", "''")
    result = run_ps(f"""
        . '{helper}'
        @{{ offline = @(Get-MangoPointCompanionStartArgs $false); prepare = @(Get-MangoPointCompanionStartArgs $true) }} | ConvertTo-Json -Compress
    """)
    assert "--wait" in result["offline"]
    assert "--wait-timeout" in result["offline"]
    assert "--no-build" in result["offline"]
    assert result["offline"][-2:] == ["--pull", "never"]
    assert "--build" not in result["offline"]
    assert "--build" in result["prepare"]


@pytest.mark.parametrize("health", [
    {"status": "healthy", "database": "connected"},
    {"status": "healthy", "database": "error"},
    {"status": "unhealthy", "database": "connected"},
    {"database": "connected"},
])
def test_docker_healthcheck_requires_connected_database(health):
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    # The compose healthchecks use JSON-compatible inline arrays. Read the
    # actual command without introducing a YAML parser dependency into tests.
    healthchecks = [json.loads(value) for value in re.findall(r'(?m)^\s+test:\s+(\[.*\])\s*$', compose)]
    command = next(check[-1] for check in healthchecks if check[:2] == ['CMD', 'python'])
    payload = json.dumps(health).encode()
    setup = f"import io, urllib.request; urllib.request.urlopen = lambda *a, **kw: io.BytesIO({payload!r}); "
    result = subprocess.run([sys.executable, "-c", setup + command], capture_output=True, timeout=5)
    expected = health.get("status") == "healthy" and health.get("database") == "connected"
    assert (result.returncode == 0) == expected


def test_cors_health_and_login_must_both_allow_deployed_site():
    helper = str(ROOT / "scripts/offline_companion_helpers.ps1").replace("'", "''")
    result = run_ps(f"""
        $ErrorActionPreference = 'Stop'
        . '{helper}'
        $script:healthOrigin = 'https://mango-point-projects.vercel.app'
        $script:loginOrigin = $script:healthOrigin
        function Invoke-WebRequest {{
            param($Uri, $Headers, $Method)
            if ($Method -eq 'Options') {{ $origin = $script:loginOrigin }} else {{ $origin = $script:healthOrigin }}
            return @{{ StatusCode = 200; Headers = @{{ 'Access-Control-Allow-Origin' = $origin }} }}
        }}
        Assert-MangoPointCompanionBrowserAccess 'http://127.0.0.1:8000' $script:healthOrigin
        $script:healthOrigin = $null
        try {{ Assert-MangoPointCompanionBrowserAccess 'http://127.0.0.1:8000' 'https://mango-point-projects.vercel.app'; $healthBlocked = $false }}
        catch {{ $healthBlocked = $_.Exception.Message.Contains('CORS_ORIGINS') }}
        $script:healthOrigin = 'https://mango-point-projects.vercel.app'
        $script:loginOrigin = $null
        try {{ Assert-MangoPointCompanionBrowserAccess 'http://127.0.0.1:8000' $script:healthOrigin; $loginBlocked = $false }}
        catch {{ $loginBlocked = $_.Exception.Message.Contains('CORS_ORIGINS') }}
        @{{ healthBlocked = $healthBlocked; loginBlocked = $loginBlocked }} | ConvertTo-Json -Compress
    """)
    assert result == {"healthBlocked": True, "loginBlocked": True}


@pytest.mark.parametrize("ready,wait_fails,check_only,expected_code", [
    (True, False, True, 0),
    (False, False, False, 0),
    (False, True, False, 1),
    (False, False, True, 1),
])
def test_launcher_gates_browser_checks_on_health(tmp_path, ready, wait_fails, check_only, expected_code):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(ROOT / "scripts/start_offline_companion.ps1", scripts)
    shutil.copy(ROOT / "scripts/offline_companion_helpers.ps1", scripts)
    (tmp_path / ".env").write_text("# Test fixture; no credentials\n")
    (scripts / "remote_access_helpers.ps1").write_text(f"""
        function Test-MangoPointApiReady {{ return ${str(ready).lower()} }}
        function Wait-MangoPointApiReady {{
            $global:events += 'wait-health'
            if (${str(wait_fails).lower()}) {{ throw 'Fixture database not ready' }}
        }}
    """)
    launcher = str(scripts / "start_offline_companion.ps1").replace("'", "''")
    result = run_ps(f"""
        $global:events = @()
        function docker {{
            $global:events += ('docker ' + ($args -join ' '))
            $global:LASTEXITCODE = 0
        }}
        function Invoke-WebRequest {{
            $global:events += 'cors'
            return @{{ StatusCode = 200; Headers = @{{ 'Access-Control-Allow-Origin' = 'https://mango-point-projects.vercel.app' }} }}
        }}
        & '{launcher}' {'-CheckOnly' if check_only else ''} 6>$null
        @{{ code = $LASTEXITCODE; events = @($global:events) }} | ConvertTo-Json -Compress
    """)
    # A successfully executed .ps1 does not set LASTEXITCODE when it ran no native command.
    assert (result["code"] or 0) == expected_code
    if ready:
        assert result["events"] == ["cors", "cors"]
    elif check_only:
        assert result["events"] == []
    else:
        assert result["events"][1].startswith("docker compose up")
        assert result["events"][2] == "wait-health"
        assert result["events"].count("cors") == (0 if wait_fails else 2)


def test_cors_repair_does_not_touch_an_already_accessible_api(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy(ROOT / 'scripts/start_offline_companion.ps1', scripts)
    shutil.copy(ROOT / 'scripts/offline_companion_helpers.ps1', scripts)
    (scripts / 'remote_access_helpers.ps1').write_text('function Test-MangoPointApiReady { return $true }')
    launcher = str(scripts / 'start_offline_companion.ps1').replace("'", "''")
    result = run_ps(f"""
        $global:events = @()
        function docker {{ throw 'An accessible API should not require Docker' }}
        function Invoke-WebRequest {{
            $global:events += 'cors'
            return @{{ StatusCode = 200; Headers = @{{ 'Access-Control-Allow-Origin' = 'https://mango-point-projects.vercel.app' }} }}
        }}
        & '{launcher}' -RepairCors 6>$null
        @{{ code = $LASTEXITCODE; events = @($global:events) }} | ConvertTo-Json -Compress
    """)
    assert (result['code'] or 0) == 0
    assert result['events'] == ['cors', 'cors', 'cors', 'cors']
    assert not (tmp_path / '.env').exists()
    assert not (tmp_path / 'outputs').exists()


def test_read_only_cannot_be_combined_with_cors_repair():
    launcher = str(ROOT / 'scripts/start_offline_companion.ps1').replace("'", "''")
    result = run_ps(f"""
        function Invoke-WebRequest {{ throw 'Should stop before browser/network checks' }}
        function docker {{ throw 'Should stop before Docker' }}
        & '{launcher}' -CheckOnly -RepairCors 6>$null
        @{{ code = $LASTEXITCODE }} | ConvertTo-Json -Compress
    """)
    assert result == {'code': 1}


@pytest.mark.parametrize("cors_line,expected", [
    ('CORS_ORIGINS=["https://existing.example"]', ['https://existing.example']),
    ('CORS_ORIGINS=\'["https://existing.example"]\' # retain this comment', ['https://existing.example']),
    ('CORS_ORIGINS=https://first.example,https://second.example', ['https://first.example', 'https://second.example']),
    ('CORS_ORIGINS=[]', []),
    ('', ['http://localhost:3000', 'http://127.0.0.1:3000', 'http://localhost:5173', 'http://127.0.0.1:5173']),
])
def test_cors_repair_preserves_settings_origins_backup_and_is_idempotent(tmp_path, cors_line, expected):
    env_file = tmp_path / '.env'
    original = 'AUTH_SECRET_KEY=fixture-only-secret\r\n' + cors_line + '\r\n# unchanged\r\nOTHER_SETTING=caf\u00e9\r\n'
    env_file.write_bytes(original.encode('utf-8'))
    helper = str(ROOT / 'scripts/offline_companion_helpers.ps1').replace("'", "''")
    path = str(env_file).replace("'", "''")
    result = run_ps(f"""
        $ErrorActionPreference = 'Stop'
        . '{helper}'
        $first = Add-MangoPointCompanionOrigin '{path}' 'https://mango-point-projects.vercel.app'
        $second = Add-MangoPointCompanionOrigin '{path}' 'https://mango-point-projects.vercel.app'
        @{{ first = $first; second = $second }} | ConvertTo-Json -Compress
    """)
    assert result == {'first': True, 'second': False}
    updated = env_file.read_bytes().decode('utf-8')
    assert updated.startswith('AUTH_SECRET_KEY=fixture-only-secret\r\n')
    assert '# unchanged\r\nOTHER_SETTING=caf\u00e9\r\n' in updated
    if '# retain this comment' in original:
        assert '# retain this comment' in updated
    line = re.search(r'^CORS_ORIGINS=(\[.*\])', updated, re.M).group(1)
    assert json.loads(line) == expected + ['https://mango-point-projects.vercel.app']
    backups = list((tmp_path / 'outputs/offline-companion').iterdir())
    assert len(backups) == 1
    assert backups[0].read_bytes() == original.encode('utf-8')


@pytest.mark.parametrize('cors_line', [
    'CORS_ORIGINS=[broken]',
    'CORS_ORIGINS=[123]',
    'CORS_ORIGINS=[]\nCORS_ORIGINS=[]',
])
def test_cors_repair_rejects_invalid_settings_without_writes(tmp_path, cors_line):
    env_file = tmp_path / '.env'
    original = cors_line.encode('utf-8')
    env_file.write_bytes(original)
    helper = str(ROOT / 'scripts/offline_companion_helpers.ps1').replace("'", "''")
    path = str(env_file).replace("'", "''")
    result = run_ps(f"""
        $ErrorActionPreference = 'Stop'
        . '{helper}'
        try {{ Add-MangoPointCompanionOrigin '{path}' 'https://mango-point-projects.vercel.app' | Out-Null; $blocked = $false }}
        catch {{ $blocked = $_.Exception.Message.Contains('CORS_ORIGINS') }}
        @{{ blocked = $blocked }} | ConvertTo-Json -Compress
    """)
    assert result == {'blocked': True}
    assert env_file.read_bytes() == original
    assert not (tmp_path / 'outputs').exists()


@pytest.mark.parametrize('container_exists', [True, False])
def test_launcher_cors_repair_recreates_existing_api_and_rechecks_access(tmp_path, container_exists):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy(ROOT / 'scripts/start_offline_companion.ps1', scripts)
    shutil.copy(ROOT / 'scripts/offline_companion_helpers.ps1', scripts)
    original = 'OTHER_SETTING=retain-me\nCORS_ORIGINS=["https://existing.example"]\n'
    env_file = tmp_path / '.env'
    env_file.write_text(original)
    (scripts / 'remote_access_helpers.ps1').write_text("""
        function Test-MangoPointApiReady { return $true }
        function Wait-MangoPointApiReady { $global:events += 'wait-health' }
    """)
    launcher = str(scripts / 'start_offline_companion.ps1').replace("'", "''")
    result = run_ps(f"""
        $global:events = @()
        $global:allowed = $false
        function docker {{
            $global:events += ('docker ' + ($args -join ' '))
            $global:LASTEXITCODE = 0
            if ($args[1] -eq 'ps' -and ${str(container_exists).lower()}) {{ return 'fixture-api-container' }}
            if ($args[1] -eq 'up') {{ $global:allowed = $true }}
        }}
        function Invoke-WebRequest {{
            $global:events += 'cors'
            $origin = if ($global:allowed) {{ 'https://mango-point-projects.vercel.app' }} else {{ $null }}
            return @{{ StatusCode = 200; Headers = @{{ 'Access-Control-Allow-Origin' = $origin }} }}
        }}
        & '{launcher}' -RepairCors 6>$null
        @{{ code = $LASTEXITCODE; events = @($global:events) }} | ConvertTo-Json -Compress
    """)
    if container_exists:
        assert result['code'] == 0
        recreate = next(event for event in result['events'] if event.startswith('docker compose up'))
        assert '--no-deps --no-build --pull never --force-recreate' in recreate
        assert recreate.endswith(' api')
        wait_index = result['events'].index('wait-health')
        assert result['events'][wait_index + 1:] == ['cors', 'cors']
        assert env_file.read_text().startswith('OTHER_SETTING=retain-me\n')
        assert 'https://mango-point-projects.vercel.app' in env_file.read_text()
    else:
        assert result['code'] == 1
        assert env_file.read_text() == original
        assert not any(event.startswith('docker compose up') for event in result['events'])
