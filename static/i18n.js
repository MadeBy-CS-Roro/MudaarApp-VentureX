"use strict";
/* مُدار — language layer.
   Arabic is written in the app and the API. In English mode every text node and label is translated
   on the fly: (1) exact phrases, (2) sentence patterns with numbers/names, (3) word & phrase fallback.
   User content (names, merchants, chat messages typed by the user) is left as is. */
(function () {
  const AR = /[\u0600-\u06FF]/;
  let lang = "ar";
  try { lang = localStorage.getItem("mudar_lang") === "en" ? "en" : "ar"; } catch (_) {}

  /* ---------- names & short labels (also used inside sentences) ---------- */
  const NAMES = {
    "تمارا": "Tamara", "تابي": "Tabby", "تمويل السيارة": "Car finance", "قسط السيارة": "Car finance", "الإيجار": "Rent",
    "نتفليكس": "Netflix", "شاهد VIP": "Shahid VIP", "سبوتيفاي": "Spotify", "ديزني+": "Disney+", "أنغامي": "Anghami",
    "فاتورة الكهرباء": "Electricity bill", "فاتورة المياه": "Water bill", "باقة STC": "STC plan", "باقة موبايلي": "Mobily plan", "باقة زين": "Zain plan",
    "عمرة": "Umrah", "جوال": "Phone", "شوز": "Shoes", "لابتوب": "Laptop", "أثاث": "Furniture", "منتج": "Item",
    "نورة": "Noura", "أنت": "You", "صقر الميزانية": "Budget Falcon", "أبو حساب": "Abu Hisab", "منظمة": "Organized", "الهادئ": "Calm One",
    "رايق": "Chill", "قطرة قطرة": "Drop by Drop", "ميزان": "Balance", "خطوة خطوة": "Step by Step", "بدر": "Badr", "مرتّبة": "Tidy",
    "متفائل": "Optimist", "الحالم": "Dreamer", "بادئ": "Beginner", "يتعلم": "Learner",
    "ممتاز": "Excellent", "جيد جداً": "Very good", "جيد": "Good", "يحتاج شغل": "Needs work",
    "سفرة داخلية": "Domestic trip", "سفرة دبي": "Dubai trip", "سفرة أوروبا": "Europe trip", "هدية": "Gift", "حفلة تخرج": "Graduation party",
    "زواج": "Wedding", "دورة": "Course", "شهادة احترافية": "Professional certificate", "دبلوم": "Diploma", "بنك تجريبي أ": "Demo Bank A", "بنك تجريبي ب": "Demo Bank B", "بنك تجريبي ج": "Demo Bank C", "بنك تجريبي": "Demo Bank",
    "بنك أ": "Bank A", "بنك ب": "Bank B", "بنك ج": "Bank C", "بنك د": "Bank D", "شركة تمويل أ": "Finance Co. A", "شركة تمويل ب": "Finance Co. B",
    "الراجحي": "Al Rajhi", "الأهلي": "SNB", "بنك الرياض": "Riyad Bank", "يدوي": "Manual",
    "الأساسية": "Basic", "بلس": "Plus", "بريميوم": "Premium",
    "سكن وإيجار": "Housing & rent", "بقالة": "Groceries", "وقود": "Fuel", "فواتير": "Bills", "اتصالات وإنترنت": "Phone & internet",
    "تعليم": "Education", "صحة": "Health", "مواصلات": "Transport", "تأمين": "Insurance", "التزامات مالية": "Financial commitments",
    "مطاعم ومقاهي": "Restaurants & cafés", "توصيل": "Delivery", "تسوق وملابس": "Shopping & clothes", "ترفيه": "Entertainment",
    "سفر": "Travel", "اشتراكات رقمية": "Digital subscriptions", "عناية شخصية": "Personal care", "هدايا ومناسبات": "Gifts & occasions",
    "رياضة": "Sports", "أخرى": "Other", "الأساسيات": "Essentials", "شخصية": "Personal", "الادخار": "Savings", "متبقي": "Left over",
    "كاش": "Cash", "3 دفعات": "3 payments", "4 دفعات": "4 payments", "6 شهور": "6 months", "تمويل 12 شهر": "12-month finance", "تجمع أول": "Save first",
    "هالشهر": "this month", "الشهر الجاي": "next month", "بعد شهرين": "in 2 months", "بعد شهر": "in 1 month", "الحين": "now",
    "بعد أكثر من سنة": "in more than a year", "أكثر من 3 سنين": "more than 3 years",
    "سنة": "1 year", "سنتين": "2 years", "3 سنين": "3 years", "4 سنين": "4 years", "5 سنين": "5 years",
    "اليوم": "today", "بكرة": "tomorrow", "بعد يومين": "in 2 days"
  };
  const name = s => NAMES[s.trim()] || tr(s.trim());

  /* ---------- exact phrases ---------- */
  const P = {
    "مُدار": "Mudar", "اللغة · Language": "Language",
    "تقييم إدارتك": "Your money score", "من 100": "out of 100", "نقاطك": "Points", "· ترتيبك": "· Rank", "كيف أرفع تقييمي؟": "How do I raise my score?",
    "الترتيب": "Standings", "ترتيبك": "Your rank", "الظهور بالترتيب": "Show me in the standings", "اظهر للآخرين باسم مستعار": "Show me to others under a nickname",
    "اسمك المستعار": "Your nickname", "اسمك ظاهر للمتنافسين، بدون أي مبالغ.": "Your nickname is visible to others, with no amounts.",
    "أنت مخفي عن غيرك، وتشوف ترتيبك لحالك.": "You're hidden from others; only you see your rank.", "(أنت)": "(you)", "نقاط كسبتها": "Points you earned",
    "تكسب نقاط إضافية لما تدفع قبل الموعد، تلغي اشتراك ما تحتاجه، وتخلّص الشهر تحت حدك.": "Earn bonus points by paying early, cancelling subscriptions you don't need, and ending the month under your limit.",
    "النقاط تُحسب على وضعك أنت وأهدافك، مو على كبر راتبك.": "Points are based on your own situation and targets, not on how big your salary is.",
    "الترتيب على حسن إدارتك لفلوسك نسبةً لوضعك، مو على كبر الراتب. ما نعرض أي مبالغ، الاسم المستعار والنقاط بس.": "Standings rank how well you manage relative to your situation, not salary size. No amounts are shown, only nicknames and scores.",
    "تمام، صرت ظاهر بالترتيب.": "Done, you're now in the standings.", "تمام، أنت مخفي عن غيرك.": "Done, you're hidden from others.",
    "اختر اسم مستعار عشان تظهر بالترتيب.": "Pick a nickname to appear in the standings.",
    "سداد الالتزامات بوقتها": "Paying commitments on time", "الالتزام بحد صرفك الشخصي": "Staying within your personal limit",
    "الالتزامات مقابل هدفك من الراتب": "Commitments vs your salary target", "نسبة الديون من راتبك": "Debt as a share of salary",
    "التحويش حسب قدرتك": "Saving what you can", "متابعة الاشتراكات": "Keeping subscriptions in check",
    "دفعت التزام قبل موعده": "Paid a commitment early", "ألغيت اشتراك ما تحتاجه": "Cancelled a subscription you didn't need",
    "أكدت التزام": "Confirmed a commitment", "خلّصت شهر": "Finished a month", "خلّصت الشهر تحت حدك الشخصي": "Finished the month under your personal limit",
    "ما عليك ولا دفعة متأخرة.": "No late payments.", "ادفع المتأخر من «ادفع الكل» أو من موقع الجهة.": "Pay late items from “Pay all” or the provider's site.",
    "صرفك الشخصي ماشي على حدك.": "Your personal spending is on track.", "صرفك أسرع من حدك هالشهر.": "You're spending faster than your limit this month.",
    "قلّل التزام أو اشتراك، أو لا تضيف التزام جديد لين تنزل النسبة.": "Cut a commitment or subscription, or avoid new ones until the share drops.",
    "كل التزام يخلص يرفع نقاطك. تجنّب أقساط جديدة لين تنزل تحت 20%.": "Every finished commitment raises your score. Avoid new installments until you're under 20%.",
    "ما كان فيه مجال للتحويش، وما ننقص عليك.": "There was no room to save, so you're not penalized.",
    "أول شهر لك، نقاط التحويش تكتمل لما يخلص الشهر.": "Your first month: saving points complete when the month ends.",
    "اشتراكاتك تحت السيطرة.": "Your subscriptions are under control.", "فيه اشتراكات تحتاج متابعة.": "Some subscriptions need attention.",
    "شغّل التذكير، وألغِ اللي ناوي تلغيه قبل التجديد.": "Turn reminders on, and cancel the ones you planned to before renewal.",
    "شراء": "Purchase", "سفرة": "Trip", "مناسبة": "Occasion", "دراسة ودورات": "Study & courses", "شي ثاني": "Something else",
    "وش تبي تخطط له؟": "What are you planning for?", "مثال: سفرة دبي": "e.g. Dubai trip", "مثال: حفلة تخرج": "e.g. graduation party", "مثال: دورة": "e.g. a course", "مثال: جوال": "e.g. phone",
    "خطط لأي مصروف كبير: شراء، سفرة، مناسبة، أو دراسة. نقارن لك التقسيط والتمويل والتحويش على وضعك الحقيقي، ونختار الأنسب.": "Plan any big expense: a purchase, a trip, an occasion or studies. We compare installments, loans and saving up on your real numbers, and pick the best fit.",
    "متى تقدر تدفعه": "When you can pay for it", "قارن طرق الدفع": "Compare ways to pay",
    "الجهات اللي تدفع لها": "Who you pay", "روابط المواقع الرسمية عشان تدفع أو تدير حسابك عندهم.": "Official sites, to pay or manage your account with them.",
    "ادفع": "Pay", "منصة إيجار": "Ejar platform", "موقع الشركة السعودية للكهرباء": "Saudi Electricity website", "موقع شركة المياه الوطنية": "National Water website",
    "تعديل": "Edit", "بياناتك": "Your details", "رقمك الحالي": "Your current number", ". لتغييره بنرسل رمز للرقم الجديد.": ". To change it we'll text a code to the new number.",
    "الرقم الجديد": "New number", "رمز التحقق": "Verification code", "تأكيد الرقم": "Confirm number", "حفظنا بياناتك.": "Your details are saved.",
    "غيّرنا رقم جوالك.": "Your mobile number is updated.", "أرسلنا رمز للرقم الجديد.": "We sent a code to the new number.", "هالرقم مسجل بحساب ثاني.": "This number belongs to another account.",
    "تشمل:": "Includes:", "أسئلة المساعد بالشهر": "Assistant questions / month", "أسئلة المساعد: بلا حد": "Assistant questions: unlimited",
    "مقارنة طرق الشراء (المخطط)": "Comparing ways to pay (Planner)", "التوقعات المالية": "Financial forecast",
    "لين 5 التزامات (أقساط، إيجار، اشتراكات)": "Up to 5 commitments (installments, rent, subscriptions)", "«تقدر تصرف» لهالشهر": "“Left to spend” for this month",
    "ربط أكثر من بنك": "Connect several banks", "تنبيه قبل الراتب وتذكير قبل تجديد الاشتراكات": "Before-payday alerts and subscription renewal reminders",
    "المصروفات مع التصنيف الذكي وحد الصرف الشخصي": "Spending with smart categories and a personal limit", "تتبع الالتزامات مقابل نسبتها من راتبك": "Commitments tracked against their share of your salary",
    "قائمة الأمنيات مع «تجمع أول»": "Wishlist with “Save first”", "المساعد الذكي: 5 أسئلة بالشهر": "Assistant: 5 questions a month",
    "لين 30 التزام": "Up to 30 commitments", "الحساب الذكي: كم يبقى لك بالشهور الجاية ومتى تقدر تشتري": "Smart account: what's left in coming months and when you can buy",
    "المخطط: مقارنة التقسيط والتمويل وتجمع أول، واختيار الأنسب لك": "Planner: compare installments, loans and saving up, and get the best fit",
    "المساعد الذكي: 30 سؤال بالشهر": "Assistant: 30 questions a month", "توقعاتك المالية لـ 12 شهر": "Your 12-month financial forecast", "المساعد الذكي بلا حد": "Unlimited assistant", "التنقل": "Navigation", "توزيع الراتب": "Salary split",
    "ر.س من مصروفك لهالشهر": "SAR of your spending money this month", "باقي عليك": "Still due", "ر.س هالشهر": "SAR this month",
    "ر.س، ألغه لو ما تبيه": "SAR, cancel if you don't need it", "ر.س من الشهر الجاي.": "SAR from next month.",
    "ر.س. تقدر تغيّره من «حسابي».": "SAR. You can change it in “Account”.", "ر.س بدون أي رسوم": "SAR with no fees", "جمعت": "Saved",
    "ر.س (دفع تجريبي)": "SAR (demo payment)", "✓ اخترته": "✓ Chosen", "ر.س تقريباً.": "SAR.", "ر.س كل شهر، وانتقل للمدفوعات السابقة.": "SAR every month. It moved to previous payments.",
    "ر.س في أضيق شهر.": "SAR in your tightest month.", "ر.س للحين": "SAR so far", "ر.س شهرياً =": "SAR a month =", "مساعد مُدار": "Mudar assistant", "شعار مُدار": "Mudar logo",
    "التزاماتك، مصاريفك، وراتبك بمكان واحد": "Your commitments, spending and salary in one place",
    "اضغط للتخطي": "Tap to skip", "حرّك الكوكب حول مداره": "Drag the planet around its orbit",
    "إنشاء حساب": "Create account", "عندي حساب، سجّل دخول": "I have an account, log in", "دخول سريع بحساب نورة (للديمو)": "Quick login as Noura (demo)",
    "الدخول عبر نفاذ (قريباً)": "Log in with Nafath (coming soon)", "بيانات وهمية للهاكاثون": "Sample data for the hackathon",
    "رجوع": "Back", "بنرسل لك رمز تحقق على جوالك.": "We'll text you a verification code.", "الاسم": "Name", "رقم الجوال": "Mobile number",
    "الإيميل (اختياري)": "Email (optional)", "أوافق على": "I agree to the", "الشروط": "Terms", "سياسة الخصوصية": "Privacy policy", "و": " and ",
    "أرسل الرمز": "Send code", "تسجيل الدخول": "Log in", "اكتب رقم جوالك ونرسل لك رمز.": "Enter your mobile number and we'll send you a code.",
    "حساب الديمو: 0500000123": "Demo account: 0500000123", "أدخل الرمز": "Enter the code", "أرسلناه لـ": "Sent to",
    "رمزك التجريبي:": "Your demo code:", "إذا الرقم مسجل بيوصلك رمز. إذا ما عندك حساب، أنشئ واحد.": "If this number is registered you'll get a code. No account? Create one.",
    "تأكيد": "Confirm", "إعادة الإرسال": "Resend", "غيّر الرقم": "Change number", "أرسلنا رمز جديد.": "We sent a new code.",
    "مُدار يعطيك معلومات وتنبيهات عن التزاماتك ومصاريفك، وهذي مو استشارة مالية.": "Mudar gives you information and alerts about your commitments and spending. This isn't financial advice.",
    "أنت المسؤول عن قراراتك المالية. العروض المعروضة بالتطبيق تجريبية للتوضيح.": "You're responsible for your financial decisions. Offers shown in the app are samples for illustration.",
    "تقدر تلغي ربط حسابك البنكي بأي وقت من «حسابي».": "You can disconnect your bank any time from “Account”.",
    "نقرأ عملياتك البنكية بموافقتك، وقراءة فقط. ما نقدر نحوّل ولا ندفع بدون موافقتك من تطبيق البنك.": "We read your bank transactions with your consent, read-only. We can't transfer or pay without your approval in your bank app.",
    "رقم جوالك ما ينحفظ كامل، نحفظ نسخة مشفّرة وآخر 3 أرقام بس.": "We never store your full number: only a hashed copy and the last 3 digits.",
    "مصاريفك ما تطلع لأي جهة، والمساعد الذكي يشوف إجماليات بس.": "Your spending is never shared, and the assistant only sees totals.",
    "اربط حساباتك البنكية": "Connect your bank accounts",
    "اختر كل البنوك اللي تستخدمها، عشان نشوف كل التزاماتك واشتراكاتك بمكان واحد. ما نقدر نحوّل ولا ندفع.": "Pick every bank you use so we can see all your commitments and subscriptions in one place. We can't transfer or pay.",
    "حساب الراتب": "Salary account", "بطاقة ائتمانية": "Credit card", "حساب توفير": "Savings account",
    "وش اللي بتوافق عليه": "What you're agreeing to", "قراءة الحسابات والرصيد": "Read accounts and balances", "قراءة العمليات لآخر 12 شهر": "Read the last 12 months of transactions",
    "التحويل أو الدفع من حسابك": "Transfers or payments from your account", "تقدر تلغي الموافقة بأي وقت، وتنتهي لحالها بعد 90 يوم": "Revoke any time; it expires by itself after 90 days",
    "اختر بنك واحد على الأقل": "Pick at least one bank", "تسجيل الخروج": "Log out", "ننتظر موافقتك من تطبيق البنك…": "Waiting for your approval in the bank app…",
    "نكتشف التزاماتك واشتراكاتك ونصنف مصاريفك…": "Finding your commitments and subscriptions, sorting your spending…",
    "أكّد كل وحدة بضغطة. لو فيه شي غلط، عدّله من صفحة الالتزامات.": "Confirm each one with a tap. If something's wrong, edit it from Commitments.",
    "صح": "Correct", "مؤكد": "Confirmed", "تمام، ودّني للرئيسية": "Done, take me home",
    "المصروفات": "Spending", "الالتزامات": "Commitments", "الرئيسية": "Home", "المخطط": "Planner", "حسابي": "Account",
    "قائمة الأمنيات": "Wishlist", "الباقات": "Plans", "الراتب اليوم": "Payday today",
    "باقي لك": "Left to spend", "تعدّيت بـ": "Over by", "دفعت هالشهر": "Paid this month", "المعيشة هالشهر": "Living costs this month",
    "التزاماتك هالشهر": "This month's commitments", "المعيشة": "Living costs", "سدّدت كل التزامات هالشهر ✓": "All of this month's commitments are paid ✓",
    "مثل المعتاد بالضبط": "Exactly your usual", "قبل الراتب": "Before payday", "الدفعة الجاية": "Next payment", "ما عليك شي": "Nothing due",
    "ولا دفعة": "No payments", "خبر حلو": "Good news", "خبر حلو:": "Good news:", "التزاماتك": "Your commitments", "شهرياً": "per month",
    "مصروفاتك هالشهر": "Your spending this month", "عرض الكل": "See all", "ما فيه مصروفات شخصية هالشهر للحين.": "No personal spending this month yet.",
    "كيف نحسب «باقي لك»": "How “left to spend” is calculated", "الراتب": "Salary", "الالتزامات والاشتراكات": "Commitments & subscriptions",
    "المعيشة (متوسط آخر 3 شهور)": "Living costs (3-month average)", "هامش الأمان": "Safety buffer", "تقدر تصرف هالشهر": "You can spend this month",
    "صرفك الشخصي هالشهر": "Your personal spending this month", "أضف مصروف": "Add expense", "حسب الفئة": "By category",
    "المعيشة (بقالة، وقود، فواتير…) والاشتراكات محسوبة ضمن «الالتزامات».": "Living costs (groceries, fuel, bills…) and subscriptions are counted under “Commitments”.",
    "عمليات هالشهر": "This month's transactions", "الكل": "All",
    "اضغط على أي عملية من البنك عشان تغيّر تصنيفها، ونتذكره للمرات الجاية.": "Tap any bank transaction to change its category. We'll remember it next time.",
    "ما فيه مصروفات هالشهر للحين.": "No spending this month yet.", "وش اشتريت؟": "What did you buy?", "مثال: قهوة": "e.g. coffee",
    "المبلغ (ر.س)": "Amount (SAR)", "التصنيف": "Category", "أضف": "Add", "اكتب المبلغ صح.": "Enter a valid amount.",
    "انضاف المصروف، و«تقدر تصرف» اتحدّث.": "Expense added, and “left to spend” is updated.", "حذفنا المصروف.": "Expense deleted.",
    "التزاماتك الشهرية": "Your monthly commitments", "الالتزامات والإيجار": "Commitments & rent", "الاشتراكات": "Subscriptions",
    "ادفع الكل": "Pay all", "ما عليك دفعات تدفعها من هنا هالشهر.": "Nothing to pay from here this month.",
    "الالتزامات الحالية": "Current", "المدفوعات السابقة": "Previous payments", "تسدّد هالشهر": "Paid this month", "متأخر": "Late",
    "التزام شهري ثابت": "Fixed monthly commitment", "ينسحب تلقائي من البنك": "Taken automatically by the bank", "أكّد": "Confirm", "حذف": "Delete",
    "ما فيه التزامات نشطة.": "No active commitments.", "أضف التزام فاته الربط": "Add a commitment we missed", "متوسط آخر 3 شهور": "3-month average",
    "الفواتير الشهرية": "Monthly bills", "الفواتير داخل متوسط المعيشة، ما نحسبها مرتين.": "Bills are inside the living-costs average, so they're not counted twice.",
    "اشتراكاتك": "Your subscriptions", "نذكّرك قبل كل تجديد، عشان ما تتجدد اشتراكات ما تستخدمها.": "We remind you before every renewal, so you don't renew subscriptions you don't use.",
    "ذكّرني قبل التجديد": "Remind me before renewal", "ناوي ألغيه": "I plan to cancel", "تراجعت، بخليه": "Never mind, keep it",
    "ألغيته خلاص": "I cancelled it", "ألغيته": "Cancelled", "مكتمل": "Completed", "إدارة الاشتراك": "Manage subscription",
    "لما يخلص أي التزام بينتقل هنا تلقائياً.": "Finished commitments move here automatically.",
    "أضف التزام": "Add commitment", "مثال: تمويل أثاث": "e.g. furniture finance", "المبلغ الشهري (ر.س)": "Monthly amount (SAR)",
    "يوم السداد (1 إلى 28)": "Due day (1 to 28)", "كم دفعة باقية؟ (اتركه فاضي لو مستمر)": "Payments left? (leave empty if ongoing)",
    "النوع": "Type", "تمويل": "Finance", "تقسيط (تمارا، تابي)": "Installments (Tamara, Tabby)", "شهري ثابت (إيجار، اشتراك)": "Fixed monthly (rent, subscription)",
    "حفظ": "Save", "تأكد من المبلغ، ويوم السداد من 1 إلى 28.": "Check the amount, and the due day must be 1 to 28.",
    "انضاف الالتزام، و«تقدر تصرف» اتحدّث.": "Commitment added, and “left to spend” is updated.", "أكدنا الالتزام.": "Commitment confirmed.",
    "نحذف هالالتزام من مُدار؟ هذا ما يلغيه عند الجهة.": "Remove this commitment from Mudar? It won't cancel it with the provider.",
    "ما فيه دفعات تقدر تدفعها من هنا هالشهر.": "No payments you can make from here this month.", "تنسحب تلقائي من البنك": "Taken automatically by the bank",
    "تدفعها من الجهة": "Paid at the provider", "انسخ رقم السداد": "Copy SADAD number",
    "الدفع يتم من حسابك البنكي مباشرة للجهات. مُدار ما يمسك فلوسك.": "Payments go straight from your bank account to each provider. Mudar never holds your money.",
    "دفع تجريبي للعرض.": "Demo payment only.", "بننقلك لتطبيق البنك عشان توافق على الدفع…": "Taking you to your bank app to approve the payment…",
    "مُدار يطلب تحويل هالمبالغ من حسابك للجهات مباشرة:": "Mudar is requesting these transfers from your account directly to the providers:",
    "الإجمالي": "Total", "وافق": "Approve", "رفض": "Decline", "ما تم أي دفع.": "No payment was made.", "تم السداد": "Paid", "تمام": "Done",
    "نسخنا رقم السداد.": "SADAD number copied.",
    "قبل لا تشتري، نقارن لك التقسيط والتمويل والتحويش على وضعك الحقيقي، ونختار الأنسب.": "Before you buy, we compare installments, loans and saving up on your real numbers, and pick the best fit.",
    "وش تبي تشتري؟": "What do you want to buy?", "السعر (ر.س)": "Price (SAR)", "بكم شهر تبي تجمعه؟": "Save it over how many months?", "اختياري": "Optional",
    "اكتب السعر عشان نقارن.": "Enter a price to compare.", "الأنسب لك": "Best for you", "يناسبك الحين": "Fits now", "ما يناسب ميزانيتك": "Doesn't fit your budget",
    "كم ينخصم كل شهر": "Monthly payment", "اللي ترجعه كامل": "Total you repay", "في أضيق شهر": "In your tightest month", "متى تبدأ": "Starts",
    "القسط الشهري": "Monthly payment", "نسبة الربح (ثابتة سنوياً)": "Profit rate (flat, yearly)", "الربح الكلي": "Total profit", "الرسوم الإدارية": "Admin fee",
    "التكلفة السنوية الفعلية": "APR (true yearly cost)", "ديونك بعده": "Your debts after", "تمويل شخصي بنكي": "Bank personal finance", "شركة تمويل": "Finance company",
    "اختر هذا": "Choose this", "التقسيط": "Installments", "التمويل الشخصي (بنوك وشركات تمويل)": "Personal finance (banks & finance companies)",
    "إخفاء الخيارات الثانية": "Hide other options", "ما فيه تقسيط أو تمويل يناسب ميزانيتك الحين. «تجمع أول» هو الخيار الآمن.": "No installment or loan fits your budget right now. “Save first” is the safe choice.",
    "بدون ديون": "No debt", "تحوّش هالشهر": "Save this month", "بعدها كل شهر": "Then each month", "متى تقدر تشتريه": "When you can buy it",
    "التكلفة الكلية": "Total cost", "بدون أي رسوم": "with no fees", "حد الادخار": "savings limit", "أضف للأمنيات بطريقة «تجمع أول»": "Add to wishlist as “Save first”",
    "ما توصل لهدفك بهالمدة.": "You won't reach your goal in that time.", "الحل:": "Options:", "تمدد المدة": "extend the time",
    "أرقام الجهات تجريبية للتوضيح، والحسابات حقيقية على بياناتك. العروض الفعلية تجي من الجهات بعد الشراكة.": "Provider rates are samples for illustration; the calculations run on your real data. Real offers come from providers after partnership.",
    "هذي معلومات، مو استشارة مالية.": "This is information, not financial advice.",
    "الحساب الذكي مو ضمن باقتك": "Smart account isn't in your plan", "تعرف كم بيبقى لك بالشهور الجاية ومتى تقدر تشتري.": "See what's left in the coming months and when you can buy.",
    "شوف الباقات": "See plans", "توقعاتك لـ 12 شهر": "Your 12-month forecast", "الحساب الذكي: الشهور الجاية": "Smart account: coming months",
    "اكتب السعر أول.": "Enter a price first.", "اختر طريقة أول.": "Choose an option first.",
    "نذكّرك أول ما يصير الشي مناسب لك.": "We'll remind you as soon as it fits your budget.", "جمعت المبلغ، مناسب الحين": "Saved up, fits now",
    "مناسب لك الحين": "Fits you now", "ما يناسب بهالطريقة، جرّب «تجمع أول»": "Doesn't fit this way, try “Save first”", "قارن طرق الشراء": "Compare ways to pay",
    "قائمتك فاضية. خطط لأي شي تبيه من «المخطط» وضيفه هنا.": "Your list is empty. Plan anything you want in “Planner” and add it here.", "روح للمخطط": "Go to Planner",
    "انتقل للشهر الجاي": "Skip to next month", "زر للديمو بس، عشان نوري التذكير بدون ما ننتظر شهر.": "Demo-only button, to show reminders without waiting a month.",
    "نزل راتبك": "Salary received", "صار مناسب لك": "now fits your budget",
    "يوم الراتب": "Payday", "حساباتك البنكية": "Your bank accounts", "اربط بنك": "Connect bank", "فصل": "Disconnect", "باقتك الحالية": "Your current plan",
    "مجانية": "Free", "توزيع راتبك": "Your salary split", "عدّل الأهداف": "Edit targets", "الرقم الأول اللي صار فعلاً هالشهر، والثاني هدفك.": "First number is what happened this month; the second is your target.",
    "المظهر": "Appearance", "فاتح": "Light", "داكن": "Dark", "حسب الجهاز": "System", "تواصل معنا": "Contact us", "الإيميل": "Email", "واتساب": "WhatsApp",
    "اسمك": "Your name", "رسالتك": "Your message", "أرسل": "Send", "وصلتنا رسالتك، بنرد عليك قريب.": "We got your message and will reply soon.",
    "خصوصيتك": "Your privacy", "مصاريفك ما تطلع لأي جهة.": "Your spending is never shared.", "المساعد الذكي يشوف إجماليات بس، مو عملياتك.": "The assistant only sees totals, not your transactions.",
    "ما نربح من الرسوم المتأخرة، وما نشجعك على التزامات جديدة.": "We don't profit from late fees, and we don't push you into new debt.",
    "أدوات الديمو": "Demo tools", "ابدأ الديمو من جديد": "Restart the demo", "إلغاء الموافقة وحذف بياناتي": "Revoke consent and delete my data",
    "أهداف توزيع راتبك": "Salary split targets", "الأساسيات (الالتزامات والمعيشة)": "Essentials (commitments & living costs)",
    "المجموع لازم يكون 100%.": "The total must be 100%.", "نسبة الادخار هي الحد الأعلى لـ«تجمع أول» كل شهر.": "The savings share is the monthly cap for “Save first”.",
    "مجموع النسب لازم يكون 100%.": "The shares must add up to 100%.", "حفظنا أهدافك.": "Targets saved.",
    "كل اللي تحتاجه عشان تعرف وضعك موجود في الأساسية. الباقات الثانية تضيف مزايا.": "Everything you need to see where you stand is in Basic. Other plans add extras.",
    "ترقية": "Upgrade", "انتقل لها": "Switch", "مقارنة سريعة": "Quick comparison", "الالتزامات المعروضة": "Commitments shown", "بلا حد": "Unlimited",
    "الحساب الذكي": "Smart account", "محاكاة الالتزامات المحدثة": "Commitment simulation", "محاكاة التوقعات المالية": "Financial forecast",
    "السعر": "Price", "مجاناً": "Free", "تبديل الباقة (للديمو)": "Switch plan (demo)", "بدون دفع، عشان تشوف الفرق بين الباقات.": "No payment, just to see the difference between plans.",
    "بدّلنا الباقة.": "Plan switched.", "قريباً.": "Coming soon.",
    "اربط بنك ثاني": "Connect another bank", "نقرأ عملياته بنفس الموافقة (قراءة فقط)، ونضيف التزاماته واشتراكاته لصورتك الكاملة.": "We read its transactions with the same read-only consent and add its commitments and subscriptions to your full picture.",
    "ربطت كل البنوك المتاحة بالديمو.": "You've connected every demo bank.", "نربط…": "Connecting…", "ما لقينا التزامات جديدة.": "No new commitments found.",
    "فصلنا آخر بنك وحذفنا بياناتك.": "Disconnected your last bank and deleted your data.", "ألغينا الموافقة وحذفنا بياناتك.": "Consent revoked and your data deleted.",
    "تأكيد قبل التعديل": "Confirm before changing", "تم.": "Done.", "انلغى.": "Cancelled.", "إلغاء": "Cancel", "تم التعديل.": "Updated.",
    "اكتب رسالتك…": "Type your message…", "لحظة، أحسب…": "One moment, calculating…", "إرسال": "Send", "إغلاق": "Close",
    "أقدر آخذ جوال بـ 3000 على 4 دفعات؟": "Can I get a 3000 phone in 4 payments?", "طيب متى أقدر؟": "OK, when can I?",
    "حط الجوال بالأمنيات": "Add the phone to my wishlist", "كم عليّ هالشهر؟": "How much do I owe this month?", "ضيف مصروف قهوة 20": "Add a coffee expense 20",
    "تمام، بنذكّرك قبل التجديد عشان تلغيه.": "OK, we'll remind you before renewal so you can cancel.", "تمام، خليناه.": "OK, kept.",
    "بنذكّرك قبل التجديد.": "We'll remind you before renewal.", "وقفنا التذكير لهالاشتراك.": "Reminder turned off for this subscription.",
    "تمام، هالالتزام ينسحب تلقائي وما ينحسب بـ«ادفع الكل».": "OK, this one is taken automatically and won't be in “Pay all”.",
    "تمام، تقدر تدفعه من «ادفع الكل».": "OK, you can pay it from “Pay all”.",
    "بنبدأ الديمو من جديد ونمسح البيانات الحالية. تبي نكمل؟": "We'll restart the demo and clear the current data. Continue?",
    "متأكد؟ بنلغي الموافقة ونحذف عملياتك والتزاماتك.": "Are you sure? We'll revoke consent and delete your transactions and commitments.",
    "فيه مشكلة بالاتصال، جرّب مرة ثانية.": "Connection problem, try again.", "صار شي غلط، جرّب مرة ثانية.": "Something went wrong, try again.",
    "تأكد من البيانات المدخلة.": "Check what you entered.", "حلو!": "Nice!",
    /* backend messages */
    "المتبقي يشمل هامش الأمان. الادخار يوضح الإيداعات المسجلة هالشهر، مو مجموع الأمنيات.": "“Left over” includes the safety buffer. Savings shows deposits recorded this month, not wishlist totals.",
    "ما يناسب ميزانيتك ضمن المدة اللي حسبناها.": "Doesn't fit your budget within the period we checked.",
    "التقسيط المتاح عندنا لين 10,000 ر.س، ومبلغك أعلى.": "Installments here go up to 10,000 SAR, and your amount is higher.",
    "القسط يخلّي نسبة ديونك فوق 33% من راتبك، فغالباً ما ينقبل.": "This payment pushes your debts above 33% of your salary, so it would likely be declined.",
    "القسط أعلى من اللي يتبقى لك كل شهر.": "The payment is more than what you have left each month.",
    "ترقّ عشان تعرف متى تقدر تشتريه": "Upgrade to see when you can buy it",
    "نفترض نفس الراتب ومتوسط المعيشة، وبدون صرف شخصي جديد بالشهور الجاية. هذي توقعات مو ضمان.": "Assumes the same salary and average living costs, with no new personal spending. A forecast, not a guarantee.",
    "التزامات بلا حد": "Unlimited commitments", "بدون الحساب الذكي": "No smart account", "بدون محاكاة الالتزامات المحدثة": "No commitment simulation",
    "محاكاة التوقعات المالية للعميل": "Personal financial forecast", "بدون محاكاة التوقعات المالية": "No financial forecast",
    "الدفع يحتاج شراكة مع الجهات وترخيص.": "Payments need provider partnerships and a licence.", "اختر دفعة وحدة على الأقل.": "Choose at least one payment.",
    "فيه دفعة ما تقدر تدفعها من هنا (تلقائية، مدفوعة، أو مو لك).": "One of these can't be paid here (automatic, already paid, or not yours).",
    "الاشتراك مو موجود.": "Subscription not found.", "هذا مو اشتراك.": "This isn't a subscription.", "اختر تصنيف من القائمة.": "Pick a category from the list.",
    "الجلسة انتهت، سجّل دخول من جديد.": "Session expired, log in again.", "لازم تسجل دخول.": "Please log in.", "طلبات كثيرة، جرب بعد دقيقة.": "Too many requests, try in a minute.",
    "طلبات كثيرة، جرّب بعد دقيقة.": "Too many requests, try in a minute.", "اربط حسابك البنكي أول.": "Connect your bank first.", "المسار غير متاح.": "Not available.",
    "لازم توافق على الشروط وسياسة الخصوصية.": "You need to accept the terms and privacy policy.", "الخطة غير موجودة.": "Plan not found.", "ما فيه شي نعدّله.": "Nothing to update.",
    "الالتزام مو موجود.": "Commitment not found.", "ربط بنك ثاني يحتاج مزود مصرفية مفتوحة مرخص.": "Connecting another bank needs a licensed open banking provider.",
    "المصروف اليدوي غير موجود.": "Manual expense not found.", "العنصر غير موجود.": "Item not found.", "مجموع نسب توزيع راتبك لازم يكون 100%.": "Your salary split must add up to 100%.",
    "خلصت أسئلتك المجانية هالشهر. تتجدد الشهر الجاي، وباقي مزايا مُدار متاحة لك.": "You've used this month's free questions. They renew next month, and the rest of Mudar is still yours.",
    "جرّب بعد 15 دقيقة.": "Try again in 15 minutes.", "اكتب رقم جوال سعودي صحيح يبدأ بـ 05.": "Enter a valid Saudi mobile number starting with 05.",
    "إرسال الرسائل يحتاج مزود SMS.": "Sending texts needs an SMS provider.", "الرقم مسجل، سجّل دخول.": "This number is registered, please log in.",
    "أرسلنا لك رمز التحقق.": "We sent you a verification code.", "إذا الرقم مسجل بيوصلك رمز.": "If the number is registered you'll get a code.",
    "اطلب رمز جديد.": "Request a new code.", "انتهى الرمز، اطلب واحد جديد.": "The code expired, request a new one.", "الرمز غلط.": "Wrong code.",
    "هالبنك مربوط من قبل.": "This bank is already connected.", "هالبنك مو مربوط.": "This bank isn't connected.",
    "الخطة مسدّدة بالكامل، ما تقدر تعيد فتحها.": "This plan is fully paid and can't be reopened.",
    "الأداة مو متاحة.": "Tool not available.", "تأكد من البيانات قبل ما نكمل.": "Check the details before we continue.", "حدد المبلغ أو عدد الدفعات.": "Set the amount or the number of payments.",
    "الأمنية مو موجودة.": "Wishlist item not found.", "الطلب مو موجود.": "Request not found.", "الطلب انتهى أو تأكد أو انلغى قبل كذا.": "This request already expired, was confirmed, or was cancelled.",
    "افتح تمارا": "Open Tamara", "افتح تابي": "Open Tabby", "افتح تطبيق البنك": "Open bank app", "تحقق": "Verify",
    "الشهر الجاي، بعد ما ينزل راتبك يوم 27 وتخلص خطة تابي.": "Next month, after your salary on the 27th and once Tabby ends.",
    "تم. بذكّرك أول ما يصير مناسب 👍": "Done. I'll remind you as soon as it fits 👍"
  };

  /* ---------- sentence patterns (numbers N, money M, names X) ---------- */
  const N = "([\\d,.]+)";
  const R = [
    [/^هلا (.*)! أنا مساعد مُدار\. اسألني عن التزاماتك، مصاريفك، أو أي شي تفكر تشتريه\.$/, m => `Hi ${name(m[1])}! I'm Mudar's assistant. Ask me about your commitments, your spending, or anything you're thinking of buying.`],
    [/^الراتب بعد (.+)$/, m => `Payday in ${days(m[1])}`],
    [/^هلا (.*)$/, m => `Hi ${name(m[1])}`],
    [/^الرقم (\d+)$/, m => `Digit ${m[1]}`],
    [/^موقع (.+)$/, m => `${name(m[1])} website`],
    [/^عندك (\d+) دفعة متأخرة، سدّدها ترجع لك النقاط\.$/, m => `You have ${m[1]} late payment(s); pay to get the points back.`],
    [/^خلك تحت ([\d,]+) ر\.س شخصي هالشهر، وما تتعدى «باقي لك»\.$/, m => `Keep personal spending under ${m[1]} SAR this month, and don't go below “left to spend”.`],
    [/^التزاماتك (\d+)% من راتبك وهدفك (\d+)%\.$/, m => `Your commitments are ${m[1]}% of your salary; your target is ${m[2]}%.`],
    [/^ديونك (\d+)% من راتبك\.$/, m => `Your debts are ${m[1]}% of your salary.`],
    [/^حوّشت ([\d,]+) ر\.س الشهر اللي فات من ([\d,]+) ممكنة\.$/, m => `You saved ${m[1]} SAR last month out of ${m[2]} possible.`],
    [/^حوّش ([\d,]+) ر\.س هالشهر \(من «تجمع أول»\) وتاخذ النقاط كاملة\.$/, m => `Save ${m[1]} SAR this month (with “Save first”) to get full points.`],
    [/^تقييمك (\d+) من 100 · نقاطك ([\d,]+)$/, m => `Score ${m[1]} of 100 · Points ${m[2]}`],
    [/^باقتك (.+): مستخدم (\d+) من (\d+) التزامات(?:، تقدر تضيف (التزام واحد|التزامين|\d+ التزامات))?\.$/, m => `Your ${name(m[1])} plan: ${m[2]} of ${m[3]} commitments used${m[4] ? `, you can add ${m[4] === "التزام واحد" ? "1 more" : m[4] === "التزامين" ? "2 more" : m[4].replace(/\D/g, "") + " more"}` : ""}.`],
    [/^وصلت حد باقتك \((\d+) التزامات\)\. ترقّ عشان تضيف أكثر\.$/, m => `You've reached your plan's limit (${m[1]} commitments). Upgrade to add more.`],
    [/^مستخدم (\d+) من (\d+) التزامات في باقتك الحالية\.$/, m => `${m[1]} of ${m[2]} commitments used in your current plan.`],
    [/^كل اللي في (.+)، وزيادة:$/, m => `Everything in ${name(m[1])}, plus:`],
    [/^أسئلة المساعد: باقي (\d+) من (\d+) هالشهر$/, m => `Assistant questions: ${m[1]} of ${m[2]} left this month`],
    [/^(.+) مو ضمن باقتك الحالية\. تقدر تستخدمه بباقة (.+) من «حسابي ← الباقات»\.$/, m => `${name(m[1])} isn't in your current plan. It's included in ${name(m[2])} (Account → Plans).`],
    [/^خلصت أسئلة المساعد في باقتك هالشهر \((\d+)\)\. تتجدد الشهر الجاي، أو ترقّ لباقة فيها أسئلة أكثر\.$/, m => `You've used this month's ${m[1]} assistant questions. They renew next month, or upgrade for more.`],
    [/^قائمة الأمنيات \((\d+)\)$/, m => `Wishlist (${m[1]})`],
    [/^(.+) تخلص هالشهر، يعني يرجع لك$/, m => `${name(m[1])} ends this month, so you get back`],
    [/^(\d+) من كل شهر$/, m => `Day ${m[1]} of every month`],
    [/^(✓|✕) (.+)$/, m => `${m[1]} ${tr(m[2])}`],
    [/^ينسحب تلقائي يوم (\d+)، ما يحتاج تدفعه$/, m => `Taken automatically on day ${m[1]}, nothing to pay`],
    [/^من راتبك\. الحد المتبع في التمويل الاستهلاكي ([\d.]+)%، يعني تقدر تضيف قسط لين$/, m => `of your salary. The usual consumer-finance limit is ${m[1]}%, so you can add a payment of up to about`],
    [/^(.+) صار مناسب لك\. بـ(.*) يبقى لك$/, m => `${name(m[1])} now fits your budget. ${m[2].trim() ? `With ${tr(m[2])} you'd` : "You'd"} keep`],
    [new RegExp(`^لقينا ${N} التزامات$`), m => `We found ${m[1]} commitments`],
    [/^لقينا (التزام واحد|التزامين)$/, m => `We found ${m[1] === "التزامين" ? "2 commitments" : "1 commitment"}`],
    [new RegExp(`^وافق من تطبيق البنك \\(${N}\\)$`), m => `Approve in bank app (${m[1]})`],
    [/^نربط (.+)…$/, m => `Connecting ${name(m[1])}…`],
    [new RegExp(`^إعادة الإرسال بعد$`), () => "Resend in"],
    [/^ثانية$/, () => "seconds"],
    [/^عليك (.+) هالشهر$/, m => `You have ${count(m[1])} due this month`],
    [new RegExp(`^ادفع الكل · ${N} ر\\.س$`), m => `Pay all · ${m[1]} SAR`],
    [new RegExp(`^ادفع · ${N} ر\\.س$`), m => `Pay · ${m[1]} SAR`],
    [/^يوم (\d+) من كل شهر$/, m => `Day ${m[1]} of every month`],
    [/^يوم (\d+)$/, m => `Day ${m[1]}`],
    [/^المدفوع: (\d+) من (\d+)$/, m => `Paid: ${m[1]} of ${m[2]}`],
    [/^باقي (.+)$/, m => `${count(m[1])} left`],
    [/^خلّصت (.+)$/, m => `Finished ${count(m[1])}`],
    [new RegExp(`^ألغيته(?: يوم ([\\d-]+))?، توفّر$`), m => `Cancelled${m[1] ? ` on ${m[1]}` : ""}, saving`],
    [/^مجموع اللي دفعته:$/, () => "Total you paid:"],
    [/^يتجدد (.+) \(يوم (\d+)\)$/, m => `Renews ${when(m[1])} (day ${m[2]})`],
    [/^انخصم هالشهر يوم (\d+)، يتجدد الشهر الجاي$/, m => `Charged this month on day ${m[1]}, renews next month`],
    [/^ناوي تلغيه؟ ألغه من موقع الجهة (.+) عشان ما ينخصم مرة ثانية\.$/, m => `Planning to cancel? Cancel on the provider's site ${m[1] === "قبل التجديد الجاي" ? "before the next renewal" : m[1].replace(/^قبل يوم (\d+)$/, "before day $1").replace(/^قبل بكرة$/, "before tomorrow")} so you're not charged again.`],
    [/^يتجدد (.+)$/, m => `Renews ${when(m[1])}`],
    [/^، ألغه لو ما تبيه$/, () => ", cancel if you don't need it"],
    [/^(.+) تخلص$/, m => `${name(m[1])} ends`],
    [/^دفعة (.+)$/, m => `${name(m[1])} payment`],
    [/^(.+)، (اليوم|بكرة|بعد .+)$/, m => `${name(m[1])}, ${when(m[2])}`],
    [new RegExp(`^التزاماتك ${N}% من راتبك، أعلى من هدفك ${N}%$`), m => `Your commitments are ${m[1]}% of your salary, above your ${m[2]}% target`],
    [new RegExp(`^صرفك الشخصي تعدّى ${N}% من راتبك هالشهر$`), m => `Your personal spending is over ${m[1]}% of your salary this month`],
    [new RegExp(`^انتبه، وصلت ${N}% من حد صرفك الشخصي هالشهر\\.$`), m => `Heads up: you've reached ${m[1]}% of your personal spending limit this month.`],
    [new RegExp(`^صرفت ${N}% من اللي تقدر تصرفه، والراتب (.+)\\.$`), m => `You've spent ${m[1]}% of what you can spend, and payday is ${when(m[2])}.`],
    [new RegExp(`^ما توصل لهدفك بهالمدة\\. تقدر تجمع ${N} ر\\.س\\.$`), m => `You won't reach your goal in that time. You can save ${m[1]} SAR.`],
    [new RegExp(`^التقسيط يبدأ من ${N} ر\\.س\\.$`), m => `Installments start from ${m[1]} SAR.`],
    [new RegExp(`^التمويل الشخصي يبدأ عادة من ${N} ر\\.س، ومبلغك أقل، فما نعرضه\\.$`), m => `Personal finance usually starts from ${m[1]} SAR. Your amount is lower, so we don't show it.`],
    [new RegExp(`^المبلغ أعلى من حد التمويل الشخصي اللي نعرضه \\(${N} ر\\.س\\)\\.$`), m => `The amount is above the personal finance limit we show (${m[1]} SAR).`],
    [new RegExp(`^أقصر مدة تناسب ميزانيتك \\((.+)\\)، وتدفع ${N} ر\\.س فوق المبلغ\\.$`), m => `The shortest term that fits your budget (${name(m[1])}); you pay ${m[2]} SAR on top.`],
    [/^يبدأ (.+)، وتكلفته أقل من الخيارات اللي تناسب نفس الوقت\.$/, m => `Starts ${when(m[1])}, and costs less than other options that fit the same time.`],
    [/^(.+) مو ضمن باقتك الحالية\. ترقّ عشان تستخدمه\.$/, m => `${name(m[1])} isn't in your current plan. Upgrade to use it.`],
    [/^ترقّ عشان تشوف (\d+) التزامات$/, m => `Upgrade to see ${m[1]} more commitments`],
    [/^باقتك تسمح بـ (\d+) التزامات\. ترقّ عشان تضيف التزام ثاني\.$/, m => `Your plan allows ${m[1]} commitments. Upgrade to add another.`],
    [/^هالالتزام خارج حد باقتك\. ترقّ عشان تشوفه وتعدّله\.$/, () => "This commitment is outside your plan's limit. Upgrade to see and edit it."],
    [/^(\d+) التزامات$/, m => `${m[1]} commitments`],
    [/^ادفع عند (.+)$/, m => `Pay at ${name(m[1])}`],
    [/^تمويل (.+)، (.+)$/, m => `${name(m[1])} loan, ${name(m[2])}`],
    [/^(\d+) شهر$/, m => `${m[1]} months`],
    [/^(\d+) × /, m => `${m[1]} × `],
    [/^تقسيط · (.+)$/, m => `Installments · ${tr(m[1])}`],
    [/^(\d+) دفعات، بدون رسوم$/, m => `${m[1]} payments, no fees`],
    [/^(\d+) شهور، رسوم (\d+)%$/, m => `${m[1]} months, ${m[2]}% fee`],
    [/^نسبة الديون فوق (\d+)%$/, m => `Debts above ${m[1]}%`],
    [/^يناسبك (.+)$/, m => `Fits ${when(m[1])}`],
    [/^يصير مناسب (.+)$/, m => `Fits ${when(m[1])}`],
    [/^توصل للمبلغ (.+)$/, m => `You'll have it ${when(m[1])}`],
    [/^توصل لهدفك خلال (.+)\.$/, m => `You'll reach your goal within ${count(m[1])}.`],
    [/^خلها (.+)$/, m => `Make it ${count(m[1])}`],
    [/^خلّ الهدف ([\d,]+)$/, m => `Set goal to ${m[1]}`],
    [/^قارن كل الخيارات \((\d+)\)$/, m => `Compare all options (${m[1]})`],
    [/^أضف للأمنيات \((.+)\)$/, m => `Add to wishlist (${tr(m[1])})`],
    [/^(.+): تحوّش$/, m => `${when(m[1])}: save`],
    [/^الحل: تمدد المدة لـ (.+)، أو تخفّض الهدف لـ$/, m => `Options: extend to ${count(m[1])}, or lower the goal to`],
    [/^التزامات ([\d,]+)، معيشة ([\d,]+)$/, m => `Commitments ${m[1]}, living ${m[2]}`],
    [/^حدك (\d+)% من راتبك =$/, m => `Your limit: ${m[1]}% of salary =`],
    [/^من (كل حساباتك البنكية|حسابك البنكي)، وتقدر تضيف يدوي\.$/, m => `From ${m[1] === "حسابك البنكي" ? "your bank account" : "all your bank accounts"}. You can also add manually.`],
    [/^من (بنكين|\d+ بنوك) مربوطة\.$/, m => `From ${m[1] === "بنكين" ? "2" : m[1].replace(/\D/g, "")} connected banks.`],
    [/^(\d[\d,]*) عملية · الموافقة لين$/, m => `${m[1]} transactions · consent until`],
    [/^ربطنا (.+)\.$/, m => `Connected ${name(m[1])}.`],
    [/^لقينا (اشتراك واحد|اشتراكين|\d+ اشتراكات|\d+ التزامات) جديدة\.$/, m => `Found ${m[1] === "اشتراك واحد" ? "1 new subscription" : m[1] === "اشتراكين" ? "2 new subscriptions" : m[1].replace(/(\d+) اشتراكات/, "$1 new subscriptions").replace(/(\d+) التزامات/, "$1 new commitments")}.`],
    [/^فصلنا (.+)\.$/, m => `Disconnected ${name(m[1])}.`],
    [/^نفصل (.+) ونحذف عملياته من مُدار؟$/, m => `Disconnect ${name(m[1])} and delete its transactions from Mudar?`],
    [/^ألغيت (.+) من موقع الجهة؟ بنشيله من التزاماتك\.$/, m => `Did you cancel ${name(m[1])} on the provider's site? We'll remove it from your commitments.`],
    [/^وفّرت$/, () => "You save"],
    [/^تم التحويل لـ(.+)$/, m => `Sent to ${name(m[1])}`],
    [/^انضاف (.+) للأمنيات \((.+)\)\. بنذكّرك أول ما يصير مناسب\.$/, m => `${name(m[1])} added to your wishlist (${tr(m[2])}). We'll remind you when it fits.`],
    [/^خلص التزام (.+)\.$/, m => `${name(m[1])} is finished.`],
    [/^يرجع لك$/, () => "You get back"],
    [/^كل شهر، وانتقل للمدفوعات السابقة\.$/, () => "every month. It moved to previous payments."],
    [/^(.+) صار مناسب لك$/, m => `${name(m[1])} now fits your budget`],
    [/^\. بـ(.+) يبقى لك$/, m => `. With ${tr(m[1])} you'll keep`],
    [/^تمام، عمليات (.+) الجاية بتنحط في (.+)\.$/, m => `OK, future ${m[1]} transactions will go under ${name(m[2])}.`],
    [/^تصنيف (.+)$/, m => `Category: ${m[1]}`],
    [/^المجموع (\d+)%(.*)$/, m => `Total ${m[1]}%${m[2].includes("✓") ? " ✓" : ", must be 100%."}`],
    [/^دفعت تقريباً$/, () => "You paid about"],
    [/^ديونك الحالية$/, () => "Your current debts"],
    [/^شهرياً =$/, () => "a month ="],
    [/^من راتبك\. الحد المتبع في التمويل الاستهلاكي$/, () => "of your salary. The usual consumer-finance limit is"],
    [/^، يعني تقدر تضيف قسط لين$/, () => ", so you can add a payment of up to about"],
    [/^تقريباً\.$/, () => "."],
    [/^نضيف مصروف «(.+)» بـ ([\d.,]+) ر\.س، بتصنيف (.+)؟$/, m => `Add an expense “${m[1]}” for ${m[2]} SAR, category ${name(m[3])}?`],
    [/^نحط «(.+)» بـ ([\d.,]+) ر\.س بالأمنيات، بطريقة (.+)؟$/, m => `Add “${m[1]}” for ${m[2]} SAR to the wishlist, as ${tr(m[3])}?`],
    [/^نضيف «(.+)» بـ ([\d.,]+) ر\.س، يوم (\d+)(?:، باقي (.+)|، التزام مستمر)?؟$/, m => `Add “${m[1]}” for ${m[2]} SAR on day ${m[3]}${m[4] ? `, ${count(m[4])} left` : ", ongoing"}?`],
    [/^نحذف التزام «(.+)» من مُدار؟ هذا ما يلغي الدين عند الجهة\.$/, m => `Remove “${name(m[1])}” from Mudar? It doesn't cancel the debt with the provider.`],
    [/^نشيل «(.+)» من الأمنيات؟$/, m => `Remove “${name(m[1])}” from the wishlist?`],
    [/^نعدّل تصنيف كل عمليات «(.+)» إلى (.+)؟$/, m => `Change the category of all “${m[1]}” transactions to ${name(m[2])}?`],
    [/^أعلى من العادة بـ$/, () => "Above usual by"], [/^أقل من المعتاد بـ$/, () => "Below usual by"], [/^للحين$/, () => "so far"],
    [/^باقي عليك$/, () => "Still due:"], [/^صرفت$/, () => "You spent"], [/^من مصروفك لهالشهر$/, () => "of your spending money this month"],
    [/^من حدك الشخصي$/, () => "of your personal limit"]
  ];

  /* ---------- fragment fallback ---------- */
  const F = Object.assign({}, NAMES, {
    "ر.س": "SAR", "ر.س من": "SAR of", "ر.س من متوسطك": "SAR of your usual", "ر.س شهرياً": "SAR / month", "من": "of", "لين": "up to",
    "بدون رسوم": "no fees", "رسوم": "fees", "شهرياً": "per month", "شهرياً.": "per month.", "يبقى لك": "you keep", "من راتبك": "of your salary",
    "من راتبك)": "of your salary)", "هدفك": "target", "بعد": "in", "قبل": "before", "يوم": "day", "الحين": "now", "حد الادخار)": "savings limit)",
    "بدون رسوم)": "no fees)", "رسوم)": "fees)", "، بحد أقصى 5,000)": ", max 5,000)", "1%": "1%", "فوق المبلغ": "on top", "شهر": "months",
    "دفعات": "payments", "دفعة": "payment", "شهور": "months", "أيام": "days"
  });
  const FRE = Object.keys(F).sort((a, b) => b.length - a.length)
    .map(k => [new RegExp(`(?<![\u0600-\u06FF])${k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\u0600-\u06FF])`, "g"), F[k]]);

  function days(s) {
    s = s.trim();
    if (s === "يوم واحد") return "1 day";
    if (s === "يومين") return "2 days";
    const m = s.match(/^(\d+) (أيام|يوم)$/);
    return m ? `${m[1]} days` : tr(s);
  }
  function count(s) {
    s = s.trim();
    const map = { "دفعة وحدة": "1 payment", "دفعتين": "2 payments", "يوم واحد": "1 day", "يومين": "2 days", "شهر واحد": "1 month", "شهرين": "2 months" };
    if (map[s]) return map[s];
    const m = s.match(/^(\d+) (دفعات|دفعة|أيام|يوم|شهور|شهر)$/);
    if (m) return `${m[1]} ${/دفع/.test(m[2]) ? "payments" : /يوم|أيام/.test(m[2]) ? "days" : "months"}`;
    return tr(s);
  }
  function when(s) {
    s = s.trim();
    if (NAMES[s]) return NAMES[s];
    let m = s.match(/^بعد (\d+) (شهور|شهر)$/); if (m) return `in ${m[1]} months`;
    m = s.match(/^بعد (.+)$/); if (m) return `in ${count(m[1])}`;
    return tr(s);
  }

  function tr(text, mid = false) {
    const cap = s => (mid ? s : s.charAt(0).toUpperCase() + s.slice(1));
    if (!text || !AR.test(text)) return text;
    const lead = text.match(/^\s*/)[0], trail = text.match(/\s*$/)[0];
    const core = text.trim();
    if (P[core]) return lead + P[core] + trail;
    if (NAMES[core]) return lead + NAMES[core] + trail;
    for (const [re, fn] of R) {
      const m = core.match(re);
      if (m) { const out = fn(m); if (out) return lead + cap(out) + trail; }
    }
    let out = core;
    for (const [re, en] of FRE) out = out.replace(re, en);
    out = out.replace(/،/g, ",").replace(/؟/g, "?").replace(/[«»]/g, "\"").replace(/\bin (\d+) payment\b/g, "in $1 payments")
      .replace(/(\d+) payment\b/g, (x, n) => n === "1" ? x : `${n} payments`).replace(/\s{2,}/g, " ");
    return lead + cap(out) + trail;
  }


  const SKIP = "script,style,textarea,input,.msg.user,[data-no-tr],.mark,.avatar";
  function translateNode(node) {
    if (lang !== "en") return;
    if (node.nodeType === 3) {
      const p = node.parentElement;
      if (!p || p.closest(SKIP) || !AR.test(node.nodeValue)) return;
      const t = tr(node.nodeValue, !!node.previousSibling && /\S/.test(node.previousSibling.textContent || ""));
      if (t !== node.nodeValue) node.nodeValue = t;
      return;
    }
    if (node.nodeType !== 1 || node.matches(SKIP)) return;
    for (const a of ["placeholder", "aria-label", "title"]) {
      const v = node.getAttribute && node.getAttribute(a);
      if (v && AR.test(v)) node.setAttribute(a, tr(v));
    }
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n = walker.nextNode();
    while (n) {
      if (n.nodeType === 1) {
        for (const a of ["placeholder", "aria-label", "title"]) {
          const v = n.getAttribute(a);
          if (v && AR.test(v)) n.setAttribute(a, tr(v));
        }
      } else translateNode(n);
      n = walker.nextNode();
    }
  }

  const observer = new MutationObserver(list => {
    if (lang !== "en") return;
    for (const m of list) {
      if (m.type === "characterData") translateNode(m.target);
      else m.addedNodes.forEach(translateNode);
    }
  });

  function apply() {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "en" ? "ltr" : "rtl";
    document.title = lang === "en" ? "Mudar" : "مُدار";
  }

  window.I18N = {
    get lang() { return lang; },
    tr,
    set(next) {
      lang = next === "en" ? "en" : "ar";
      try { localStorage.setItem("mudar_lang", lang); } catch (_) {}
      apply();
    },
    start() {
      apply();
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
      if (lang === "en") translateNode(document.body);
    }
  };
})();
