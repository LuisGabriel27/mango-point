"""Real PostgreSQL checks in a fresh temporary schema, never application records."""
import asyncio
import re
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.core.config import settings
from api.core.database import get_db
from api.core.migrations import execute_script, split_sql_statements
from api.core.security import decode_access_token, get_password_hash, session_credential_stamp
from api.routes.auth import router
from api.services.notification_service import notification_service
from db.models import AuthSession, PasswordResetChallenge, UserAccount, UserRoleEnum
from utils.datetime_utils import utcnow_naive

ROOT = Path(__file__).resolve().parents[1]


@pytest_asyncio.fixture
async def account_api(monkeypatch):
    url = make_url(settings.DATABASE_URL).set(drivername='postgresql+asyncpg')
    if url.host not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.skip('Security integration checks require a local PostgreSQL server.')
    schema = 'test_account_security_' + uuid.uuid4().hex
    assert re.fullmatch(r'test_account_security_[0-9a-f]{32}', schema)
    admin = create_async_engine(url)
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA {schema}'))
    except Exception as error:
        await admin.dispose()
        pytest.skip(f'Local PostgreSQL unavailable ({type(error).__name__}).')
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': f'{schema},public'}})
    try:
        async with engine.begin() as connection:
            assert await connection.scalar(text('SELECT current_schema()')) == schema
            # Explicit CREATE avoids accidentally adopting a public account table.
            await connection.run_sync(lambda sync: UserAccount.__table__.create(sync, checkfirst=False))
            await execute_script(connection, (ROOT / 'db/migrations/0011_password_reset_challenges.sql').read_text())
            migration = (ROOT / 'db/migrations/0012_account_session_security.sql').read_text()
            await execute_script(connection, migration)
            await execute_script(connection, migration)  # Safe to run again during startup.
            hosted = (ROOT / 'supabase/migrations/202610170000_account_session_security.sql').read_text()
            for statement in split_sql_statements(hosted):
                if statement.strip().upper() in {'BEGIN', 'COMMIT', 'SET SEARCH_PATH = PUBLIC, EXTENSIONS, GIS', 'RESET SEARCH_PATH'}:
                    continue
                await connection.exec_driver_sql(statement)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory.begin() as db:
            db.add(UserAccount(full_name='Isolated Security Test', username='security-test', email='security@example.test',
                password_hash=get_password_hash('old-password'), role=UserRoleEnum.ADMIN, is_active=True))
        monkeypatch.setattr(settings, 'AUTH_SECRET_KEY', 'isolated-account-security-secret-at-least-32-bytes')
        sender = AsyncMock(return_value=True)
        monkeypatch.setattr(notification_service, 'send_password_reset_code', sender)
        app = FastAPI()
        app.include_router(router)
        async def database():
            async with factory() as db:
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        app.dependency_overrides[get_db] = database
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated.test') as client:
            client.test_factory, client.test_sender = factory, sender
            yield client, factory, sender
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        await admin.dispose()


async def sign_in(client, password='old-password', username='security-test'):
    # Advance only isolated fixture challenges so session tests need not sleep.
    async with client.test_factory.begin() as db:
        await db.execute(update(PasswordResetChallenge).where(PasswordResetChallenge.purpose == 'login')
            .values(created_at=utcnow_naive() - timedelta(seconds=settings.LOGIN_CODE_RESEND_SECONDS + 1)))
    issued = await client.post('/auth/login', json={'username_or_email':username, 'password':password})
    if issued.status_code != 200:
        return issued
    return await client.post('/auth/login/verify', json={
        'challenge_id':issued.json()['challenge_id'], 'code':client.test_sender.await_args.args[1]})


def bearer(response):
    return {'Authorization':'Bearer ' + response.json()['access_token']}


