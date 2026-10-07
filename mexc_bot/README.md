# Futures scalping bot (Binance / MEXC)

Har bir savdoga balansning **kichik qismi (standart 1%)** tikiladi, shuning uchun
balansning katta qismi doim bo'sh qoladi va bot bir vaqtda bir nechta coinda savdo qila oladi.
Bu moliyaviy maslahat emas. Avval `paper` yoki `demo` rejimda sinab ko'ring.

| Bot | Uslub | Ushlab turish |
|---|---|---|
| `allin_bot.py` | 5m EMA kesishishi, martingeyl | soatlar |
| `trend_bot.py` | 5m trend, har +1% da SL siljiydi | soatlar |
| `razgon_bot.py` | har daqiqada savdo, +0.1% da yopish | daqiqalar |
| **`swing_bot.py`** | **4h trend + 1h yorish, piramida, balans maqsadi** | **1–3 kun** |

Bir vaqtda bitta hisobda faqat **bitta** botni ishga tushiring. Har birini avval `backtest.py` bilan sinang.

## Coinlar qanday tanlanadi (`universe.py`)
1. Birjadagi barcha USDT perpetual coinlardan 24 soatlik savdo hajmi bo'yicha **eng likvid 50 tasi** olinadi
   (stablecoin, indeks, oltin kabi coin bo'lmagan kontraktlar chiqariladi).
2. Har bir coinning oxirgi **7 kunlik soatlik** narx o'zgarishlari solishtiriladi.
3. Coinlar likvidlik tartibida ko'rib chiqiladi: allaqachon tanlangan coin bilan
   **korrelyatsiyasi ≥ 0.8** bo'lsa (grafigi deyarli bir xil yuradi) — chiqarib tashlanadi.
   Masalan, ETH ko'pincha BTC bilan bir xil harakat qiladi, shuning uchun chiqarilishi mumkin.
4. 5 kundan kam tarixi bor yangi coinlar olinmaydi.
5. Bozor juda bir xil harakat qilgan kunlarda ham kamida **10 ta** coin qoladi.
6. Ro'yxat har **6 soatda** yangilanadi.

Qaysi coinlar tanlangani va qaysilari nega chiqarilganini ko'rish: `python3 allin_bot.py --coins`

## Strategiya
- Har bir yangi 5 daqiqalik sham yopilganda tanlangan coinlar tahlil qilinadi
- Signal: EMA9 / EMA21 kesishishi + RSI filtri
- Marja = balansning **1%**, leverage **10x**, isolated
- **TP**: narx **+3%** foyda tomonga yursa (Binance'da ROI ≈ +30%)
- **Martingeyl (2 qadam)**: narx kirishdan **−1%** qarshi yursa — pozitsiyaga **2×**, **−2%** da yana **4×** qo'shiladi
- Martingeyl qilingan coinning sof foydasi (komissiyalardan keyin) **+1$** ga yetishi bilan
  **shu coindagi barcha savdolar yopiladi** (bu narx birjaga TP sifatida ham qo'yiladi)
- **Oxirgi SL**: kirishdan **−3%** (ikkala martingeyldan keyin). Martingeyl o'chirilsa (`MARTINGALE_STEPS=0`) SL = −1%
- Bir vaqtda **20 tagacha** coinda savdo, har bir coinda bitta pozitsiya
- Barcha pozitsiyalar marjasi balansning **50%** idan oshmaydi — limitga yetsa, yangi savdo va martingeyl qilinmaydi
- Yopilgan coin kamida bitta sham davomida qayta ochilmaydi
- Bugungi zarar balansning **3%** iga yetsa — ertagacha yangi savdo ochilmaydi (ochiqlari kuzatiladi)

### 5 000 USDT balansda bitta coin
| Holat | Pozitsiya | Natija (komissiya bilan) |
|---|---|---|
| Kirish (marja 50 USDT × 10x) | 500 USDT | TP +3% da ≈ **+14.5** |
| 1-martingeyl (−1%) | +1 000 → 1 500 USDT | +1$ da yopiladi ≈ **+1.0** |
| 2-martingeyl (−2%) | +2 000 → 3 500 USDT | +1$ da yopiladi ≈ **+1.0** |
| Oxirgi SL (−3%) | 3 500 USDT | ≈ **−58** |

### ⚠️ Martingeyl haqida haqiqat
Martingeyl savdolarning **~90%** ini yutuq qiladi, lekin bitta oxirgi SL (≈ −58 USDT) **~58 ta**
+1$ yutuqni yeb ketadi. Narx tasodifiy harakat qilganda o'rtacha natija savdo boshiga
**≈ −1.7 USDT** (martingeylsiz ≈ −0.5 USDT) — farq katta pozitsiyalar komissiyasidan.
Shuning uchun statistikada **yutuq foiziga emas**, `--stats` dagi **Sof natija** va **Profit factor** ga qarang.

## Buyruqlar
```bash
cd ~/YunusjonAI/mexc_bot
source .venv/bin/activate

caffeinate -i python3 allin_bot.py   # botni ishga tushirish (Mac uxlab qolmaydi)
python3 allin_bot.py --stats         # statistika
python3 allin_bot.py --coins         # tanlangan va chiqarilgan coinlar
python3 allin_bot.py --close         # barcha ochiq pozitsiyalarni yopish
python3 allin_bot.py --close SOL     # faqat SOL ni yopish
```
`--stats`, `--coins` va `--close` ni bot ishlab turganda **yangi terminal oynasida** (Cmd+T) ishlating.

## Statistika qayerda
1. **Bot oynasida** — har 5 daqiqada balans holati:
   `📊 Balans 5012.30 USDT | ochiq 3/5: SOL LONG +4.10, XRP SHORT -1.20, ... | bugun: 4 savdo, +8.40 USDT`
   va har bir yopilgan savdodan keyin umumiy natija.
2. **`python3 allin_bot.py --stats`** — to'liq hisobot: birjadagi joriy balans va ochiq pozitsiyalar,
   yutuq foizi, sof natija, komissiyalar, eng yaxshi/yomon savdo, kunlar va coinlar bo'yicha natija,
   oxirgi 10 ta savdo.
3. **`trades_binance_demo.csv`** — barcha yopilgan savdolar jadvali (Numbers yoki Excel'da ochiladi):
   `open trades_binance_demo.csv`
4. **`bot_binance_demo.log`** — bot yozgan barcha xabarlar tarixi.

## .env ni yangilash (eski versiyadan o'tganda bir marta)
Eski `.env` dagi `LEVERAGE=20`, `TP_PCT=1.0`, `TIMEFRAME=1m` kabi qatorlar yangi sozlamalarni bosib ketadi.
Quyidagi buyruq kalitlarni saqlab qoladi, eski sozlamalarni olib tashlaydi (nusxasi `.env.backup` da qoladi):
```bash
cd ~/YunusjonAI/mexc_bot && cp .env .env.backup && grep -E '^(EXCHANGE|MODE|BINANCE_|MEXC_)' .env.backup > .env
```
Bot ishga tushganda `Sozlamalar: ...` qatorida qaysi qiymatlar ishlayotganini ko'rsatadi.

## Sozlamalar (.env, ixtiyoriy)
| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `MARGIN_PCT` | 1 | Har savdoga balansning necha foizi marja |
| `LEVERAGE` | 10 | Leverage (plecho) |
| `TP_PCT` | 3 | Narx necha % foyda tomonga yursa yopiladi |
| `SL_PCT` | 1 | Martingeyl o'chiq bo'lganda SL (narx %) |
| `MAX_POSITIONS` | 20 | Bir vaqtda nechta coinda savdo |
| `MAX_MARGIN_PCT` | 50 | Barcha pozitsiyalar marjasi, balansdan % (martingeyl bilan birga) |
| `MARTINGALE_STEPS` | 2 | Martingeyl qadamlari (0 = o'chiq) |
| `MARTINGALE_STEP_PCT` | 1 | Narx kirishdan har necha % qarshi yurganda qo'shiladi |
| `MARTINGALE_MULT` | 2 | Har qadamda hajm necha baravar (1x → 2x → 4x) |
| `MARTINGALE_PROFIT_USDT` | 1 | Martingeyl qilingan coin shu sof foydada (USDT) yopiladi |
| `MARTINGALE_SL_PCT` | 3 | Martingeyldan keyingi oxirgi SL (kirishdan narx %) |
| `DAILY_LOSS_PCT` | 3 | Kunlik zarar limiti (balansdan %) |
| `TIMEFRAME` | 5m | Shamlar |
| `STATUS_MINUTES` | 5 | Holat qatori necha daqiqada bir |
| `TOP_COINS` | 50 | Hajm bo'yicha nechta eng likvid coin ko'rib chiqiladi |
| `CORR_MAX` | 0.8 | O'xshashlik chegarasi: korrelyatsiya shundan yuqori bo'lsa — chiqariladi (1 = filtr o'chiq) |
| `CORR_TIMEFRAME` / `CORR_LOOKBACK` | 1h / 168 | O'xshashlik qaysi shamlar bo'yicha va necha sham (168 × 1h = 7 kun) |
| `MIN_COINS` | 10 | Kamida nechta coin qolsin |
| `REFRESH_HOURS` | 6 | Ro'yxat necha soatda bir yangilanadi |
| `SYMBOLS` | bo'sh (avtomatik) | O'z ro'yxatingiz, masalan `BTC,ETH,SOL` (o'xshashlik filtri baribir qo'llanadi) |

Ko'proq coin kerak bo'lsa `CORR_MAX=0.85`, kamroq (yanada farqli) kerak bo'lsa `CORR_MAX=0.7` qiling.

`TP_PCT`/`SL_PCT` — **narx** o'zgarishi. Binance'dagi ROI = narx % × leverage
(10x da TP 3% = ROI +30%). ROI +3% da yopish kerak bo'lsa: `TP_PCT=0.3` — lekin bunda
foydaning ~1/3 qismi komissiyaga ketadi.

## 🐢 Swing bot — 2–3 kunlik trend + piramida (`swing_bot.py`)
Bir necha kun davom etadigan trendlarni ushlaydi va trend tasdiqlangan sari pozitsiyani kattalashtiradi.
- **Yo'nalish (4h):** EMA50 > EMA200 — faqat LONG, EMA50 < EMA200 — faqat SHORT
- **Kirish (1h):** narx oxirgi **48 soatning** eng yuqori nuqtasini yorsa LONG (eng pastini — SHORT)
- **SL:** 2.5 × ATR(1h). **Hajm risk bo'yicha:** SL urilsa balansning **2%** i ketadi
- **Piramida (razgon):** narx har **+1 ATR** yurganda yana xuddi shunday qism qo'shiladi (jami **3** qismgacha),
  butun pozitsiya SL i oxirgi qo'shimchadan 2.5 ATR orqaga ko'tariladi
- **Chandelier SL:** eng yaxshi narx − **3 × ATR**, faqat foyda tomonga siljiydi. TP yo'q — trend tugaguncha
- **Balans maqsadi:** balans (ochiq savdolar bilan) **+10%** ga yetsa — hamma pozitsiya yopiladi, keyingi maqsad yangi balansdan
- **10x**, bir vaqtda **3** coin, marja limiti **80%**, kunlik zarar limiti **15%**. Haqiqiy pulda faqat `SWING_LIVE_OK=1` bilan.
  Faqat Binance (demo/live) yoki paper rejimda ishlaydi.

### 5 000 USDT balansda (SL ~3% bo'lgan coin)
| Holat | Pozitsiya | SL urilsa |
|---|---|---|
| Kirish (1 qism) | ≈ 3 300 USDT | ≈ −100 USDT (−2%) |
| +1 ATR → 2-qism | ≈ 6 700 USDT | SL ko'tarilgan, zarar kamroq |
| +2 ATR → 3-qism | ≈ 10 000 USDT | SL birinchi kirishdan ≈ 0.6% pastda |
| Trend +10% ga borib, chandelier +6.4% da yopsa | 10 000 USDT | foyda ≈ +520 USDT (213 + 173 + 133) |
| Trend +20% ga borsa (SL +16.4% da) | 10 000 USDT | foyda ≈ +1 520 USDT |

```bash
python3 backtest.py --swing                 # 1) avval 90 kunlik Binance tarixida sinang
python3 backtest.py --swing --sweep         #    SL / chandelier / qismlar sonini solishtirish
python3 backtest.py --swing --target 0      #    balans maqsadisiz (trendni oxirigacha ushlab)
caffeinate -i python3 swing_bot.py          # 2) demo'da ishga tushirish
python3 swing_bot.py --stats                #    statistika
python3 swing_bot.py --close                #    hamma pozitsiyani yopish
```
⚠️ Bot to'xtatilsa, birjadagi SL joyida qoladi, lekin **siljimaydi va qism qo'shilmaydi**. Balans maqsadi bot qayta
ishga tushganda o'sha paytdagi balansdan qayta hisoblanadi.

Tasodifiy (sintetik) bozorlarda backtest xarajatsiz ≈ 0 natija beradi (40 bozorda +0.06% ± 0.05% hajmdan) —
ya'ni mexanikada yashirin foyda yo'q. Haqiqiy tarixda foyda chiqsa — u haqiqiy trendlardan. Shu bilan birga
trend strategiyalarida natija bir necha katta yutuqqa bog'liq: bitta yaxshi backtest omad bo'lishi mumkin —
uzunroq davr (`--days 180`) va demo bilan tasdiqlang.

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| `SWING_RISK_PCT` | 2 | Har qism SL urilsa balansning necha foizi |
| `SWING_STOP_ATR` | 2.5 | Boshlang'ich SL = shuncha × ATR |
| `SWING_TRAIL_ATR` | 3 | Chandelier: eng yaxshi narx − shuncha × ATR |
| `SWING_ADD_ATR` | 1 | Har necha ATR da yangi qism |
| `SWING_MAX_UNITS` | 3 | Jami qismlar (1 = piramidasiz) |
| `SWING_BREAKOUT_BARS` | 48 | Yorish uchun necha soat |
| `SWING_LEVERAGE` | 10 | Leverage |
| `SWING_MAX_OPEN` | 3 | Bir vaqtda nechta coin |
| `SWING_MAX_MARGIN_PCT` | 80 | Barcha marja limiti (balansdan %) |
| `SWING_TARGET_PCT` | 10 | Balans maqsadi (0 = o'chiq) |
| `SWING_DAILY_LOSS_PCT` | 15 | Kunlik zarar limiti |
| `SWING_SCAN_COINS` | 20 | Nechta eng likvid coin tekshiriladi |

## 📈 Trend bot — 5m razgon, SL zinapoyasi (`trend_bot.py`)
Har **15 daqiqada** 5 daqiqalik shamlar bo'yicha eng kuchli trenddagi coinda savdo ochadi va foyda
har **+1%** ga yetganda SL ni siljitib boradi.
- **Kirish:** LONG — EMA20 > EMA50, narx EMA20 dan yuqorida, RSI 50–75; SHORT — teskarisi (RSI 25–50).
  Bir nechta coin mos kelsa — trend kuchi (EMA farqi / ATR) va hajm bo'yicha eng kuchlisi. Mos coin bo'lmasa — navbat o'tkaziladi.
- **Hajm:** marja balansning **10%** i × **20x** (pozitsiya ≈ balansning 2 baravari), bir vaqtda **3 tagacha**
- **SL zinapoyasi** (TP yo'q — foyda trend davom etguncha o'sadi):

| Narx foydasi | SL qayerda | 5 000 USDT balansda (pozitsiya 10 000) |
|---|---|---|
| 0% (kirish) | −1% | SL bo'lsa ≈ −110 USDT |
| +1% ga yetdi | zararsiz (+0.12%) | ≈ 0 |
| +2% ga yetdi | +1% | ≈ +90 USDT |
| +3% ga yetdi | +2% | ≈ +190 USDT |
| +5% ga yetdi | +4% | ≈ +390 USDT |

- Bugungi zarar **15%** ga yetsa — ertagacha yangi savdo yo'q. Haqiqiy pulda faqat `TREND_LIVE_OK=1` bilan.

```bash
python3 backtest.py                  # 1) avval strategiyani Binance tarixida sinang (14 kun)
python3 backtest.py --days 30 --sweep  #    30 kun + bir nechta sozlamani solishtirish
caffeinate -i python3 trend_bot.py   # 2) demo'da ishga tushirish
python3 trend_bot.py --stats         #    statistika
python3 trend_bot.py --close         #    hamma pozitsiyani yopish
```
⚠️ Bot to'xtatilsa, birjadagi SL joyida qoladi, lekin **endi siljimaydi**.

### Backtest nima ko'rsatadi
`backtest.py` botdagi **aynan o'sha** qoidalarni Binance'ning haqiqiy 5m tarixida o'ynaydi
(komissiya 0.05%+0.05%, SL da 0.05% sirpanish, sham ichida avval SL tekshiriladi). Sintetik tasodifiy
bozorlarda bu strategiya o'rtacha **komissiya miqdorida yutqazadi** (median −33…−44%) — ya'ni foyda
faqat haqiqiy bozorda trendlar davom etsa bo'ladi. Buni faqat haqiqiy tarix ko'rsatadi: avval backtest, keyin demo.
`--sweep` dagi eng yaxshi qator o'tmishga "moslashgan" bo'lishi mumkin — uni demo'da tasdiqlang.

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| `TREND_INTERVAL_MIN` | 15 | Necha daqiqada bir yangi savdo (10–15) |
| `TREND_MARGIN_PCT` | 10 | Har savdoga balansning necha foizi marja |
| `TREND_LEVERAGE` | 20 | Leverage |
| `TREND_SL_PCT` | 1 | Boshlang'ich SL (narx %) |
| `TREND_STEP_PCT` | 1 | Har necha % foydada SL siljiydi |
| `TREND_TP_PCT` | 0 | TP (0 = yo'q) |
| `TREND_MAX_OPEN` | 3 | Bir vaqtda nechta savdo |
| `TREND_DAILY_LOSS_PCT` | 15 | Kunlik zarar limiti |
| `TREND_SCAN_COINS` | 20 | Nechta eng likvid coin tekshiriladi |

## ⚡ Razgon bot (`razgon_bot.py`)
Har daqiqada 1 ta savdo ochadi va sof foydasi (komissiyalardan keyin) **+0.1%** bo'lishi bilan yopadi.
- Coin: tanlangan coinlardan eng likvid 15 tasi ichida **1 daqiqalik trendi eng kuchlisi**; yo'nalish — trend bo'yicha
  (RSI > 75 da LONG, RSI < 25 da SHORT ochilmaydi)
- Marja balansning **5%** i × **20x** → pozitsiya ≈ balansning 100%
- TP: narx **+0.2%** (sof +0.1%), SL: narx **−2%**
- Bir vaqtda **5 tagacha** savdo; bugungi zarar **20%** ga yetsa — ertagacha to'xtaydi
- Savdolar alohida faylga yoziladi: `trades_razgon_binance_demo.csv`

```bash
caffeinate -i python3 razgon_bot.py   # ishga tushirish
python3 razgon_bot.py --stats         # razgon statistikasi
python3 razgon_bot.py --close         # hamma ochiq pozitsiyani yopish
```
**Asosiy bot bilan bir vaqtda, bitta hisobda ishga tushirmang** — ular bir-birining pozitsiyalarini ko'radi.
Haqiqiy pulda (`MODE=live`) faqat `.env` da `RAZGON_LIVE_OK=1` bo'lsa ishlaydi.

### ⚠️ Hisob (narx tasodifiy harakat qilsa)
| | |
|---|---|
| Yutuqli savdolar | ~91% |
| Bitta yutuq / bitta zarar | +0.1% / −2.1% balans |
| O'rtacha natija | **−0.1% balans har savdoda** (komissiya) |
| 1 kun (~400 savdo), median | **−34%** |
| 7 kun, median | **−95%** |

Savdo qancha ko'p bo'lsa, komissiya shuncha ko'p yeydi. Demo'da natijani `--stats` dagi **Sof natija** bilan kuzating.

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| `RAZGON_MARGIN_PCT` | 5 | Har savdoga balansning necha foizi marja |
| `RAZGON_LEVERAGE` | 20 | Leverage |
| `RAZGON_PROFIT_PCT` | 0.1 | Sof foyda (pozitsiyadan %) — shunda yopiladi |
| `RAZGON_SL_PCT` | 2 | SL (narx %) |
| `RAZGON_MAX_OPEN` | 5 | Bir vaqtda nechta savdo |
| `RAZGON_DAILY_LOSS_PCT` | 20 | Kunlik zarar limiti (balansdan %) |
| `RAZGON_SCAN_COINS` | 15 | Har daqiqada nechta coin tekshiriladi |

## Rejimlar
| `MODE` | Nima | Kalit |
|---|---|---|
| `paper` | Haqiqiy narxlar, virtual balans (bot ichida) | kerak emas |
| `demo` | Binance Demo Trading — virtual pul, haqiqiy birja orderlari | demo.binance.com kalitlari |
| `live` | Haqiqiy pul | asosiy hisob kalitlari |

### Binance demo
1. https://demo.binance.com → Profil → **Управление API** → kalit yarating (**Включить фьючерсы** ✅).
2. Futures sozlamalarida **Односторонний режим** (One-way) yoqilgan bo'lsin.
3. `.env` ga `EXCHANGE=binance`, `MODE=demo` va kalitlarni yozing.

## Xavfsizlik
- Bot qayta ishga tushirilganda birjada ochiq qolgan pozitsiyalar kuzatiladi, lekin ularga **martingeyl qo'shilmaydi**
  (oldingi holat noma'lum) — ular birjadagi SL/TP bilan yopiladi.
- MEXC live rejimida martingeyl o'chiq (sinalmagan).
- API kalitga **Withdraw ruxsatini bermang**, IP cheklovini qo'ying.
- SL/TP birjaga qo'yiladi; SL qo'yilmasa, pozitsiya darhol yopiladi (Binance).
- MEXC'da futures demo API yo'q — u yerda `paper` rejimdan foydalaning. MEXC live sinalmagan.
- Bot to'xtatilganda ochiq pozitsiyalar birjada SL/TP bilan qoladi: `--stats` bilan ko'ring, `--close` bilan yoping.
