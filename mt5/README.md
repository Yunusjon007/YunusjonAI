# XAU Sniper Razgon v2 — MetaTrader 5 (Exness) uchun oltin razgon EA

`XAU_Sniper_Razgon.mq5` — XAUUSD / XAUUSDc uchun avtomatik savdo dasturi (EA, "sovetnik").
Tahlil **H1** dan boshlanadi va pastga tushadi: H1 → M15 → M5 → **M1**. Hammasi bir tomonga qaraganda
M1 signal bilan "sniper" kirish qiladi. Lot: **har 100 balansga kamida 0.01 lot**. TP SL'dan 3 baravar uzoq.
Balans 4 baravar bo'lsa hamma pozitsiyani yopadi va o'zini to'xtatadi.

> ⚠️ **Avval o'qing:** EA haftasiga ~15 ta savdo qiladi. Sun'iy sinovda (ustunliksiz bozor) 1 haftada 4x bo'lish
> ehtimoli ~4%, yarim yil ichida ~19%; ~79% holatda balansning 90% i ketgan (2-bo'lim).
> Faqat yo'qotishga tayyor pulni qo'ying va avval Strategy Tester'da sinang.

## 1. Strategiya qanday ishlaydi

| Timeframe | Nima tekshiriladi |
|---|---|
| **H1** | EMA50 > EMA200 → faqat BUY, EMA50 < EMA200 → faqat SELL; oxirgi H1 sham EMA50 dan trend tomonida yopilgan |
| **M15** | Oxirgi 8 shamda (2 soat) narx EMA20 ga qaytib tekkan ("zona"), lekin EMA50 dan buzilmagan |
| **M5** | Oxirgi M5 sham EMA20 dan trend tomonida yopilgan — impuls qaytdi |
| **M1** | Oxirgi yopilgan sham oldingi 5 sham cho'qqisidan yuqori (SELL da tubidan past) yopildi → **KIRISH** |

- **SL** — oxirgi 10 ta M1 shamning eng past nuqtasi ortida (SELL da eng baland nuqtasi ustida) + kichik zaxira.
  SL juda kichik (< 0.5 × ATR M5) yoki juda katta (> 3 × ATR M5) bo'lsa, kirilmaydi.
- **TP** — SL masofasi × 3 (RR 1:3).
- **Lot** — har 100 balansga 0.01 lot (balans o'sgani sari lot ham o'sadi):

  | Balans (USC) | Lot | Oltin 1 $ yursa |
  |---|---|---|
  | 5 000 | 0.50 | ±50 USC (balansning 1%) |
  | 10 000 | 1.00 | ±100 USC |
  | 20 000 | 2.00 | ±200 USC |

  Odatdagi SL 7–8 $ atrofida, demak bitta zarar ≈ balansning **7–8%** i (−375 USC), TP ≈ **+22%** (+1125 USC).
  Cent hisobda 100 USC = 1 $. Agar "har haqiqiy 100 $" demoqchi bo'lsangiz — `InpBalanceStep = 10000` qiling.
- Xohlasangiz `InpRiskPercent` ni yoqing (masalan 20): EA lot qoidasi va "SL urilsa balansning 20% i" lotidan **kattasini** oladi.
- **Maqsad**: hisob equity'si boshlang'ich balansdan 4 baravar bo'lishi bilan (savdo o'rtasida bo'lsa ham)
  hamma pozitsiya yopiladi va EA to'xtaydi.
- Bir vaqtda faqat **1 ta** pozitsiya, kuniga ko'pi bilan **10 ta** savdo. Signal har yangi M1 shamda tekshiriladi.
- Filtrlar: savdo faqat 07:00–20:00 server vaqtida (Exness = GMT, Toshkent vaqti bilan 12:00–01:00),
  spred katta bo'lsa yoki muhim USD yangiligidan 30 daqiqa oldin/keyin kirilmaydi,
  juma kuni 20:00 da (Toshkent: shanba 01:00) hamma pozitsiya yopiladi.

## 2. Haqiqat: nima kutish mumkin

EA qoidalari Python'da aynan takrorlanib, **24 yillik sun'iy oltin narxida** sinaldi
(ustunliksiz bozor: tasodifiy narx, oltinga o'xshash tebranish, spred 0.35 $, SL'da 0.30 $ sirpanish):

- haftasiga o'rtacha **15.5 ta savdo** (kuniga ~3 ta), savdo odatda **~40 daqiqa** ochiq turadi;
- 24% savdo TP ga yetadi; o'rtacha natija −0.04R (spred va sirpanish) — "pul bosib chiqaradigan" sozlama yo'q;
- lot qoidasida bitta savdo riski: odatda 8%, 4% dan 19% gacha (SL kattaligiga qarab).

**1 hafta ichida** (5000 USC dan boshlab):

| Lot | 4x bo'ldi | Balansning yarmi va ko'pi ketdi | 90%+ ketdi | O'rtacha (median) hafta oxiri |
|---|---|---|---|---|
| **0.01 / 100 (standart)** | **4%** | **22%** | **3%** | **0.78x** |
| + `InpRiskPercent = 20` | 11% | 59% | 17% | 0.38x |
| + `InpRiskPercent = 33` | 17% | 74% | 55% | 0.10x |

**Yarim yil to'xtamay ishlasa** (4x yoki −90% bo'lguncha):

