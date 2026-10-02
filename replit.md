# Mawid backend

This imported project is a Python 3.11 FastAPI backend using SQLite. Keep its existing structure and stack.

## Running

- Use Replit's **Run** button to start the **Mawid backend** workflow.
- Command: `python -m uvicorn main:app --host 0.0.0.0 --port 5000`
- The preview root serves the uploaded Arabic RTL frontend from `static/index.html`, linked to the existing API through relative same-origin URLs.
- Interactive API docs: `/docs`; health check: `/api/health`.
- Dependencies are listed in `requirements.txt`.
- Tests: `python -m pytest -q`. Tests use a separate temporary SQLite database.
- Post-merge setup: `scripts/post-merge.sh` installs dependencies and runs tests non-interactively; Replit then reconciles workflows. It does not reset or migrate the runtime database.

## Configuration

- Required secrets: `HMAC_KEY` and `SIGNING_SECRET`, with distinct long random values. Both are configured in Replit Secrets; never commit their values.
- Optional secret: `ANTHROPIC_API_KEY`. Without it, chat uses the included rule-based assistant.
- Demo mode is the default (`MAWID_ENV=demo`, or unset): authentication is optional and the provider uses fake banking data. This setup is for a demo, not real banking or production use.
- To enable production safeguards, set `MAWID_ENV=production` (or the compatible `DEMO_MODE=false`). Production requires distinct random `HMAC_KEY` and `SIGNING_SECRET` values of at least 32 characters, plus `ALLOWED_ORIGINS` as a comma-separated list of exact HTTPS origins without paths or wildcards. The app refuses to start if these settings are missing or invalid.
- Production API requests require a signed bearer token with a `mode` claim of `production` and a `sub` matching a provisioned user's HMAC. Demo consent, reset, and next-month simulation routes are unavailable in production. This backend does not yet include production identity/token issuance or real bank enrollment; connect an approved identity/banking flow before onboarding real users.
- SQLite defaults to `mawid.db` in the project directory; `MAWID_DB` can override its path. Do not commit runtime databases.

## Trying the demo

Open the preview and use the demo bank onboarding when prompted. You can also call `POST /api/consent` with `{"bank_id":"demo1"}` to initialize demo data, then try `/api/summary`, `/api/plans`, `/api/scenarios`, and `/api/chat` in the docs.
Consent creation and `/api/demo/reset` reset the demo data. No live bank connection is configured.

## Frontend scope

Only the uploaded frontend and its icons/manifest were integrated; uploaded backend files were not copied over existing fixes.
Expense and obligation views use the existing summary API. Manual expense entry and payment-plan creation/deletion are unavailable in the current backend and must not be presented as working.
