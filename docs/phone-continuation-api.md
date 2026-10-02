# Phone continuation integration contract

The new uploaded continuation instructions are authoritative; preserve the existing expense/date/description merge, onboarding, confirmations, assistant, contact form, sample offers, wishlist PATCH, and phone-width RTL design.

Backend is owned by main agent. UI is owned by design helper (static files only).

## Budget
- GET and PUT /api/budget. PUT {essentials_pct,personal_pct,savings_pct}, integer 0..100, sum exactly 100. Default 70/20/10. Per-user storage.
- Response {targets:{essentials_pct,personal_pct,savings_pct},actual:[{id,label,amount,pct}],target:[{id,label,amount,pct}],warnings:[{type,message,...}],salary}. Actual IDs essentials/personal/savings/remaining, target IDs essentials/personal/savings. Labels الأساسيات، شخصية، الادخار، متبقي. All figures server-derived. Monthly savings is recorded deposits, not cumulative wishlist savings. Existing budget pie renderer can be reused for these runtime API values.
- Summary includes budget, entitlements, and budget warnings in alerts (type personal_budget_exceeded or personal_budget_heads_up, message). Display these on overview and expenses. Noura essentials actual 7600, pct 87; budget warning message "التزاماتك 87% من راتبك، أعلى من هدفك 70%".

## Offers / saving deadline
- POST /api/offers {price,target_months?:integer 1..36}. Plus/Premium only; 403 Basic, Arabic detail and feature "planner".
- Existing offers[] and best_offer_id retained; each offer has reason string.
- save retains old fields, adds target_months, required_months (number of deposits INCLUDING this month), reachable_in_target (bool or null), max_target, warning string|null. For N=3 / price3000 / savings10%, max_target1920, required_months5, buyK4. Do not reinterpret existing buyK as deposit count.
- Recommended badge changes to الأنسب لك. Only recommended offer initially, expand others with عرض العروض الثانية and allow selection. Save-first below same-width, with input "بكم شهر تبي توصل للهدف؟". Show two working options if insufficient: set target_months to required_months; or set buy-price to max_target and recalculate. Separate buttons أضف للأمنيات on selected offer and save plan, use existing POST /api/wishlist. Existing global button may be removed/reused; preserve wishlist fields and badge refresh.
- Locked planner shows lock + ترقية linking #subscriptions. Do not call planner API for Basic beyond handling a 403.

## Subscriptions
- GET /api/subscriptions returns {current:{id,name,price,...},tiers:[{id,name,price,obligation_limit,smart_account,planner,forecast,features}],demo_mode}.
- POST /api/demo/subscription {plan:"basic"|"plus"|"premium"} demo-only, persisted per user. No payments. Returns subscription response.
- GET /api/account retains contact/profile, adds entitlements {plan,obligation_limit,smart_account,planner,forecast} and current subscription id. Noura defaults Plus.
- #account shows current plan and الباقات button, not full comparison. Add #subscriptions separate page (no sixth bottom tab), comparison rows=features, columns=plans, demo plan switch labeled تبديل الباقة (للديمو). Paid non-demo controls stay قريباً, no invented payment flow.
- GET /api/smart-account (Plus/Premium) {months:[{k,label,date,available,safe_to_spend}],wishes:[{id,name,when_label,...}],assumption}. Three future months, future buying times.
- GET /api/forecast (Premium only) {months:[{k,label,date,salary,obligations,essentials,buffer,available,safe_to_spend,saving_cap}],assumption}, 12 months including current.
- Premium forecast section and smart account can live in حسابي. Basic smart lock / Basic+Plus forecast lock link #subscriptions.
- Basic still sees current-month values and wishlist affordability now; future when_label redacted to a locked label.
- /api/obligations response adds limit,hidden_count,locked_message,active_items; active_items contains first N active obligations. previous_payments contains completed plans. Legacy items includes visible active and completed records for backward compatibility: don't render archive rows twice. Render locked upsell if hidden_count>0. Basic 5 / Plus30 / Premium null. Totals use ALL obligations regardless of visibility. /api/plans similarly caps visibility.
- Plan creation/edit/pay-all hidden items enforce 403 on backend. Creation at cap rejected; completed archive does not consume active-plan limit.
- Plan objects include pay_all_total (additional settlement quote), pay_all_reserved (already budgeted current installment), and pay_all_gross. For multiple remaining payments, the quote is extra beyond this month's reservation: Tamara600 additional,600 reserved,1200 gross. For one unpaid payment it is the current payment and reserved0. POST /api/plans/{id}/pay-all records settlement, NOT a bank transfer; explicit confirmation required. Response {ok,amount,reserved_current,gross,already_paid}. This month's reserved installment remains in the formula, additional prepayment lowers current available, future installments are freed. Refresh overview/obligations.
- After demo next month, Tabby goes into previous_payments and displayed in المدفوعات السابقة, not active obligations.

## Appearance
- فاتح / داكن / حسب الجهاز under المظهر in account. Only appearance setting and existing session token may be in localStorage. Apply all app CSS variables including body, onboarding, sheets, chart labels, inputs, badges, chat, toast, focus states. Respect prefers-color-scheme live in system mode; no flash if feasible.
- Keep five bottom tabs; centered frame max430 on desktop, usable at390. All app copy casual Saudi Arabic masculine singular. No emojis. Financial numbers and quotas from API.