| Lot | 4x bo'ladi | Odatda qancha vaqtda | −90% bo'ladi |
|---|---|---|---|
| **0.01 / 100** | **19%** | ~3 hafta | **79%** (~7 haftada) |
| + risk 20% | 18% | ~1 hafta | 82% (~2 haftada) |
| + risk 33% | 20% | ~1 hafta | 80% (~1 haftada) |

Xulosa: **ustunlik bo'lmasa, lot kattaligi faqat tezlikni o'zgartiradi** — 4x ehtimoli baribir ~5 tadan 1.

**Ustunlik bo'lsa** (Strategy Tester ko'rsatadi, 4-bo'lim) — rasm o'zgaradi va **kichikroq lot yaxshiroq** bo'ladi
(taxminiy hisob, yarim yil ichida 4x ga −90% dan oldin yetish):

| TP ga yetgan savdolar (testerdagi Profit Factor) | 0.01 / 100 (~8% risk) | Risk 20% | Risk 33% |
|---|---|---|---|
| 25% (PF ≈ 1.0 — ustunlik yo'q) | 15% | 19% | 21% |
| 30% (PF ≈ 1.3) | 71% (~6 hafta) | 43% (~1 hafta) | 35% (~2–3 kun) |
| 35% (PF ≈ 1.6) | 99% (~4 hafta) | 71% (~1 hafta) | 53% (~2–3 kun) |

Qoida: testerda **Profit Factor 1 dan kichik** — haqiqiy pulda ishlatmang. **1.3 dan katta** bo'lsa —
standart lot qoidasi (0.01 / 100) eng ishonchli yo'l; `InpRiskPercent` faqat tezlik uchun.

## 3. O'rnatish (Windows, MT5)

**1-qadam. Faylni yuklab oling.** Windows'dagi brauzerda oching:
`https://github.com/Yunusjon007/YunusjonAI/blob/claude/sweet-albattani-n4ex24/mt5/XAU_Sniper_Razgon.mq5`
→ o'ng yuqoridagi **Download raw file** (↓) tugmasi. Eski versiya bo'lsa — ustidan yozing.

**2-qadam. EA papkasiga qo'ying.** MT5 → **File → Open Data Folder**
(ruschada **Файл → Открыть каталог данных**) → `MQL5` → `Experts` → faylni shu yerga ko'chiring.

**3-qadam. Kompilyatsiya.** MT5 da **F4** (MetaEditor ochiladi) → chapdagi Navigator'da
`Experts → XAU_Sniper_Razgon.mq5` ni oching → **F7** (Compile / Компилировать).
Pastdagi "Errors" (Ошибки) oynasida `0 errors` chiqishi kerak.
Xato chiqsa — skrinshot qilib yuboring.

**4-qadam. Grafik oching.** **Ctrl+M** (Market Watch / Обзор рынка) → `XAUUSDc` ni toping
(ko'rinmasa: o'ng tugma → Symbols / Символы → qidiruvga `XAUUSD` yozing → Show / Показать) →
o'ng tugma → **Chart Window** (Окно графика). Timeframe istalgan (EA o'zi H1, M15, M5, M1 ni o'qiydi), M1 qulay.

**5-qadam. EA ni ulang.** **Ctrl+N** (Navigator) → `Expert Advisors` (Советники) → `XAU_Sniper_Razgon`
ni grafikka sudrab olib keling:
- **Common** (Общие) bo'limi: ✅ **Allow Algo Trading** (Разрешить алгоритмическую торговлю).
- **Inputs** (Входные параметры): sozlamalar (pastdagi jadval).
- **OK**.

Yuqoridagi panelda **Algo Trading** (Алго-трейдинг) tugmasi yashil bo'lishi kerak.
Grafikning chap yuqori burchagida EA paneli chiqadi: boshlanish, hozirgi balans, maqsad, hozirgi lot,
bugungi savdolar, **Natija** (nechta savdo, nechtasi foyda/zarar, jami) va **Holat**.

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
| Timeframe | `M1` |
| Date | Custom period (Пользовательский период) — oxirgi 6 oy (M1 da test sekinroq) |
| Modelling | **Every tick based on real ticks** (Каждый тик на основе реальных тиков) |
| Deposit | `5000` (hisob valyutasi — USC) |
| Leverage | hisobingizdagi bilan bir xil (masalan 1:2000) |

**1-test — strategiyaning o'zi foyda beradimi?** Inputs'da `InpBalanceStep = 1000000` (har doim 0.01 lot),
`InpRiskPercent = 0`, `InpGoalX = 0` → **Start**. Natija **Backtest** (Бэктест) bo'limida:

| Profit Factor (Прибыльность) | Ma'nosi |
|---|---|
| 1.0 dan kichik | Ustunlik yo'q — razgon faqat lotereya, haqiqiy pulda ishlatmang |
| 1.0–1.3 | Kuchsiz ustunlik — kuyish ehtimoli katta |
| 1.3 dan katta (100+ savdo bilan) | Ustunlik bor — lekin kelajakda ham shunday bo'lishi kafolat emas |

Shuningdek qarang: Total trades (Всего трейдов) — haftasiga nechta savdo (sun'iy sinovda ~15),
Profit trades (Прибыльные трейды) — RR 1:3 da ustunliksiz bozorda ~25%.

**2-test — razgon.** Standart sozlamalar (`InpBalanceStep = 100`, `InpGoalX = 4`), sanani 1–2 oy qilib,
6–8 xil boshlanish sanasidan sinang. Nechtasida 4x bo'ldi, nechtasida balans 90% kamaydi va bu necha haftada bo'ldi — shuni sanang.

Eslatma: testerda yangiliklar filtri ishlamaydi. Birinchi "real ticks" testi tarixni yuklab olishi uchun biroz vaqt oladi.

## 5. Sozlamalar

**Lot va razgon**

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| `InpLotPerStep` | 0.01 | Har `InpBalanceStep` balansga kamida shuncha lot |
| `InpBalanceStep` | 100 | Balans qadami (hisob valyutasida; cent hisobda 100 USC = 1 $) |
| `InpRiskPercent` | 0 | 0 = faqat lot qoidasi. >0: "SL urilsa balansning shuncha % i" loti bilan solishtirib kattasi olinadi |
| `InpRR` | 3 | TP = SL masofasi × 3 |
| `InpGoalX` | 4 | Balans shuncha baravar bo'lsa hammasi yopiladi, EA to'xtaydi (0 = o'chiq) |
| `InpStartBalance` | 0 | Boshlang'ich balans (0 = EA birinchi ulangan paytdagi balans) |
| `InpResetGoal` | false | `true` → boshlang'ich balans, statistika va "maqsad bajarildi" yangilanadi |
| `InpBreakevenR` | 0 | Masalan 1: foyda 1R bo'lsa SL zararsiz nuqtaga (0 = o'chiq) |
| `InpMaxTradesDay` | 10 | Kuniga ko'pi bilan nechta savdo |

**Sniper: H1 → M15 → M5 → M1**

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| `InpH1Fast` / `InpH1Slow` | 50 / 200 | H1 trend EMA'lari |
| `InpM15Fast` / `InpM15Slow` | 20 / 50 | M15 qaytish zonasi va tuzilma EMA'lari |
| `InpZoneBars` | 8 | M15: oxirgi necha shamda zonaga tegilgan bo'lsin |
| `InpM5EMA` | 20 | M5: oxirgi yopilish shu EMA ning trend tomonida bo'lsin |
| `InpTriggerBars` | 5 | M1: oldingi necha sham cho'qqisi (tubi) yorilsa — kirish |
| `InpSwingBars` | 10 | M1: SL qo'yiladigan tublik (cho'qqi) uchun necha sham |
| `InpMinStopATR` / `InpMaxStopATR` | 0.5 / 3 | SL chegaralari, × ATR(M5) |

**Filtrlar**

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| `InpStartHour` / `InpEndHour` | 7 / 20 | Savdo soatlari, server vaqti (Exness = GMT) |
| `InpMaxSpreadUSD` | 1.00 | Spred shundan katta bo'lsa kirilmaydi ($) |
| `InpMaxSpreadSL` | 15 | Spred SL masofasining 15% idan katta bo'lsa kirilmaydi |
| `InpNewsFilter` / `InpNewsMinutes` | true / 30 | Muhim USD yangiligidan 30 daqiqa oldin va keyin kirilmaydi |
| `InpFridayClose` / `InpFridayHour` | true / 20 | Juma 20:00 da yopish (16:00 dan keyin yangi kirish yo'q) |

**Boshqa** — `InpMagic` (770077) EA savdolari belgisi, `InpSlippageUSD` (0.50 $) ruxsat etilgan sirpanish,
`InpPush` (true) telefonga push xabar.

## 6. Muhim

- **Kompyuter va MT5 doim yoqiq** bo'lishi kerak (uyqu rejimini o'chiring) — yoki VPS ishlating.
- Bu hisobda **qo'lda savdo qilmang**: 4x maqsad butun hisob equity'si bo'yicha tekshiriladi.
- Bitta EA — bitta grafik. Ikki grafikka bir xil `InpMagic` bilan qo'ymang.
- Marja yetmasa, EA lotni kamaytiradi (jurnalda yoziladi), minimal lotga ham yetmasa — kirmaydi.
- **Maqsad bajarilgach** EA to'xtaydi. Qayta boshlash: `InpResetGoal = true` → OK →
  keyin yana `false` qiling (aks holda har qayta ishga tushganda boshlang'ich balans yangilanaveradi).
- Paneldagi **Holat** nima kutilayotganini ko'rsatadi: `H1: trend yo'q`, `M15: zonaga qaytish kutilmoqda`,
  `M5: impuls qaytishi kutilmoqda`, `M1: sniper kirish kutilmoqda`, `spred katta`, `sessiya tashqarisida`,
  `muhim yangilik yaqin`, `pozitsiya ochiq` va hokazo.
- Haqiqiy hisobdan oldin Exness **demo** hisobida 1–2 hafta sinab ko'ring (demo'da belgi `XAUUSDm` yoki `XAUUSD` bo'lishi mumkin — EA qaysi grafikka qo'yilsa, shu belgida ishlaydi).
