# MangoPoint organization inquiries

A separate public website for organizations interested in a MangoPoint
demonstration, licensing or subscription. The private review inbox authenticates
with the existing MangoPoint administrator account and uses its FastAPI data
boundary. Approval records a review decision; it never grants account access.

There are no framework or build dependencies:

```powershell
node build.mjs
node --test tests/submission.test.mjs
node server.mjs
```

Open `http://127.0.0.1:8088/` for the public page or `/review.html` for the inbox.
Allow this origin in the MangoPoint backend for actual API requests.
The API base is declared in `public/api.mjs`; it contains only the public
service address. Records are stored by FastAPI, not by this static website.

The deployment manifest is `.openai/hosting.json`. Preserve its registered
project ID on updates. Source files are in `public/`; `build.mjs` copies them
into `dist/` for hosting. Production publishes the static assets only.

Full application configuration and verification notes are maintained in the
main MangoPoint project's `docs/access-request-website.md`.

For Sites publication on Windows, run the supported source helper with the
installed Git Bash before the WindowsApps Bash launcher on the process PATH.
Set `TAR_OPTIONS=--force-local` for that process so GNU tar treats `C:/...`
archive paths as local files. If the checkout was created by the sandbox user,
scope any Git `safe.directory` allowance to this exact checkout and process.
Pass repository credentials through the helper's hidden stdin only.
