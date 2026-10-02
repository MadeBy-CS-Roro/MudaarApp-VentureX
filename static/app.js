(() => {
  "use strict";

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
  const number = value => Number(value || 0);
  const format = value => number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const money = value => `${format(value)} ر.س`;
  const toNum = value => Number(String(value ?? "").replace(/[٠-٩]/g, d => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace(/[^\d.]/g, ""));
  let token = null;
  try { token = localStorage.getItem("mawid_token"); } catch (_) {}
  let apiMode = "unknown", started = false, language = null, selectedBank = null;
  let obligationsCache = null, plannerResult = null, chosenMethod = null, wishlistCount = 0, salaryAmount = 0;
  let obTab = "all", planBusy = false, expenseBusy = false, chatBusy = false, offerTimer;
  let expenseToday = "";
  const deletingExpenses = new Set();
  const PAGES = ["overview", "expenses", "obligations", "buy", "account", "wish"];
  const METHOD_LABELS = { cash: "كاش", save: "تجمع أول", fin12: "تمويل 12 شهر" };
  const METHOD_IDS = ["save", "cash", "bnpl3", "bnpl4", "bnpl6", "fin12"];

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(path, { ...options, headers, body: options.body !== undefined ? JSON.stringify(options.body) : undefined });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const raw = data.detail;
      let message = typeof raw === "string" ? raw : "فيه مشكلة بالاتصال، جرّب مرة ثانية.";
      if (/ما فيه حساب مربوط|ابدأ من POST \/api\/consent/.test(message)) message = "اربط حسابك البنكي أول.";
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function saveToken(value) {
    token = value || null;
    try { if (token) localStorage.setItem("mawid_token", token); else localStorage.removeItem("mawid_token"); } catch (_) {}
  }
  function toast(message, type = "good", timeout = 3600) {
    const item = document.createElement("div");
    item.className = `toast ${type}`;
    item.textContent = String(message);
    $("toasts").appendChild(item);
    window.setTimeout(() => item.remove(), timeout);
  }
  function languageForm(kind, n) {
    const forms = language && language[kind];
    const value = Number(n);
    if (!Number.isFinite(value) || !forms) throw new Error("ما قدرنا نحمل صيغ الأعداد. جرّب مرة ثانية.");
    const key = value === 1 ? "one" : value === 2 ? "two" : value >= 3 && value <= 10 ? "few" : "many";
    const template = forms[key];
    if (typeof template !== "string" || !template) throw new Error("ما قدرنا نحمل صيغ الأعداد. جرّب مرة ثانية.");
    return template.replaceAll("{n}", String(value));
  }
  const methodLabel = method => /^bnpl\d+$/.test(String(method)) ? languageForm("payments", Number(String(method).replace("bnpl", ""))) : (METHOD_LABELS[method] || method);
  const monthLabel = k => k === null || k === undefined ? "بعد أكثر من سنة" : Number(k) === 0 ? "هالشهر" : Number(k) === 1 ? "الشهر الجاي" : Number(k) === 2 ? "بعد شهرين" : `بعد ${Number(k)} شهور`;
  const dayLabel = d => Number(d) === 0 ? "اليوم" : `بعد ${esc(languageForm("days", d))}`;
  function showError(error) {
    const message = String(error?.message || "فيه مشكلة بالاتصال، جرّب مرة ثانية.");
    if (error?.status === 401 || error?.status === 404 && message === "اربط حسابك البنكي أول.") {
      saveToken(null);
      if (apiMode === "production") return showOnboardScreen("ob-production");
      return showOnboardScreen("ob-connect");
    }
    toast(message, "error");
  }
  function stat(label, value, tone = "purple", note = "") {
    return `<div class="stat tint-${tone}"><div class="stat-label">${label}</div><div class="stat-value">${value}</div>${note ? `<div class="stat-note">${note}</div>` : ""}</div>`;
  }
  function empty(title, copy) {
    return `<div class="empty-state"><strong>${esc(title)}</strong>${esc(copy)}</div>`;
  }
  function actionControl(action) {
    if (!action) return "";
    if (action.kind === "url" && action.url) {
      try {
        const link = new URL(action.url);
        if (link.protocol !== "https:") return "";
        return `<a class="small-action" href="${esc(link.href)}" target="_blank" rel="noopener noreferrer">${esc(action.label || "افتح جهة التمويل")}</a>`;
      } catch (_) { return ""; }
    }
    if (action.kind === "copy" && action.value) return `<button class="small-action" type="button" data-copy="${esc(action.value)}">${esc(action.label || "نسخ رقم السداد")}</button>`;
    return "";
  }
  document.addEventListener("click", async event => {
    const copy = event.target.closest("[data-copy]");
    if (!copy) return;
    try { await navigator.clipboard.writeText(copy.dataset.copy); toast("نسخنا رقم السداد"); }
    catch (_) { toast(`رقم السداد: ${copy.dataset.copy}`, "good", 6000); }
  });

  function route() {
    if (!started) return;
    const id = (location.hash || "#overview").slice(1);
    const page = PAGES.includes(id) ? id : "overview";
    document.querySelectorAll(".page").forEach(section => section.classList.toggle("active", section.id === `p-${page}`));
    document.querySelectorAll("[data-page]").forEach(link => {
      if (link.dataset.page === page) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    window.scrollTo({ top: 0, behavior: "instant" });
    const loaders = { overview: loadOverview, expenses: loadExpenses, obligations: loadObligations, buy: loadOffers, account: loadAccount, wish: loadWishlist };
    const section = $(`p-${page}`);
    section.querySelectorAll(".screen-error,.screen-loading").forEach(node => node.remove());
    const loading = document.createElement("div");
    loading.className = "screen-loading";
    loading.setAttribute("aria-label", "لحظة، نحمل بياناتك");
    loading.innerHTML = "<i></i><i></i>";
    section.prepend(loading);
    Promise.resolve(loaders[page]?.()).then(() => loading.remove()).catch(error => {
      loading.remove();
      if (error.status === 401 || error.status === 404) return showError(error);
      const panel = document.createElement("div");
      panel.className = "screen-error";
      const text = document.createElement("p");
      text.textContent = error.message || "فيه مشكلة بالاتصال.";
      const retry = document.createElement("button");
      retry.type = "button"; retry.className = "button secondary"; retry.dataset.retryPage = page; retry.textContent = "حاول مرة ثانية";
      panel.append(text, retry);
      section.prepend(panel);
    });
  }
  $("main-content").addEventListener("click", event => {
    if (event.target.closest("[data-retry-page]")) route();
  });
  window.addEventListener("hashchange", route);
  $("open-wishlist").addEventListener("click", () => { location.hash = "#wish"; });

  async function updateWishCount() {
    try {
      const list = await api("/api/wishlist");
      wishlistCount = Array.isArray(list.items) ? list.items.length : 0;
      $("wish-count").textContent = wishlistCount > 99 ? "99+" : wishlistCount;
      $("wish-count").setAttribute("aria-label", "عدد الأمنيات");
    } catch (error) { if (error.status === 401) showError(error); }
  }
  function renderDonut(parts, salary) {
    const colors = ["#7650d4", "#32877c", "#b8a2ec", "#e4d7bb"];
    const total = parts.reduce((sum, item) => sum + Math.max(0, item.value), 0) || 1;
    const circumference = 2 * Math.PI * 55;
    let offset = 0;
    const circles = parts.map((item, index) => {
      const length = circumference * Math.max(0, item.value) / total;
      const circle = `<circle cx="80" cy="80" r="55" fill="none" stroke="${colors[index]}" stroke-width="17" stroke-dasharray="${Math.max(0,length - 2)} ${circumference}" stroke-dashoffset="${-offset}"/>`;
      offset += length;
      return circle;
    }).join("");
    $("ov-chart").innerHTML = `<svg viewBox="0 0 160 160" role="img" aria-label="توزيع الراتب"><g transform="rotate(-90 80 80)">${circles}</g><text x="80" y="77" text-anchor="middle" class="chart-center">${format(salary)}</text><text x="80" y="94" text-anchor="middle" class="chart-center-sub">راتبك</text></svg>`;
    $("ov-legend").innerHTML = parts.map((item, index) => `<div class="legend-item"><i class="legend-dot" style="background:${colors[index]}"></i><span>${esc(item.label)}<strong>${format(item.value)} ر.س</strong></span></div>`).join("");
  }
  function alertMarkup(item) {
    if (item.type === "before_salary") return `<div class="list-row"><div class="row-copy"><div class="row-title">عندك دفعة قبل الراتب</div><div class="row-sub">${(item.plans || []).map(plan => `${esc(plan.name)} · ${dayLabel(plan.days_until)}`).join("، ")}</div></div><span class="badge upcoming">${money(item.amount)}</span></div>`;
    if (item.type === "plan_ending") return `<div class="list-row"><div class="row-copy"><div class="row-title">خطة ${esc(item.name)} تخلص هالشهر</div><div class="row-sub">يرجع لك ${money(item.frees)} من الشهر الجاي</div></div></div>`;
    if (item.type === "spending_pace") return `<div class="list-row"><div class="row-copy"><div class="row-title">صرفك وصل ${esc(item.pct)}%</div><div class="row-sub">الراتب ${dayLabel(item.days_to_salary)}</div></div></div>`;
    return "";
  }
  async function loadOverview() {
    const [s, w] = await Promise.all([api("/api/summary"), api("/api/wishlist")]);
    const f = s.formula || {};
    salaryAmount = number(f.salary);
    const displayName = s.display_name || "يا هلا";
    $("overview-title").textContent = `هلا ${displayName}`;
    $("ov-sub").textContent = `راتبك ${dayLabel(s.salary?.days_left || 0)}`;
    const totalObligations = number(s.obligations_total ?? f.total_obligations ?? f.obligations);
    $("ov-stats").innerHTML =
      stat("راتبك الشهري", money(f.salary), "purple", `ينزل يوم ${format(s.salary?.day)}`) +
      stat("التزاماتك", money(totalObligations), "sand", "الأقساط والمعيشة") +
      stat("تقدر تصرف الحين", money(s.available), "teal", `صرفك ${format(s.spent)} ر.س`) +
      stat("هامش الأمان", money(f.buffer), "rose", "ما نحسبه للصرف");
    const alerts = Array.isArray(s.alerts) ? s.alerts.map(alertMarkup).filter(Boolean) : [];
    $("ov-alerts").innerHTML = alerts.length ? `<article class="surface">${alerts.join("")}</article>` : "";
    const spendable = number(s.safe_to_spend);
    $("ov-formula").innerHTML = `${format(f.salary)} − ${format(totalObligations)} − ${format(f.buffer)} = <strong>${format(spendable)} ر.س</strong>`;
    $("ov-formula-note").textContent = `بعد التزاماتك وهامش الأمان، هذا المبلغ اللي تقدر تصرفه. صرفت للحين ${format(s.spent)} ر.س.`;
    const plans = Array.isArray(s.plans) ? s.plans : [];
    const upcoming = plans.find(plan => plan.status === "upcoming" || plan.status === "late");
    $("ov-next").innerHTML = upcoming ? `<div class="list-row"><div class="row-copy"><div class="row-title">${esc(upcoming.name)}</div><div class="row-sub">${dayLabel(upcoming.days_until)} · يوم ${format(upcoming.day)} من كل شهر</div></div><div class="row-amount">${money(upcoming.amount)}<div class="row-sub">${upcoming.remaining != null ? `باقي ${esc(languageForm("payments", upcoming.remaining))}` : ""}</div></div></div>` : empty("ما فيه دفعات قريبة", "إذا تأكدت خطة، بتطلع لك هنا.");
    const essentials = number(f.essentials);
    renderDonut([
      { label: "المعيشة", value: essentials }, { label: "الأقساط", value: number(f.obligations) },
      { label: "تقدر تصرف", value: Math.max(0, spendable) }, { label: "هامش الأمان", value: number(f.buffer) }
    ], number(f.salary));
    wishlistCount = Array.isArray(w.items) ? w.items.length : 0;
    $("wish-count").textContent = wishlistCount > 99 ? "99+" : wishlistCount;
  }

  async function loadExpenses() {
    $("expense-list").innerHTML = `<p class="quiet">نحمّل مصروفاتك…</p>`;
    let data, summary;
    try {
      [data, summary] = await Promise.all([api("/api/expenses"), api("/api/summary")]);
    } catch (error) {
      $("expense-list").innerHTML = `<p class="quiet" role="alert">ما قدرنا نحمل المصروفات. اضغط تحديث وحاول مرة ثانية.</p>`;
      $("ex-summary").innerHTML = "";
      throw error;
    }
    $("ex-summary").innerHTML = stat("مصروفاتك المرنة", money(summary.spent), "purple", "من دورة الراتب الحالية") +
      stat("المتاح قبل الراتب", money(summary.available), summary.available < 0 ? "rose" : "teal", "بعد الالتزامات وهامش الأمان") +
      stat("متوسط الأساسيات", money(summary.formula.essentials), "sand", "متوسط آخر 3 شهور، مو صرف هالدورة");
    const categories = Object.entries(summary.categories?.flexible || {}).map(([name, value]) =>
      `<div class="list-row"><span>${esc(name)}</span><strong>${money(value)}</strong></div>`).join("");
    $("ex-summary").innerHTML += `<div class="surface" style="grid-column:1/-1"><h2>المرن حسب الفئة</h2>${categories || '<p class="quiet">ما فيه مصروفات مرنة بهالدورة.</p>'}</div>`;
    expenseToday = summary.today;
    const dateInput = $("expense-form").elements.date;
    dateInput.max = expenseToday;
    if (!dateInput.value) dateInput.value = expenseToday;
    const items = Array.isArray(data.items) ? data.items : [];
    $("expense-list").innerHTML = items.length ? items.map(item => {
      const manual = item.source === "manual" && item.deletable === true;
      return `<div class="list-row"><div class="row-copy"><div class="row-title">${esc(item.merchant)}</div><div class="row-sub">${esc(item.date || "")} · ${esc(item.category || "غير مصنف")} · ${manual ? "يدوي" : "من البنك، للقراءة بس"}</div>${item.description ? `<div class="row-sub">${esc(item.description)}</div>` : ""}</div><div class="row-amount">${money(item.amount)}${manual ? `<div><button class="danger-action" type="button" data-expense-delete="${esc(item.id)}">حذف</button></div>` : ""}</div></div>`;
    }).join("") : empty("ما فيه مصروفات مسجلة للحين", "تقدر تضيف مصروفك اليدوي من النموذج فوق.");
    $("wish-count").textContent = $("wish-count").textContent || "0";
  }
  async function createExpense(form) {
    const fd = new FormData(form);
    const name = String(fd.get("name") || "").trim();
    const amountText = String(fd.get("amount") || "").trim();
    const amount = Number(amountText);
    const category = String(fd.get("category") || "");
    const date = String(fd.get("date") || "");
    const description = String(fd.get("description") || "").trim();
    if (!name || !/^\d+(?:\.\d{1,2})?$/.test(amountText) || !Number.isFinite(amount) || amount <= 0 || amount > 1000000 || !expenseToday || !date || date > expenseToday) return toast("تأكد من المبلغ والتاريخ. المبلغ بحد أقصى منزلتين عشريتين، والتاريخ مو بعد اليوم بحسابك.", "error");
    const submit = form.querySelector('button[type="submit"]');
    if (expenseBusy) return;
    expenseBusy = true;
    if (submit) submit.disabled = true;
    try {
      await api("/api/expenses", { method: "POST", body: { merchant: name, amount, category, date, description } });
      toast("أضفنا المصروف.");
      form.reset();
      form.elements.date.value = expenseToday;
      await Promise.all([loadExpenses(), loadOverview()]);
      return true;
    } catch (error) { showError(error); return false; }
    finally { expenseBusy = false; if (submit) submit.disabled = false; }
  }
  $("expense-list").addEventListener("click", async event => {
    const remove = event.target.closest("[data-expense-delete]");
    if (remove && !deletingExpenses.has(remove.dataset.expenseDelete)) {
      if (!window.confirm("تحذف هالمصروف؟")) return;
      remove.disabled = true;
      deletingExpenses.add(remove.dataset.expenseDelete);
      try { await api(`/api/expenses/${encodeURIComponent(remove.dataset.expenseDelete)}`, { method: "DELETE" }); toast("حذفنا المصروف."); await Promise.all([loadExpenses(), loadOverview()]); }
      catch (error) { showError(error); }
      finally { deletingExpenses.delete(remove.dataset.expenseDelete); remove.disabled = false; }
      return;
    }
  });
  $("expense-form").addEventListener("submit", event => {
    const form = event.currentTarget;
    event.preventDefault();
    createExpense(form);
  });
  $("expense-refresh").addEventListener("click", () => loadExpenses().catch(showError));
  $("category-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget, submit = form.querySelector("button");
    if (submit.disabled) return;
    submit.disabled = true;
    try {
      await api("/api/categories", { method: "POST", body: { merchant: form.elements.merchant.value.trim(), category: form.elements.category.value } });
      await loadExpenses(); form.reset(); toast("عدّلنا التصنيف.");
    } catch (error) { showError(error); }
    finally { submit.disabled = false; }
  });

  async function loadObligations() {
    const data = await api("/api/obligations");
    obligationsCache = data;
    $("ob-total").textContent = money(data.total);
    const counts = data.counts || {};
    $("ob-stats").innerHTML = stat("قادم هالشهر", format(counts.upcoming), "sand") + stat("تسدّد هالشهر", format(counts.paid), "teal");
    $("ob-list").innerHTML = "";
    $("living-list").innerHTML = "";
    const plans = (data.items || []).filter(item => item.type === "plan" || item.kind === "bnpl" || item.kind === "loan" || item.kind === "recurring" && item.source === "manual");
    const living = (data.items || []).filter(item => !plans.includes(item));
    if (obTab !== "living") {
      $("ob-list").innerHTML = `<div class="section-heading list-section"><div><span class="eyebrow">الخطط المكتشفة أو المضافة</span><h2>الأقساط</h2></div></div>` + (plans.length ? plans.map(renderPlanCard).join("") : empty("ما عندك أقساط ظاهرة", "إذا عندك التزام يدوي، أضفه من النموذج." ));
    }
    if (obTab !== "plans") {
      const essentials = data.essentials_by_category || {};
      const categories = Object.entries(essentials).map(([name, amount]) => `<div class="list-row"><div class="row-copy"><div class="row-title">${esc(name)}</div><div class="row-sub">متوسط شهري</div></div><div class="row-amount">${money(amount)}</div></div>`).join("");
      const bills = living.map(item => renderLivingItem(item)).join("");
      $("living-list").innerHTML = `<article class="surface"><div class="section-heading"><div><span class="eyebrow">متوسط آخر 3 شهور</span><h2>المعيشة</h2></div></div>${categories || empty("ما فيه متوسطات جاهزة", "بتظهر فئات المعيشة بعد توفر بياناتها.")}</article><article class="surface"><div class="section-heading"><div><span class="eyebrow">للعرض فقط</span><h2>الفواتير الدورية</h2></div></div>${bills || empty("ما فيه فواتير دورية", "الفواتير محسوبة ضمن متوسط المعيشة، ما نضيفها مرة ثانية.")}</article>`;
    }
  }
  function statusBadge(status) {
    const map = { paid: ["paid", "تسدّد هالشهر"], completed: ["paid", "مكتمل"], upcoming: ["upcoming", "قادم"], late: ["late", "متأخر"] };
    const [style, label] = map[status] || ["upcoming", "قادم"];
    return `<span class="badge ${style}">${label}</span>`;
  }
  function renderPlanCard(plan) {
    const remains = plan.remaining === null || plan.remaining === undefined ? "التزام شهري" : `باقي ${esc(languageForm("payments", plan.remaining))}`;
    const progress = Number(plan.progress ?? (plan.total ? (plan.total - plan.remaining) / plan.total * 100 : 0));
    const pct = Math.max(0, Math.min(100, progress <= 1 ? progress * 100 : progress));
    const manual = plan.source === "manual";
    const deleteButton = manual ? `<button class="danger-action" type="button" data-plan-delete="${esc(plan.id)}">حذف</button>` : "";
    return `<article class="item-card">
      <div class="item-head"><div><div class="item-title">${esc(plan.name)}</div><div class="item-meta">يوم ${format(plan.day)} من كل شهر · ${esc(remains)}</div></div><div>${statusBadge(plan.status)}</div></div>
      <div class="item-head" style="align-items:end;margin-top:9px"><span class="item-meta">كم ينخصم كل شهر</span><strong class="item-price">${money(plan.amount)}</strong></div>
      ${plan.total ? `<div class="progress-track" aria-label="التقدم ${Math.round(pct)}%"><span style="width:${pct}%"></span></div><div class="item-meta">${format(number(plan.total) - number(plan.remaining))} من ${esc(languageForm("payments", plan.total))}</div>` : ""}
      <div class="item-actions">${actionControl(plan.action)}<span>${plan.confirmed ? `<span class="badge sample">مؤكد</span>` : `<button class="small-action" type="button" data-plan-confirm="${esc(plan.id)}">أكد الخطة</button>`} <button class="small-action" type="button" data-plan-edit="${esc(plan.id)}" data-amount="${esc(plan.amount)}" data-remaining="${esc(plan.remaining ?? "")}">تعديل</button> ${deleteButton}</span></div>
    </article>`;
  }
  function renderLivingItem(item) {
    return `<div class="list-row"><div class="row-copy"><div class="row-title">${esc(item.name)}</div><div class="row-sub">${item.due_date ? `تستحق ${esc(item.due_date)}` : item.day ? `يوم ${format(item.day)}` : "فاتورة دورية"} · ${statusBadge(item.status)}</div></div><div class="row-amount">${money(item.amount)}</div></div>`;
  }
  $("p-obligations").addEventListener("click", async event => {
    const tab = event.target.closest("[data-ob-tab]");
    if (tab) {
      obTab = tab.dataset.obTab;
      document.querySelectorAll("[data-ob-tab]").forEach(item => item.setAttribute("aria-selected", String(item === tab)));
      if (obligationsCache) renderObligationsCached();
    }
    const confirmButton = event.target.closest("[data-plan-confirm]");
    const editButton = event.target.closest("[data-plan-edit]");
    const deleteButton = event.target.closest("[data-plan-delete]");
    if (confirmButton) await confirmPlan(confirmButton.dataset.planConfirm, {}, confirmButton);
    if (editButton) {
      const amountText = window.prompt("المبلغ الشهري، ر.س", editButton.dataset.amount);
      if (amountText === null) return;
      const amount = toNum(amountText);
      if (!amount || amount > 1000000) return toast("اكتب المبلغ صح.", "error");
      const remainingText = editButton.dataset.remaining === "" ? null : window.prompt("عدد الدفعات الباقية", editButton.dataset.remaining);
      if (remainingText === null && editButton.dataset.remaining !== "") return;
      const body = { amount };
      if (remainingText !== null) {
        const remaining = Number(String(remainingText).replace(/[٠-٩]/g, d => "٠١٢٣٤٥٦٧٨٩".indexOf(d)));
        if (!Number.isInteger(remaining) || remaining < 0 || remaining > 600) return toast("اكتب عدد الدفعات صح.", "error");
        body.remaining = remaining;
      }
      await confirmPlan(editButton.dataset.planEdit, body, editButton);
    }
    if (deleteButton) {
      if (!window.confirm("تحذف الالتزام اليدوي؟")) return;
      deleteButton.disabled = true;
      try { await api(`/api/plans/${encodeURIComponent(deleteButton.dataset.planDelete)}`, { method: "DELETE" }); await loadObligations(); toast("حذفنا الالتزام."); }
      catch (error) { showError(error); deleteButton.disabled = false; }
    }
  });
  function renderObligationsCached() {
    const data = obligationsCache;
    const plans = (data.items || []).filter(item => item.type === "plan" || ["bnpl","loan","recurring"].includes(item.kind) && item.source === "manual");
    const living = (data.items || []).filter(item => !plans.includes(item));
    $("ob-list").innerHTML = obTab === "living" ? "" : `<div class="section-heading list-section"><div><span class="eyebrow">الخطط المكتشفة أو المضافة</span><h2>الأقساط</h2></div></div>` + (plans.length ? plans.map(renderPlanCard).join("") : empty("ما عندك أقساط ظاهرة", "إذا عندك التزام يدوي، أضفه من النموذج."));
    if (obTab === "plans") { $("living-list").innerHTML = ""; return; }
    const categories = Object.entries(data.essentials_by_category || {}).map(([name, amount]) => `<div class="list-row"><div class="row-copy"><div class="row-title">${esc(name)}</div><div class="row-sub">متوسط شهري</div></div><div class="row-amount">${money(amount)}</div></div>`).join("");
    $("living-list").innerHTML = `<article class="surface"><div class="section-heading"><div><span class="eyebrow">متوسط آخر 3 شهور</span><h2>المعيشة</h2></div></div>${categories || empty("ما فيه متوسطات جاهزة", "بتظهر فئات المعيشة بعد توفر بياناتها.")}</article><article class="surface"><div class="section-heading"><div><span class="eyebrow">للعرض فقط</span><h2>الفواتير الدورية</h2></div></div>${living.length ? living.map(renderLivingItem).join("") : empty("ما فيه فواتير دورية", "الفواتير محسوبة ضمن متوسط المعيشة، ما نضيفها مرة ثانية.")}</article>`;
  }
  $("plan-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget, button = form.querySelector("button");
    if (planBusy) return;
    const amount = toNum(form.elements.amount.value), day = Number(form.elements.day.value);
    const remainingText = form.elements.remaining.value.trim();
    if (!amount || !Number.isInteger(day) || day < 1 || day > 28) return toast("راجع المبلغ ويوم الاستحقاق.", "error");
    const body = { name: form.elements.name.value.trim(), amount, day, kind: form.elements.kind.value, remaining: remainingText ? Number(remainingText) : null };
    if (remainingText && (!Number.isInteger(body.remaining) || body.remaining < 1 || body.remaining > 600)) return toast("اكتب عدد الدفعات صح.", "error");
    planBusy = true; button.disabled = true;
    try { await api("/api/plans", { method: "POST", body }); form.reset(); await Promise.all([loadObligations(), loadOverview()]); toast("أضفنا الالتزام."); }
    catch (error) { showError(error); }
    finally { planBusy = false; button.disabled = false; }
  });
  async function confirmPlan(id, body, button) {
    if (planBusy) return;
    planBusy = true; if (button) button.disabled = true;
    try { await api(`/api/plans/${encodeURIComponent(id)}/confirm`, { method: "POST", body }); await Promise.all([loadObligations(), loadOverview()]); toast(Object.keys(body).length ? "عدّلنا الخطة وأكدناها." : "أكدنا الخطة."); }
    catch (error) { showError(error); if (button) button.disabled = false; }
    finally { planBusy = false; }
  }

  async function loadOffers() {
    const price = toNum($("buy-price").value);
    $("btn-buy-wish").disabled = true;
    if (!price || price > 10000000) {
      plannerResult = null;
      $("buy-scenarios").innerHTML = empty("اكتب سعر المنتج", "نقارن لك الطرق بعد ما تدخل السعر.");
      return;
    }
    $("buy-scenarios").innerHTML = `<div class="item-card"><div class="skeleton-block"></div><div class="row-sub">لحظة، نحسب الخيارات…</div></div>`;
    try {
      const [result, summary] = await Promise.all([api("/api/offers", { method: "POST", body: { price } }), api("/api/summary")]);
      salaryAmount = number(summary.formula?.salary);
      plannerResult = result;
      const bestOffer = (result.offers || []).find(offer => offer.id === result.best_offer_id);
      chosenMethod = bestOffer?.method || (result.offers || [])[0]?.method || "save";
      renderOffers(result, price);
      $("btn-buy-wish").disabled = false;
    } catch (error) { $("buy-scenarios").innerHTML = `<div class="empty-state"><strong>ما قدرنا نحسبها</strong><button class="button secondary" type="button" id="offers-retry">حاول مرة ثانية</button></div>`; showError(error); }
  }
  function saveCard(save, price) {
    const progress = Array.isArray(save.progress) ? save.progress : [];
    const months = Number(save.months || progress.length || 0);
    const pct = number(save.salary_pct ?? (salaryAmount ? number(save.monthly) / salaryAmount * 100 : 0));
    const rows = progress.map(step => `<li><b>${esc(step.label || monthLabel(step.k))}:</b> ${money(step.amount)} · المجموع ${money(step.cumulative)}</li>`).join("");
    return `<button type="button" class="offer-card save-card ${chosenMethod === "save" ? "selected" : ""}" data-method="save">
      <div class="offer-title">تجمع أول</div><div class="offer-subtitle">خطة ادخار على قد وضعك</div>
      <div class="offer-price">${money(save.monthly)} <small>شهريًا · ${format(pct)}% من الراتب</small></div>
      <div class="offer-detail"><span>عدد الشهور</span><b>${format(months)}</b></div>
      <div class="offer-detail"><span>تقدر تشتريه</span><b>${esc(save.buy_label || monthLabel(save.buyK))}</b></div>
      <div class="offer-detail"><span>قيمة المنتج</span><b>${money(save.total ?? price)}</b></div>
      ${rows ? `<ol class="save-progress-list">${rows}</ol>` : ""}
    </button>`;
  }
  function renderOffers(result, price) {
    const offers = Array.isArray(result.offers) ? [...result.offers].sort((a, b) =>
      Number(b.id === result.best_offer_id) - Number(a.id === result.best_offer_id)) : [];
    const cards = offers.map(offer => {
      const isBest = offer.id === result.best_offer_id;
      const method = offer.method || offer.id;
      const remaining = offer.tight == null ? "ما فيه شهر مناسب" : Number(offer.tight) >= 0 ? `${money(offer.tight)} تبقى في ${monthLabel(offer.tightK)}` : `${money(-Number(offer.tight))} ناقص في ${monthLabel(offer.tightK)}`;
      const startTight = offer.start_tight == null ? "ما فيه شهر يناسبك بهالطريقة" : Number(offer.start_tight) >= 0 ? `${money(offer.start_tight)} تبقى في ${monthLabel(offer.start_tightK)}` : `${money(-Number(offer.start_tight))} ناقص`;
      const fitTiming = offer.ok ? "مناسب لك الحين" : offer.earliest == null ? "ما فيه شهر مناسب بهالطريقة" : `يصير مناسب ${esc(offer.earliest_label || monthLabel(offer.earliest))}`;
      const count = Number(offer.count || 0);
      const fee = number(offer.fee_pct);
      const feeCopy = fee ? `رسوم ${format(fee)}%` : "بدون رسوم";
      return `<button type="button" class="offer-card ${chosenMethod === method ? "selected" : ""} ${isBest ? "best" : ""}" data-method="${esc(method)}">
        <div class="offer-title">${esc(offer.provider)} · ${esc(offer.label)}</div><div class="offer-subtitle">${esc(feeCopy)} · عرض تجريبي</div>
        <div class="offer-price">${money(offer.monthly)} <small>${count ? `× ${esc(languageForm("payments", count))}` : "شهريًا"}</small></div>
        <div class="offer-detail"><span>الإجمالي</span><b>${money(offer.total)}</b></div>
        ${number(offer.extra_cost) ? `<div class="offer-detail"><span>زيادة على السعر</span><b>${money(offer.extra_cost)}</b></div>` : ""}
        <div class="offer-detail"><span>أضيق شهر الحين</span><b>${esc(remaining)}</b></div>
        <div class="offer-note">${fitTiming} · ${esc(startTight)}</div>
      </button>`;
    }).join("");
    $("buy-scenarios").innerHTML = saveCard(result.save || {}, price) + cards;
  }
  $("buy-price").addEventListener("input", () => {
    clearTimeout(offerTimer);
    offerTimer = setTimeout(() => loadOffers(), 280);
  });
  $("buy-scenarios").addEventListener("click", event => {
    const card = event.target.closest("[data-method]");
    if (!card) {
      if (event.target.id === "offers-retry") loadOffers();
      return;
    }
    chosenMethod = card.dataset.method;
    document.querySelectorAll(".offer-card").forEach(item => item.classList.toggle("selected", item.dataset.method === chosenMethod));
  });
  $("btn-buy-wish").addEventListener("click", async event => {
    const button = event.currentTarget;
    const price = toNum($("buy-price").value), name = $("buy-name").value.trim();
    if (!price || !name || !chosenMethod) return toast("اكتب اسم المنتج وسعره أول.", "error");
    if (button.disabled) return;
    button.disabled = true;
    try { await api("/api/wishlist", { method: "POST", body: { name, price, method: chosenMethod } }); await updateWishCount(); toast(`أضفنا ${name} للأمنيات. بنذكّرك إذا صار مناسب.`); location.hash = "#wish"; }
    catch (error) { showError(error); }
    finally { button.disabled = false; }
  });

  function methodOptions() {
    return METHOD_IDS.map(key => `<option value="${key}">${esc(methodLabel(key))}</option>`).join("");
  }
  async function loadWishlist() {
    const data = await api("/api/wishlist");
    const items = Array.isArray(data.items) ? data.items : [];
    wishlistCount = items.length;
    $("wish-count").textContent = wishlistCount > 99 ? "99+" : wishlistCount;
    $("wish-stats").innerHTML = stat("عدد الأمنيات", format(items.length), "purple") + stat("قيمتها كلها", money(items.reduce((sum, item) => sum + number(item.price), 0)), "teal");
    $("wish-list").innerHTML = items.length ? items.map(item => {
      const status = item.status || {};
      const save = item.method === "save";
      const label = save ? (status.ok ? "جمعت المبلغ، مناسب الحين" : `تقدر تشتريه ${item.when_label || monthLabel(status.whenK)}`) : (status.ok ? "مناسب لك الحين" : status.whenK === null ? "ما يناسبك الحين بهالطريقة" : `يصير مناسب ${item.when_label || monthLabel(status.whenK)}`);
      const pct = Math.max(0, Math.min(100, number(status.pct)));
      return `<article class="item-card" data-wish-card="${esc(item.id)}">
        <div class="item-head"><div><div class="item-title">${esc(item.name)}</div><div class="item-meta">${esc(methodLabel(item.method))}</div></div><button class="danger-action" type="button" data-wish-delete="${esc(item.id)}">حذف</button></div>
        <div class="item-head" style="align-items:center;margin-top:9px"><span class="badge ${status.ok ? "paid" : "upcoming"}">${esc(label)}</span><strong class="item-price">${money(item.price)}</strong></div>
        ${save ? `<div class="progress-track"><span style="width:${pct}%"></span></div><div class="item-meta">جمعت ${money(item.saved)} من ${money(item.price)}</div>` : ""}
        <div class="item-actions"><button class="small-action" type="button" data-wish-compare="${esc(item.id)}" data-name="${esc(item.name)}" data-price="${esc(item.price)}">قارن طرق الشراء</button><button class="small-action" type="button" data-wish-edit="${esc(item.id)}" data-name="${esc(item.name)}" data-price="${esc(item.price)}" data-method="${esc(item.method)}">تعديل</button></div>
        <form class="wish-edit-form stack-form" data-edit-form="${esc(item.id)}" hidden>
          <label>الاسم<input name="name" readonly value="${esc(item.name)}"></label>
          <div class="form-row"><label>السعر<input name="price" type="number" min="1" step="0.01" required value="${esc(item.price)}"></label><label>الطريقة<select name="method">${METHOD_IDS.map(key => `<option value="${key}" ${item.method === key ? "selected" : ""}>${esc(methodLabel(key))}</option>`).join("")}</select></label></div>
          <button class="button secondary" type="submit">حفظ التعديل</button>
        </form>
      </article>`;
    }).join("") : empty("قائمة الأمنيات فاضية", "أضف اللي على بالك، ونحسب لك متى يناسبك.");
  }
  $("wish-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget, button = form.querySelector("button");
    const price = toNum(form.elements.price.value), name = form.elements.name.value.trim();
    if (!price || !name || button.disabled) return;
    button.disabled = true;
    try { await api("/api/wishlist", { method: "POST", body: { name, price, method: form.elements.method.value } }); form.reset(); await loadWishlist(); toast("أضفناها لقائمة الأمنيات."); }
    catch (error) { showError(error); }
    finally { button.disabled = false; }
  });
  $("wish-list").addEventListener("click", async event => {
    const remove = event.target.closest("[data-wish-delete]");
    const edit = event.target.closest("[data-wish-edit]");
    const compare = event.target.closest("[data-wish-compare]");
    if (remove) {
      if (!window.confirm("تحذف هالأمنية؟")) return;
      remove.disabled = true;
      try { await api(`/api/wishlist/${encodeURIComponent(remove.dataset.wishDelete)}`, { method: "DELETE" }); await loadWishlist(); toast("حذفناها من الأمنيات."); }
      catch (error) { showError(error); remove.disabled = false; }
    }
    if (edit) {
      const form = document.querySelector(`[data-edit-form="${CSS.escape(edit.dataset.wishEdit)}"]`);
      form.hidden = !form.hidden;
    }
    if (compare) {
      $("buy-name").value = compare.dataset.name;
      $("buy-price").value = compare.dataset.price;
      location.hash = "#buy";
    }
  });
  $("wish-list").addEventListener("submit", async event => {
    const form = event.target.closest("[data-edit-form]");
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector("button");
    if (button.disabled) return;
    const body = { price: toNum(form.elements.price.value), method: form.elements.method.value };
    if (!body.price) return toast("راجع بيانات الأمنية.", "error");
    button.disabled = true;
    try { await api(`/api/wishlist/${encodeURIComponent(form.dataset.editForm)}`, { method: "PATCH", body }); await loadWishlist(); toast("عدّلنا الأمنية."); }
    catch (error) { showError(error); }
    finally { button.disabled = false; }
  });
  $("btn-next-month").addEventListener("click", async event => {
    const button = event.currentTarget;
    if (button.disabled) return;
    button.disabled = true;
    try {
      const result = await api("/api/demo/next-month", { method: "POST" });
      (result.events || []).forEach((item, index) => window.setTimeout(() => {
        if (item.type === "salary") toast(`نزل راتبك: ${money(item.amount)}`);
        else if (item.type === "plan_end") toast(`خلصت خطة ${item.name}. يرجع لك ${money(item.frees)} كل شهر.`);
        else if (item.type === "wish_affordable") toast(`${item.name} صار مناسب لك ${item.tight !== undefined ? `ويبقى ${money(item.tight)} في أضيق شهر.` : ""}`);
      }, index * 700));
      await Promise.all([loadWishlist(), loadOverview()]);
    } catch (error) { showError(error); }
    finally { button.disabled = false; }
  });

  function dateOnly(date) { if (!date) return "—"; return String(date).slice(0,10); }
  async function loadAccount() {
    const account = await api("/api/account");
    const subscription = account.subscription || {};
    $("account-profile").innerHTML = `<article class="surface profile-card"><span class="eyebrow">معلومات حسابك</span><div class="profile-name">${esc(account.display_name || "حسابك")}</div>
      <div class="profile-line"><span>رقم الجوال</span><strong>${esc(account.phone_masked || "غير متوفر")}</strong></div>
      <div class="profile-line"><span>الإيميل</span><strong>${esc(account.email || "غير مضاف")}</strong></div>
      <div class="profile-line"><span>البنك</span><strong>${esc(account.bank_name || "ما فيه بنك مربوط")}</strong></div>
      <div class="profile-line"><span>انتهاء الموافقة</span><strong>${esc(dateOnly(account.consent_expires_at))}</strong></div>
      <div class="profile-line"><span>يوم الراتب</span><strong>${account.salary_day ? `يوم ${format(account.salary_day)} من كل شهر` : "غير محدد"}</strong></div>
      <div class="profile-line"><span>نوع الحساب</span><strong>${account.demo_mode ? "بيانات تجريبية" : "حسابك"}</strong></div></article>`;
    $("account-plan").innerHTML = `<article class="surface current-plan"><span class="eyebrow">باقتك الحالية</span><div class="plan-title">${esc(subscription.name || "—")}</div><p class="quiet">${subscription.price != null ? `${money(subscription.price)}${number(subscription.price) === 0 ? " · مجانية" : " شهريًا"}` : ""}</p><p class="quiet">أسئلة المساعد: ${subscription.assistant_questions == null ? "—" : format(subscription.assistant_questions)} بالشهر</p></article>`;
    const tiers = Array.isArray(account.tiers) ? account.tiers : [];
    $("tiers").innerHTML = tiers.length ? tiers.map(tier => `<div class="tier"><div class="tier-head"><strong>${esc(tier.name)}</strong><span class="tier-price">${tier.price == null ? "—" : number(tier.price) === 0 ? "مجانًا" : `${money(tier.price)} / شهر`}</span></div><ul>${(tier.features || []).map(feature => `<li>${esc(feature)}</li>`).join("")}</ul><button class="button ghost full" type="button" data-upgrade="${esc(tier.id)}">جرّب هالباقة</button></div>`).join("") : empty("ما قدرنا نعرض الباقات", "جرّب تحديث الصفحة بعد شوي.");
    $("contact-channels").innerHTML = `<div class="contact-links">${account.contact?.email ? `<a class="contact-link" href="mailto:${esc(account.contact.email)}">راسلنا بالإيميل</a>` : `<div class="contact-unavailable">الإيميل مو متاح للحين.</div>`}${account.contact?.whatsapp ? `<a class="contact-link" href="${esc(safeWhatsApp(account.contact.whatsapp))}" target="_blank" rel="noopener noreferrer">تواصل معنا بواتساب</a>` : `<div class="contact-unavailable">واتساب مو متاح للحين.</div>`}</div>`;
    $("demo-tools").innerHTML = apiMode === "demo" && account.demo_mode ? `<article class="surface demo-control"><div class="section-heading"><div><span class="eyebrow">بيئة تجريبية</span><h2>أدوات العرض</h2></div></div><button class="button secondary full" id="btn-reset">ابدأ الديمو من جديد</button></article>` : "";
    const reset = $("btn-reset");
    if (reset) reset.addEventListener("click", resetDemo);
    $("tiers").querySelectorAll("[data-upgrade]").forEach(button => button.addEventListener("click", () => toast("الباقات المدفوعة قريباً.")));
  }
  function safeWhatsApp(value) {
    const source = String(value || "").trim();
    try {
      const url = new URL(source);
      return url.protocol === "https:" && (url.hostname === "wa.me" || url.hostname.endsWith(".wa.me")) ? url.href : "#";
    } catch (_) {
      const digits = source.replace(/\D/g, "");
      return digits.length >= 8 ? `https://wa.me/${digits}` : "#";
    }
  }
  $("contact-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget, button = form.querySelector("button");
    if (button.disabled) return;
    button.disabled = true;
    try { await api("/api/contact", { method: "POST", body: { name: form.elements.name.value.trim(), message: form.elements.message.value.trim() } }); form.reset(); toast("وصلتنا رسالتك، شكرًا لك."); }
    catch (error) { showError(error); }
    finally { button.disabled = false; }
  });
  $("btn-revoke").addEventListener("click", async event => {
    const button = event.currentTarget;
    if (!window.confirm("متأكد؟ بنلغي الموافقة ونحذف بيانات حسابك.")) return;
    button.disabled = true;
    try { await api("/api/consent", { method: "DELETE" }); clearConversation(); saveToken(null); showOnboardScreen("ob-connect"); toast("ألغينا الموافقة وحذفنا بياناتك."); }
    catch (error) { showError(error); button.disabled = false; }
  });
  async function resetDemo() {
    if (apiMode !== "demo" || !window.confirm("بنبدأ الديمو من جديد ونمسح البيانات الحالية. نكمل؟")) return;
    try {
      const result = await api("/api/demo/reset", { method: "POST" });
      saveToken(result.token);
      clearConversation();
      await startDetection(result);
    } catch (error) { showError(error); }
  }

  /* Persistent assistant sheet; chat nodes stay mounted while closed. */
  const suggestions = ["كم عليّ هالشهر؟", "أقدر آخذ جوال بـ 3000؟", "ضيف مصروف قهوة 20"];
  $("chat-suggestions").innerHTML = suggestions.map(text => `<button type="button">${esc(text)}</button>`).join("");
  function appendMessage(kind, text) {
    const node = document.createElement("div");
    node.className = `message ${kind}`;
    node.textContent = text;
    $("chat-messages").appendChild(node);
    $("chat-messages").scrollTop = $("chat-messages").scrollHeight;
    return node;
  }
  function clearConversation() {
    $("chat-messages").replaceChildren();
    appendMessage("assistant", "هلا! اسألني عن أقساطك أو مصاريفك أو شي تفكر تشتريه.");
  }
  clearConversation();
  let chatReturnFocus = null;
  function openChat() {
    chatReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : $("chat-open");
    $("app").inert = true;
    $("app").setAttribute("aria-hidden", "true");
    $("chat-backdrop").hidden = false;
    requestAnimationFrame(() => $("chat-backdrop").classList.add("visible"));
    $("chat-sheet").classList.add("open");
    $("chat-sheet").setAttribute("aria-hidden", "false");
    $("chat-open").setAttribute("aria-expanded", "true");
    document.body.classList.add("sheet-open");
    $("chat-input").focus({ preventScroll: true });
  }
  function closeChat() {
    $("chat-sheet").classList.remove("open");
    $("chat-sheet").setAttribute("aria-hidden", "true");
    $("chat-open").setAttribute("aria-expanded", "false");
    $("chat-backdrop").classList.remove("visible");
    document.body.classList.remove("sheet-open");
    $("app").inert = false;
    $("app").removeAttribute("aria-hidden");
    window.setTimeout(() => { if (!$("chat-sheet").classList.contains("open")) $("chat-backdrop").hidden = true; }, 240);
    const target = chatReturnFocus && chatReturnFocus.isConnected ? chatReturnFocus : $("chat-open");
    target.focus({ preventScroll: true });
  }
  $("chat-open").addEventListener("click", openChat);
  $("chat-close").addEventListener("click", closeChat);
  $("chat-backdrop").addEventListener("click", closeChat);
  document.addEventListener("keydown", event => {
    if (!$("chat-sheet").classList.contains("open")) return;
    if (event.key === "Escape") { closeChat(); return; }
    if (event.key !== "Tab") return;
    const focusable = [...$("chat-sheet").querySelectorAll('button:not(:disabled),input:not(:disabled),a[href],[tabindex]:not([tabindex="-1"])')].filter(item => item.offsetParent !== null);
    if (!focusable.length) { event.preventDefault(); return; }
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || ! $("chat-sheet").contains(document.activeElement))) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || ! $("chat-sheet").contains(document.activeElement))) {
      event.preventDefault(); first.focus();
    }
  });
  $("chat-suggestions").addEventListener("click", event => { const button = event.target.closest("button"); if (button) sendChat(button.textContent); });
  $("chat-form").addEventListener("submit", event => { event.preventDefault(); const text = $("chat-input").value.trim(); if (text) sendChat(text); });
  async function sendChat(text) {
    if (chatBusy) return;
    chatBusy = true;
    $("chat-input").value = "";
    appendMessage("user", text);
    const pending = appendMessage("assistant", "لحظة، أحسب…");
    try {
      const result = await api("/api/chat", { method: "POST", body: { message: text } });
      pending.textContent = result.reply || "ما قدرت أطلع لك إجابة الحين.";
      if (result.tools?.length) {
        const trace = document.createElement("small");
        trace.className = "tool-trace";
        trace.textContent = `engine: ${result.tools.join(" · ")}`;
        pending.appendChild(trace);
      }
      (result.actions || []).filter(action => action.status === "pending").forEach(renderPendingAction);
    } catch (error) {
      pending.textContent = error.message || "فيه مشكلة بالاتصال، جرّب مرة ثانية.";
    } finally { chatBusy = false; $("chat-input").focus({ preventScroll: true }); }
  }
  function renderPendingAction(action) {
    const card = document.createElement("div");
    card.className = "message pending";
    const summary = document.createElement("div");
    summary.className = "pending-summary";
    summary.textContent = action.summary || "فيه تعديل ينتظر موافقتك.";
    const actions = document.createElement("div");
    actions.className = "pending-actions";
    const yes = document.createElement("button");
    yes.type = "button"; yes.className = "confirm-action"; yes.textContent = "أكّد";
    const no = document.createElement("button");
    no.type = "button"; no.className = "cancel-action"; no.textContent = "إلغاء";
    yes.addEventListener("click", () => resolveAction(action.id, "confirm", card, yes));
    no.addEventListener("click", () => resolveAction(action.id, "cancel", card, no));
    actions.append(yes, no); card.append(summary, actions); $("chat-messages").appendChild(card);
    $("chat-messages").scrollTop = $("chat-messages").scrollHeight;
  }
  async function resolveAction(id, operation, card, button) {
    if (button.disabled) return;
    card.querySelectorAll("button").forEach(item => item.disabled = true);
    try {
      await api(`/api/chat/actions/${encodeURIComponent(id)}/${operation}`, { method: "POST" });
      card.textContent = operation === "confirm" ? "تم التعديل." : "ألغينا التعديل.";
      if (operation === "confirm") {
        await updateWishCount();
        const page = (location.hash || "#overview").slice(1);
        const loaders = { overview: loadOverview, expenses: loadExpenses, obligations: loadObligations, buy: loadOffers, account: loadAccount, wish: loadWishlist };
        await loaders[page]?.();
      }
    } catch (error) { card.querySelectorAll("button").forEach(item => item.disabled = false); showError(error); }
  }

  /* Existing bank consent/onboarding, followed by explicit review of every detected plan. */
  const banks = [["demo1","بنك تجريبي أ"],["demo2","بنك تجريبي ب"],["demo3","بنك تجريبي ج"]];
  $("banks").innerHTML = banks.map(([id,name], index) => `<button type="button" class="bank-option" data-bank="${id}" aria-pressed="false"><span class="bank-monogram">${index + 1}</span><span>${esc(name)}</span></button>`).join("");
  $("banks").addEventListener("click", event => {
    const bank = event.target.closest("[data-bank]");
    if (!bank) return;
    selectedBank = bank.dataset.bank;
    $("banks").querySelectorAll("[data-bank]").forEach(item => item.setAttribute("aria-pressed", String(item === bank)));
    $("btn-connect").disabled = false;
  });
  function showOnboardScreen(id) {
    $("onboarding").hidden = false;
    ["ob-connect","ob-loading","ob-production","ob-error","ob-detect"].forEach(section => $(section).hidden = section !== id);
    if (id === "ob-production") $("ob-demo-note").hidden = true;
  }
  $("btn-connect").addEventListener("click", async event => {
    const button = event.currentTarget;
    if (apiMode === "production") return showOnboardScreen("ob-production");
    if (!selectedBank || button.disabled) return;
    button.disabled = true;
    showOnboardScreen("ob-loading");
    try {
      const [result] = await Promise.all([api("/api/consent", { method: "POST", body: { bank_id: selectedBank } }), new Promise(resolve => setTimeout(resolve, 700))]);
      saveToken(result.token);
      await startDetection(result);
    } catch (error) {
      showOnboardScreen("ob-error");
      $("ob-error-text").textContent = error.message || "تأكد من النت وجرّب مرة ثانية.";
    } finally { button.disabled = false; }
  });
  async function startDetection(result) {
    showOnboardScreen("ob-detect");
    $("ob-detect-title").textContent = `هذي الخطط اللي لقيناها (${format(result.plans_found || 0)})`;
    try { const plans = await api("/api/plans"); renderDetected(plans.plans || []); }
    catch (error) { showOnboardScreen("ob-error"); $("ob-error-text").textContent = error.message; }
  }
  function renderDetected(plans) {
    $("ob-plans").innerHTML = plans.length ? plans.map(plan => `<article class="detected-plan" data-detected="${esc(plan.id)}"><h3>${esc(plan.name)}</h3><div class="form-row"><label>المبلغ الشهري<input type="number" min="0.01" step="0.01" inputmode="decimal" name="amount" value="${esc(plan.amount)}" aria-label="المبلغ الشهري لخطة ${esc(plan.name)}"></label><label>الدفعات الباقية<input type="number" min="0" max="600" inputmode="numeric" name="remaining" value="${esc(plan.remaining ?? "")}" aria-label="الدفعات الباقية لخطة ${esc(plan.name)}"></label></div><div class="item-meta">يوم ${format(plan.day)} من كل شهر ${plan.confirmed ? "· مؤكدة" : ""}</div><button class="button ${plan.confirmed ? "secondary" : "primary"} full" type="button" data-detected-confirm="${esc(plan.id)}" ${plan.confirmed ? "disabled" : ""}>${plan.confirmed ? "تم التأكيد" : "أكد هالخطة"}</button></article>`).join("") : empty("ما لقينا خطط", "تقدر تضيف التزاماتك من الرئيسية بعدين.");
    $("btn-onboard-done").disabled = plans.some(plan => !plan.confirmed);
    $("btn-onboard-done").dataset.plans = String(plans.length);
  }
  $("ob-plans").addEventListener("click", async event => {
    const button = event.target.closest("[data-detected-confirm]");
    if (!button || button.disabled) return;
    const card = button.closest("[data-detected]");
    const amount = toNum(card.querySelector('[name="amount"]').value);
    const rawRemaining = card.querySelector('[name="remaining"]').value.trim();
    const remaining = rawRemaining === "" ? null : Number(rawRemaining);
    if (!amount || rawRemaining !== "" && (!Number.isInteger(remaining) || remaining < 0 || remaining > 600)) return toast("راجع مبلغ الخطة وعدد الدفعات.", "error");
    button.disabled = true;
    try {
      const result = await api(`/api/plans/${encodeURIComponent(button.dataset.detectedConfirm)}/confirm`, { method: "POST", body: { amount, ...(remaining === null ? {} : { remaining }) } });
      renderDetected(result.plans || (await api("/api/plans")).plans || []);
    } catch (error) { showError(error); button.disabled = false; }
  });
  $("btn-onboard-done").addEventListener("click", () => {
    $("onboarding").hidden = true;
    started = true;
    location.hash = "#overview";
    route();
  });
  $("btn-retry").addEventListener("click", boot);
  async function boot() {
    showOnboardScreen("ob-loading");
    try {
      const results = await Promise.all([
        api("/api/health"),
        api("/api/language").catch(() => { throw new Error("ما قدرنا نحمل صيغ الأعداد. جرّب مرة ثانية."); })
      ]);
      apiMode = results[0].demo_mode === true ? "demo" : "production";
      language = results[1]?.forms || results[1];
      if (!["payments","days"].every(kind => language?.[kind] && ["one","two","few","many"].every(form => typeof language[kind][form] === "string" && language[kind][form]))) {
        throw new Error("ما قدرنا نحمل صيغ الأعداد. جرّب مرة ثانية.");
      }
      $("wish-method").innerHTML = methodOptions();
      if (apiMode === "production") $("demo-next-month").hidden = true;
      if (!token) return showOnboardScreen(apiMode === "production" ? "ob-production" : "ob-connect");
      const summary = await api("/api/summary");
      if (apiMode === "demo" && !(number(summary.salary?.amount) > 0)) { saveToken(null); return showOnboardScreen("ob-connect"); }
      started = true;
      $("onboarding").hidden = true;
      route();
      updateWishCount();
    } catch (error) {
      if (error.status === 401 || error.status === 404) { saveToken(null); return showOnboardScreen(apiMode === "production" ? "ob-production" : "ob-connect"); }
      showOnboardScreen("ob-error");
      $("ob-error-text").textContent = error.message || "تأكد من النت وجرّب مرة ثانية.";
    }
  }
  boot();

  if ("serviceWorker" in navigator) {
    // Registered in the document shell; the worker caches static files only.
  }
})();