@pytest.mark.asyncio
async def test_simultaneous_logins_never_allocate_more_than_two_slots(account_api):
    client, factory, sender = account_api
    await sign_in(client)
    async with factory.begin() as db:
        await db.execute(update(PasswordResetChallenge).values(created_at=utcnow_naive() - timedelta(seconds=61)))
    issued = await client.post('/auth/login', json={'username_or_email':'security-test', 'password':'old-password'})
    payload = {'challenge_id':issued.json()['challenge_id'], 'code':sender.await_args.args[1]}
    responses = await asyncio.gather(*(client.post('/auth/login/verify', json=payload) for _ in range(12)))
    assert sum(response.status_code == 200 for response in responses) == 1
    assert sum(response.status_code == 400 for response in responses) == 11
    assert (await sign_in(client)).status_code == 409
    async with factory() as db:
        assert len((await db.scalars(select(AuthSession))).all()) == 2


@pytest.mark.asyncio
async def test_refresh_reuses_slot_and_logout_prevents_token_replay(account_api):
    client, factory, _ = account_api
    first, second = await sign_in(client), await sign_in(client)
    assert (await sign_in(client)).status_code == 409
    renewed = await client.post('/auth/session/refresh', headers=bearer(first), json={})
    assert renewed.status_code == 200
    assert decode_access_token(first.json()['access_token'])['sid'] == decode_access_token(renewed.json()['access_token'])['sid']
    async with factory() as db:
        assert len((await db.scalars(select(AuthSession))).all()) == 2
    assert (await client.post('/auth/logout', headers=bearer(first))).status_code == 200
    assert (await client.get('/auth/me', headers=bearer(renewed))).status_code == 401
    assert (await client.get('/auth/me', headers=bearer(second))).status_code == 200
    assert (await sign_in(client)).status_code == 200


@pytest.mark.asyncio
async def test_expired_sessions_release_slots_without_background_requests_renewing_them(account_api):
    client, factory, _ = account_api
    first = await sign_in(client)
    await sign_in(client)
    sid = decode_access_token(first.json()['access_token'])['sid']
    async with factory.begin() as db:
        row = await db.get(AuthSession, sid)
        row.expires_at = utcnow_naive() - timedelta(seconds=1)
    assert (await client.get('/auth/me', headers=bearer(first))).status_code == 401
    assert (await sign_in(client)).status_code == 200


@pytest.mark.asyncio
async def test_password_change_requires_current_password_and_emailed_code_then_revokes_all_sessions(account_api):
    client, _, sender = account_api
    first, second = await sign_in(client), await sign_in(client)
    headers = bearer(first)
    sender.reset_mock()
    assert (await client.post('/auth/password/code', headers=headers, json={'current_password':'wrong'})).status_code == 400
    sender.assert_not_awaited()
    assert (await client.post('/auth/password', headers=headers, json={'current_password':'old-password','new_password':'new-password-123'})).status_code == 422
    issued = await client.post('/auth/password/code', headers=headers, json={'current_password':'old-password'})
    assert issued.status_code == 200
    code = sender.await_args.args[1]
    assert sender.await_args.args[0] == 'security@example.test'
    assert sender.await_args.kwargs['purpose'] == 'change'
    payload = {'current_password':'old-password','new_password':'new-password-123','challenge_id':issued.json()['challenge_id'],'code':code}
    assert (await client.post('/auth/password/code', headers=headers, json={'current_password':'old-password'})).status_code == 429
    assert (await client.post('/auth/password/reset', json={'challenge_id':payload['challenge_id'],'code':code,'new_password':'bypass-password'})).status_code == 400
    assert (await client.post('/auth/password', headers=headers, json={**payload,'code':'999999' if code != '999999' else '000000'})).status_code == 400
    assert (await client.get('/auth/me', headers=bearer(second))).status_code == 200
    assert (await client.post('/auth/password', headers=headers, json=payload)).status_code == 200
    for response in (first, second):
        assert (await client.get('/auth/me', headers=bearer(response))).status_code == 401
    assert (await sign_in(client, 'new-password-123')).status_code == 200
    assert (await sign_in(client)).status_code == 401


