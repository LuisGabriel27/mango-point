"""Write synthetic email previews locally without accounts, API calls or delivery.

Usage: python -m scripts.preview_emails
"""

import argparse
from html import escape
from pathlib import Path

from api.services.email_templates import alert_email_html, verification_email


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('outputs/email-design-preview'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    links = []
    for purpose, minutes in [('login', 5), ('reset', 10), ('change', 10), ('email', 10)]:
        template = verification_email('123456', minutes, purpose=purpose)
        filename = f'{purpose}.html'
        (args.output / filename).write_text(template.html, encoding='utf-8')
        links.append((filename, template.subject))
    # Fictional content for layout inspection only; not an orchard record,
    # generated simulation result or field finding.
    sample_message = (
        "Forecast conditions may be suitable for fruit-attacking Cecid in the sample orchard. "
        "Review the saved forecast and inspect susceptible fruitlets.\n\n"
        "Recommended actions:\n"
        "1. Inspect fruitlet-stage trees during the indicated activity window.\n"
        "2. Check susceptible fruit for symptoms and record what you find.\n"
        "3. Review field observations before treatment decisions."
    )
    (args.output / 'alert.html').write_text(alert_email_html(
        '[MangoPoint] HIGH Condition Alert', sample_message, 'sample-alert-preview-only',
        'https://mango-point-projects.vercel.app',
    ), encoding='utf-8')
    links.append(('alert.html', 'Pest alert — fictional layout sample'))
    items = ''.join(f'<li><a href="{name}">{escape(title)}</a></li>' for name, title in links)
    (args.output / 'index.html').write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>MangoPoint email previews</title>'
        '<body style="max-width:720px;margin:40px auto;padding:0 20px;font:16px/1.6 Arial;color:#203e2a">'
        '<h1>MangoPoint email previews</h1>'
        '<p>Synthetic codes and fictional alert content for design review. '
        'No email was sent and no application records were created.</p>'
        f'<ul>{items}</ul><p>Resize the browser or use its dark appearance to inspect the layout. '
        'A browser preview does not reproduce every email client.</p></body></html>', encoding='utf-8',
    )
    print(f'Local previews written to {args.output / "index.html"}. No messages sent.')


if __name__ == '__main__':
    main()
