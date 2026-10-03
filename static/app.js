"use strict";
/* مُدار — phone web app. Every number comes from the API; nothing is calculated here
   except formatting and the ring's percentage. */

/* ---------- helpers ---------- */
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = n => Math.round(Number(n) || 0).toLocaleString("en-US");
const money = n => `<span class="num">${fmt(n)}</span> ر.س`;
const toNum = s => Number(String(s ?? "").replace(/[٠-٩]/g, d => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace(/[^\d.]/g, "")) || 0;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const T = s => (window.I18N && I18N.lang === "en" ? I18N.tr(s) : s);
const ask = s => confirm(T(s));

function counted(n, kind = "payments") {
  const f = kind === "days"
    ? ["يوم واحد", "يومين", "أيام", "يوم"]
    : kind === "months" ? ["شهر واحد", "شهرين", "شهور", "شهر"]
    : ["دفعة وحدة", "دفعتين", "دفعات", "دفعة"];
  if (n === 1) return f[0];
  if (n === 2) return f[1];
  return `${n} ${n >= 3 && n <= 10 ? f[2] : f[3]}`;
}
const whenDays = d => d <= 0 ? "اليوم" : d === 1 ? "بكرة" : d === 2 ? "بعد يومين" : `بعد ${counted(d, "days")}`;
const catName = c => (c && c.includes(":")) ? c.split(":")[1] : "أخرى";
const METHOD = { cash: "كاش", bnpl3: "3 دفعات", bnpl4: "4 دفعات", bnpl6: "6 شهور", fin12: "تمويل 12 شهر", save: "تجمع أول" };

const ICON = {
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  expenses: '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4M16 3v4M8 11h8M8 15h5"/>',
  obligations: '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 12h7M9 16h5"/>',
  planner: '<path d="M4 19h16"/><path d="m6 15 4-5 3 2 5-6"/><path d="M15 6h3v3"/>',
  account: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  heart: '<path d="M20.8 8.6c0 5.3-8.8 11-8.8 11s-8.8-5.7-8.8-11A4.6 4.6 0 0 1 12 6.2a4.6 4.6 0 0 1 8.8 2.4z"/>',
  chat: '<path d="M20 12a8 8 0 0 1-11.7 7.1L4 20l1-4.1A8 8 0 1 1 20 12z"/>',
  send: '<path d="m3 11 18-8-8 18-2-8z"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  back: '<path d="m9 6 6 6-6 6"/>',
  check: '<path d="m5 12 4 4 10-10"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  ext: '<path d="M14 4h6v6M10 14 20 4M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h9"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  card: '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18"/>',
  bill: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
  wallet: '<path d="M19 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3"/><path d="M21 8h-5a3 3 0 0 0 0 6h5z"/>',
  bank: '<path d="m3 9 9-5 9 5M5 10v8M9 10v8M15 10v8M19 10v8M3 20h18"/>',
  trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/><path d="M8 6H5a2 2 0 0 0 2 4h1M16 6h3a2 2 0 0 1-2 4h-1M12 13v4M9 21h6M10 17h4"/>',
  plane: '<path d="M10 3.5a1.5 1.5 0 0 1 3 0V9l8 4v2l-8-2v4l2 2v1l-3.5-1-3.5 1v-1l2-2v-4l-8 2v-2l8-4z"/>',
  gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v8h14v-8M12 8v12M12 8c-2-4-6-4-6-1s6 1 6 1zm0 0c2-4 6-4 6-1s-6 1-6 1z"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h7"/>',
  box: '<path d="m3 7 9-4 9 4-9 4z"/><path d="M3 7v10l9 4 9-4V7M12 11v10"/>'
};
const ic = (name, cls = "icon") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICON[name] || ""}</svg>`;

function toast(html, kind = "", ms = 5000) {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.innerHTML = html;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), ms);
}

/* ---------- API ---------- */
const S = {
  token: null, me: null, demo: true,
  chat: [], planner: { name: (() => { try { return localStorage.getItem("mudar_lang") === "en" ? "Phone" : "جوال"; } catch (_) { return "جوال"; } })(), price: "3000", months: "", chosen: null, others: false },
  obTab: "current", lastPhone: "", demoCode: "", authFlow: null
};
try { S.token = localStorage.getItem("mawid_token"); } catch (_) {}

function setToken(t) {
  S.token = t;
  try { t ? localStorage.setItem("mawid_token", t) : localStorage.removeItem("mawid_token"); } catch (_) {}
}

async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (S.token) headers.Authorization = "Bearer " + S.token;
  let res;
  try {
    res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch (_) {
    const e = new Error("فيه مشكلة بالاتصال، جرّب مرة ثانية."); e.status = 0; throw e;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = "صار شي غلط، جرّب مرة ثانية.";
    if (typeof data.detail === "string") msg = data.detail;
    else if (Array.isArray(data.detail)) msg = "تأكد من البيانات المدخلة.";
    const e = new Error(msg); e.status = res.status; throw e;
  }
  return data;
}

function handleError(e) {
  if (e.status === 401) { setToken(null); showWelcome(); return; }
  if (e.status === 404 && /اربط حسابك/.test(e.message)) { showBankConnect(); return; }
  toast(esc(e.message), "bad");
}

/* ---------- theme ---------- */
function applyTheme(t) {
  const theme = t || (() => { try { return localStorage.getItem("mudar_theme") || "dark"; } catch (_) { return "dark"; } })();
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("mudar_theme", theme); } catch (_) {}
  const dark = theme === "dark" || (theme === "system" && !matchMedia("(prefers-color-scheme: light)").matches);
  $('meta[name="theme-color"]').setAttribute("content", dark ? "#1f1d26" : "#f4f2fb");
}

/* ---------- sheets ---------- */
function openSheet({ title = "", body = "", tall = false, onMount } = {}) {
  closeSheet();
  const bg = document.createElement("div");
  bg.className = "sheet-bg";
  bg.innerHTML = `<div class="sheet ${tall ? "tall" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <div class="grab"></div>
      <div class="sheet-head"><h3>${esc(title)}</h3><button class="x-btn" data-close aria-label="إغلاق">${ic("x")}</button></div>
      <div class="sheet-body">${body}</div></div>`;
  bg.addEventListener("click", e => { if (e.target === bg || e.target.closest("[data-close]")) closeSheet(); });
  $("#layer").appendChild(bg);
  const sheet = $(".sheet", bg);
  onMount && onMount(sheet);
  return sheet;
}
function closeSheet() { $$(".sheet-bg").forEach(x => x.remove()); }

/* ---------- auth screens ---------- */
function screen(html) {
  closeSheet();
  $("#layer").innerHTML = `<div class="screen" id="screen"><div class="inner">${html}</div></div>`;
  $("#nav").hidden = true; $("#fab").hidden = true;
  return $("#screen");
}
function closeScreen() { const s = $("#screen"); if (s) s.remove(); }

let LOGO_ID = 0;
function logoSVG(cls = "") {
  const id = "arcg" + (++LOGO_ID);
  return `<svg class="mark ${cls}" viewBox="0 0 240 240" role="img" aria-label="شعار مُدار">
    <defs><linearGradient id="${id}" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6a4bdc"/><stop offset=".55" stop-color="#9b82f2"/><stop offset="1" stop-color="#c4b5ff"/></linearGradient></defs>
    <circle class="trk" cx="120" cy="120" r="100" fill="none" stroke-width="9"/>
    <circle class="arc" cx="120" cy="120" r="100" fill="none" stroke="url(#${id})" stroke-width="9" stroke-linecap="round" stroke-dasharray="471 628" transform="rotate(-90 120 120)"/>
    <text class="d-letter" x="132" y="96" font-size="56" text-anchor="middle">و</text>
    <text class="m-letter" x="120" y="182" font-size="100" text-anchor="middle">م</text>
    <g class="orbit"><circle class="planet" cx="20" cy="120" r="13"/></g>
  </svg>`;
}

/* Opening animation: the orbit draws itself, the planet travels around it, the meem rises,
   the damma drops in, then the logo flies up into the welcome screen. Tap to skip (the planet spins). */
function splash() {
  return new Promise(resolve => {
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const el = document.createElement("div");
    el.className = "splash";
    el.setAttribute("role", "presentation");
    el.innerHTML = `<div class="stage">${logoSVG()}</div><div class="word">مُدار</div>
      <div class="tag">التزاماتك، مصاريفك، وراتبك بمكان واحد</div><div class="skip">اضغط للتخطي</div>`;
    document.body.appendChild(el);
    let done = false;
    const finish = () => {
      if (done) return; done = true;
      el.classList.add("out");
      setTimeout(() => el.remove(), 750);
      resolve();
    };
    el.addEventListener("click", () => { el.classList.add("spin"); setTimeout(finish, 420); });
    setTimeout(finish, reduce ? 250 : 2700);
  });
}

/* Welcome logo: drag the planet around its orbit; it springs back home. Tap for a spin. */
function bindOrbit(wrap) {
  const orbit = $(".orbit", wrap);
  let dragging = false, moved = false;
  const angle = e => {
    const r = wrap.getBoundingClientRect();
    return Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)) * 180 / Math.PI;
  };
  wrap.addEventListener("pointerdown", e => { dragging = true; moved = false; wrap.classList.add("dragging"); wrap.setPointerCapture(e.pointerId); });
  wrap.addEventListener("pointermove", e => {
    if (!dragging) return;
    moved = true;
    orbit.style.transform = `rotate(${angle(e) - 180}deg)`;
  });
  const end = () => {
    if (!dragging) return;
    dragging = false; wrap.classList.remove("dragging");
    if (!moved) {
      orbit.style.transition = "transform .8s cubic-bezier(.65,0,.35,1)";
      orbit.style.transform = "rotate(360deg)";
      setTimeout(() => { orbit.style.transition = "none"; orbit.style.transform = "rotate(0deg)"; requestAnimationFrame(() => (orbit.style.transition = "")); }, 820);
    } else {
      orbit.style.transform = "rotate(0deg)";
    }
  };
  wrap.addEventListener("pointerup", end);
  wrap.addEventListener("pointercancel", end);
}

function showWelcome() {
  const el = screen(`
    <div class="orbit-play" id="orbit-play">${logoSVG()}</div>
    <p class="orbit-hint">حرّك الكوكب حول مداره</p>
    <h1 class="brand-name lavender">مُدار</h1>
    <p class="brand-tag">التزاماتك، مصاريفك، وراتبك بمكان واحد</p>
    <div class="stack" style="margin-top:auto">
      <button class="btn block" data-go="signup">إنشاء حساب</button>
      <button class="btn ghost block" data-go="login">عندي حساب، سجّل دخول</button>
      <button class="btn soft block" data-go="demo">دخول سريع بحساب نورة (للديمو)</button>
      <button class="btn ghost block" disabled>الدخول عبر نفاذ (قريباً)</button>
      <p class="muted" style="text-align:center;margin:6px 0 0">بيانات وهمية للهاكاثون</p>
    </div>`);
  bindOrbit($("#orbit-play", el));
  el.addEventListener("click", async e => {
    const go = e.target.closest("[data-go]")?.dataset.go;
    if (go === "signup") showSignup();
    if (go === "login") showLogin();
    if (go === "demo") {
      try { const r = await api("/api/auth/demo", { method: "POST" }); setToken(r.token); await startApp(); }
      catch (err) { handleError(err); }
    }
  });
}

function backBtn(attr) { return `<button class="back-btn" ${attr}>${ic("back")} رجوع</button>`; }

function legalSheet(kind) {
  const terms = `<p>مُدار يعطيك معلومات وتنبيهات عن التزاماتك ومصاريفك، وهذي مو استشارة مالية.</p>
    <p>أنت المسؤول عن قراراتك المالية. العروض المعروضة بالتطبيق تجريبية للتوضيح.</p>
    <p>تقدر تلغي ربط حسابك البنكي بأي وقت من «حسابي».</p>`;
  const privacy = `<p>نقرأ عملياتك البنكية بموافقتك، وقراءة فقط. ما نقدر نحوّل ولا ندفع بدون موافقتك من تطبيق البنك.</p>
    <p>رقم جوالك ما ينحفظ كامل، نحفظ نسخة مشفّرة وآخر 3 أرقام بس.</p>
    <p>مصاريفك ما تطلع لأي جهة، والمساعد الذكي يشوف إجماليات بس.</p>`;
  openSheet({ title: kind === "terms" ? "الشروط" : "سياسة الخصوصية", body: `<div class="card" style="line-height:1.9">${kind === "terms" ? terms : privacy}</div>` });
}

function showSignup() {
  const el = screen(`
    ${backBtn('data-act="welcome"')}
    <h1 class="page-title">إنشاء حساب</h1>
    <p class="page-sub">بنرسل لك رمز تحقق على جوالك.</p>
    <form id="f-signup">
      <label class="field"><span>الاسم</span><input name="name" required minlength="2" maxlength="40" autocomplete="given-name"></label>
      <label class="field"><span>رقم الجوال</span><input name="phone" required inputmode="tel" placeholder="05XXXXXXXX" dir="ltr" style="text-align:right" autocomplete="tel" value="${esc(S.lastPhone)}"></label>
      <label class="field"><span>الإيميل (اختياري)</span><input name="email" type="email" dir="ltr" style="text-align:right" autocomplete="email"></label>
      <label class="check"><input type="checkbox" name="terms" required>
        <span>أوافق على <a href="#" data-legal="terms">الشروط</a> و<a href="#" data-legal="privacy">سياسة الخصوصية</a></span></label>
      <button class="btn block" type="submit">أرسل الرمز</button>
    </form>`);
  el.addEventListener("click", e => {
    if (e.target.closest('[data-act="welcome"]')) showWelcome();
    const legal = e.target.closest("[data-legal]");
    if (legal) { e.preventDefault(); legalSheet(legal.dataset.legal); }
  });
  $("#f-signup").addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.target;
    S.lastPhone = f.phone.value.trim();
    try {
      const r = await api("/api/auth/signup", { method: "POST", body: {
        name: f.name.value.trim(), phone: S.lastPhone, email: f.email.value.trim() || null, accept_terms: f.terms.checked } });
      S.demoCode = r.demo_code || ""; S.authFlow = "signup";
      showOtp();
    } catch (err) {
      if (err.status === 409) { toast(esc(err.message)); showLogin(); return; }
      handleError(err);
    }
  });
}

function showLogin() {
  const el = screen(`
    ${backBtn('data-act="welcome"')}
    <h1 class="page-title">تسجيل الدخول</h1>
    <p class="page-sub">اكتب رقم جوالك ونرسل لك رمز.</p>
    <form id="f-login">
      <label class="field"><span>رقم الجوال</span><input name="phone" required inputmode="tel" placeholder="05XXXXXXXX" dir="ltr" style="text-align:right" autocomplete="tel" value="${esc(S.lastPhone)}"></label>
      <button class="btn block" type="submit">أرسل الرمز</button>
    </form>
    <p class="muted" style="margin-top:14px">حساب الديمو: 0500000123</p>`);
  el.addEventListener("click", e => { if (e.target.closest('[data-act="welcome"]')) showWelcome(); });
  $("#f-login").addEventListener("submit", async e => {
    e.preventDefault();
    S.lastPhone = e.target.phone.value.trim();
    try {
      const r = await api("/api/auth/login", { method: "POST", body: { phone: S.lastPhone } });
      S.demoCode = r.demo_code || ""; S.authFlow = "login";
      showOtp();
    } catch (err) { handleError(err); }
  });
}

function showOtp() {
  const last = S.lastPhone.replace(/\D/g, "").slice(-3);
  const el = screen(`
    ${backBtn('data-act="change"')}
    <h1 class="page-title">أدخل الرمز</h1>
    <p class="page-sub">أرسلناه لـ <span dir="ltr">05XX XXX ${esc(last)}</span></p>
    ${S.demoCode ? `<div class="alert good">رمزك التجريبي: <b class="num" dir="ltr">${esc(S.demoCode)}</b></div>`
      : `<div class="alert warn">إذا الرقم مسجل بيوصلك رمز. إذا ما عندك حساب، أنشئ واحد.</div>`}
    <div class="otp" id="otp">${Array.from({ length: 6 }, (_, i) => `<input inputmode="numeric" maxlength="1" aria-label="الرقم ${i + 1}" autocomplete="${i ? "off" : "one-time-code"}">`).join("")}</div>
    <button class="btn block" id="verify">تأكيد</button>
    <div class="btn-row" style="justify-content:space-between;margin-top:14px">
      <button class="link-btn" id="resend" disabled>إعادة الإرسال بعد <span id="secs">60</span> ثانية</button>
      <button class="link-btn" data-act="change">غيّر الرقم</button>
    </div>`);
  const boxes = $$("#otp input", el);
  boxes[0].focus();
  const code = () => boxes.map(b => b.value).join("");
  boxes.forEach((b, i) => {
    b.addEventListener("input", () => {
      b.value = b.value.replace(/[٠-٩]/g, d => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace(/\D/g, "").slice(-1);
      if (b.value && i < 5) boxes[i + 1].focus();
      if (code().length === 6) verify();
    });
    b.addEventListener("keydown", e => { if (e.key === "Backspace" && !b.value && i > 0) boxes[i - 1].focus(); });
    b.addEventListener("paste", e => {
      const t = (e.clipboardData.getData("text") || "").replace(/\D/g, "").slice(0, 6);
      if (t.length) { e.preventDefault(); t.split("").forEach((d, j) => boxes[j] && (boxes[j].value = d)); if (t.length === 6) verify(); }
    });
  });
  let left = 60;
  const timer = setInterval(() => {
    left -= 1; const s = $("#secs"); if (s) s.textContent = left;
    if (left <= 0) { clearInterval(timer); const r = $("#resend"); if (r) { r.disabled = false; r.textContent = "إعادة الإرسال"; } }
  }, 1000);
  let busy = false;
  async function verify() {
    if (busy || code().length !== 6) return;
    busy = true;
    try {
      const r = await api("/api/auth/verify", { method: "POST", body: { phone: S.lastPhone, code: code() } });
      clearInterval(timer);
      setToken(r.token);
      if (r.bank_connected) await startApp(); else showBankConnect();
    } catch (err) {
      boxes.forEach(b => (b.value = "")); boxes[0].focus();
      handleError(err);
    } finally { busy = false; }
  }
  $("#verify").addEventListener("click", verify);
  el.addEventListener("click", async e => {
    if (e.target.closest('[data-act="change"]')) { clearInterval(timer); S.authFlow === "signup" ? showSignup() : showLogin(); }
    if (e.target.closest("#resend") && !$("#resend").disabled) {
      try {
        const r = await api("/api/auth/login", { method: "POST", body: { phone: S.lastPhone } });
        S.demoCode = r.demo_code || S.demoCode; clearInterval(timer); showOtp(); toast("أرسلنا رمز جديد.", "good");
      } catch (err) { handleError(err); }
    }
  });
}

/* ---------- bank connection (onboarding) ---------- */
function showBankConnect() {
  const banks = [["demo1", "بنك تجريبي أ", "حساب الراتب"], ["demo2", "بنك تجريبي ب", "بطاقة ائتمانية"], ["demo3", "بنك تجريبي ج", "حساب توفير"]];
  const picked = new Set(["demo1"]);
  const el = screen(`
    <div style="width:84px;margin:6px auto 0">${logoSVG()}</div>
    <h1 class="page-title" style="text-align:center;margin-top:10px">اربط حساباتك البنكية</h1>
    <p class="page-sub" style="text-align:center">اختر كل البنوك اللي تستخدمها، عشان نشوف كل التزاماتك واشتراكاتك بمكان واحد. ما نقدر نحوّل ولا ندفع.</p>
    <div id="banks">${banks.map(([id, n, sub]) => `<button class="bank multi" data-bank="${id}" aria-pressed="${picked.has(id)}">
      <span class="ico">${ic("bank")}</span><span><b>${n}</b><br><span class="muted">${sub}</span></span></button>`).join("")}</div>
    <div class="card tight">
      <h2>وش اللي بتوافق عليه</h2>
      <ul class="perm">
        <li><span class="teal">✓</span>قراءة الحسابات والرصيد</li>
        <li><span class="teal">✓</span>قراءة العمليات لآخر 12 شهر</li>
        <li><span class="red">✕</span>التحويل أو الدفع من حسابك</li>
        <li><span class="teal">✓</span>تقدر تلغي الموافقة بأي وقت، وتنتهي لحالها بعد 90 يوم</li>
      </ul>
    </div>
    <button class="btn block" id="approve">وافق من تطبيق البنك (${picked.size})</button>
    <button class="link-btn" style="margin:14px auto 0" data-act="logout">تسجيل الخروج</button>`);
  el.addEventListener("click", async e => {
    const b = e.target.closest("[data-bank]");
    if (b) {
      picked.has(b.dataset.bank) ? picked.delete(b.dataset.bank) : picked.add(b.dataset.bank);
      b.setAttribute("aria-pressed", picked.has(b.dataset.bank));
      $("#approve").textContent = picked.size ? `وافق من تطبيق البنك (${picked.size})` : "اختر بنك واحد على الأقل";
      $("#approve").disabled = !picked.size;
    }
    if (e.target.closest('[data-act="logout"]')) logout();
    if (e.target.closest("#approve") && picked.size) connect([...picked]);
  });
}

async function connect(bankIds) {
  const el = screen(`<div class="spinner"></div><p style="text-align:center" id="load-text">ننتظر موافقتك من تطبيق البنك…</p>`);
  const say = t => { const x = $("#load-text", el); if (x) x.textContent = t; };
  try {
    const [first, ...rest] = bankIds;
    const [r] = await Promise.all([api("/api/consent", { method: "POST", body: { bank_id: first } }), sleep(900)]);
    setToken(r.token);
    for (const id of rest) {
      say(`نربط ${id === "demo2" ? "بنك تجريبي ب" : id === "demo3" ? "بنك تجريبي ج" : "البنك"}…`);
      await Promise.all([api("/api/banks", { method: "POST", body: { bank_id: id } }), sleep(600)]);
    }
    say("نكتشف التزاماتك واشتراكاتك ونصنف مصاريفك…");
    await sleep(700);
    showDetected();
  } catch (err) { showBankConnect(); handleError(err); }
}

async function showDetected() {
  const data = await api("/api/plans");
  const plans = data.plans.filter(p => p.remaining !== 0);
  const render = () => {
    const el = screen(`
      <h1 class="page-title">لقينا ${counted(plans.length).replace("دفعة وحدة", "التزام واحد").replace("دفعتين", "التزامين").replace("دفعات", "التزامات").replace("دفعة", "التزام")}</h1>
      <p class="page-sub">أكّد كل وحدة بضغطة. لو فيه شي غلط، عدّله من صفحة الالتزامات.</p>
      <div class="card tight">${plans.map(p => `<div class="row">
        <div class="l"><span class="ico">${ic("card")}</span><div><div class="t">${esc(p.name)}</div>
        <div class="s">${p.total ? `${p.total} × ${fmt(p.amount)}، باقي ${counted(p.remaining)}` : `${fmt(p.amount)} شهرياً`}، يوم ${p.day}</div></div></div>
        ${p.confirmed ? `<span class="badge b-paid">${ic("check", "icon")}مؤكد</span>` : `<button class="btn soft sm" data-confirm="${esc(p.id)}">صح</button>`}</div>`).join("")}</div>
      <button class="btn block" id="done" ${plans.some(p => !p.confirmed) ? "disabled" : ""}>تمام، ودّني للرئيسية</button>`);
    el.addEventListener("click", async e => {
      const c = e.target.closest("[data-confirm]");
      if (c) {
        try { await api(`/api/plans/${encodeURIComponent(c.dataset.confirm)}/confirm`, { method: "POST", body: {} });
          plans.find(p => p.id === c.dataset.confirm).confirmed = true; render(); }
        catch (err) { handleError(err); }
      }
      if (e.target.closest("#done")) { location.hash = "#home"; startApp(); }
    });
  };
  render();
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (_) {}
  setToken(null); S.chat = []; S.me = null;
  showWelcome();
}

/* ---------- app shell ---------- */
const TABS = [
  { id: "expenses", label: "المصروفات", icon: "expenses" },
  { id: "obligations", label: "الالتزامات", icon: "obligations" },
  { id: "home", label: "الرئيسية", icon: "home", center: true },
  { id: "planner", label: "المخطط", icon: "planner" },
  { id: "account", label: "حسابي", icon: "account" }
];
const PAGES = { home: renderHome, expenses: renderExpenses, obligations: renderObligations, planner: renderPlanner,
  account: renderAccount, wishlist: renderWishlist, subscriptions: renderSubscriptions, standings: renderStandings };

async function startApp() {
  try {
    S.me = await api("/api/auth/me");
    const health = await api("/api/health"); S.demo = !!health.demo_mode;
  } catch (err) { handleError(err); return; }
  if (!S.me.bank_connected) { showBankConnect(); return; }
  closeScreen();
  $("#nav").hidden = false; $("#fab").hidden = false;
  $("#nav").innerHTML = TABS.map(t => t.center
    ? `<a href="#home" class="home" data-tab="home"><span class="orb">${ic("home")}</span><span>${t.label}</span></a>`
    : `<a href="#${t.id}" data-tab="${t.id}">${ic(t.icon)}<span>${t.label}</span></a>`).join("");
  $("#fab").innerHTML = ic("chat");
  route();
}

function route() {
  if (!S.token || !S.me) return;
  const id = (location.hash || "#home").slice(1);
  const page = PAGES[id] ? id : "home";
  $$("#nav [data-tab]").forEach(a => a.setAttribute("aria-current", a.dataset.tab === page ? "page" : "false"));
  window.scrollTo(0, 0);
  $("#view").innerHTML = `<div class="skeleton"></div><div class="skeleton" style="height:90px"></div>`;
  PAGES[page]().catch(handleError);
}
window.addEventListener("hashchange", route);
function refresh() { route(); }

function topbar(html) { $("#topbar").innerHTML = html; }
function heartBtn(count = 0, ready = false) {
  return `<a class="square-btn" href="#wishlist" aria-label="قائمة الأمنيات (${count})">${ic("heart")}${ready ? '<span class="dot"></span>' : ""}</a>`;
}
function pageTop(title, count, ready) {
  topbar(`<div><h1 class="page-title">${esc(title)}</h1></div>${heartBtn(count, ready)}`);
}
function backTop(title) {
  topbar(`<div><button class="back-btn" onclick="history.length > 1 ? history.back() : (location.hash = '#home')">${ic("back")} رجوع</button>
    <h1 class="page-title">${esc(title)}</h1></div>`);
}
async function wishState() {
  try { const w = await api("/api/wishlist"); return { count: w.items.length, ready: w.items.some(i => i.status && i.status.ok), items: w.items }; }
  catch (_) { return { count: 0, ready: false, items: [] }; }
}
function alertBox(a) {
  if (a.type === "before_salary") return { cls: "warn", icon: "alert", text: `عندك ${a.plans.length === 1 ? "دفعة" : counted(a.plans.length)} (${money(a.amount)}) قبل نزول راتبك: ${a.plans.map(p => `${esc(p.name)} ${whenDays(p.days_until)}`).join("، ")}.` };
  if (a.type === "plan_ending") return { cls: "good", icon: "check", text: `<b>خبر حلو:</b> ${esc(a.name)} تخلص هالشهر، يعني يرجع لك ${money(a.frees)} من الشهر الجاي.` };
  if (a.type === "spending_pace") return { cls: "warn", icon: "clock", text: `صرفت ${a.pct}% من اللي تقدر تصرفه، والراتب ${whenDays(a.days_to_salary)}.` };
  if (a.type === "personal_budget_exceeded") return { cls: "bad", icon: "alert", text: esc(a.message) };
  if (a.message) return { cls: "warn", icon: "alert", text: esc(a.message) };
  return null;
}
const alertsHtml = list => list.map(alertBox).filter(Boolean).map(a => `<div class="alert ${a.cls}">${ic(a.icon)}<div>${a.text}</div></div>`).join("");

/* ---------- HOME ---------- */
function ringSvg(fraction, cls = "") {
  const R = 96, C = 2 * Math.PI * R, f = Math.max(0, Math.min(1, fraction));
  return `<svg viewBox="0 0 224 224"><circle class="track" cx="112" cy="112" r="${R}" fill="none" stroke-width="18"/>
    <circle class="fill ${cls}" cx="112" cy="112" r="${R}" fill="none" stroke-width="18" stroke-linecap="round"
      stroke-dasharray="${C}" stroke-dashoffset="${C}" data-target="${C * (1 - f)}"/></svg>`;
}
function animateRings(root = document) {
  requestAnimationFrame(() => $$(".ring .fill", root).forEach(f => (f.style.strokeDashoffset = f.dataset.target)));
}

async function renderHome() {
  const [s, w, sc, lb] = await Promise.all([api("/api/summary"), wishState(), api("/api/score"), api("/api/leaderboard")]);
  S._score = sc;
  const days = s.salary.days_left;
  topbar(`<div class="who"><span class="avatar">${esc(T(s.display_name || "م").trim().charAt(0))}</span>
      <div><b>هلا ${esc(s.display_name || "")}</b><small>${days <= 0 ? "الراتب اليوم" : `الراتب بعد ${counted(days, "days")}`}</small></div></div>
    ${heartBtn(w.count, w.ready)}`);

  /* slide 1: what's left to spend */
  const safe = Math.max(0, s.safe_to_spend), avail = s.available;
  const pct = safe > 0 ? avail / safe : 0;
  const slide1 = `<section class="card ring-card slide" aria-label="باقي لك">
      <div class="ring">${ringSvg(avail < 0 ? 1 : pct, avail < 0 ? "neg" : "")}
        <div class="ring-center"><span class="k">${avail < 0 ? "تعدّيت بـ" : "باقي لك"}</span>
          <span class="v num ${avail < 0 ? "neg" : ""}">${fmt(Math.abs(avail))}</span>
          <span class="of">ر.س من <span class="num">${fmt(s.safe_to_spend)}</span></span></div></div>
      <p class="ring-foot">صرفت ${money(s.spent)} من مصروفك لهالشهر</p>
    </section>`;

  /* slide 2: this month's obligations — paid vs left */
  const plans = s.plans;
  const dueTotal = plans.reduce((a, p) => a + p.amount, 0);
  const paid = plans.filter(p => p.status === "paid").reduce((a, p) => a + p.amount, 0);
  const left = dueTotal - paid;
  const slide2 = `<section class="card ring-card slide" aria-label="التزاماتك هالشهر">
      <div class="ring">${ringSvg(dueTotal ? paid / dueTotal : 0, "v")}
        <div class="ring-center"><span class="k">دفعت هالشهر</span>
          <span class="v num lav" style="font-size:48px">${fmt(paid)}</span>
          <span class="of">ر.س من <span class="num">${fmt(dueTotal)}</span></span></div></div>
      <p class="ring-foot">${left > 0 ? `باقي عليك ${money(left)} هالشهر` : "سدّدت كل التزامات هالشهر ✓"}</p>
      <div class="mini-list">${plans.slice(0, 6).map(p => `<span class="badge ${p.status === "paid" ? "b-paid" : "b-upcoming"}">${p.status === "paid" ? "✓" : "•"} ${esc(p.name)}</span>`).join("")}</div>
    </section>`;

  /* slide 3: living expenses recorded this month vs the usual average */
  const en = s.essentials_now || { total: 0, average: 0, by_category: {} };
  const top = Object.entries(en.by_category).slice(0, 4);
  const slide3 = `<section class="card ring-card slide" aria-label="المعيشة هالشهر">
      <div class="ring">${ringSvg(en.average ? en.total / en.average : 0, en.total > en.average ? "neg" : "g")}
        <div class="ring-center"><span class="k">المعيشة هالشهر</span>
          <span class="v num gold" style="font-size:48px">${fmt(en.total)}</span>
          <span class="of">ر.س من متوسطك <span class="num">${fmt(en.average)}</span></span></div></div>
      <p class="ring-foot">${en.total > en.average ? `أعلى من العادة بـ ${money(en.total - en.average)}` : en.total === en.average ? "مثل المعتاد بالضبط" : `أقل من المعتاد بـ ${money(en.average - en.total)} للحين`}</p>
      <div class="mini-list">${top.map(([k, v]) => `<span class="badge b-grey">${esc(k)} ${fmt(v)}</span>`).join("")}</div>
    </section>`;

  const before = s.alerts.find(a => a.type === "before_salary");
  const renew = s.alerts.find(a => a.type === "subscription_renewal");
  const ending = s.alerts.find(a => a.type === "plan_ending");
  const next = s.plans.find(p => p.status === "upcoming");

  const card1 = before
    ? `<div class="card tight small-card tap" data-act="pay"><span class="dot-label amber">قبل الراتب</span>
        <div><div class="big">${money(before.amount)}</div><div class="muted">${before.plans.length === 1 ? `دفعة ${esc(before.plans[0].name)}` : counted(before.plans.length)}</div></div></div>`
    : next
      ? `<a class="card tight small-card tap" href="#obligations" style="text-decoration:none"><span class="dot-label violet">الدفعة الجاية</span>
          <div><div class="big">${money(next.amount)}</div><div class="muted">${esc(next.name)}، ${whenDays(next.days_until)}</div></div></a>`
      : `<div class="card tight small-card"><span class="dot-label teal">ما عليك شي</span><div><div class="big">ولا دفعة</div><div class="muted">قبل الراتب</div></div></div>`;
  const card2 = renew
    ? `<a class="card tight small-card tap" href="#obligations" style="text-decoration:none"><span class="dot-label gold">يتجدد ${whenDays(renew.days_until)}</span>
        <div><div class="big">${esc(renew.name)}</div><div class="muted">${money(renew.amount)}، ألغه لو ما تبيه</div></div></a>`
    : ending
      ? `<a class="card tight small-card tap" href="#obligations" style="text-decoration:none"><span class="dot-label teal">خبر حلو</span>
          <div><div class="big">${esc(ending.name)} تخلص</div><div class="muted">هالشهر</div></div></a>`
      : `<a class="card tight small-card tap" href="#obligations" style="text-decoration:none"><span class="dot-label violet">التزاماتك</span>
          <div><div class="big">${money(s.obligations_total)}</div><div class="muted">شهرياً</div></div></a>`;

  const featured = renew || ending;
  const otherAlerts = s.alerts.filter(a => a.type !== "before_salary" && a !== featured);
  $("#view").innerHTML = `
    <div class="slider" id="slider">${scoreSlide(sc, lb)}${slide1}${slide2}${slide3}</div>
    <div class="dots" id="dots">${["تقييم إدارتك", "باقي لك", "التزاماتك هالشهر", "المعيشة"].map((l, i) => `<button aria-label="${l}" data-slide="${i}" aria-current="${i === 0}"></button>`).join("")}</div>
    <div class="grid-2">${card1}${card2}</div>
    ${otherAlerts.length ? `<section class="card tight">${alertsHtml(otherAlerts)}</section>` : ""}
    <a class="card tap" href="#obligations" style="display:block;text-decoration:none">
      <div class="card-head"><h2>كيف نحسب «باقي لك»</h2></div>
      <div class="row"><span class="muted">الراتب</span><span class="r">${money(s.formula.salary)}</span></div>
      <div class="row"><span class="muted">الالتزامات والاشتراكات</span><span class="r">− ${money(s.formula.obligations)}</span></div>
      <div class="row"><span class="muted">المعيشة (متوسط آخر 3 شهور)</span><span class="r">− ${money(s.formula.essentials)}</span></div>
      <div class="row"><span class="muted">هامش الأمان</span><span class="r">− ${money(s.formula.buffer)}</span></div>
      <div class="row"><span class="t teal">تقدر تصرف هالشهر</span><span class="r teal">${money(s.safe_to_spend)}</span></div>
      ${(s.banks || []).length > 1 ? `<p class="muted" style="margin:8px 0 0">من ${s.banks.length === 2 ? "بنكين" : `${s.banks.length} بنوك`} مربوطة.</p>` : ""}
    </a>`;
  animateRings();
  bindSlider();
}

function bindSlider() {
  const slider = $("#slider"), dots = $$("#dots button");
  if (!slider) return;
  const slides = $$(".slide", slider);
  const io = new IntersectionObserver(entries => {
    entries.forEach(en => {
      if (en.intersectionRatio > 0.6) {
        const i = slides.indexOf(en.target);
        dots.forEach((d, j) => d.setAttribute("aria-current", j === i));
      }
    });
  }, { root: slider, threshold: [0.6] });
  slides.forEach(s => io.observe(s));
  dots.forEach((d, i) => d.addEventListener("click", () => slides[i].scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" })));
}

/* ---------- EXPENSES ---------- */
let CATS = null;
async function categories() {
  if (!CATS) CATS = (await api("/api/categories")).groups;
  return CATS;
}
function cycleStart(todayIso, salaryDay) {
  const t = new Date(todayIso + "T00:00:00");
  const d = new Date(t.getFullYear(), t.getMonth(), salaryDay);
  if (t.getDate() < salaryDay) d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 10);
}
async function renderExpenses() {
  const [ex, s, w] = await Promise.all([api("/api/expenses"), api("/api/summary"), wishState()]);
  pageTop("المصروفات", w.count, w.ready);
  const start = cycleStart(s.today, s.salary.day);
  const all = ex.items.filter(i => i.date >= start && i.date <= s.today && !["installment", "income", "subscription"].includes(i.category));
  const sources = [...new Set(all.map(i => i.bank_name))];
  const f = S.expFilter && sources.includes(S.expFilter) ? S.expFilter : "all";
  const items = f === "all" ? all : all.filter(i => i.bank_name === f);
  const personal = (s.budget.target || []).find(t => t.id === "personal") || { amount: 0, pct: 20 };
  const used = personal.amount ? s.spent / personal.amount : 0;
  const warns = s.alerts.filter(a => a.type && a.type.startsWith("personal_budget"));
  const flex = Object.entries(s.categories.flexible || {}).sort((a, b) => b[1] - a[1]);
  $("#view").innerHTML = `
    <p class="page-sub">من ${(s.banks || []).length > 1 ? "كل حساباتك البنكية" : "حسابك البنكي"}، وتقدر تضيف يدوي.</p>
    <section class="card">
      <div class="muted">صرفك الشخصي هالشهر</div>
      <div class="huge" style="margin:4px 0 10px">${money(s.spent)}</div>
      <div class="bar ${used >= 1 ? "over" : used >= .8 ? "warn" : ""}"><span style="width:${Math.min(100, used * 100)}%"></span></div>
      <p class="muted" style="margin:8px 0 0">حدك ${personal.pct}% من راتبك = ${money(personal.amount)}. تقدر تغيّره من «حسابي».</p>
      ${warns.length ? `<div style="margin-top:12px">${alertsHtml(warns)}</div>` : ""}
    </section>
    <button class="btn block" data-act="add-expense" style="margin-bottom:14px">${ic("plus")} أضف مصروف</button>
    <section class="card">
      <h2>حسب الفئة</h2>
      ${flex.length ? flex.map(([k, v]) => `<div class="row"><span>${esc(k)}</span><span class="r">${money(v)}</span></div>`).join("") : `<div class="empty">ما فيه مصروفات شخصية هالشهر للحين.</div>`}
      <p class="muted" style="margin:10px 0 0">المعيشة (بقالة، وقود، فواتير…) والاشتراكات محسوبة ضمن «الالتزامات».</p>
    </section>
    <section class="card">
      <h2>عمليات هالشهر</h2>
      ${sources.length > 1 ? `<div class="filters">${["all", ...sources].map(x => `<button data-exp-filter="${esc(x)}" aria-pressed="${f === x}">${x === "all" ? "الكل" : esc(x)}</button>`).join("")}</div>` : ""}
      <p class="muted" style="margin-top:0">اضغط على أي عملية من البنك عشان تغيّر تصنيفها، ونتذكره للمرات الجاية.</p>
      ${items.length ? items.map(i => `<${i.deletable ? "div" : "button"} class="row" ${i.deletable ? "" : `data-recat="${esc(i.merchant)}"`}>
          <div class="l"><span class="ico ${i.category && i.category.startsWith("essential") ? "t" : ""}">${ic("wallet")}</span>
          <div><div class="t">${esc(i.merchant)}</div>
            <div class="s"><span class="num">${esc(i.date)}</span> · ${esc(catName(i.category))}</div>
            <div class="bank-tag">${ic("bank", "icon")} ${esc(i.bank_name)}</div></div></div>
          <div style="display:flex;align-items:center;gap:6px"><span class="r">${money(i.amount)}</span>
          ${i.deletable ? `<button class="x-btn" data-del-exp="${esc(i.id)}" aria-label="حذف">${ic("trash")}</button>` : ""}</div>
        </${i.deletable ? "div" : "button"}>`).join("") : `<div class="empty">ما فيه مصروفات هالشهر للحين.</div>`}
    </section>`;
}

async function addExpenseSheet() {
  const groups = await categories();
  const flex = groups.find(g => g.id === "flexible").items;
  const sheet = openSheet({ title: "أضف مصروف", body: `
    <form id="f-exp">
      <label class="field"><span>وش اشتريت؟</span><input name="name" required maxlength="60" placeholder="مثال: قهوة"></label>
      <label class="field"><span>المبلغ (ر.س)</span><input name="amount" required inputmode="decimal"></label>
      <label class="field"><span>التصنيف</span><select name="category">${flex.map(c => `<option value="flexible:${esc(c)}">${esc(c)}</option>`).join("")}</select></label>
      <button class="btn block" type="submit">أضف</button>
    </form>` });
  $("#f-exp", sheet).addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.target, amount = toNum(f.amount.value);
    if (!amount) return toast("اكتب المبلغ صح.", "bad");
    try {
      await api("/api/expenses", { method: "POST", body: { name: f.name.value.trim(), amount, category: f.category.value } });
      closeSheet(); toast("انضاف المصروف، و«تقدر تصرف» اتحدّث.", "good"); refresh();
    } catch (err) { handleError(err); }
  });
}
async function recategorizeSheet(merchant) {
  const groups = await categories();
  const sheet = openSheet({ title: `تصنيف ${merchant}`, body: groups.map(g => `
      <h2 style="font-size:15px;margin:6px 0 8px">${esc(g.label)}</h2>
      <div class="btn-row" style="margin-bottom:12px">${g.items.map(c => `<button class="chip" data-cat="${esc(g.id)}:${esc(c)}">${esc(c)}</button>`).join("")}</div>`).join("") });
  sheet.addEventListener("click", async e => {
    const b = e.target.closest("[data-cat]"); if (!b) return;
    try {
      await api("/api/categories", { method: "POST", body: { merchant, category: b.dataset.cat } });
      closeSheet(); toast(`تمام، عمليات ${esc(merchant)} الجاية بتنحط في ${esc(catName(b.dataset.cat))}.`, "good"); refresh();
    } catch (err) { handleError(err); }
  });
}

/* ---------- OBLIGATIONS ---------- */
async function renderObligations() {
  const [o, due, s, w] = await Promise.all([api("/api/obligations"), api("/api/payments/due"), api("/api/summary"), wishState()]);
  pageTop("الالتزامات", w.count, w.ready);
  const L = o.limit_info || { limit: null, used: 0, left: null };
  const full = L.limit !== null && L.left === 0;
  const today = new Date(s.today + "T00:00:00");
  const daysTo = iso => Math.round((new Date(iso + "T00:00:00") - today) / 86400000);
  const plans = o.active_items.filter(i => i.type !== "bill" && i.kind !== "subscription");
  const subs = o.active_items.filter(i => i.kind === "subscription");
  const subsTotal = subs.reduce((a, x) => a + x.amount, 0);
  const subCard = x => {
    const d = daysTo(x.due_date);
    const charged = x.status === "paid";
    const renew = charged ? `انخصم هالشهر يوم ${x.day}، يتجدد الشهر الجاي` : `يتجدد ${whenDays(d)} (يوم ${x.day})`;
    return `<article class="card ob sub-card">
      <div class="top">
        <div class="l" style="display:flex;gap:12px;align-items:center"><span class="ico a">${ic("clock")}</span>
          <div><div class="t" style="font-weight:700">${esc(x.name)}</div><div class="muted renew">${renew}</div></div></div>
        <div style="text-align:left"><div class="amount">${money(x.amount)}</div><div class="muted">شهرياً</div></div>
      </div>
      ${x.cancel_planned ? `<div class="alert warn">${ic("alert")}<div>ناوي تلغيه؟ ألغه من موقع الجهة ${charged ? "قبل التجديد الجاي" : `قبل ${whenDays(d) === "بكرة" ? "بكرة" : `يوم ${x.day}`}`} عشان ما ينخصم مرة ثانية.</div></div>` : ""}
      <div class="foot">
        <label class="switch"><input type="checkbox" data-remind="${esc(x.id)}" ${x.remind ? "checked" : ""}>ذكّرني قبل التجديد</label>
        <div class="btn-row">${action(x.action)}${siteChip(x)}</div>
      </div>
      <div class="btn-row">
        <button class="btn ${x.cancel_planned ? "ghost" : "soft"} sm" data-intent="${esc(x.id)}" data-on="${x.cancel_planned ? 0 : 1}">${x.cancel_planned ? "تراجعت، بخليه" : "ناوي ألغيه"}</button>
        <button class="btn ghost sm" data-cancelled="${esc(x.id)}" data-name="${esc(x.name)}">ألغيته خلاص</button>
      </div>
    </article>`;
  };
  const bills = o.active_items.filter(i => i.type === "bill");
  const statusBadge = i => i.status === "paid" ? `<span class="badge b-paid">${ic("check")}تسدّد هالشهر</span>`
    : i.status === "late" ? `<span class="badge b-late">${ic("alert")}متأخر</span>`
    : `<span class="badge b-upcoming">${ic("clock")}${whenDays(daysTo(i.due_date))}</span>`;
  const action = a => !a ? "" : a.kind === "url" && a.url && a.url !== "#"
    ? `<a class="chip" href="${esc(a.url)}" target="_blank" rel="noopener">${ic("ext")}${esc(a.label)}</a>`
    : a.kind === "copy" ? `<button class="chip" data-copy="${esc(a.value)}">${ic("copy")}${esc(a.label)}</button>` : "";

  const planCard = p => `<article class="card ob">
      <div class="top">
        <div class="l" style="display:flex;gap:12px;align-items:center"><span class="ico">${ic("card")}</span>
          <div><div class="t" style="font-weight:700">${esc(p.name)}</div><div class="muted">يوم ${p.day} من كل شهر</div></div></div>
        ${statusBadge(p)}
      </div>
      <div class="top" style="align-items:flex-end">
        <div class="muted">${p.total ? `المدفوع: ${p.total - (p.remaining || 0)} من ${p.total}` : "التزام شهري ثابت"}</div>
        <div style="text-align:left"><div class="amount">${money(p.amount)}</div>${p.remaining ? `<div class="muted">باقي ${counted(p.remaining)}</div>` : ""}</div>
      </div>
      ${p.total ? `<div class="bar v"><span style="width:${p.progress ?? 0}%"></span></div>` : ""}
      <div class="foot">
        <label class="switch"><input type="checkbox" data-mode="${esc(p.id)}" ${p.pay_mode === "auto" ? "checked" : ""}>ينسحب تلقائي من البنك</label>
        <div class="btn-row">${action(p.action)}${siteChip(p)}
          ${p.confirmed ? "" : `<button class="btn soft sm" data-confirm="${esc(p.id)}">أكّد</button>`}
          <button class="btn soft sm" data-plan-edit="${esc(p.id)}">تعديل</button>
          ${p.source === "manual" ? `<button class="x-btn" data-del-plan="${esc(p.id)}" aria-label="حذف">${ic("trash")}</button>` : ""}</div>
      </div>
    </article>`;

  const current = `
    ${plans.map(planCard).join("") || `<div class="card empty">ما فيه التزامات نشطة.</div>`}
    ${subs.length ? `<div class="group-title">${ic("clock", "icon gold")} اشتراكاتك <span class="muted" style="font-weight:400">${money(subsTotal)} شهرياً</span></div>
      <p class="muted" style="margin-top:-6px">نذكّرك قبل كل تجديد، عشان ما تتجدد اشتراكات ما تستخدمها.</p>
      ${subs.map(subCard).join("")}` : ""}
    ${o.hidden_count ? `<section class="card lock">${ic("lock")}<p>${esc(o.locked_message)}</p><a class="btn soft" href="#subscriptions">الباقات</a></section>` : ""}
    ${L.limit !== null ? `<div class="note">${ic("card", "icon")} باقتك ${esc(L.plan_name || "")}: مستخدم ${L.used} من ${L.limit} التزامات${full ? "" : `، تقدر تضيف ${L.left === 1 ? "التزام واحد" : L.left === 2 ? "التزامين" : `${L.left} التزامات`}`}.</div>` : ""}
    ${full ? `<section class="card tight" style="text-align:center"><p style="margin:0 0 10px">وصلت حد باقتك (${L.limit} التزامات). ترقّ عشان تضيف أكثر.</p><a class="btn soft" href="#subscriptions">شوف الباقات</a></section>`
      : `<button class="btn ghost block" data-act="add-plan" style="margin-bottom:14px">${ic("plus")} أضف التزام فاته الربط</button>`}
    <section class="card">
      <div class="card-head"><h2>المعيشة</h2><span class="big">${money(o.essentials_total)}</span></div>
      <p class="muted" style="margin-top:-6px">متوسط آخر 3 شهور</p>
      ${Object.entries(o.essentials_by_category || {}).map(([k, v]) => `<div class="row"><span>${esc(k)}</span><span class="r">${money(v)}</span></div>`).join("")}
      ${bills.length ? `<h2 style="font-size:15px;margin:16px 0 4px">الفواتير الشهرية</h2>
        ${bills.map(b => `<div class="row"><div class="l"><span class="ico t">${ic("bill")}</span><div><div class="t">${esc(b.name)}</div><div class="s">يوم ${b.day}</div></div></div>
          <div style="text-align:left"><div class="r">${money(b.amount)}</div>${statusBadge(b)}${b.site ? `<div><a class="link-btn" style="font-size:12px" href="${esc(b.site.url)}" target="_blank" rel="noopener">${ic("ext", "icon")} ادفع</a></div>` : ""}</div></div>`).join("")}
        <p class="muted" style="margin:8px 0 0">الفواتير داخل متوسط المعيشة، ما نحسبها مرتين.</p>` : ""}
    </section>
    ${(o.payees || []).length ? `<section class="card"><h2>الجهات اللي تدفع لها</h2>
      <p class="muted" style="margin-top:-6px">روابط المواقع الرسمية عشان تدفع أو تدير حسابك عندهم.</p>
      <div class="payees">${o.payees.map(x => `<a class="chip" href="${esc(x.url)}" target="_blank" rel="noopener">${ic("ext")}${esc(x.name)}</a>`).join("")}</div></section>` : ""}`;

  const previous = o.previous_payments.length ? o.previous_payments.map(p => `<article class="card ob">
      <div class="top"><div class="l" style="display:flex;gap:12px;align-items:center"><span class="ico t">${ic("check")}</span>
        <div><div class="t" style="font-weight:700">${esc(p.name)}</div><div class="muted">${p.status === "cancelled" ? `ألغيته${p.cancelled_at ? ` يوم ${esc(p.cancelled_at)}` : ""}، توفّر ${money(p.amount)} شهرياً` : p.total ? `خلّصت ${counted(p.total)}` : "خلص"}</div></div></div>
        <span class="badge ${p.status === "cancelled" ? "b-grey" : "b-paid"}">${p.status === "cancelled" ? "ألغيته" : "مكتمل"}</span></div>
      ${p.total ? `<div class="muted">مجموع اللي دفعته: ${money(p.total * p.amount)}</div>` : ""}
    </article>`).join("") : `<div class="card empty">لما يخلص أي التزام بينتقل هنا تلقائياً.</div>`;

  const target = (s.budget.target || []).find(t => t.id === "essentials") || { amount: 0, pct: 70 };
  const usedPct = target.amount ? o.total / target.amount : 0;
  const essWarn = s.alerts.filter(a => a.type === "essentials_budget_exceeded");
  $("#view").innerHTML = `
    <section class="card">
      <div class="muted">التزاماتك الشهرية</div>
      <div class="huge" style="margin:4px 0 10px">${money(o.total)}</div>
      <div class="bar ${usedPct > 1 ? "over" : usedPct >= .9 ? "warn" : "v"}"><span style="width:${Math.min(100, usedPct * 100)}%"></span></div>
      <p class="muted" style="margin:8px 0 6px">حدك ${target.pct}% من راتبك = ${money(target.amount)}. تقدر تغيّره من «حسابي».</p>
      ${essWarn.length ? `<div style="margin:6px 0 10px">${alertsHtml(essWarn)}</div>` : ""}
      <div class="row"><span class="muted">الالتزامات والإيجار</span><span class="r">${money(o.plans_total - subsTotal)}</span></div>
      ${subsTotal ? `<div class="row"><span class="muted">الاشتراكات</span><span class="r">${money(subsTotal)}</span></div>` : ""}
      <div class="row"><span class="muted">المعيشة (متوسط آخر 3 شهور)</span><span class="r">${money(o.essentials_total)}</span></div>
    </section>
    <section class="card tight">
      ${due.payable.length ? `<div class="card-head" style="margin-bottom:10px"><div><div class="t" style="font-weight:700">عليك ${due.payable.length === 1 ? "دفعة وحدة" : counted(due.payable.length)} هالشهر</div>
        <div class="muted">${due.payable.map(i => esc(i.name)).join("، ")}</div></div></div>
        <button class="btn block" data-act="pay">ادفع الكل · ${fmt(due.payable_total)} ر.س</button>`
        : `<div class="alert good">${ic("check")}<div>ما عليك دفعات تدفعها من هنا هالشهر.</div></div>`}
    </section>
    <div class="tabs" role="tablist">
      <button role="tab" data-tab-ob="current" aria-selected="${S.obTab === "current"}">الالتزامات الحالية</button>
      <button role="tab" data-tab-ob="previous" aria-selected="${S.obTab === "previous"}">المدفوعات السابقة</button>
    </div>
    <div>${S.obTab === "current" ? current : previous}</div>`;
}
async function editPlanSheet(planId) {
  try {
    const data = await api("/api/plans");
    const plan = data.plans.find(p => p.id === planId);
    if (!plan) return toast("الخطة غير موجودة.", "bad");
    const sheet = openSheet({ title: `تعديل ${plan.name}`, body: `
      <form id="f-plan-edit">
        <p class="muted">اترك الحقل فاضي إذا ما تبي تغيّره.</p>
        <label class="field"><span>المبلغ الشهري (ر.س)</span><input name="amount" inputmode="decimal" value="${esc(plan.amount)}"></label>
        ${plan.remaining != null ? `<label class="field"><span>الدفعات الباقية</span><input name="remaining" inputmode="numeric" value="${esc(plan.remaining)}"></label>` : ""}
        <label class="field"><span>يوم السداد (1 إلى 28)</span><input name="day" inputmode="numeric" value="${esc(plan.day)}"></label>
        <div class="btn-row"><button class="btn" type="submit">احفظ التعديل</button><button class="btn ghost" type="button" data-edit-cancel>إلغاء</button></div>
      </form>` });
    $("[data-edit-cancel]", sheet).addEventListener("click", closeSheet);
    $("#f-plan-edit", sheet).addEventListener("submit", async e => {
      e.preventDefault();
      const form = e.target, button = $("[type=submit]", form), body = {};
      if (button.disabled) return;
      const limits = { amount: [0, 1000000], remaining: [0, 600], day: [1, 28] };
      for (const [field, [min, max]] of Object.entries(limits)) {
        const text = form.elements[field]?.value.trim();
        if (!text) continue;
        const value = Number(text.replace(/[٠-٩]/g, d => "٠١٢٣٤٥٦٧٨٩".indexOf(d)));
        if (!Number.isFinite(value) || value < min || value > max ||
            (field === "amount" ? value === 0 : !Number.isInteger(value))) {
          return toast(field === "day" ? "اكتب يوم السداد من 1 إلى 28." :
            field === "remaining" ? "اكتب عدد الدفعات صح." : "اكتب المبلغ صح.", "bad");
        }
        if (value !== plan[field]) body[field] = value;
      }
      if (!Object.keys(body).length) return toast("ما غيّرت شي في الخطة.");
      button.disabled = true;
      try {
        await api(`/api/plans/${encodeURIComponent(planId)}/confirm`, { method: "POST", body });
        closeSheet(); toast("عدّلنا الخطة وأكدناها.", "good"); refresh();
      } catch (err) { handleError(err); button.disabled = false; }
    });
  } catch (err) { handleError(err); }
}
function addPlanSheet() {
  const sheet = openSheet({ title: "أضف التزام", body: `
    <form id="f-plan">
      <label class="field"><span>الاسم</span><input name="name" required maxlength="60" placeholder="مثال: تمويل أثاث"></label>
      <label class="field"><span>المبلغ الشهري (ر.س)</span><input name="amount" required inputmode="decimal"></label>
      <label class="field"><span>يوم السداد (1 إلى 28)</span><input name="day" required inputmode="numeric"></label>
      <label class="field"><span>كم دفعة باقية؟ (اتركه فاضي لو مستمر)</span><input name="remaining" inputmode="numeric"></label>
      <label class="field"><span>النوع</span><select name="kind"><option value="loan">تمويل</option><option value="bnpl">تقسيط (تمارا، تابي)</option><option value="recurring">شهري ثابت (إيجار، اشتراك)</option></select></label>
      <button class="btn block" type="submit">حفظ</button>
    </form>` });
  $("#f-plan", sheet).addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.target, amount = toNum(f.amount.value), day = toNum(f.day.value), rem = toNum(f.remaining.value);
    if (!amount || !day || day > 28) return toast("تأكد من المبلغ، ويوم السداد من 1 إلى 28.", "bad");
    try {
      await api("/api/plans", { method: "POST", body: { name: f.name.value.trim(), amount, day, remaining: rem || null, kind: f.kind.value } });
      closeSheet(); toast("انضاف الالتزام، و«تقدر تصرف» اتحدّث.", "good"); refresh();
    } catch (err) { handleError(err); }
  });
}

function siteChip(p) {
  if (!p.site) return "";
  if (p.action && p.action.url === p.site.url) return "";
  return `<a class="chip" href="${esc(p.site.url)}" target="_blank" rel="noopener">${ic("ext")}${esc(p.site.label)}</a>`;
}

/* ---------- pay all (simulated open banking payment initiation) ---------- */
async function paySheet() {
  let due;
  try { due = await api("/api/payments/due"); } catch (err) { handleError(err); return; }
  const chosen = new Set(due.payable.map(i => i.id));
  const linkBtn = i => i.pay_link ? `<a class="chip" href="${esc(i.pay_link.url)}" target="_blank" rel="noopener">${ic("ext")}${esc(i.pay_link.label)}</a>`
    : i.action && i.action.kind === "copy" ? `<button class="chip" data-copy="${esc(i.action.value)}">${ic("copy")}انسخ رقم السداد</button>` : "";
  const step1 = () => {
    const total = due.payable.filter(i => chosen.has(i.id)).reduce((a, i) => a + i.amount, 0);
    return `
      ${due.payable.length ? due.payable.map(i => `<label class="row" style="cursor:pointer">
          <div class="l"><input type="checkbox" data-pick="${esc(i.id)}" ${chosen.has(i.id) ? "checked" : ""} style="width:22px;height:22px;min-height:0;accent-color:var(--violet)">
          <div><div class="t">${esc(i.name)}</div><div class="s">${whenDays(i.days_until)}، يوم ${i.day}</div></div></div>
          <span class="r">${money(i.amount)}</span></label>`).join("") : `<div class="empty">ما فيه دفعات تقدر تدفعها من هنا هالشهر.</div>`}
      ${due.auto.length ? `<h2 style="font-size:14px;margin:16px 0 4px" class="muted">تنسحب تلقائي من البنك</h2>
        ${due.auto.map(i => `<div class="row" style="opacity:.6"><div><div class="t">${esc(i.name)}</div>
          <div class="s">ينسحب تلقائي يوم ${i.day}، ما يحتاج تدفعه</div></div><span class="r">${money(i.amount)}</span></div>`).join("")}` : ""}
      ${due.link_only.length ? `<h2 style="font-size:14px;margin:16px 0 4px" class="muted">تدفعها من الجهة</h2>
        ${due.link_only.map(i => `<div class="row"><div><div class="t">${esc(i.name)}</div><div class="s">${money(i.amount)}، ${whenDays(i.days_until)}</div></div>${linkBtn(i)}</div>`).join("")}` : ""}
      ${due.payable.length ? `<button class="btn block" id="pay-go" style="margin-top:16px" ${total ? "" : "disabled"}>ادفع · ${fmt(total)} ر.س</button>` : ""}
      <p class="muted" style="text-align:center;margin:10px 0 0">${esc(due.note)}<br>دفع تجريبي للعرض.</p>`;
  };
  const sheet = openSheet({ title: "ادفع الكل", body: `<div id="pay-body">${step1()}</div>` });
  const body = $("#pay-body", sheet);
  sheet.addEventListener("change", e => {
    const c = e.target.closest("[data-pick]"); if (!c) return;
    c.checked ? chosen.add(c.dataset.pick) : chosen.delete(c.dataset.pick);
    body.innerHTML = step1();
  });
  sheet.addEventListener("click", async e => {
    if (e.target.closest("#pay-go")) {
      const items = due.payable.filter(i => chosen.has(i.id));
      const total = items.reduce((a, i) => a + i.amount, 0);
      body.innerHTML = `<div class="spinner" style="margin-top:30px"></div><p style="text-align:center">بننقلك لتطبيق البنك عشان توافق على الدفع…</p>`;
      await sleep(1100);
      body.innerHTML = `<div class="bank-approve">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px"><span class="ico">${ic("bank")}</span><b>بنك تجريبي</b></div>
          <p class="muted" style="margin-top:0">مُدار يطلب تحويل هالمبالغ من حسابك للجهات مباشرة:</p>
          ${items.map(i => `<div class="pay-step"><span>${esc(i.name)}</span><b>${money(i.amount)}</b></div>`).join("")}
          <div class="pay-step" style="border:0"><span class="t">الإجمالي</span><b class="big">${money(total)}</b></div>
          <div class="btn-row" style="margin-top:8px"><button class="btn teal" style="flex:1" id="bank-ok">وافق</button><button class="btn ghost" style="flex:1" id="bank-no">رفض</button></div>
        </div>`;
    }
    if (e.target.closest("#bank-no")) { body.innerHTML = step1(); toast("ما تم أي دفع."); }
    if (e.target.closest("#bank-ok")) {
      try {
        const r = await api("/api/payments/pay", { method: "POST", body: { item_ids: [...chosen] } });
        body.innerHTML = `<div id="steps"></div>`;
        for (const p of r.paid) {
          await sleep(500);
          $("#steps", body).insertAdjacentHTML("beforeend", `<div class="pay-step"><span>تم التحويل لـ${esc(p.name)}</span><span class="teal">${ic("check")}</span></div>`);
        }
        await sleep(400);
        $("#steps", body).insertAdjacentHTML("beforeend", `<div class="alert good" style="margin-top:14px">${ic("check")}<div><b>تم السداد</b> ${money(r.total)} (دفع تجريبي)</div></div>
          <button class="btn block" data-close style="margin-top:12px">تمام</button>`);
        refresh();
      } catch (err) { body.innerHTML = step1(); handleError(err); }
    }
  });
}

/* ---------- PLANNER ---------- */
const PLAN_KINDS = [
  { id: "item", label: "شراء", icon: "box", hint: "مثال: جوال", quick: [["شوز", 500], ["جوال", 3000], ["لابتوب", 7000], ["أثاث", 15000]] },
  { id: "trip", label: "سفرة", icon: "plane", hint: "مثال: سفرة دبي", quick: [["سفرة داخلية", 3000], ["سفرة دبي", 6000], ["سفرة أوروبا", 18000]] },
  { id: "event", label: "مناسبة", icon: "gift", hint: "مثال: حفلة تخرج", quick: [["هدية", 800], ["حفلة تخرج", 5000], ["زواج", 40000]] },
  { id: "education", label: "دراسة ودورات", icon: "book", hint: "مثال: دورة", quick: [["دورة", 2500], ["شهادة احترافية", 8000], ["دبلوم", 20000]] },
  { id: "other", label: "شي ثاني", icon: "planner", hint: "وش تبي تخطط له؟", quick: [] }
];

async function renderPlanner() {
  const w = await wishState();
  pageTop("المخطط", w.count, w.ready);
  const P = S.planner;
  P.kind = P.kind || "item";
  const K = PLAN_KINDS.find(k => k.id === P.kind) || PLAN_KINDS[0];
  $("#view").innerHTML = `
    <p class="page-sub">خطط لأي مصروف كبير: شراء، سفرة، مناسبة، أو دراسة. نقارن لك التقسيط والتمويل والتحويش على وضعك الحقيقي، ونختار الأنسب.</p>
    <section class="card">
      <div class="kind-chips">${PLAN_KINDS.map(k => `<button data-kind="${k.id}" aria-pressed="${k.id === P.kind}">${ic(k.icon)}${k.label}</button>`).join("")}</div>
      <label class="field"><span>وش تبي تخطط له؟</span><input id="pl-name" value="${esc(P.name)}" maxlength="60" placeholder="${esc(K.hint)}"></label>
      <div class="grid-2" style="margin:0">
        <label class="field" style="margin:0"><span>المبلغ (ر.س)</span><input id="pl-price" value="${esc(P.price)}" inputmode="decimal"></label>
        <label class="field" style="margin:0"><span>بكم شهر تبي تجمعه؟</span><input id="pl-months" value="${esc(P.months)}" inputmode="numeric" placeholder="اختياري"></label>
      </div>
      ${K.quick.length ? `<div class="btn-row" style="margin-top:10px">${K.quick.map(([n, p]) => `<button class="chip" data-quick="${p}" data-qname="${n}">${n} ${fmt(p)}</button>`).join("")}</div>` : ""}
    </section>
    <div id="pl-out"><div class="skeleton"></div></div>
    <div id="pl-forecast"></div>`;
  let t;
  const update = () => { clearTimeout(t); t = setTimeout(() => plannerResults().catch(handleError), 300); };
  $("#pl-name").addEventListener("input", e => { P.name = e.target.value; });
  $("#pl-price").addEventListener("input", e => { P.price = e.target.value; P.chosen = null; P.tenors = {}; update(); });
  $("#pl-months").addEventListener("input", e => { P.months = e.target.value; update(); });
  await plannerResults();
  plannerForecast().catch(() => {});
}

function bnplCard(o, { best = false, chosen = false } = {}) {
  const fits = o.ok ? `<span class="badge b-paid">يناسبك الحين</span>`
    : o.earliest !== null ? `<span class="badge b-upcoming">يناسبك ${esc(o.earliest_label)}</span>` : `<span class="badge b-late">ما يناسب ميزانيتك</span>`;
  const tight = o.ok ? o.tight : o.start_tight;
  return `<button class="offer ${best ? "best" : ""}" data-pick-type="bnpl" data-pick-id="${esc(o.id)}" aria-pressed="${chosen}">
      <div class="top"><div><b>${esc(o.provider)}</b> <span class="muted">تقسيط · ${esc(o.label)}</span></div>${best ? `<span class="badge b-paid">الأنسب لك</span>` : fits}</div>
      ${best ? `<div class="muted">${esc(o.reason)}</div>` : ""}
      <dl class="kv">
        <dt>كم ينخصم كل شهر</dt><dd>${money(o.monthly)} × ${o.count}</dd>
        <dt>اللي ترجعه كامل</dt><dd>${money(o.total)}${o.extra_cost > 0 ? ` <span class="muted">(+${fmt(o.extra_cost)} رسوم)</span>` : " <span class='muted'>(بدون رسوم)</span>"}</dd>
        ${tight !== null && tight !== undefined ? `<dt>في أضيق شهر</dt><dd>يبقى لك ${money(tight)}</dd>` : ""}
        <dt>متى تبدأ</dt><dd>${o.ok ? "الحين" : esc(o.earliest_label)}</dd>
      </dl>
    </button>`;
}

function loanCard(l, months, { best = false, chosen = false } = {}) {
  const o = l.options.find(x => x.months === months) || l.options[0];
  const status = !o.dbr_ok ? `<span class="badge b-late">نسبة الديون فوق ${fmt(33)}%</span>`
    : o.earliest === null ? `<span class="badge b-late">ما يناسب ميزانيتك</span>`
    : o.ok ? `<span class="badge b-paid">يناسبك الحين</span>` : `<span class="badge b-upcoming">يناسبك ${esc(o.earliest_label)}</span>`;
  const tight = o.ok ? o.tight : o.start_tight;
  return `<div class="offer ${best ? "best" : ""}" role="group" aria-pressed="${chosen}">
      <div class="top"><div><b>${esc(l.name)}</b> <span class="muted">${l.type === "bank" ? "تمويل شخصي بنكي" : "شركة تمويل"}</span></div>${best ? `<span class="badge b-paid">الأنسب لك</span>` : status}</div>
      ${best ? `<div class="muted">${esc(l.reason)}</div>` : ""}
      <div class="tenors">${l.options.map(x => `<button data-tenor="${esc(l.id)}" data-months="${x.months}" aria-pressed="${x.months === o.months}"
          class="${!x.dbr_ok || x.earliest === null ? "no" : ""}">${x.months} شهر</button>`).join("")}</div>
      <dl class="kv">
        <dt>القسط الشهري</dt><dd>${money(o.monthly)}</dd>
        <dt>نسبة الربح (ثابتة سنوياً)</dt><dd>${o.flat_rate}%</dd>
        <dt>الربح الكلي</dt><dd>${money(o.profit)}</dd>
        <dt>الرسوم الإدارية</dt><dd>${money(o.fee)} <span class="muted">(1%، بحد أقصى 5,000)</span></dd>
        <dt>اللي ترجعه كامل</dt><dd><b>${money(o.total_cost)}</b> <span class="muted">(+${fmt(o.extra_cost)})</span></dd>
        <dt>التكلفة السنوية الفعلية</dt><dd>${o.apr}%</dd>
        <dt>ديونك بعده</dt><dd class="${o.dbr_ok ? "" : "red"}">${o.dbr_after}% من راتبك</dd>
        ${tight !== null && tight !== undefined ? `<dt>في أضيق شهر</dt><dd>يبقى لك ${money(tight)}</dd>` : ""}
        <dt>متى تبدأ</dt><dd>${o.earliest === null ? "—" : o.ok ? "الحين" : esc(o.earliest_label)}</dd>
      </dl>
      <button class="btn ${chosen ? "" : "soft"} sm" data-pick-type="loan" data-pick-id="${esc(l.id)}" data-pick-months="${o.months}">${chosen ? "✓ اخترته" : "اختر هذا"}</button>
    </div>`;
}

async function plannerResults() {
  const P = S.planner, out = $("#pl-out");
  if (!out) return;
  P.tenors = P.tenors || {};
  const price = toNum(P.price), months = toNum(P.months);
  if (!price) { out.innerHTML = `<div class="card empty">اكتب السعر عشان نقارن.</div>`; return; }
  let r;
  try {
    r = await api("/api/offers", { method: "POST", body: { price, target_months: months >= 1 && months <= 36 ? Math.round(months) : null } });
  } catch (err) {
    if (err.status === 403) {
      out.innerHTML = `<section class="card lock">${ic("lock")}<h2>${esc(err.message)}</h2><a class="btn soft" href="#subscriptions">شوف الباقات</a></section>`;
      return;
    }
    throw err;
  }
  S._offers = r;
  const best = r.best;
  // the user's pick (or the recommendation)
  const chosen = P.chosen || (best ? { type: best.type, id: best.id, months: best.months } : null);
  const isChosen = (type, id) => chosen && chosen.type === type && chosen.id === id;
  const tenorOf = l => P.tenors[l.id] || (isChosen("loan", l.id) && chosen.months) || l.default_months;

  let bestHtml = "";
  if (best && best.type === "bnpl") bestHtml = bnplCard(r.offers.find(o => o.id === best.id), { best: true, chosen: isChosen("bnpl", best.id) });
  if (best && best.type === "loan") { const l = r.loans.find(x => x.id === best.id); bestHtml = loanCard(l, P.tenors[l.id] || best.months, { best: true, chosen: isChosen("loan", l.id) }); }
  if (!best) bestHtml = `<div class="alert warn">${ic("alert")}<div>ما فيه تقسيط أو تمويل يناسب ميزانيتك الحين. «تجمع أول» هو الخيار الآمن.</div></div>`;

  const otherBnpl = r.offers.filter(o => !(best && best.type === "bnpl" && o.id === best.id));
  const otherLoans = r.loans.filter(l => !(best && best.type === "loan" && l.id === best.id));
  const notes = r.hidden.map(h => `<div class="note">${ic("alert", "icon")} ${esc(h.reason)}</div>`).join("");
  const dbr = r.loans.length ? `<div class="note">ديونك الحالية ${money(r.dbr.debt_monthly)} شهرياً = <b>${r.dbr.current_pct}%</b> من راتبك. الحد المتبع في التمويل الاستهلاكي ${r.dbr.limit}%، يعني تقدر تضيف قسط لين ${money(r.dbr.room_monthly)} تقريباً.</div>` : "";
  const total = otherBnpl.length + otherLoans.length;

  const chosenLabel = (() => {
    if (!chosen) return null;
    if (chosen.type === "bnpl") { const o = r.offers.find(x => x.id === chosen.id); return o ? `${o.provider}، ${o.label.split("،")[0]}` : null; }
    const l = r.loans.find(x => x.id === chosen.id); return l ? `${l.name}، ${tenorOf(l)} شهر` : null;
  })();

  const sv = r.save;
  const steps = (sv.progress || []).slice(0, 8);
  const target = sv.target_months;
  out.innerHTML = `
    <h2 style="font-size:16px;margin:4px 0 10px">الأنسب لك</h2>
    ${bestHtml}
    ${notes}
    ${total ? `<button class="btn ghost block" data-act="others" style="margin-bottom:12px">${P.others ? "إخفاء الخيارات الثانية" : `قارن كل الخيارات (${total})`}</button>` : ""}
    ${P.others ? `
      ${otherBnpl.length ? `<div class="group-title">${ic("card", "icon violet")} التقسيط</div>${otherBnpl.map(o => bnplCard(o, { chosen: isChosen("bnpl", o.id) })).join("")}` : ""}
      ${otherLoans.length ? `<div class="group-title">${ic("bank", "icon violet")} التمويل الشخصي (بنوك وشركات تمويل)</div>${dbr}
        ${otherLoans.map(l => loanCard(l, tenorOf(l), { chosen: isChosen("loan", l.id) })).join("")}` : ""}` : (best && best.type === "loan" ? dbr : "")}
    ${chosenLabel ? `<button class="btn block" data-act="wish-chosen" style="margin-bottom:18px">${ic("heart")} أضف للأمنيات (${esc(chosenLabel)})</button>` : ""}

    <section class="card">
      <div class="card-head"><h2>تجمع أول</h2><span class="badge b-violet">بدون ديون</span></div>
      <dl class="kv">
        <dt>تحوّش هالشهر</dt><dd>${money(sv.monthly)} <span class="muted">(${fmt(sv.salary_pct)}% من راتبك)</span></dd>
        <dt>بعدها كل شهر</dt><dd>لين ${money(sv.max_monthly)} <span class="muted">(حد الادخار)</span></dd>
        <dt>متى تقدر تدفعه</dt><dd>${esc(sv.buy_label)}</dd>
        <dt>التكلفة الكلية</dt><dd>${money(price)} بدون أي رسوم</dd>
      </dl>
      ${target ? (sv.reachable_in_target
        ? `<div class="alert good" style="margin-top:12px">${ic("check")}<div>توصل لهدفك خلال ${counted(target, "months")}.</div></div>`
        : `<div class="alert warn" style="margin-top:12px">${ic("alert")}<div>${esc(sv.warning || "ما توصل لهدفك بهالمدة.")}<br>
            الحل: ${sv.required_months ? `تمدد المدة لـ ${counted(sv.required_months, "months")}` : "تمدد المدة"}، أو تخفّض الهدف لـ ${money(sv.max_target)}.</div></div>
           <div class="btn-row" style="margin-top:8px">${sv.required_months ? `<button class="btn soft sm" data-set-months="${sv.required_months}">خلها ${counted(sv.required_months, "months")}</button>` : ""}
           <button class="btn soft sm" data-set-price="${Math.floor(sv.max_target)}">خلّ الهدف ${fmt(sv.max_target)}</button></div>`) : ""}
      ${steps.length ? `<div class="steps">${steps.map(p => `<div class="st"><span>${esc(p.label)}: تحوّش ${money(p.amount)}</span><span class="num">${p.pct}%</span></div>`).join("")}</div>` : ""}
      <button class="btn soft block" data-act="wish-save" style="margin-top:14px">${ic("heart")} أضف للأمنيات بطريقة «تجمع أول»</button>
    </section>
    <p class="muted" style="text-align:center">أرقام الجهات تجريبية للتوضيح، والحسابات حقيقية على بياناتك. العروض الفعلية تجي من الجهات بعد الشراكة.<br>هذي معلومات، مو استشارة مالية.</p>`;
  P._chosenMethod = !chosen ? null : chosen.type === "bnpl"
    ? (r.offers.find(o => o.id === chosen.id) || {}).method
    : `loan:${chosen.id}:${(() => { const l = r.loans.find(x => x.id === chosen.id); return l ? tenorOf(l) : chosen.months; })()}`;
}

async function plannerForecast() {
  const box = $("#pl-forecast"); if (!box) return;
  let data, title;
  try { data = await api("/api/forecast"); title = "توقعاتك لـ 12 شهر"; }
  catch (e) {
    if (e.status !== 403) throw e;
    try { data = await api("/api/smart-account"); title = "الحساب الذكي: الشهور الجاية"; }
    catch (e2) {
      if (e2.status !== 403) throw e2;
      box.innerHTML = `<section class="card lock">${ic("lock")}<h2>الحساب الذكي مو ضمن باقتك</h2><p class="muted">تعرف كم بيبقى لك بالشهور الجاية ومتى تقدر تشتري.</p><a class="btn soft" href="#subscriptions">شوف الباقات</a></section>`;
      return;
    }
  }
  box.innerHTML = `<section class="card"><h2>${title}</h2>
    ${data.months.map(m => `<div class="row"><div><div class="t">${esc(m.label)}</div><div class="s">التزامات ${fmt(m.obligations)}، معيشة ${fmt(m.essentials)}</div></div>
      <span class="r ${m.available < 0 ? "red" : "teal"}">${money(m.available)}</span></div>`).join("")}
    <p class="muted" style="margin:10px 0 0">${esc(data.assumption)}</p></section>`;
}

async function addWishFromPlanner(method) {
  const P = S.planner, price = toNum(P.price), name = (P.name || "").trim() || "منتج";
  if (!price) return toast("اكتب السعر أول.", "bad");
  if (!method) return toast("اختر طريقة أول.", "bad");
  try {
    const r = await api("/api/wishlist", { method: "POST", body: { name, price, method, kind: P.kind || "item" } });
    const item = r.items.find(i => i.name === name);
    toast(`انضاف ${esc(name)} للأمنيات (${esc(item ? item.method_label : method)}). بنذكّرك أول ما يصير مناسب.`, "good");
    location.hash = "#wishlist";
  } catch (err) { handleError(err); }
}

/* ---------- WISHLIST ---------- */
async function renderWishlist() {
  backTop("قائمة الأمنيات");
  const w = await api("/api/wishlist");
  $("#view").innerHTML = `
    <p class="page-sub">نذكّرك أول ما يصير الشي مناسب لك.</p>
    ${w.items.length ? w.items.map(i => {
      const st = i.status || {};
      const line = i.smart_locked ? esc(i.when_label)
        : i.method === "save" ? (st.ok ? "جمعت المبلغ، مناسب الحين" : `توصل للمبلغ ${esc(i.when_label)}`)
        : st.ok ? "مناسب لك الحين" : st.whenK === null ? "ما يناسب بهالطريقة، جرّب «تجمع أول»" : `يصير مناسب ${esc(i.when_label)}`;
      return `<article class="card ob">
        <div class="top"><div class="l" style="display:flex;gap:12px;align-items:center"><span class="ico">${ic(({ trip: "plane", event: "gift", education: "book", item: "box" })[i.kind] || "heart")}</span>
          <div><div class="t" style="font-weight:700">${esc(i.name)}</div><div class="muted">${esc(i.method_label || METHOD[i.method] || i.method)}</div></div></div>
          <button class="x-btn" data-del-wish="${i.id}" aria-label="حذف">${ic("trash")}</button></div>
        <div class="top" style="align-items:center"><span class="badge ${st.ok ? "b-paid" : "b-upcoming"}">${ic(st.ok ? "check" : "clock")}${line}</span>
          <span class="amount">${money(i.price)}</span></div>
        ${i.method === "save" ? `<div class="bar"><span style="width:${st.pct || 0}%"></span></div>
          <div class="muted">جمعت ${money(i.saved)} من ${money(i.price)} (${st.pct || 0}%)</div>` : ""}
        <div class="foot"><button class="chip" data-compare="${i.id}" data-name="${esc(i.name)}" data-price="${i.price}" data-wkind="${esc(i.kind || "item")}">${ic("planner")}قارن طرق الدفع</button></div>
      </article>`;
    }).join("") : `<section class="card empty">قائمتك فاضية. خطط لأي شي تبيه من «المخطط» وضيفه هنا.<br><br><a class="btn soft" href="#planner">روح للمخطط</a></section>`}
    ${S.demo ? `<section class="card" style="text-align:center"><button class="btn teal block" data-act="next-month">انتقل للشهر الجاي</button>
      <p class="muted" style="margin:8px 0 0">زر للديمو بس، عشان نوري التذكير بدون ما ننتظر شهر.</p></section>` : ""}`;
}

async function nextMonth() {
  try {
    const r = await api("/api/demo/next-month", { method: "POST" });
    r.events.forEach((ev, i) => setTimeout(() => {
      if (ev.type === "salary") toast(`<b>نزل راتبك</b> ${money(ev.amount)}`, "good");
      if (ev.type === "plan_end") toast(`<b>خلص التزام ${esc(ev.name)}.</b> يرجع لك ${money(ev.frees)} كل شهر، وانتقل للمدفوعات السابقة.`, "good", 7000);
      if (ev.type === "wish_affordable") toast(`<b>خبر حلو:</b> ${esc(ev.name)} صار مناسب لك${ev.tight !== undefined ? `. بـ${METHOD[ev.method] || ""} يبقى لك ${money(ev.tight)} في أضيق شهر.` : "."}`, "good", 9000);
    }, i * 900));
    refresh();
  } catch (err) { handleError(err); }
}

/* ---------- ACCOUNT ---------- */
function donut(parts) {
  const total = parts.reduce((a, p) => a + Math.max(0, p.value), 0) || 1, r = 52, c = 2 * Math.PI * r;
  let off = 0;
  const segs = parts.map(p => {
    const len = Math.max(0, p.value) / total * c;
    const s = `<circle r="${r}" cx="70" cy="70" fill="none" stroke="${p.color}" stroke-width="22" stroke-dasharray="${Math.max(0, len - 2)} ${c}" stroke-dashoffset="${-off}"/>`;
    off += len; return s;
  }).join("");
  return `<svg viewBox="0 0 140 140" width="140" height="140" role="img" aria-label="توزيع الراتب"><g transform="rotate(-90 70 70)">${segs}</g></svg>`;
}
const BUDGET_COLORS = { essentials: "var(--violet-2)", personal: "var(--teal)", savings: "var(--amber)", remaining: "var(--track)" };

async function renderAccount() {
  const [a, b, w, bk] = await Promise.all([api("/api/account"), api("/api/budget"), wishState(), api("/api/banks")]);
  S._banks = bk;
  S._account = a;
  pageTop("حسابي", w.count, w.ready);
  const theme = document.documentElement.dataset.theme || "dark";
  const targets = Object.fromEntries((b.target || []).map(t => [t.id, t]));
  const contact = a.contact || {};
  $("#view").innerHTML = `
    <section class="card">
      <div class="who" style="margin-bottom:12px"><span class="avatar" style="width:52px;height:52px;font-size:22px;border-radius:16px">${esc(T(a.display_name || "م").charAt(0))}</span>
        <div style="flex:1"><b style="font-size:18px">${esc(a.display_name || "")}</b><small dir="ltr" style="display:block;text-align:right">${esc(a.phone_masked || "")}</small></div>
        <button class="btn soft sm" data-act="edit-profile">تعديل</button></div>
      ${a.email ? `<div class="row"><span class="muted">الإيميل</span><span dir="ltr">${esc(a.email)}</span></div>` : ""}
      <div class="row"><span class="muted">يوم الراتب</span><span>${a.salary_day} من كل شهر</span></div>
    </section>

    <section class="card">
      <div class="card-head"><h2>حساباتك البنكية</h2>${S.demo ? `<button class="link-btn" data-act="add-bank">${ic("plus", "icon")} اربط بنك</button>` : ""}</div>
      ${bk.banks.map(x => `<div class="row"><div class="l"><span class="ico">${ic("bank")}</span><div><div class="t">${esc(x.name)}</div>
        <div class="s">${fmt(x.transactions)} عملية · الموافقة لين <span class="num">${esc((x.expires_at || "").slice(0, 10))}</span></div></div></div>
        <button class="btn ghost sm" data-del-bank="${esc(x.bank_id)}" data-name="${esc(x.name)}">فصل</button></div>`).join("")}
    </section>

    <a class="card tap" href="#subscriptions" style="display:flex;justify-content:space-between;align-items:center;text-decoration:none">
      <div><div class="muted">باقتك الحالية</div><div class="big">${esc(a.subscription.name)}</div>
        <div class="muted">${a.subscription.price ? `${fmt(a.subscription.price)} ر.س شهرياً` : "مجانية"}</div>
        <div class="muted">${a.subscription.questions_left == null ? "أسئلة المساعد: بلا حد" : `أسئلة المساعد: باقي ${a.subscription.questions_left} من ${a.subscription.assistant_questions} هالشهر`}</div></div>
      <span class="btn soft sm">الباقات</span></a>

    <section class="card">
      <div class="card-head"><h2>توزيع راتبك</h2><button class="link-btn" data-act="edit-budget">عدّل الأهداف</button></div>
      <div class="donut-wrap">${donut(b.actual.map(x => ({ value: x.amount, color: BUDGET_COLORS[x.id] })))}
        <div class="legend">${b.actual.map(x => `<div class="li" style="flex-direction:column;align-items:flex-start;gap:0">
          <span><i style="background:${BUDGET_COLORS[x.id]}"></i>${esc(x.label)} <b class="num">${x.pct}%</b></span>
          ${targets[x.id] ? `<span class="muted" style="font-size:12px;padding-inline-start:18px">هدفك ${targets[x.id].pct}%</span>` : ""}</div>`).join("")}</div></div>
      <p class="muted" style="margin:10px 0 0">الرقم الأول اللي صار فعلاً هالشهر، والثاني هدفك.</p>
      ${b.warnings.length ? `<div style="margin-top:12px">${alertsHtml(b.warnings)}</div>` : ""}
    </section>

    <section class="card">
      <h2>المظهر</h2>
      <div class="seg">${[["light", "فاتح"], ["dark", "داكن"], ["system", "حسب الجهاز"]].map(([k, l]) => `<button data-theme-set="${k}" aria-pressed="${theme === k}">${l}</button>`).join("")}</div>
    </section>

    <section class="card">
      <h2>اللغة · Language</h2>
      <div class="seg" style="grid-template-columns:1fr 1fr" data-no-tr>
        <button data-lang-set="ar" aria-pressed="${!window.I18N || I18N.lang === "ar"}">العربية</button>
        <button data-lang-set="en" aria-pressed="${!!window.I18N && I18N.lang === "en"}">English</button>
      </div>
    </section>

    <section class="card">
      <h2>تواصل معنا</h2>
      ${contact.email || contact.whatsapp ? `<div class="btn-row" style="margin-bottom:12px">
        ${contact.email ? `<a class="chip" href="mailto:${esc(contact.email)}">${ic("ext")}الإيميل</a>` : ""}
        ${contact.whatsapp ? `<a class="chip" href="https://wa.me/${esc(String(contact.whatsapp).replace(/\D/g, ""))}" target="_blank" rel="noopener">${ic("ext")}واتساب</a>` : ""}</div>` : ""}
      <form id="f-contact">
        <label class="field"><span>اسمك</span><input name="name" required maxlength="60" value="${esc(T(a.display_name || ""))}"></label>
        <label class="field"><span>رسالتك</span><textarea name="message" required minlength="5" maxlength="2000"></textarea></label>
        <button class="btn block" type="submit">أرسل</button>
      </form>
    </section>

    <section class="card">
      <h2>خصوصيتك</h2>
      <div class="muted" style="font-size:14px;line-height:1.9">مصاريفك ما تطلع لأي جهة.<br>المساعد الذكي يشوف إجماليات بس، مو عملياتك.<br>ما نربح من الرسوم المتأخرة، وما نشجعك على التزامات جديدة.</div>
      <div class="btn-row" style="margin-top:12px"><button class="link-btn" data-legal="privacy">سياسة الخصوصية</button><button class="link-btn" data-legal="terms">الشروط</button></div>
    </section>

    ${S.demo ? `<section class="card"><h2>أدوات الديمو</h2><div class="stack">
      <button class="btn ghost block" data-act="next-month">انتقل للشهر الجاي</button>
      <button class="btn ghost block" data-act="reset">ابدأ الديمو من جديد</button></div></section>` : ""}

    <div class="stack" style="margin-bottom:10px">
      <button class="btn ghost block" data-act="logout">تسجيل الخروج</button>
      <button class="btn danger block" data-act="revoke">إلغاء الموافقة وحذف بياناتي</button>
    </div>`;
  $("#f-contact").addEventListener("submit", async e => {
    e.preventDefault();
    try { await api("/api/contact", { method: "POST", body: { name: e.target.name.value.trim(), message: e.target.message.value.trim() } });
      e.target.message.value = ""; toast("وصلتنا رسالتك، بنرد عليك قريب.", "good"); }
    catch (err) { handleError(err); }
  });
  S._budget = b;
}

function budgetSheet() {
  const t = Object.fromEntries((S._budget.target || []).map(x => [x.id, x.pct]));
  const sheet = openSheet({ title: "أهداف توزيع راتبك", body: `
    <form id="f-budget">
      ${[["essentials_pct", "الأساسيات (الالتزامات والمعيشة)", t.essentials], ["personal_pct", "شخصية", t.personal], ["savings_pct", "الادخار", t.savings]]
        .map(([k, l, v]) => `<div class="pct-row"><span>${l}</span><input name="${k}" inputmode="numeric" value="${v}"></div>`).join("")}
      <p class="muted" id="sum-note">المجموع لازم يكون 100%.</p>
      <p class="muted">نسبة الادخار هي الحد الأعلى لـ«تجمع أول» كل شهر.</p>
      <button class="btn block" type="submit">حفظ</button>
    </form>` });
  const f = $("#f-budget", sheet);
  const sum = () => ["essentials_pct", "personal_pct", "savings_pct"].reduce((a, k) => a + Math.round(toNum(f[k].value)), 0);
  f.addEventListener("input", () => { const s = sum(); $("#sum-note", sheet).textContent = `المجموع ${s}%${s === 100 ? " ✓" : "، لازم يكون 100%."}`; });
  f.addEventListener("submit", async e => {
    e.preventDefault();
    if (sum() !== 100) return toast("مجموع النسب لازم يكون 100%.", "bad");
    const body = Object.fromEntries(["essentials_pct", "personal_pct", "savings_pct"].map(k => [k, Math.round(toNum(f[k].value))]));
    try { await api("/api/budget", { method: "PUT", body }); closeSheet(); toast("حفظنا أهدافك.", "good"); refresh(); }
    catch (err) { handleError(err); }
  });
}

/* ---------- SUBSCRIPTIONS ---------- */
async function renderSubscriptions() {
  backTop("الباقات");
  const r = await api("/api/subscriptions");
  const cur = r.current.id;
  const yes = `<span class="teal">✓</span>`, no = `<span class="muted">✕</span>`;
  $("#view").innerHTML = `
    <p class="page-sub">كل اللي تحتاجه عشان تعرف وضعك موجود في الأساسية. الباقات الثانية تضيف مزايا.</p>
    ${r.usage && r.usage.limit !== null ? `<div class="note">مستخدم ${r.usage.used} من ${r.usage.limit} التزامات في باقتك الحالية.</div>` : ""}
    ${r.tiers.map(t => `<article class="plan ${t.id === cur ? "current" : ""}">
      <div class="card-head" style="margin:0"><b style="font-size:18px">${esc(t.name)}</b>
        ${t.id === cur ? `<span class="badge b-paid">باقتك الحالية</span>` : ""}</div>
      <div class="huge" style="margin:6px 0 0">${t.price ? `${money(t.price)}<span class="muted" style="font-size:14px"> / شهر</span>` : "مجانية"}</div>
      ${t.includes_previous ? `<p class="muted" style="margin:10px 0 0">كل اللي في ${esc(t.includes_previous)}، وزيادة:</p>` : `<p class="muted" style="margin:10px 0 0">تشمل:</p>`}
      <ul>${t.features.map(f => `<li>✓ ${esc(f)}</li>`).join("")}</ul>
      ${t.id === cur ? `<button class="btn ghost block" disabled>باقتك الحالية</button>` : `<button class="btn block" data-act="upgrade">${t.price > r.current.price ? "ترقية" : "انتقل لها"}</button>`}
    </article>`).join("")}
    <section class="card">
      <h2>مقارنة سريعة</h2>
      <div class="cmp-wrap"><table class="cmp">
        <tr><th></th>${r.tiers.map(t => `<th>${esc(t.name)}</th>`).join("")}</tr>
        <tr><td>الالتزامات</td>${r.tiers.map(t => `<td>${t.obligation_limit == null ? "بلا حد" : t.obligation_limit}</td>`).join("")}</tr>
        <tr><td>أسئلة المساعد بالشهر</td>${r.tiers.map(t => `<td>${t.assistant_questions == null ? "بلا حد" : t.assistant_questions}</td>`).join("")}</tr>
        <tr><td>الحساب الذكي</td>${r.tiers.map(t => `<td>${t.smart_account ? yes : no}</td>`).join("")}</tr>
        <tr><td>محاكاة الالتزامات المحدثة</td>${r.tiers.map(t => `<td>${t.planner ? yes : no}</td>`).join("")}</tr>
        <tr><td>محاكاة التوقعات المالية</td>${r.tiers.map(t => `<td>${t.forecast ? yes : no}</td>`).join("")}</tr>
        <tr><td>السعر</td>${r.tiers.map(t => `<td>${t.price ? `${t.price} ر.س` : "مجاناً"}</td>`).join("")}</tr>
      </table></div>
    </section>
    ${r.demo_mode ? `<section class="card"><h2>تبديل الباقة (للديمو)</h2>
      <div class="seg">${r.tiers.map(t => `<button data-plan-switch="${t.id}" aria-pressed="${t.id === cur}">${esc(t.name)}</button>`).join("")}</div>
      <p class="muted" style="margin:8px 0 0">بدون دفع، عشان تشوف الفرق بين الباقات.</p></section>` : ""}`;
}

function profileSheet() {
  const a = S._account || {};
  const sheet = openSheet({ title: "بياناتك", body: `
    <form id="f-profile">
      <label class="field"><span>الاسم</span><input name="display_name" required minlength="2" maxlength="40" value="${esc(T(a.display_name || ""))}"></label>
      <label class="field"><span>الإيميل (اختياري)</span><input name="email" type="email" dir="ltr" value="${esc(a.email || "")}"></label>
      <button class="btn block" type="submit">حفظ</button>
    </form>
    <h2 style="font-size:15px;margin:22px 0 8px">رقم الجوال</h2>
    <p class="muted" style="margin-top:0">رقمك الحالي <span dir="ltr">${esc(a.phone_masked || "—")}</span>. لتغييره بنرسل رمز للرقم الجديد.</p>
    <form id="f-phone">
      <label class="field"><span>الرقم الجديد</span><input name="phone" required inputmode="tel" dir="ltr" placeholder="05XXXXXXXX"></label>
      <div id="phone-code" hidden>
        <div class="alert good" id="phone-demo" hidden></div>
        <label class="field"><span>رمز التحقق</span><input name="code" inputmode="numeric" maxlength="6" dir="ltr"></label>
      </div>
      <button class="btn ghost block" type="submit" id="phone-btn">أرسل الرمز</button>
    </form>` });
  $("#f-profile", sheet).addEventListener("submit", async e => {
    e.preventDefault();
    try {
      await api("/api/account", { method: "PATCH", body: { display_name: e.target.display_name.value.trim(), email: e.target.email.value.trim() } });
      if (S.me) S.me.name = e.target.display_name.value.trim();
      closeSheet(); toast("حفظنا بياناتك.", "good"); refresh();
    } catch (err) { handleError(err); }
  });
  let sent = false;
  $("#f-phone", sheet).addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.target;
    try {
      if (!sent) {
        const r = await api("/api/account/phone", { method: "POST", body: { phone: f.phone.value.trim() } });
        sent = true; $("#phone-code", sheet).hidden = false; $("#phone-btn", sheet).textContent = T("تأكيد الرقم");
        if (r.demo_code) { const d = $("#phone-demo", sheet); d.hidden = false; d.innerHTML = `${T("رمزك التجريبي:")} <b dir="ltr">${esc(r.demo_code)}</b>`; }
        f.code.focus();
      } else {
        await api("/api/account/phone/verify", { method: "POST", body: { phone: f.phone.value.trim(), code: f.code.value.trim() } });
        closeSheet(); toast("غيّرنا رقم جوالك.", "good"); refresh();
      }
    } catch (err) { handleError(err); }
  });
}

async function addBankSheet() {
  const data = S._banks || await api("/api/banks");
  const have = new Set(data.banks.map(b => b.bank_id));
  const options = data.available.filter(b => !have.has(b.bank_id));
  const sheet = openSheet({ title: "اربط بنك ثاني", body: options.length
    ? `<p class="muted" style="margin-top:0">نقرأ عملياته بنفس الموافقة (قراءة فقط)، ونضيف التزاماته واشتراكاته لصورتك الكاملة.</p>
       ${options.map(b => `<button class="bank" data-add-bank="${esc(b.bank_id)}"><span class="ico">${ic("bank")}</span>${esc(b.name)}</button>`).join("")}`
    : `<div class="empty">ربطت كل البنوك المتاحة بالديمو.</div>` });
  sheet.addEventListener("click", async e => {
    const b = e.target.closest("[data-add-bank]"); if (!b) return;
    b.disabled = true; b.insertAdjacentHTML("beforeend", `<span class="muted" style="margin-inline-start:auto">نربط…</span>`);
    try {
      const r = await api("/api/banks", { method: "POST", body: { bank_id: b.dataset.addBank } });
      closeSheet();
      const subs = r.plans.filter(p => p.kind === "subscription").length;
      toast(`<b>ربطنا ${esc(r.bank_name)}.</b> ${r.plans.length ? `لقينا ${subs ? `${subs === 1 ? "اشتراك واحد" : subs === 2 ? "اشتراكين" : `${subs} اشتراكات`}` : `${r.plans.length} التزامات`} جديدة.` : "ما لقينا التزامات جديدة."}`, "good", 6000);
      refresh();
    } catch (err) { b.disabled = false; handleError(err); }
  });
}

/* ---------- SCORE & STANDINGS ---------- */
function scoreSlide(sc, lb) {
  const cls = sc.score >= 85 ? "" : sc.score >= 55 ? "v" : "g";
  return `<section class="card ring-card slide" aria-label="تقييم إدارتك">
      <div class="slide-top">
        <span class="badge b-violet">${esc(sc.grade)}</span>
        <a class="square-btn" href="#standings" aria-label="الترتيب">${ic("trophy")}</a>
      </div>
      <div class="ring" style="margin-top:-8px">${ringSvg(sc.score / 100, cls)}
        <div class="ring-center"><span class="k">تقييم إدارتك</span>
          <span class="v num ${cls === "v" ? "lav" : cls === "g" ? "gold" : ""}">${sc.score}</span>
          <span class="of">من 100</span></div></div>
      <p class="ring-foot">نقاطك <b class="num">${fmt(sc.points)}</b> · ترتيبك <b class="num">#${lb.rank}</b> من <span class="num">${lb.total}</span></p>
      <button class="link-btn" data-act="score-why" style="margin:6px auto 0">كيف أرفع تقييمي؟</button>
    </section>`;
}

function scoreSheet() {
  const sc = S._score;
  if (!sc) return;
  openSheet({ title: "تقييم إدارتك", body: `
    <div class="note">${esc(sc.fair_note)}</div>
    ${sc.parts.map(p => `<div class="card tight" style="margin-bottom:10px">
        <div class="card-head" style="margin-bottom:6px"><b>${esc(p.label)}</b><span class="num"><b>${p.points}</b> / ${p.max}</span></div>
        <div class="bar ${p.points >= p.max ? "" : p.points >= p.max / 2 ? "v" : "warn"}"><span style="width:${p.points / p.max * 100}%"></span></div>
        <p class="muted" style="margin:8px 0 0">${esc(p.note)}</p>
        ${p.tip ? `<p style="margin:6px 0 0;font-size:14px" class="teal">${esc(p.tip)}</p>` : ""}
      </div>`).join("")}
    ${sc.events && sc.events.length ? `<h2 style="font-size:15px;margin:14px 0 6px">نقاط كسبتها</h2>
      ${sc.events.map(e => `<div class="row"><span>${esc(e.label)}</span><span class="r teal">+${e.points}</span></div>`).join("")}` : ""}
    <p class="muted" style="margin-top:12px">تكسب نقاط إضافية لما تدفع قبل الموعد، تلغي اشتراك ما تحتاجه، وتخلّص الشهر تحت حدك.</p>` });
}

async function renderStandings() {
  backTop("الترتيب");
  const lb = await api("/api/leaderboard");
  $("#view").innerHTML = `
    <section class="card" style="text-align:center">
      <div class="muted">ترتيبك</div>
      <div class="huge lavender">#${lb.rank} <span class="muted" style="font-size:15px">من ${lb.total}</span></div>
      <p class="muted" style="margin:6px 0 0">تقييمك ${lb.score} من 100 · نقاطك ${fmt(lb.points)}</p>
    </section>
    <div class="note">${esc(lb.note)}</div>
    <section class="card">
      <h2>الظهور بالترتيب</h2>
      <label class="switch" style="margin-bottom:12px"><input type="checkbox" id="lb-opt" ${lb.opt_in ? "checked" : ""}>اظهر للآخرين باسم مستعار</label>
      <div class="btn-row"><input id="lb-name" maxlength="24" placeholder="اسمك المستعار" value="${esc(lb.nickname || "")}" style="flex:1">
        <button class="btn sm" data-act="lb-save">حفظ</button></div>
      <p class="muted" style="margin:8px 0 0">${lb.opt_in ? "اسمك ظاهر للمتنافسين، بدون أي مبالغ." : "أنت مخفي عن غيرك، وتشوف ترتيبك لحالك."}</p>
    </section>
    <section class="card">
      ${lb.rows.map(r => `<div class="row" style="${r.me ? "background:var(--violet-bg);border-radius:14px;padding-inline:10px" : ""}">
          <div class="l"><span class="num" style="width:28px;font-weight:700;${r.rank <= 3 ? "color:var(--gold)" : ""}">${r.rank <= 3 ? ["🥇", "🥈", "🥉"][r.rank - 1] : "#" + r.rank}</span>
            <span class="t" ${r.me ? "" : "data-no-tr"}>${esc(r.name)}${r.me ? ` <span class="muted">(أنت)</span>` : ""}</span></div>
          <span class="r num">${r.score}</span></div>`).join("")}
    </section>`;
}

/* ---------- CHAT ---------- */
const SUGGESTIONS = ["أقدر آخذ جوال بـ 3000 على 4 دفعات؟", "طيب متى أقدر؟", "حط الجوال بالأمنيات", "كم عليّ هالشهر؟", "ضيف مصروف قهوة 20"];
function chatHtml() {
  return S.chat.map(m => {
    if (m.type === "action") {
      const a = m.action;
      const done = a.state === "confirmed" ? `<div class="alert good" style="margin-top:10px">${ic("check")}<div>تم.</div></div>`
        : a.state === "cancelled" ? `<div class="muted" style="margin-top:8px">انلغى.</div>`
        : `<div class="btn-row"><button class="btn teal sm" data-act-confirm="${esc(a.id)}">أكّد</button><button class="btn ghost sm" data-act-cancel="${esc(a.id)}">إلغاء</button></div>`;
      return `<div class="action-card"><b>تأكيد قبل التعديل</b><div style="margin-top:4px">${esc(a.summary)}</div>${done}</div>`;
    }
    return `<div class="msg ${m.role}">${esc(m.text)}${m.tools && m.tools.length ? `<span class="tools">engine: ${m.tools.map(esc).join(", ")}</span>` : ""}</div>`;
  }).join("");
}
function openChat() {
  if (!S.chat.length) S.chat.push({ role: "bot", text: `هلا ${S.me && S.me.name ? S.me.name : ""}! أنا مساعد مُدار. اسألني عن التزاماتك، مصاريفك، أو أي شي تفكر تشتريه.` });
  const sheet = openSheet({ title: "مساعد مُدار", tall: true, body: `<div class="msgs" id="msgs">${chatHtml()}</div>` });
  sheet.insertAdjacentHTML("beforeend", `
    <div class="suggest">${SUGGESTIONS.map(s => `<button type="button" data-suggest>${s}</button>`).join("")}</div>
    <form class="composer" id="f-chat"><input id="chat-in" placeholder="اكتب رسالتك…" maxlength="500" autocomplete="off">
      <button class="btn" type="submit" aria-label="إرسال">${ic("send")}</button></form>`);
  const body = $(".sheet-body", sheet);
  const paint = () => { $("#msgs", sheet).innerHTML = chatHtml(); body.scrollTop = body.scrollHeight; };
  paint();
  async function send(text) {
    S.chat.push({ role: "user", text }); S.chat.push({ role: "bot", text: "لحظة، أحسب…", pending: true }); paint();
    try {
      const r = await api("/api/chat", { method: "POST", body: { message: text, lang: window.I18N ? I18N.lang : "ar" } });
      S.chat.pop(); S.chat.push({ role: "bot", text: r.reply, tools: r.tools });
      (r.actions || []).forEach(a => S.chat.push({ type: "action", action: { ...a, state: "pending" } }));
    } catch (err) {
      S.chat.pop(); S.chat.push({ role: "bot", text: err.message || "فيه مشكلة بالاتصال، جرّب مرة ثانية." });
      if (err.status === 401) { closeSheet(); handleError(err); return; }
    }
    paint();
  }
  $("#f-chat", sheet).addEventListener("submit", e => { e.preventDefault(); const v = $("#chat-in", sheet).value.trim(); if (v) { $("#chat-in", sheet).value = ""; send(v); } });
  sheet.addEventListener("click", async e => {
    const sug = e.target.closest("[data-suggest]"); if (sug) send(sug.textContent);
    const c = e.target.closest("[data-act-confirm]"), x = e.target.closest("[data-act-cancel]");
    const id = c ? c.dataset.actConfirm : x ? x.dataset.actCancel : null;
    if (!id) return;
    const item = S.chat.find(m => m.type === "action" && m.action.id === id);
    try {
      await api(`/api/chat/actions/${encodeURIComponent(id)}/${c ? "confirm" : "cancel"}`, { method: "POST" });
      item.action.state = c ? "confirmed" : "cancelled"; paint();
      if (c) { toast("تم التعديل.", "good"); refresh(); }
    } catch (err) { item.action.state = "cancelled"; paint(); handleError(err); }
  });
}

/* ---------- global events ---------- */
document.addEventListener("click", async e => {
  const t = e.target;
  const copy = t.closest("[data-copy]");
  if (copy) {
    e.preventDefault();
    try { await navigator.clipboard.writeText(copy.dataset.copy); toast("نسخنا رقم السداد.", "good"); }
    catch (_) { toast("رقم السداد: " + esc(copy.dataset.copy)); }
    return;
  }
  if (t.closest("#fab")) return openChat();
  const legal = t.closest("[data-legal]");
  if (legal && !t.closest("#screen")) { e.preventDefault(); return legalSheet(legal.dataset.legal); }
  if (t.closest("#layer .sheet-bg") || t.closest("#screen")) return;   // sheets & screens handle their own clicks

  const act = t.closest("[data-act]")?.dataset.act;
  if (act === "pay") return paySheet();
  if (act === "add-expense") return addExpenseSheet();
  if (act === "add-plan") return addPlanSheet();
  if (act === "next-month") return nextMonth();
  if (act === "edit-budget") return budgetSheet();
  if (act === "logout") return logout();
  if (act === "upgrade") return toast("قريباً.");
  if (act === "others") { S.planner.others = !S.planner.others; return plannerResults().catch(handleError); }
  if (act === "wish-save") return addWishFromPlanner("save");
  if (act === "wish-chosen") return addWishFromPlanner(S.planner._chosenMethod);
  if (act === "add-bank") return addBankSheet();
  if (act === "edit-profile") return profileSheet();
  if (act === "score-why") return scoreSheet();
  if (act === "lb-save") {
    const opt = $("#lb-opt").checked, nickname = $("#lb-name").value.trim();
    try { await api("/api/leaderboard/me", { method: "PUT", body: { opt_in: opt, nickname: nickname || null } });
      toast(opt ? "تمام، صرت ظاهر بالترتيب." : "تمام، أنت مخفي عن غيرك.", "good"); refresh(); }
    catch (err) { handleError(err); }
    return;
  }
  if (act === "reset") {
    if (!ask("بنبدأ الديمو من جديد ونمسح البيانات الحالية. تبي نكمل؟")) return;
    try { const r = await api("/api/demo/reset", { method: "POST" }); setToken(r.token); S.chat = []; showDetected(); } catch (err) { handleError(err); }
    return;
  }
  if (act === "revoke") {
    if (!ask("متأكد؟ بنلغي الموافقة ونحذف عملياتك والتزاماتك.")) return;
    try { await api("/api/consent", { method: "DELETE" }); toast("ألغينا الموافقة وحذفنا بياناتك.", "good"); S.chat = []; showBankConnect(); }
    catch (err) { handleError(err); }
    return;
  }

  const pick = t.closest("[data-pick-type]");
  if (pick) {
    const months = pick.dataset.pickMonths ? Number(pick.dataset.pickMonths) : null;
    S.planner.chosen = { type: pick.dataset.pickType, id: pick.dataset.pickId, months };
    return plannerResults().catch(handleError);
  }
  const tenor = t.closest("[data-tenor]");
  if (tenor) {
    const id = tenor.dataset.tenor, months = Number(tenor.dataset.months);
    S.planner.tenors = { ...(S.planner.tenors || {}), [id]: months };
    if (S.planner.chosen && S.planner.chosen.type === "loan" && S.planner.chosen.id === id) S.planner.chosen.months = months;
    return plannerResults().catch(handleError);
  }
  const kindBtn = t.closest("[data-kind]");
  if (kindBtn) { S.planner = { ...S.planner, kind: kindBtn.dataset.kind, name: "", chosen: null, tenors: {} }; return renderPlanner().catch(handleError); }
  const quick = t.closest("[data-quick]");
  if (quick) {
    S.planner = { ...S.planner, price: quick.dataset.quick, name: T(quick.dataset.qname), chosen: null, tenors: {} };
    $("#pl-price").value = S.planner.price; $("#pl-name").value = S.planner.name;
    return plannerResults().catch(handleError);
  }
  const expF = t.closest("[data-exp-filter]");
  if (expF) { S.expFilter = expF.dataset.expFilter; return refresh(); }
  const intent = t.closest("[data-intent]");
  if (intent) {
    const on = intent.dataset.on === "1";
    try { await api(`/api/plans/${encodeURIComponent(intent.dataset.intent)}`, { method: "PATCH", body: { cancel_planned: on, remind: true } });
      toast(on ? "تمام، بنذكّرك قبل التجديد عشان تلغيه." : "تمام، خليناه.", "good"); refresh(); }
    catch (err) { handleError(err); }
    return;
  }
  const canc = t.closest("[data-cancelled]");
  if (canc) {
    if (!ask(`ألغيت ${canc.dataset.name} من موقع الجهة؟ بنشيله من التزاماتك.`)) return;
    try { const r = await api(`/api/plans/${encodeURIComponent(canc.dataset.cancelled)}/cancelled`, { method: "POST" });
      toast(`<b>حلو!</b> وفّرت ${money(r.saves)} شهرياً.${r.charged_this_month ? " انخصم هالشهر، ومن الشهر الجاي ما عاد ينخصم." : ""}`, "good", 6000); refresh(); }
    catch (err) { handleError(err); }
    return;
  }
  const delB = t.closest("[data-del-bank]");
  if (delB) {
    if (!ask(`نفصل ${delB.dataset.name} ونحذف عملياته من مُدار؟`)) return;
    try { const r = await api(`/api/banks/${encodeURIComponent(delB.dataset.delBank)}`, { method: "DELETE" });
      if (r.last_bank) { toast("فصلنا آخر بنك وحذفنا بياناتك.", "good"); S.chat = []; showBankConnect(); return; }
      toast(`فصلنا ${esc(delB.dataset.name)}.`, "good"); refresh(); }
    catch (err) { handleError(err); }
    return;
  }
  const setM = t.closest("[data-set-months]");
  if (setM) { S.planner.months = setM.dataset.setMonths; $("#pl-months").value = S.planner.months; return plannerResults().catch(handleError); }
  const setP = t.closest("[data-set-price]");
  if (setP) { S.planner.price = setP.dataset.setPrice; $("#pl-price").value = S.planner.price; return plannerResults().catch(handleError); }
  const cmp = t.closest("[data-compare]");
  if (cmp) { S.planner = { ...S.planner, name: cmp.dataset.name, price: cmp.dataset.price, kind: cmp.dataset.wkind || "item", chosen: null }; location.hash = "#planner"; return; }
  const delW = t.closest("[data-del-wish]");
  if (delW) { try { await api(`/api/wishlist/${delW.dataset.delWish}`, { method: "DELETE" }); refresh(); } catch (err) { handleError(err); } return; }
  const delE = t.closest("[data-del-exp]");
  if (delE) { e.stopPropagation(); try { await api(`/api/expenses/${encodeURIComponent(delE.dataset.delExp)}`, { method: "DELETE" }); toast("حذفنا المصروف.", "good"); refresh(); } catch (err) { handleError(err); } return; }
  const recat = t.closest("[data-recat]");
  if (recat) return recategorizeSheet(recat.dataset.recat);
  const tab = t.closest("[data-tab-ob]");
  if (tab) { S.obTab = tab.dataset.tabOb; return refresh(); }
  const conf = t.closest("[data-confirm]");
  const edit = t.closest("[data-plan-edit]");
  if (edit) return editPlanSheet(edit.dataset.planEdit);
  if (conf) { try { await api(`/api/plans/${encodeURIComponent(conf.dataset.confirm)}/confirm`, { method: "POST", body: {} }); toast("أكدنا الالتزام.", "good"); refresh(); } catch (err) { handleError(err); } return; }
  const delP = t.closest("[data-del-plan]");
  if (delP) { if (!ask("نحذف هالالتزام من مُدار؟ هذا ما يلغيه عند الجهة.")) return;
    try { await api(`/api/plans/${encodeURIComponent(delP.dataset.delPlan)}`, { method: "DELETE" }); refresh(); } catch (err) { handleError(err); } return; }
  const lg = t.closest("[data-lang-set]");
  if (lg) {
    if (lg.dataset.langSet === I18N.lang) return;
    I18N.set(lg.dataset.langSet);
    try { sessionStorage.setItem("mudar_skip_splash", "1"); } catch (_) {}
    location.reload();
    return;
  }
  const th = t.closest("[data-theme-set]");
  if (th) { applyTheme(th.dataset.themeSet); $$("[data-theme-set]").forEach(b => b.setAttribute("aria-pressed", b === th)); return; }
  const sw = t.closest("[data-plan-switch]");
  if (sw) { try { await api("/api/demo/subscription", { method: "POST", body: { plan: sw.dataset.planSwitch } }); toast("بدّلنا الباقة.", "good"); refresh(); } catch (err) { handleError(err); } }
});

document.addEventListener("change", async e => {
  const rm = e.target.closest("[data-remind]");
  if (rm && !e.target.closest(".sheet-bg")) {
    try { await api(`/api/plans/${encodeURIComponent(rm.dataset.remind)}`, { method: "PATCH", body: { remind: rm.checked } });
      toast(rm.checked ? "بنذكّرك قبل التجديد." : "وقفنا التذكير لهالاشتراك.", "good"); }
    catch (err) { rm.checked = !rm.checked; handleError(err); }
    return;
  }
  const m = e.target.closest("[data-mode]");
  if (!m || e.target.closest(".sheet-bg")) return;
  try {
    await api(`/api/plans/${encodeURIComponent(m.dataset.mode)}`, { method: "PATCH", body: { pay_mode: m.checked ? "auto" : "manual" } });
    toast(m.checked ? "تمام، هالالتزام ينسحب تلقائي وما ينحسب بـ«ادفع الكل»." : "تمام، تقدر تدفعه من «ادفع الكل».", "good");
    refresh();
  } catch (err) { m.checked = !m.checked; handleError(err); }
});

/* ---------- boot ---------- */
applyTheme();
if (window.I18N) I18N.start();
if (S.token) startApp(); else showWelcome();
(() => {
  let skip = false;
  try { skip = sessionStorage.getItem("mudar_skip_splash") === "1"; sessionStorage.removeItem("mudar_skip_splash"); } catch (_) {}
  if (!skip) splash();
})();
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/static/sw.js").catch(() => {}));
}