@pytest.mark.asyncio
async def test_code_locks_after_five_attempts_and_email_change_cannot_bypass_it(account_api):
    client, factory, sender = account_api
    first = await sign_in(client)
    headers = bearer(first)
    issued = await client.post('/auth/me/email/code', headers=headers, json={'current_password':'old-password'})
    code = sender.await_args.args[1]
    payload = {'email':'replacement@example.test', 'current_password':'old-password', 'challenge_id':issued.json()['challenge_id'],'code':code}
    assert (await client.post('/auth/password', headers=headers, json={**payload,'new_password':'bypass-password'})).status_code == 400
    for _ in range(5):
        assert (await client.patch('/auth/me/email', headers=headers, json={**payload,'code':'999999' if code != '999999' else '000000'})).status_code == 400
    assert (await client.patch('/auth/me/email', headers=headers, json=payload)).status_code == 400
    assert (await client.get('/auth/me', headers=headers)).json()['user']['email'] == 'security@example.test'


@pytest.mark.asyncio
async def test_email_delivery_failure_leaves_password_and_sessions_unchanged(account_api):
    client, factory, sender = account_api
    first = await sign_in(client)
    sender.return_value = False
    result = await client.post('/auth/password/code', headers=bearer(first), json={'current_password':'old-password'})
    assert result.status_code == 503
    assert (await client.get('/auth/me', headers=bearer(first))).status_code == 200
    async with factory() as db:
        assert (await db.scalars(select(PasswordResetChallenge).where(PasswordResetChallenge.purpose == 'change'))).all() == []


@pytest.mark.asyncio
async def test_expired_and_replaced_codes_cannot_change_a_password(account_api):
    client, factory, sender = account_api
    headers = bearer(await sign_in(client))
    issued = await client.post('/auth/password/code', headers=headers, json={'current_password':'old-password'})
    payload = {'current_password':'old-password', 'new_password':'new-password-123',
        'challenge_id':issued.json()['challenge_id'], 'code':sender.await_args.args[1]}
    async with factory.begin() as db:
        challenge = await db.get(PasswordResetChallenge, payload['challenge_id'])
        challenge.expires_at = utcnow_naive() - timedelta(seconds=1)
        challenge.created_at = utcnow_naive() - timedelta(seconds=61)
    assert (await client.post('/auth/password', headers=headers, json=payload)).status_code == 400
    replacement = await client.post('/auth/password/code', headers=headers, json={'current_password':'old-password'})
    assert replacement.status_code == 200
    assert replacement.json()['challenge_id'] != payload['challenge_id']
    async with factory.begin() as db:
        old = await db.get(PasswordResetChallenge, payload['challenge_id'])
        assert old.consumed_at is not None
        old.expires_at = utcnow_naive() + timedelta(minutes=10)
    assert (await client.post('/auth/password', headers=headers, json=payload)).status_code == 400
    payload.update(challenge_id=replacement.json()['challenge_id'], code=sender.await_args.args[1])
    assert (await client.post('/auth/password', headers=headers, json=payload)).status_code == 200


@pytest.mark.asyncio
async def test_codes_are_bound_to_the_account_and_existing_inbox_and_cannot_be_reused(account_api):
    client, factory, sender = account_api
    headers = bearer(await sign_in(client))
    async with factory.begin() as db:
        db.add(UserAccount(full_name='Second Isolated Account', username='other-security-test', email='other@example.test',
            password_hash=get_password_hash('old-password'), role=UserRoleEnum.ADMIN, is_active=True))
    other = await sign_in(client, username='other-security-test')
    issued = await client.post('/auth/password/code', headers=headers, json={'current_password':'old-password'})
    password_payload = {'current_password':'old-password', 'new_password':'new-password-123',
        'challenge_id':issued.json()['challenge_id'], 'code':sender.await_args.args[1]}
    assert (await client.post('/auth/password', headers=bearer(other), json=password_payload)).status_code == 400
    async with factory.begin() as db:
        challenge = await db.get(PasswordResetChallenge, password_payload['challenge_id'])
        challenge.created_at = utcnow_naive() - timedelta(seconds=61)
        assert challenge.consumed_at is None
    issued_email = await client.post('/auth/me/email/code', headers=headers, json={'current_password':'old-password'})
    assert issued_email.status_code == 200
    assert sender.await_args.args[0] == 'security@example.test'
    assert sender.await_args.kwargs['purpose'] == 'email'
    email_payload = {'current_password':'old-password', 'email':'replacement@example.test',
        'challenge_id':issued_email.json()['challenge_id'], 'code':sender.await_args.args[1]}
    changed = await client.patch('/auth/me/email', headers=headers, json=email_payload)
    assert changed.status_code == 200
    assert changed.json()['user']['email'] == 'replacement@example.test'
    assert (await client.patch('/auth/me/email', headers=headers, json=email_payload)).status_code == 400
    assert (await client.post('/auth/password', headers=headers, json=password_payload)).status_code == 400
    assert (await client.get('/auth/me', headers=headers)).status_code == 200


