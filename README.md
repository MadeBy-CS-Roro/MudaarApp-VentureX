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

## Production safeguards

Set `MAWID_ENV=production` (or `DEMO_MODE=false`) to enable production safeguards. Configure distinct random `HMAC_KEY` and `SIGNING_SECRET` values with at least 32 characters each, and set `ALLOWED_ORIGINS` to comma-separated exact HTTPS origins (no paths or wildcards). The service refuses to start if production configuration is missing or invalid.

All protected production routes require a signed bearer token with `mode=production` and a `sub` matching a provisioned user's HMAC. `/api/consent`, `/api/demo/reset`, and `/api/demo/next-month` are demo-only and return 404 in production. Production identity/token issuance and bank enrollment are not included; set up an approved identity and banking flow before onboarding real users. No real bank connection or storage migration is part of this backend.

## Demo numbers (tested)
Safe to spend 600 = 8,700 − 4,100 − 3,500 − 500. Spent 420, available 180.
Phone 3,000 in 4 payments: short 570 now, fits next month with 150 left in the tightest month.
After "next month": Tabby ends, safe to spend 900, phone notification fires.
