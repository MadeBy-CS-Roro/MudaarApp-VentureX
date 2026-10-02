# Mawid backend

This imported project is a Python 3.11 FastAPI backend using SQLite. Keep its existing structure and stack.

## Running

- Use Replit's **Run** button to start the **Mawid backend** workflow.
- Command: `python -m uvicorn main:app --host 0.0.0.0 --port 5000`
- The preview root serves the uploaded Arabic RTL frontend from `static/index.html`, linked to the existing API through relative same-origin URLs.
- Interactive API docs: `/docs`; health check: `/api/health`.
- Dependencies are listed in `requirements.txt`.
- Tests: `python -m pytest -q`. Tests use a separate temporary SQLite database.
- Optional interactive phone checks: `python scripts/verify_phone_browser.py` uses existing Chromium and a temporary test database; it never resets the running app's data.
- Post-merge setup: `scripts/post-merge.sh` installs dependencies and runs tests non-interactively; Replit then reconciles workflows. It does not reset or migrate the runtime database.

## Publishing

- Publishing must start the ASGI server: `python -m uvicorn main:app --host 0.0.0.0 --port 5000`. Running `python main.py` alone only imports the app and exits.
- Publishing settings take effect only after republishing.
- The current publishing target is Autoscale. The local SQLite database is suitable for a resettable demo, not durable published user data: the published filesystem is not persistent. Do not migrate the database or change deployment type without approval.

## Configuration

- Required secrets: `HMAC_KEY` and `SIGNING_SECRET`, with distinct long random values. Both are configured in Replit Secrets; never commit their values.
- Optional secret: `ANTHROPIC_API_KEY`. Without it, chat uses the included rule-based assistant.
- Demo mode is the default (`MAWID_ENV=demo`, or unset): authentication is optional and the provider uses fake banking data. This setup is for a demo, not real banking or production use.
- To enable production safeguards, set `MAWID_ENV=production` (or the compatible `DEMO_MODE=false`). Production requires distinct random `HMAC_KEY` and `SIGNING_SECRET` values of at least 32 characters, plus `ALLOWED_ORIGINS` as a comma-separated list of exact HTTPS origins without paths or wildcards. The app refuses to start if these settings are missing or invalid.
- Production API requests require a signed bearer token with a `mode` claim of `production` and a `sub` matching a provisioned user's HMAC. Demo consent, reset, and next-month simulation routes are unavailable in production. This backend does not yet include production identity/token issuance or real bank enrollment; connect an approved identity/banking flow before onboarding real users.
- SQLite defaults to `mawid.db` in the project directory; `MAWID_DB` can override its path. Do not commit runtime databases.
- SQLite backups must run daily at 02:00 UTC and before releases that change database data or schema. Configure an operator-controlled scheduler to run `python scripts/backup_db.py backup --database "${MAWID_DB:-mawid.db}" --backup-dir /secure/off-instance/mawid --retention-days 30`; the destination must be private, encrypted, durable, and outside the project/deployment filesystem. The script creates owner-only snapshots and prunes expired snapshots after a successful backup, but does not encrypt files or configure the scheduler/storage.
- Backups are sensitive financial data. Limit access to the service/operator account and named recovery operators, use least privilege, and keep access auditable. Retain snapshots for 30 days; perform monthly restore drills only with synthetic data. Do not onboard real financial data until encrypted off-instance storage, scheduling, and recovery have been verified. See the "SQLite backups and recovery" section in `README.md` for recovery steps.

## Trying the demo

Open the preview and use the demo bank onboarding when prompted. You can also call `POST /api/consent` with `{"bank_id":"demo1"}` to initialize demo data, then try `/api/summary`, `/api/plans`, `/api/scenarios`, and `/api/chat` in the docs.
Consent creation and `/api/demo/reset` reset the demo data. No live bank connection is configured.


## Phone app scope

Backend updates are approved. Port uploaded features selectively while preserving current security, production safeguards, backups, and wishlist fixes. Do not replace the backend wholesale.
Manual flexible expense entry, dated history, and manual-only deletion use `/api/expenses`; bank-derived transactions remain read-only in that history.
All screens are Arabic RTL, purple/teal, phone-first (390px); desktop keeps a centered frame no wider than 430px. Preserve provider demo data and the safe-to-spend formula. Only the session token and per-device appearance choice may be stored in localStorage. Budget targets and subscription are server-owned per-user data. Assistant writes require explicit, expiring, one-time confirmation.
Use consistent casual Saudi Arabic, address the user in masculine singular, and greet with "هلا نورة". Use هالشهر، الشهر الجاي، الحين، شهور، ر.س. Shared number agreement comes from the language API.
The assistant includes five questions per salary cycle; confirmation/cancellation does not count as another question. Demo reset clears usage. No paid checkout is implemented. Demo Noura starts Plus and can switch tiers without payment; production cannot call the demo switch.
Budget targets default 70/20/10 and must total 100. Actual essentials combine plans and usual essentials; remaining includes the safety buffer. Savings deadlines count this month's deposit as period one, unlike elapsed `buyK`: 3000 at 10% requires five deposits, four future months; three deposits reach 1920. The user's savings target drives the shared saving rule.
Subscriptions limit active obligations to Basic5 / Plus30 / Premiumunlimited without changing totals. Basic has no smart-account or planner access; Plus adds both; only Premium gets a 12-month financial forecast. Completed plans appear in previous payments rather than active obligations.
Contact form submissions are stored locally and rate limited. Public email/WhatsApp links need the non-secret settings `MAWID_CONTACT_EMAIL` and `MAWID_CONTACT_WHATSAPP`; do not invent owner contact details.