async def begin_email_login(client):
    return await client.post('/auth/login', json={'username_or_email':'security-test', 'password':'old-password'})


@pytest.mark.asyncio
async def test_email_login_never_grants_access_before_verification_and_code_is_single_use(account_api):
    client, factory, sender = account_api
    wrong = await client.post('/auth/login', json={'username_or_email':'security-test', 'password':'incorrect'})
    assert wrong.status_code == 401
    sender.assert_not_awaited()
    issued = await begin_email_login(client)
    body = issued.json()
    assert issued.status_code == 200 and body['verification_required'] is True
    assert issued.headers['cache-control'] == 'no-store'
    assert body['masked_email'] == 's***@example.test'
    code = sender.await_args.args[1]
    assert sender.await_args.kwargs['purpose'] == 'login'
    assert sender.await_args.args[2] == settings.LOGIN_CODE_EXPIRE_MINUTES
    assert not {'access_token', 'user', 'code', 'password'} & body.keys()
    assert (await client.get('/auth/me', headers={'Authorization':'Bearer ' + body['challenge_id']})).status_code == 401
    async with factory() as db:
        assert (await db.scalars(select(AuthSession))).all() == []
        user = (await db.scalars(select(UserAccount))).one()
        assert user.last_login_at is None
        challenge = await db.get(PasswordResetChallenge, body['challenge_id'])
        assert challenge.code_hash != code and challenge.purpose == 'login'
    payload = {'challenge_id':body['challenge_id'], 'code':code}
    assert (await client.post('/auth/password/reset', json={**payload,'new_password':'bypass-password'})).status_code == 400
    verified = await client.post('/auth/login/verify', json=payload)
    assert verified.status_code == 200
    assert verified.headers['cache-control'] == 'no-store'
    assert (await client.get('/auth/me', headers=bearer(verified))).status_code == 200
    assert (await client.post('/auth/login/verify', json=payload)).status_code == 400
    assert (await client.post('/auth/login/resend', json={'challenge_id':body['challenge_id']})).status_code == 400
    async with factory() as db:
        assert len((await db.scalars(select(AuthSession))).all()) == 1


@pytest.mark.asyncio
async def test_login_code_attempt_limit_is_persisted_under_concurrent_requests(account_api):
    client, factory, sender = account_api
    issued = await begin_email_login(client)
    code = sender.await_args.args[1]
    payload = {'challenge_id':issued.json()['challenge_id'], 'code':'000000' if code != '000000' else '999999'}
    responses = await asyncio.gather(*(client.post('/auth/login/verify', json=payload) for _ in range(12)))
    assert all(response.status_code == 400 for response in responses)
    assert (await client.post('/auth/login/verify', json={**payload,'code':code})).status_code == 400
    assert (await client.post('/auth/login/resend', json={'challenge_id':payload['challenge_id']})).status_code == 400
    async with factory() as db:
        row = await db.get(PasswordResetChallenge, payload['challenge_id'])
        assert row.attempt_count == settings.LOGIN_CODE_MAX_ATTEMPTS and row.consumed_at is not None
        assert (await db.scalars(select(AuthSession))).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['expired', 'password', 'email', 'inactive', 'purpose'])
