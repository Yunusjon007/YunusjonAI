# Futures scalping bot (Binance / MEXC)

Har bir savdoga balansning **kichik qismi (standart 1%)** tikiladi, shuning uchun
balansning katta qismi doim bo'sh qoladi va bot bir vaqtda bir nechta coinda savdo qila oladi.
Bu moliyaviy maslahat emas. Avval `paper` yoki `demo` rejimda sinab ko'ring.

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
