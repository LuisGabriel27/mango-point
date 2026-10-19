# Email notification redesign, 2026-10-19

Account-code and pest-alert emails now share a compact MangoPoint header with
the mango-only mark, green palette, rounded card, readable spacing and plain-text
alternative.
The design lives in `api/services/email_templates.py`; the notification service
builds its ordinary MIME messages from these templates. Delivery still uses the
existing configured SMTP or Brevo transport and existing recipient rules.
Brevo requests now also include the generated plain-text body through its
documented [`textContent` field](https://developers.brevo.com/reference/send-transac-email),
alongside the redesigned HTML.

## Layout and content

Sign-in, password reset, password change and recovery-email change each have a
short purpose-specific heading and instruction. A prominent code panel keeps all
six digits as one selectable text value, including leading zeros, followed by
the actual supplied expiry and single-use guidance. All four subjects omit the
code, including password reset. A hidden inbox preview describes the task and
expiry without exposing the code. Expiry copy refers to a code, not a link.

Pest alerts retain the supplied subject/severity label, full summary, reference
ID and recommendations. The existing `Recommended actions` section becomes
numbered rows under **What to do next**. Unknown message formats retain all their
text rather than losing an unrecognized section. The dashboard button uses the
configured HTTP(S) app URL; it is omitted if that URL is absent or unsafe. The
reference is placed at the bottom so it does not interrupt the main explanation.
Alert generation, model claims, recommendations and treatment decisions are
unchanged. No forecast or field evidence is fabricated by the template.

The layout uses presentation tables, inline baseline CSS and system fonts.
The header uses the existing mango-only PNG from the deployed frontend at
`https://mango-point-projects.vercel.app/brand/mangopoint-logo-v2.png`, displayed
at 48 by 48 pixels. It replaces the initial M badge, without using the image
wordmark. The ordinary MangoPoint text and category remain readable if a client
blocks images; the image also has descriptive alternative text. The original
transparent image is reused without alteration. Email clients may request this
public asset to display it; no account data or code is included in its URL.
Width media rules tighten spacing on phones. A dark
palette is supplied for clients that support color-scheme media queries. Gmail
and other clients can still transform colors or ignore unsupported styles; the
browser dark preview does not emulate Gmail iPhone's automatic color processing.
See [Google's supported email CSS](https://developers.google.com/workspace/gmail/design/css),
[table support](https://www.caniemail.com/features/html-table/) and
[dark media-query support](https://www.caniemail.com/features/css-at-media-prefers-color-scheme/).

The sender name/avatar, Gmail's External or Inbox badges, unsubscribe interface,
reply/forward controls and other email-client chrome are separate from the HTML
body. This redesign does not change them or the configured sender identity.

## Preview and checks

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_emails
```

Open `outputs/email-design-preview/index.html` for all five HTML previews.
They use synthetic code `123456` and fictional alert content, with no API calls,
account access, email delivery, simulation execution or saved application data.
The local contact sheet is
`outputs/email-design-preview/email-design-contact-sheet.png`.
The subsequent mango-logo previews are in `outputs/email-logo-preview/`,
including `email-logo-contact-sheet.png` and `index.html`. Earlier previews are
preserved so they still document the initial redesign.

Executed checks:

- Full Python regression suite: **979 passed**, with one existing
  Starlette/httpx deprecation warning. Results are in
  `outputs/email-redesign-full-python.log`.
- Targeted Python template, notification, password and session regressions:
  **52 passed**. Coverage includes MIME bodies, leading zeros, code-free subjects
  and inbox previews, escaping, supplied content retention, private recipients,
  safe dashboard links and existing email-code authentication behavior.
  The final focused rerun also verifies that Brevo receives plain text alongside
  HTML; results are in `outputs/email-redesign-targeted-final-python.log`.
- Headless Edge rendered all five templates at **320, 390 and 760 pixels**, in
  light and dark schemes: **30 renders passed without horizontal overflow**.
  Removing the embedded style block also fit at 320 pixels, checking the inline
  CSS fallback. These are local HTML rendering checks, not inbox-client passes.
- The sign-in, reset and alert contact sheet was visually inspected, including
  the full alert/footer, readable code and both color schemes.

The later mango-logo change passed **28 targeted template, delivery and
password-reset tests** (`outputs/email-logo-tests.log`). The published logo
returned HTTP 200 with `image/png`, and its SHA-256 matched the existing
repository PNG. All **30 browser renders** were repeated with that verified
image fulfilled locally: the 48-pixel logo loaded in every template, width and
appearance. The inline-only fallback and an additional image-blocked layout
check both fit at 320 pixels. The updated contact sheet was visually inspected.
These logo-specific checks are in `outputs/email-logo-preview/`; the earlier
full-suite and redesign outputs above remain preserved. No delivery to a real
inbox was performed for the logo change.

Logs and images are in ignored `outputs/email-design-preview/` and
`outputs/email-redesign-*.log`. No manual workflow result was marked Pass.
Actual Gmail iPhone, Apple Mail and Outlook inbox rendering remain untested.
To rehearse delivery, use normal dedicated-test-account flows after activation
and check the newly received message in both client appearances. Existing inbox
messages retain their original HTML and cannot be restyled by a code update.

## Release state

The initial design and logo checks above preceded activation. On October 19,
2026, the server laptop's stale FastAPI process was replaced with a process
started at 14:20:14 (Asia/Manila), after both template files were updated. Local
and published API health checks passed. See the
[activation record](email-template-activation-2026-10-19.md) for the process and
verification evidence. Real inbox rendering of a newly generated email remains
to be checked; no test email was requested during activation checks.

The redesign source remains uncommitted and unpushed, but the restarted laptop
API now loads these local files. Future server-side template updates also need
an API restart, or an image rebuild if using Docker. A frontend Vercel deployment
alone cannot update server-generated email HTML. No frontend code, dependency,
account, recipient configuration or Supabase schema change was needed. Existing
deployment notes and the modified access-site submodule were preserved.