async def test_pending_login_rejects_expiry_account_changes_and_other_code_purposes(account_api, change):
    client, factory, sender = account_api
    issued = await begin_email_login(client)
    payload = {'challenge_id':issued.json()['challenge_id'], 'code':sender.await_args.args[1]}
    async with factory.begin() as db:
        row = await db.get(PasswordResetChallenge, payload['challenge_id'])
        user = await db.get(UserAccount, row.user_id)
        if change == 'expired': row.expires_at = utcnow_naive() - timedelta(seconds=1)
        elif change == 'password': user.password_hash = get_password_hash('changed-password')
        elif change == 'email': user.email = 'changed@example.test'
        elif change == 'inactive': user.is_active = False
        else: row.purpose = 'reset'
    assert (await client.post('/auth/login/verify', json=payload)).status_code == 400
    assert (await client.post('/auth/login/resend', json={'challenge_id':payload['challenge_id']})).status_code == 400
    async with factory() as db:
        assert (await db.scalars(select(AuthSession))).all() == []


@pytest.mark.asyncio
async def test_resend_cooldown_replaces_old_login_code_and_failed_delivery_keeps_old_code(account_api):
    client, factory, sender = account_api
    first = await begin_email_login(client)
    payload = {'challenge_id':first.json()['challenge_id'], 'code':sender.await_args.args[1]}
    for path, body in [('/auth/login/resend', {'challenge_id':payload['challenge_id']}),
                       ('/auth/login', {'username_or_email':'security-test', 'password':'old-password'})]:
        response = await client.post(path, json=body)
        assert response.status_code == 429 and response.headers['retry-after'] == str(settings.LOGIN_CODE_RESEND_SECONDS)
    assert sender.await_count == 1
    async with factory.begin() as db:
        row = await db.get(PasswordResetChallenge, payload['challenge_id'])
        row.created_at = utcnow_naive() - timedelta(seconds=settings.LOGIN_CODE_RESEND_SECONDS + 1)
    sender.return_value = False
    assert (await client.post('/auth/login/resend', json={'challenge_id':payload['challenge_id']})).status_code == 503
    async with factory() as db:
        rows = (await db.scalars(select(PasswordResetChallenge))).all()
        assert len(rows) == 1 and rows[0].consumed_at is None
    sender.return_value = True
    replacement = await client.post('/auth/login/resend', json={'challenge_id':payload['challenge_id']})
    assert replacement.status_code == 200 and replacement.json()['challenge_id'] != payload['challenge_id']
    assert (await client.post('/auth/login/verify', json=payload)).status_code == 400
    verified = await client.post('/auth/login/verify', json={'challenge_id':replacement.json()['challenge_id'],
                                                           'code':sender.await_args.args[1]})
    assert verified.status_code == 200


@pytest.mark.asyncio
async def test_failed_login_delivery_creates_no_challenge_session_or_login_record(account_api):
    client, factory, sender = account_api
    sender.return_value = False
    response = await begin_email_login(client)
    assert response.status_code == 503 and 'access_token' not in response.json()
    async with factory() as db:
        assert (await db.scalars(select(PasswordResetChallenge))).all() == []
        assert (await db.scalars(select(AuthSession))).all() == []
        assert (await db.scalars(select(UserAccount))).one().last_login_at is None


@pytest.mark.asyncio
async def test_verification_rechecks_session_capacity_and_consumes_the_correct_code(account_api):
    client, factory, sender = account_api
    issued = await begin_email_login(client)
    payload = {'challenge_id':issued.json()['challenge_id'], 'code':sender.await_args.args[1]}
    async with factory.begin() as db:
        user = (await db.scalars(select(UserAccount))).one()
        for _ in range(2):
            db.add(AuthSession(session_id=str(uuid.uuid4()), user_id=user.user_id,
                credential_stamp=session_credential_stamp(user), expires_at=utcnow_naive() + timedelta(minutes=5)))
    assert (await client.post('/auth/login/verify', json=payload)).status_code == 409
    assert (await client.post('/auth/login/verify', json=payload)).status_code == 400
    async with factory() as db:
        assert len((await db.scalars(select(AuthSession))).all()) == 2
        assert (await db.get(PasswordResetChallenge, payload['challenge_id'])).consumed_at is not None
