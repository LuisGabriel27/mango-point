"""Presentation-only email templates. No delivery, settings or account access."""

from dataclasses import dataclass
from html import escape
import re
from urllib.parse import urlsplit


_MANGO_LOGO_URL = 'https://mango-point-projects.vercel.app/brand/mangopoint-logo-v2.png'


@dataclass(frozen=True)
class VerificationEmail:
    subject: str
    text: str
    html: str


def _paragraphs(value: str) -> str:
    return "".join(
        '<p class="body-copy" style="margin:0 0 14px;color:#35463c;font-size:15px;line-height:1.6;overflow-wrap:break-word;">'
        + escape(part).replace("\n", "<br>") + "</p>"
        for part in re.split(r"\n\s*\n", value.strip()) if part.strip()
    )


def _shell(*, title: str, preview: str, category: str, content: str, footer: str) -> str:
    """Inline styles are the baseline; media rules enhance supporting clients."""
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>{escape(title)}</title>
  <style>
    body, table, td, a {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
    table, td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; }}
    table {{ border-spacing:0; }}
    a[x-apple-data-detectors] {{ color:inherit !important; text-decoration:none !important; }}
    @media screen and (max-width:480px) {{
      .outer-pad {{ padding:16px 10px !important; }}
      .card-pad {{ padding:24px 20px !important; }}
      .brand-pad {{ padding:20px !important; }}
      .email-title {{ font-size:25px !important; }}
      .verification-code {{ font-size:34px !important; letter-spacing:7px !important; }}
    }}
    @media (prefers-color-scheme:dark) {{
      .email-bg {{ background-color:#101a15 !important; }}
      .email-card {{ background-color:#19271f !important; border-color:#35473b !important; }}
      .heading, .brand-name {{ color:#edf6ec !important; }}
      .body-copy, .action-copy {{ color:#d2ddd3 !important; }}
      .muted, .footer-copy {{ color:#b0c1b4 !important; }}
      .divider {{ border-color:#35473b !important; }}
      .code-panel {{ background-color:#233d2c !important; border-color:#48684e !important; }}
      .verification-code {{ color:#e2f5ce !important; }}
      .code-label {{ color:#bfd2b5 !important; }}
      .notice {{ background-color:#3e3421 !important; color:#f3d69b !important; }}
      .action-number {{ background-color:#2c4633 !important; color:#d9eccb !important; }}
      .cta {{ background-color:#c4dda5 !important; color:#183623 !important; border-color:#c4dda5 !important; }}
    }}
  </style>
</head>
<body class="email-bg" style="margin:0;padding:0;width:100%;background-color:#f3f5ef;font-family:Arial,Helvetica,sans-serif;">
  <div aria-hidden="true" style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">{escape(preview)}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="email-bg" style="background-color:#f3f5ef;">
    <tr><td align="center" class="outer-pad" style="padding:28px 16px;">
      <!--[if mso]><table role="presentation" width="560"><tr><td><![endif]-->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="email-card" style="max-width:560px;background-color:#ffffff;border:1px solid #dce4d7;border-radius:18px;">
        <tr><td class="brand-pad divider" style="padding:24px 28px;border-bottom:1px solid #e5eadf;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td width="48" height="48" align="center" valign="middle">
              <img src="{_MANGO_LOGO_URL}" alt="MangoPoint mango logo" width="48" height="48" style="display:block;width:48px;height:48px;border:0;outline:none;text-decoration:none;">
            </td>
            <td style="padding-left:10px;">
              <p class="brand-name" style="margin:0;color:#203e2a;font-size:19px;font-weight:bold;line-height:1.25;">MangoPoint</p>
              <p class="muted" style="margin:4px 0 0;color:#63745f;font-size:10px;line-height:1.3;letter-spacing:1.2px;">{escape(category)}</p>
            </td>
          </tr></table>
        </td></tr>
        <tr><td class="card-pad" style="padding:28px;">{content}</td></tr>
      </table>
      <!--[if mso]></td></tr></table><![endif]-->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;">
        <tr><td align="center" class="footer-copy" style="padding:18px 14px 0;color:#687662;font-size:11px;line-height:1.6;">{escape(footer)}</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>'''


def verification_email(code: str, expires_minutes: int, *, purpose: str = "reset") -> VerificationEmail:
    details = {
        "login": ("Your MangoPoint sign-in code", "Confirm your sign-in", "Enter this code in MangoPoint to finish signing in."),
        "reset": ("Your MangoPoint password reset code", "Reset your password", "Enter this code in MangoPoint to choose a new password."),
        "change": ("Confirm your MangoPoint password change", "Confirm password change", "Enter this code in Account settings to change your password."),
        "email": ("Confirm your MangoPoint recovery email change", "Confirm email change", "Enter this code in Account settings to update your recovery email."),
    }
    subject, title, instruction = details.get(purpose, details["reset"])
    advice = ("Didn't try to sign in? Do not use this code. Review your account password."
              if purpose == "login" else "Didn't request this? You can ignore this email; your account details have not changed.")
    expiry = f"Expires in {expires_minutes} {'minute' if expires_minutes == 1 else 'minutes'}"
    text = (f"MangoPoint | Account security\n\n{title}\n{instruction}\n\n"
            f"Your verification code: {code}\n{expiry}. Use this code once.\n\n"
            f"Never share this code with anyone.\n{advice}\n")
    content = f'''
      <h1 class="email-title heading" style="margin:0 0 12px;color:#203e2a;font-size:28px;line-height:1.2;letter-spacing:-0.5px;">{escape(title)}</h1>
      <p class="body-copy" style="margin:0;color:#35463c;font-size:15px;line-height:1.6;">{escape(instruction)}</p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
        <tr><td align="center" class="code-panel" style="padding:22px 12px;background-color:#f0f5e8;border:1px solid #d4e1c5;border-radius:12px;">
          <p class="code-label" style="margin:0 0 10px;color:#536b40;font-size:10px;font-weight:bold;letter-spacing:1.4px;line-height:1.4;">YOUR VERIFICATION CODE</p>
          <p class="verification-code" style="margin:0;padding-left:8px;color:#224b35;font-family:Consolas,'Courier New',monospace;font-size:38px;font-weight:bold;letter-spacing:8px;line-height:1.2;white-space:nowrap;">{escape(code)}</p>
          <p class="code-label" style="margin:12px 0 0;color:#536b40;font-size:12px;line-height:1.5;">{escape(expiry)} &middot; Use once</p>
        </td></tr>
      </table>
      <p class="heading" style="margin:0 0 8px;color:#203e2a;font-size:13px;font-weight:bold;line-height:1.5;">Never share this code with anyone.</p>
      <p class="muted" style="margin:0;color:#63745f;font-size:12px;line-height:1.6;">{escape(advice)}</p>'''
    return VerificationEmail(subject, text, _shell(
        title=title, preview=f"{title}. {expiry}.", category="ACCOUNT SECURITY",
        content=content, footer="MangoPoint · Automated account email",
    ))


def _alert_content(message: str) -> str:
    """Format the existing alert text; do not infer facts or alter recommendations."""
    summary, marker, recommendations = message.strip().partition("\n\nRecommended actions:\n")
    if not marker or not re.match(r"^\d+\.\s+", recommendations):
        return _paragraphs(message)
    actions = re.split(r"(?m)^\d+\.\s+", recommendations)[1:]
    rows = "".join(
        f'''<tr>
          <td width="30" valign="top" style="padding:0 10px 12px 0;">
            <span class="action-number" style="display:inline-block;width:24px;height:24px;line-height:24px;text-align:center;background-color:#edf3e5;color:#395733;border-radius:12px;font-size:12px;font-weight:bold;">{number}</span>
          </td>
          <td valign="top" class="action-copy" style="padding:0 0 12px;color:#35463c;font-size:14px;line-height:1.6;overflow-wrap:break-word;">{escape(action.strip()).replace(chr(10), '<br>')}</td>
        </tr>'''
        for number, action in enumerate(actions, 1)
    )
    return (_paragraphs(summary)
            + '<h2 class="heading" style="margin:22px 0 14px;color:#203e2a;font-size:16px;line-height:1.4;">What to do next</h2>'
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>')


def alert_email_html(subject: str, message: str, alert_id: str, app_url: str) -> str:
    label = subject.replace("[MangoPoint]", "").strip() or "Orchard notification"
    try:
        parsed = urlsplit(app_url)
        valid_url = parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        valid_url = False
    cta = (f'''<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0;">
      <tr><td class="cta" align="center" style="background-color:#224b35;border:1px solid #224b35;border-radius:9px;">
        <a class="cta" href="{escape(app_url, quote=True)}" style="display:inline-block;padding:13px 22px;background-color:#224b35;border-radius:9px;color:#ffffff;text-decoration:none;font-size:14px;font-weight:bold;line-height:1.4;mso-padding-alt:0;">Open MangoPoint &rarr;</a>
      </td></tr></table>''' if valid_url else "")
    content = f'''
      <p style="margin:0 0 14px;line-height:1.5;"><span class="notice" style="display:inline-block;padding:5px 9px;border-radius:5px;background-color:#fff2d8;color:#845316;font-size:10px;font-weight:bold;letter-spacing:0.5px;">{escape(label)}</span></p>
      <h1 class="email-title heading" style="margin:0 0 16px;color:#203e2a;font-size:28px;line-height:1.2;letter-spacing:-0.5px;">Pest risk alert</h1>
      {_alert_content(message)}
      {cta}
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr><td class="divider" style="padding-top:18px;border-top:1px solid #e5eadf;">
          <p class="muted" style="margin:0 0 8px;color:#63745f;font-size:12px;line-height:1.6;">Inspect the orchard and confirm conditions before treatment decisions.</p>
          <p class="muted" style="margin:0;color:#63745f;font-size:10px;line-height:1.6;overflow-wrap:anywhere;word-break:break-all;">Reference: {escape(alert_id)}</p>
        </td></tr>
      </table>'''
    return _shell(title="MangoPoint pest risk alert", preview="Review the orchard alert and recommended actions in MangoPoint.",
                  category="ORCHARD MONITORING", content=content, footer="MangoPoint · Automated orchard notification")
