# Mawid backend

This imported project is a Python 3.11 FastAPI backend using SQLite. Keep its existing structure and stack.

## Running

- Use Replit's **Run** button to start the **Mawid backend** workflow.
- Command: `python -m uvicorn main:app --host 0.0.0.0 --port 5000`
- The preview root redirects to `/docs` because no frontend was imported.
- Interactive API docs: `/docs`; health check: `/api/health`.
- Dependencies are listed in `requirements.txt`.
- Tests: `python -m pytest -q`. Tests use a separate temporary SQLite database.
- Post-merge setup: `scripts/post-merge.sh` installs dependencies and runs tests non-interactively; Replit then reconciles workflows. It does not reset or migrate the runtime database.

## Configuration

- Required secrets: `HMAC_KEY` and `SIGNING_SECRET`, with distinct long random values. Both are configured in Replit Secrets; never commit their values.
- Optional secret: `ANTHROPIC_API_KEY`. Without it, chat uses the included rule-based assistant.
- `DEMO_MODE` defaults to `true`: authentication is optional and the provider uses fake banking data. This setup is for a demo, not real banking or production use.
- SQLite defaults to `mawid.db` in the project directory; `MAWID_DB` can override its path. Do not commit runtime databases.

## Trying the demo

Call `POST /api/consent` with `{"bank_id":"demo1"}` to initialize demo data, then try `/api/summary`, `/api/plans`, `/api/scenarios`, and `/api/chat` in the docs.
Consent creation and `/api/demo/reset` reset the demo data. No live bank connection is configured.