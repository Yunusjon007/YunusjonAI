# XAU Sniper Razgon — MetaTrader 5 (Exness) uchun oltin razgon EA

`XAU_Sniper_Razgon.mq5` — XAUUSD / XAUUSDc uchun avtomatik savdo dasturi (EA, "sovetnik").
U to'rtta timeframe'ni tekshiradi va hammasi bir tomonga qaraganda "sniper" kirish qiladi:
SL kichik, TP SL'dan 3 baravar uzoq, lot katta. Balans 4 baravar bo'lsa hamma pozitsiyani yopadi
va o'zini to'xtatadi.

> ⚠️ **Avval o'qing:** 1 haftada 4x — bu kafolat emas, bu lotereyaga yaqin natija.
> Pastdagi jadvalga qarang: 4x bo'lish ehtimolidan balansning yarmini yo'qotish ehtimoli ancha katta.
> Faqat yo'qotishga tayyor pulni qo'ying va avval Strategy Tester'da sinang.

## 1. Strategiya qanday ishlaydi

| Timeframe | Nima tekshiriladi |
|---|---|
| **D1** | Kechagi kunlik sham EMA50 dan trend tomonida yopilgan |
| **H4** | EMA50 > EMA200 → faqat BUY, EMA50 < EMA200 → faqat SELL |
| **H1** | Oxirgi 6 soatda narx EMA20 ga qaytib tekkan (arzon "zona"), lekin EMA50 dan buzilmagan |
| **M15** | Oxirgi yopilgan sham oldingi 4 sham cho'qqisidan yuqori (SELL da tubidan past) yopildi → **KIRISH** |

- **SL** — oxirgi 8 ta M15 shamning eng past nuqtasi ortida (SELL da eng baland nuqtasi ustida) + kichik zaxira.
- **TP** — SL masofasi × 3 (RR 1:3).
- **Lot** avtomatik hisoblanadi: SL urilsa balansning **33%** i ketadi, TP urilsa balans taxminan **+99%** (deyarli 2 baravar).
  Misol: balans 5000 USC → SL urilsa −1650 USC (≈ −16.5 $), TP urilsa ≈ +4950 USC (≈ +49.5 $).
- **Maqsad**: hisob equity'si boshlang'ich balansdan 4 baravar bo'lishi bilan (savdo o'rtasida bo'lsa ham)
  hamma pozitsiya yopiladi va EA to'xtaydi. Ikki ketma-ket TP deyarli 4x degani.
- Bir vaqtda faqat **1 ta** pozitsiya, kuniga ko'pi bilan **3 ta** savdo.
- Filtrlar: savdo faqat 07:00–20:00 server vaqtida (Exness = GMT, Toshkent vaqti bilan 12:00–01:00),
  spred katta bo'lsa yoki muhim USD yangiligidan 30 daqiqa oldin/keyin kirilmaydi,
  juma kuni 20:00 da (Toshkent: shanba 01:00) hamma pozitsiya yopiladi.

## 2. Haqiqat: 1 haftada nima bo'lishi mumkin

