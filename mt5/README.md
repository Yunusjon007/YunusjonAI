# XAU Sniper Razgon — MetaTrader 5 (Exness) uchun oltin razgon EA

`XAU_Sniper_Razgon.mq5` — XAUUSD / XAUUSDc uchun avtomatik savdo dasturi (EA, "sovetnik").
U to'rtta timeframe'ni tekshiradi va hammasi bir tomonga qaraganda "sniper" kirish qiladi:
SL yaqin tublik (cho'qqi) ortida, TP SL'dan 3 baravar uzoq, lot katta. Balans 4 baravar bo'lsa hamma pozitsiyani yopadi
va o'zini to'xtatadi.

> ⚠️ **Avval o'qing:** EA haftasiga o'rtacha 2–3 ta savdo qiladi. 1 haftada 4x bo'lishi uchun ketma-ket 2 ta TP kerak —
> bu taxminan **4%** ehtimol. To'xtamay ishlatilsa, strategiyada ustunlik bo'lmasa, taxminan **5 tadan 1** holatda 4x bo'ladi,
> **4 tadan 3** holatda balansning 90% i ketadi (2-bo'lim). Faqat yo'qotishga tayyor pulni qo'ying va avval Strategy Tester'da sinang.

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

## 2. Haqiqat: nima kutish mumkin

EA qoidalari Python'da aynan takrorlanib, **80 yillik sun'iy oltin narxida** sinaldi
(ustunliksiz bozor: tasodifiy narx, oltinga o'xshash kunlik tebranish, spred 0.35 $, SL'da 0.30 $ sirpanish):

- haftasiga o'rtacha **2.7 ta savdo** (7% haftada 0 ta, 42% da 1–2 ta, 39% da 3–4 ta, 12% da 5+ ta);
- savdo o'rtacha **12 soat** ochiq turadi, SL o'rtacha 2.3 × ATR(M15), 22% savdo TP ga yetadi;
- bunday bozorda o'rtacha natija ≈ 0R minus spred — "pul bosib chiqaradigan" sozlama yo'q.

**1 hafta ichida** (har hafta 5000 USC dan boshlansa):

| Risk (har savdo) | 4x bo'ldi | Balansning yarmi va ko'pi ketdi | 90%+ ketdi | O'rtacha (median) hafta oxiri |
|---|---|---|---|---|
| 50% | 10% | 53% | 9% | 0.49x |
| **33% (standart)** | **4%** | **33%** | **0.5%** | **0.67x** |
| 25% | 2% | 17% | 0% | 0.75x |
| 20% | 1% | 10% | 0% | 0.81x |

**To'xtamay ishlasa** (4x yoki −90% bo'lguncha):

| Risk | 4x bo'ladi | Odatda qancha vaqtda | −90% bo'ladi |
|---|---|---|---|
| 50% | 24% | ~2 hafta | 76% |
| **33%** | **22%** | **~3 hafta** | **78%** |
| 25% | 22% | ~4 hafta | 78% |
| 20% | 21% | ~6 hafta | 79% |

Xulosa: **ustunlik bo'lmasa risk faqat tezlikni o'zgartiradi** — 4x ehtimoli baribir ~22% (5 tadan 1).

**Ustunlik bo'lsa** (Strategy Tester ko'rsatadi, 4-bo'lim) — rasm o'zgaradi va **kichikroq risk yaxshiroq** bo'ladi
(taxminiy hisob, 4x ga −90% dan oldin yetish ehtimoli):

| TP ga yetgan savdolar (testerdagi Profit Factor) | Risk 33% | Risk 20% | Risk 10% |
|---|---|---|---|
| 25% (PF ≈ 1.0 — ustunlik yo'q) | 18% | 16% | 11% |
| 30% (PF ≈ 1.3) | 31% (~2 hafta) | 37% (~6 hafta) | 52% (~23 hafta) |
| 35% (PF ≈ 1.6) | 47% (~3 hafta) | 65% (~6 hafta) | 93% (~19 hafta) |

Qoida: testerda **Profit Factor 1 dan kichik** — ishlatmang. **1.3 dan katta** bo'lsa — 4x ehtimolini oshirish uchun
`InpRiskPercent` ni 20 ga tushiring (sekinroq, lekin ishonchliroq), tezlik muhim bo'lsa — 33.

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
Grafikning chap yuqori burchagida EA paneli chiqadi: boshlanish, hozirgi balans, maqsad, bugungi savdolar,
**Natija** (nechta savdo, nechtasi foyda/zarar, jami) va **Holat**.

**Qayerdan kuzataman:** **Ctrl+T** (Toolbox / Инструменты) → **Trade** (Торговля) — ochiq savdo,
**History** (История) — yopilganlar, **Experts** (Эксперты) — EA xabarlari.

**Telefondan kuzatish.**
1. Telefonga **MetaTrader 5** ilovasini o'rnating va Exness hisobingizga kiring — ochiq savdolar va tarix shu yerda ko'rinadi.
2. Push xabarlar: telefon ilovasida **Settings** (Настройки) → **Messages** (Сообщения) bo'limida **MetaQuotes ID** yozilgan — uni ko'chiring.
   Kompyuterdagi MT5: **Tools → Options → Notifications** (Сервис → Настройки → Уведомления) →
   ✅ **Enable Push Notifications** (Разрешить Push-уведомления) → MetaQuotes ID ni yozing → **Test** → **OK**.
3. Endi EA savdo ochilganda, yopilganda (TP/SL, natija va balans) va maqsad bajarilganda telefonga xabar yuboradi.

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

Shuningdek qarang: Total trades (Всего трейдов) — haftasiga nechta savdo (sun'iy sinovda ~2.7).
Profit trades (Прибыльные трейды) ustunliksiz bozorda ham ~27–29% bo'ladi (juma yopilishlari tufayli),
shuning uchun asosiy ko'rsatkich — **Profit Factor**.

**2-test — razgon.** `InpRiskPercent = 33`, `InpGoalX = 4`, sanani 1–2 oy qilib, 6–8 xil boshlanish sanasidan sinang.
Nechtasida 4x bo'ldi, nechtasida balans 90% kamaydi va bu necha haftada bo'ldi — shuni sanang.

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

**Boshqa** — `InpMagic` (770077) EA savdolari belgisi, `InpSlippageUSD` (0.50 $) ruxsat etilgan sirpanish,
`InpPush` (true) telefonga push xabar.

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
