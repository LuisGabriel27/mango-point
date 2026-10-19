"""Email rendering contracts, with no real recipients, credentials or delivery."""

from html.parser import HTMLParser

import pytest

from api.core.config import Settings
from api.services.email_templates import alert_email_html, verification_email
from api.services.notification_service import NotificationService


class Markup(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.links = []
        self.images = []
        self.text = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'a':
            self.links.append(dict(attrs).get('href'))
        if tag == 'img':
            self.images.append(dict(attrs))

    def handle_data(self, data):
        self.text.append(data)


@pytest.fixture
def service():
    return NotificationService(Settings(_env_file=None, SMTP_FROM_EMAIL='preview@example.test',
        SMTP_FROM_NAME='MangoPoint', ALERT_EMAIL_APP_URL='https://mangopoint.example.test/?a=1&b=2'))


@pytest.mark.parametrize('purpose,minutes', [('login', 5), ('reset', 10), ('change', 10), ('email', 10)])
def test_verification_code_is_private_copyable_and_kept_in_both_mime_bodies(service, purpose, minutes):
    message = service._build_password_reset_code_message('012345', minutes, purpose=purpose)
    assert message.is_multipart()
    assert message['To'] == 'Undisclosed recipient:;'
    assert '012345' not in str(message['Subject'])
    assert '012345' not in message['From']
    for kind in ('plain', 'html'):
        content = message.get_body(preferencelist=(kind,)).get_content()
        assert '012345' in content  # Keep the leading zero and contiguous selectable digits.
        assert f'Expires in {minutes} minutes' in content
        assert 'link expires' not in content.lower()
    markup = Markup(message.get_body(preferencelist=('html',)).get_content())
    assert markup.links == []  # Account email never invents an action URL or external code service.
    assert not {'script', 'form', 'input', 'iframe'} & set(markup.tags)
    assert len(markup.images) == 1
    assert markup.images[0]['src'] == 'https://mango-point-projects.vercel.app/brand/mangopoint-logo-v2.png'
    assert markup.images[0]['alt'] == 'MangoPoint mango logo'
    assert markup.images[0]['width'] == markup.images[0]['height'] == '48'
    template = verification_email('012345', minutes, purpose=purpose)
    preview = template.html.split('<div aria-hidden="true"', 1)[1].split('</div>', 1)[0]
    assert '012345' not in preview


def test_alert_keeps_all_supplied_details_actions_and_reference_in_html_and_plain_text(service):
    summary = "Source: manual assumption. Orchard 'A & B'. Expected time: Oct 20, 7 AM."
    actions = ['Inspect fruitlets; do not infer observed infestation.', 'Record 2.5 mm rainfall & field findings.',
               'Use the existing plan.\nKeep the second line.']
    message = summary + '\n\nRecommended actions:\n' + '\n'.join(f'{i}. {text}' for i, text in enumerate(actions, 1))
    email = service._build_message('[MangoPoint] HIGH Condition Alert', message, 'alert-123<&>')
    plain = email.get_body(preferencelist=('plain',)).get_content()
    assert message in plain
    markup = Markup(email.get_body(preferencelist=('html',)).get_content())
    text = ' '.join(' '.join(markup.text).split())
    assert summary in text
    for action in actions:
        assert ' '.join(action.split()) in text
    assert 'alert-123<&>' in text
    assert 'HIGH Condition Alert' in text
    assert markup.links == ['https://mangopoint.example.test/?a=1&b=2']
    assert len(markup.images) == 1
    assert markup.images[0]['src'].endswith('/brand/mangopoint-logo-v2.png')


def test_unknown_message_formats_keep_all_original_text_instead_of_dropping_sections():
    message = 'Unstructured alert.\n\nRecommended actions:\nDo not discard this unnumbered section.\nMore details.'
    markup = Markup(alert_email_html('Notice', message, 'reference', ''))
    content = ' '.join(' '.join(markup.text).split())
    assert ' '.join(message.split()) in content
    assert not markup.links


def test_dynamic_email_text_cannot_inject_markup_or_links(service):
    payload = '<img src=x onerror="alert(1)"><script>bad()</script> & "quoted"'
    email = service._build_message(payload, payload + '\n\nRecommended actions:\n1. ' + payload, payload)
    markup = Markup(email.get_body(preferencelist=('html',)).get_content())
    assert not {'script', 'iframe'} & set(markup.tags)
    assert len(markup.images) == 1
    assert 'onerror' not in markup.images[0]
    assert payload in ''.join(markup.text)
    assert markup.links == ['https://mangopoint.example.test/?a=1&b=2']
    verification = Markup(verification_email(payload, 5, purpose='login').html)
    assert 'script' not in verification.tags
    assert len(verification.images) == 1
    assert 'onerror' not in verification.images[0]


@pytest.mark.parametrize('url', ['', 'javascript:alert(1)', 'data:text/html,test', '//example.test',
                                 'https://user:password@example.test', 'http://[invalid'])
def test_dashboard_button_is_omitted_for_missing_or_unsafe_urls(url):
    assert Markup(alert_email_html('Alert', 'Inspect the orchard.', 'reference', url)).links == []


def test_line_breaks_cannot_create_extra_alert_headers(service):
    email = service._build_message('Alert\r\nBcc: other@example.test', 'Summary', 'reference')
    assert email['Bcc'] is None
    assert '\n' not in str(email['Subject'])
