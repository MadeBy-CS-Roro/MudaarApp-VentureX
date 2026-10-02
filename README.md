# Mawid backend

FastAPI + SQLite. The engine does all the math. The assistant only explains tool results.

## Run on Replit
1. Copy these files into the project (keep your old Blind Trust folder separate).
2. Secrets: `HMAC_KEY`, `SIGNING_SECRET` (already there). Optional: `ANTHROPIC_API_KEY` for the real LLM.
   Without it, the assistant uses rule-based answers with the same tools, so the demo always works.
3. `pip install -r requirements.txt`
4. Run: `uvicorn main:app --host 0.0.0.0 --port 8000`
5. Open `/docs` to try every endpoint. Run `pytest -q` to check the demo numbers.
6. Put the front end in `static/index.html` to serve it from `/`.

## Files
| File | What it does | Owner |
|---|---|---|
| `engine.py` | Safe to spend, scenarios, wishlist rule. Pure functions. | Reema |
| `detect.py` | Plan detection, categories, validation checks, essentials average | Reema / Ghala |
| `security.py` | HMAC hashing, signed tokens, rate limiter | Reema |
| `main.py` | API routes, input validation, auth | Ghala |
| `assistant.py` | Tool calling + offline fallback | Ghala |
| `db.py` | Schema, audit log | Lilyan |
| `provider.py` | Fake open banking data (Noura) | Lilyan |
| `service.py` | Glue: DB -> detection -> engine | Ghala |

## Endpoints
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/consent` | `{bank_id}` | `consent_id, token, plans_found, unknown_merchants` (also resets the demo) |
| DELETE | `/api/consent` | | revokes and deletes transactions and plans |
| GET | `/api/plans` | | plans with `remaining`, `action` |
| POST | `/api/plans/{id}/confirm` | `{amount?, remaining?}` | updated plans |
| GET | `/api/summary` | | `available, safe_to_spend, spent, formula, plans[], alerts[], categories` |
| POST | `/api/scenarios` | `{price}` | `cash, bnpl4, fin12` (monthly, total, tight, tightK, ok, earliest) + `save` (buyK) |
| GET / POST | `/api/wishlist` | `{name, price, method}` | items with `status.ok`, `when_label` |
| POST | `/api/categories` | `{merchant, category}` | user fixes a category once |
| POST | `/api/chat` | `{message}` | `{reply, tools}` |
| POST | `/api/demo/next-month` | | `events[]`: salary, plan_end, wish_affordable |
| POST | `/api/demo/reset` | | same as consent |

`tightK`, `earliest`, `buyK`: months from now (0 = this month, 1 = next month).
Demo auth: send `Authorization: Bearer <token>` from `/api/consent`; with demo mode enabled (default), the token is optional.

## SQLite backups and recovery

The database remains a local SQLite file (`mawid.db`, or the path in `MAWID_DB`). Backups contain user identifiers, consent records, and financial data, so treat each backup as sensitive as the live database.

### Required operational policy

- Run a verified backup every day at **02:00 UTC**, and again immediately before any release that changes database data or schema. Configure an operator-controlled scheduler to run the command below.
- The destination must be a **private, encrypted, durable location outside the project and deployment filesystem**. Ensure that location is mounted and available before the scheduled job runs. The backup utility rejects destinations inside the project, creates snapshots with owner-only file permissions, and prunes snapshots older than the retention period after a successful backup.
- Restrict create access to the service/operator account and restore access to named, authorized operators who need it for recovery. Use least privilege, keep access auditable, and do not put backups in Git, tickets, chat, or unencrypted personal storage. The utility does not encrypt files itself; encryption at rest and in transit must be provided by the selected storage and transfer method.
- Retain rolling snapshots for **30 days**. Older snapshots are removed on the next successful scheduled backup. A daily schedule means data written since the last successful backup may be lost (up to roughly 24 hours); alert an operator when a scheduled backup fails or is missing.
- Perform a restore drill at least **monthly**, using a separate test database and synthetic data. Do not use a live database for a drill.

This repository supplies the snapshot and restore commands, but it does **not** configure the scheduler or provision encrypted off-instance storage. Do not onboard real financial data until both are configured and a restore drill succeeds.

### Backup, verify, and restore

Run from the project directory. Use the actual private off-instance backup location configured for the environment:

```sh
python scripts/backup_db.py backup \
  --database "${MAWID_DB:-mawid.db}" \
  --backup-dir /secure/off-instance/mawid \
  --retention-days 30

python scripts/backup_db.py verify --database "${MAWID_DB:-mawid.db}"
```

The backup command uses SQLite's online backup API, validates the snapshot's integrity, required tables, and foreign keys, then writes it atomically with mode `0600` into a mode `0700` directory. Keep the destination outside the project and on encrypted storage.

For recovery:

1. Stop the backend so no process is writing to the database.
2. Select the latest known-good backup from the secured off-instance location. Preserve the failed database and any `-wal` / `-shm` sidecars separately in restricted incident storage before replacing anything.
3. Restore to the configured database path. The command validates the backup and refuses to replace an existing database unless the explicit overwrite flag is supplied. It also refuses to restore while SQLite sidecars remain beside the target.

   ```sh
   python scripts/backup_db.py restore \
     /secure/off-instance/mawid/mawid-YYYYMMDDTHHMMSSffffffZ.sqlite3 \
     --database "${MAWID_DB:-mawid.db}" \
     --confirm-overwrite
   ```

4. Verify the restored database, restart the backend, and check that expected users, consent statuses, transactions, and plans are present before resuming service.

The automated restore test uses synthetic users, consents, transactions, and plans; run it with `python -m pytest -q`.

## Production safeguards

Set `MAWID_ENV=production` (or `DEMO_MODE=false`) to enable production safeguards. Configure distinct random `HMAC_KEY` and `SIGNING_SECRET` values with at least 32 characters each, and set `ALLOWED_ORIGINS` to comma-separated exact HTTPS origins (no paths or wildcards). The service refuses to start if production configuration is missing or invalid.

All protected production routes require a signed bearer token with `mode=production` and a `sub` matching a provisioned user's HMAC. `/api/consent`, `/api/demo/reset`, and `/api/demo/next-month` are demo-only and return 404 in production. Production identity/token issuance and bank enrollment are not included; set up an approved identity and banking flow before onboarding real users. No real bank connection or storage migration is part of this backend.

## Demo numbers (tested)
Safe to spend 600 = 8,700 − 4,100 − 3,500 − 500. Spent 420, available 180.
Phone 3,000 in 4 payments: short 570 now, fits next month with 150 left in the tightest month.
After "next month": Tabby ends, safe to spend 900, phone notification fires.
