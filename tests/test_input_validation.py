import pytest
import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from api.models.auth import CurrentUserUpdateRequest, LoginRequest, PasswordResetConfirmRequest
from api.models.schemas import AlertEmailRecipientCreate, AlertEmailRecipientUpdate, ManualWeather, OrchardCreate, SimulationRequest
from utils.input_validation import normalize_email


@pytest.mark.parametrize('email', ['manager+alerts@example.com', "o'connor@example.com", 'Manager@example.co.uk'])
def test_valid_email_forms_are_preserved_and_normalized(email):
    expected = email.strip().lower()
    assert AlertEmailRecipientCreate(email=email).email == expected
    assert AlertEmailRecipientUpdate(email=email).email == expected


@pytest.mark.parametrize('email', ['a..b@example.com', '.a@example.com', 'a.@example.com', 'a@-example.com',
    'a@example-.com', 'a@example..com', 'a@example.com.', 'a b@example.com', 'a@example.com\r\nBcc: other@example.com',
    'a@', '@example.com', 'a@localhost', 'a@' + 'b'*64 + '.com', 'a'*65 + '@example.com', 'a@@example.com'])
def test_malformed_email_addresses_are_rejected_in_all_contact_schemas(email):
    with pytest.raises(ValueError): normalize_email(email)
    with pytest.raises(ValidationError): AlertEmailRecipientCreate(email=email)
    with pytest.raises(ValidationError): AlertEmailRecipientUpdate(email=email)


@pytest.mark.parametrize('name', [' ', '<script>', '12345', 'Name\x00Test', 'Name\nTest'])
def test_names_reject_blank_markup_and_control_characters(name):
    with pytest.raises(ValidationError): CurrentUserUpdateRequest(full_name=name)


def test_unicode_names_optional_recipient_names_and_long_login_inputs():
    assert CurrentUserUpdateRequest(full_name='  María O’Neill  ').full_name == 'María O’Neill'
    assert AlertEmailRecipientCreate(email='scout@example.com', name='  ').name is None
    with pytest.raises(ValidationError): LoginRequest(username_or_email='x'*255, password='password')
    with pytest.raises(ValidationError): LoginRequest(username_or_email='user', password='x'*257)
    with pytest.raises(ValidationError): LoginRequest(username_or_email='   ', password='password')


def test_blank_passwords_and_nonfinite_numeric_inputs_are_rejected():
    with pytest.raises(ValidationError): PasswordResetConfirmRequest(challenge_id='0'*36, code='123456', new_password=' '*8)
    for number in [float('inf'), float('-inf'), float('nan')]:
        with pytest.raises(ValidationError): OrchardCreate(name='Test orchard', area_size=number)
        with pytest.raises(ValidationError): ManualWeather(temperature_c=number)
        with pytest.raises(ValidationError): SimulationRequest(pest_type='fruitfly', orchard_geojson={'type':'FeatureCollection','features':[]}, tg_max_neighbor_dist_m=number)


@pytest.mark.asyncio
async def test_api_validation_returns_field_errors_without_echoing_passwords_or_nonfinite_inputs():
    from api.main import app as application
    from api.models.auth import PasswordChangeRequest

    app = FastAPI()
    app.add_exception_handler(RequestValidationError, application.exception_handlers[RequestValidationError])

    @app.post('/weather')
    async def weather(payload: ManualWeather):
        return {'accepted': True}

    @app.post('/password')
    async def password(payload: PasswordChangeRequest):
        return {'accepted': True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated.test') as client:
        for value in ['NaN', 'Infinity', '-Infinity']:
            response = await client.post('/weather', content='{"temperature_c":' + value + '}', headers={'Content-Type':'application/json'})
            assert response.status_code == 422
            assert response.json()['detail'][0]['loc'] == ['body', 'temperature_c']
            assert 'input' not in response.json()['detail'][0]
        response = await client.post('/password', json={'current_password':'private-current-password',
            'new_password':'private-current-password', 'challenge_id':'0'*36, 'code':'123456'})
        assert response.status_code == 422
        assert 'private-current-password' not in response.text
        assert '123456' not in response.text