Taxminiy hisob (Monte-Karlo, 100 000 hafta): haftada ~10 ta savdo, RR 1:3, spred/komissiya ≈ 0.08R,
TP ga yetish ehtimoli 25–35% (25% = strategiyada ustunlik yo'q, 35% = juda yaxshi sniper).

| Risk (har savdo) | 4x bo'lish | Balansning yarmi va undan ko'pi ketishi | 90%+ ketishi |
|---|---|---|---|
| 50% | 19–36% | 60–80% | 46–71% |
| **33% (standart)** | **14–31%** | **49–75%** | **9–24%** |
| 25% | 10–25% | 26–53% | 1–6% |
| 20% | 7–20% | 26–53% | 1–6% |

- Haftada 5 ta savdo bo'lsa, 33% riskda 4x ehtimoli 9–18% ga tushadi.
- "Eng kuchli razgon" = 33%. 50% da 4x ehtimoli ozgina oshadi, lekin hisob deyarli yarmi holatda kuyadi.
- Agar xavfni kamaytirmoqchi bo'lsangiz — `InpRiskPercent` ni 25 yoki 20 qiling.

## 3. O'rnatish (Windows, MT5)

**1-qadam. Faylni yuklab oling.** Windows'dagi brauzerda oching:
`https://github.com/Yunusjon007/YunusjonAI/blob/claude/sweet-albattani-n4ex24/mt5/XAU_Sniper_Razgon.mq5`
→ o'ng yuqoridagi **Download raw file** (↓) tugmasi.

**2-qadam. EA papkasiga qo'ying.** MT5 → **File → Open Data Folder**
(ruschada **Файл → Открыть каталог данных**) → `MQL5` → `Experts` → faylni shu yerga ko'chiring.

**3-qadam. Kompilyatsiya.** MT5 da **F4** (MetaEditor ochiladi) → chapdagi Navigator'da
`Experts → XAU_Sniper_Razgon.mq5` ni oching → **F7** (Compile / Компилировать).
Pastdagi "Errors" (Ошибки) oynasida `0 errors` chiqishi kerak.
Xato chiqsa — skrinshot qilib yuboring.

**4-qadam. Grafik oching.** **Ctrl+M** (Market Watch / Обзор рынка) → `XAUUSDc` ni toping
(ko'rinmasa: o'ng tugma → Symbols / Символы → qidiruvga `XAUUSD` yozing → Show / Показать) →
o'ng tugma → **Chart Window** (Окно графика). Timeframe istalgan, M15 qulay.

**5-qadam. EA ni ulang.** **Ctrl+N** (Navigator) → `Expert Advisors` (Советники) → `XAU_Sniper_Razgon`
ni grafikka sudrab olib keling:
- **Common** (Общие) bo'limi: ✅ **Allow Algo Trading** (Разрешить алгоритмическую торговлю).
- **Inputs** (Входные параметры): sozlamalar (pastdagi jadval).
- **OK**.

Yuqoridagi panelda **Algo Trading** (Алго-трейдинг) tugmasi yashil bo'lishi kerak.
Grafikning chap yuqori burchagida EA paneli chiqadi: boshlanish, hozirgi balans, maqsad, bugungi savdolar va **Holat**.

**Qayerdan kuzataman:** **Ctrl+T** (Toolbox / Инструменты) → **Trade** (Торговля) — ochiq savdo,
**History** (История) — yopilganlar, **Experts** (Эксперты) — EA xabarlari.

## 4. Avval Strategy Tester'da sinang (majburiy)

**Ctrl+R** (View → Strategy Tester / Вид → Тестер стратегий):

| Maydon | Qiymat |
|---|---|
| Expert | `XAU_Sniper_Razgon.ex5` |
| Symbol | `XAUUSDc` |
| Timeframe | `M15` |
| Date | Custom period (Пользовательский период) — oxirgi 12 oy |
| Modelling | **Every tick based on real ticks** (Каждый тик на основе реальных тиков) |
| Deposit | `5000` (hisob valyutasi — USC) |
| Leverage | hisobingizdagi bilan bir xil (masalan 1:2000) |

**1-test — strategiyaning o'zi foyda beradimi?** Inputs'da `InpRiskPercent = 1`, `InpGoalX = 0` → **Start**.
Natija **Backtest** (Бэктест) bo'limida:

| Profit Factor (Прибыльность) | Ma'nosi |
|---|---|
| 1.0 dan kichik | Ustunlik yo'q — razgon faqat lotereya, haqiqiy pulda ishlatmang |
| 1.0–1.3 | Kuchsiz ustunlik — 33% riskda kuyish ehtimoli katta |
| 1.3 dan katta (30+ savdo bilan) | Ustunlik bor — lekin kelajakda ham shunday bo'lishi kafolat emas |

Shuningdek qarang: Total trades (Всего трейдов) — haftasiga nechta savdo,
Profit trades (Прибыльные трейды) — RR 1:3 da 28–30% dan yuqori bo'lsa yaxshi.

**2-test — razgon.** `InpRiskPercent = 33`, `InpGoalX = 4`, sanani **1 hafta** qilib, 8–10 xil haftani alohida sinang.
Nechtasida 4x bo'ldi, nechtasida balans yarmidan pastga tushdi — shuni sanang.

Eslatma: testerda yangiliklar filtri ishlamaydi. Birinchi "real ticks" testi tarixni yuklab olishi uchun biroz vaqt oladi.

## 5. Sozlamalar

**Razgon**

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| `InpRiskPercent` | 33 | SL urilsa balansning necha foizi ketadi |
| `InpRR` | 3 | TP = SL masofasi × 3 |
| `InpGoalX` | 4 | Balans shuncha baravar bo'lsa hammasi yopiladi, EA to'xtaydi (0 = o'chiq) |
| `InpStartBalance` | 0 | Boshlang'ich balans (0 = EA birinchi ulangan paytdagi balans) |
| `InpResetGoal` | false | `true` → boshlang'ich balans va "maqsad bajarildi" yangilanadi |
| `InpBreakevenR` | 0 | Masalan 1: foyda 1R bo'lsa SL zararsiz nuqtaga (0 = o'chiq) |
| `InpMaxTradesDay` | 3 | Kuniga ko'pi bilan nechta savdo |

**Sniper** — `InpUseD1` (true), H4 `InpTrendFast`/`InpTrendSlow` (50/200), H1 `InpZoneFast`/`InpZoneSlow` (20/50),
`InpZoneBars` (6 soat), M15 `InpTriggerBars` (4), `InpSwingBars` (8),
SL chegaralari `InpMinStopATR`/`InpMaxStopATR` (0.5–3 × ATR M15).

**Filtrlar**

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| `InpStartHour` / `InpEndHour` | 7 / 20 | Savdo soatlari, server vaqti (Exness = GMT) |
| `InpMaxSpreadUSD` | 1.00 | Spred shundan katta bo'lsa kirilmaydi ($) |
| `InpMaxSpreadSL` | 10 | Spred SL masofasining 10% idan katta bo'lsa kirilmaydi |
| `InpNewsFilter` / `InpNewsMinutes` | true / 30 | Muhim USD yangiligidan 30 daqiqa oldin va keyin kirilmaydi |
| `InpFridayClose` / `InpFridayHour` | true / 20 | Juma 20:00 da yopish (16:00 dan keyin yangi kirish yo'q) |

**Boshqa** — `InpMagic` (770077) EA savdolari belgisi, `InpSlippageUSD` (0.50 $) ruxsat etilgan sirpanish.

## 6. Muhim

- **Kompyuter va MT5 doim yoqiq** bo'lishi kerak (uyqu rejimini o'chiring) — yoki VPS ishlating.
- Bu hisobda **qo'lda savdo qilmang**: 4x maqsad butun hisob equity'si bo'yicha tekshiriladi.
- Bitta EA — bitta grafik. Ikki grafikka bir xil `InpMagic` bilan qo'ymang.
- **Maqsad bajarilgach** EA to'xtaydi. Qayta boshlash: `InpResetGoal = true` → OK →
  keyin yana `false` qiling (aks holda har qayta ishga tushganda boshlang'ich balans yangilanaveradi).
- EA har yangi M15 sham ochilganda tekshiradi. Paneldagi **Holat** nima kutilayotganini ko'rsatadi:
  `H4: trend yo'q`, `H1: zonaga qaytish kutilmoqda`, `M15: sniper kirish kutilmoqda`, `spred katta`,
  `sessiya tashqarisida`, `muhim yangilik yaqin`, `pozitsiya ochiq` va hokazo. Savdo kun davomida bo'lmasligi normal holat.
- Haqiqiy hisobdan oldin Exness **demo** hisobida 1–2 hafta sinab ko'ring (demo'da belgi `XAUUSDm` yoki `XAUUSD` bo'lishi mumkin — EA qaysi grafikka qo'yilsa, shu belgida ishlaydi).
