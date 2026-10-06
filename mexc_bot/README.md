# Futures scalping bot (Binance / MEXC)

Har bir savdoga balansning **kichik qismi (standart 1%)** tikiladi, shuning uchun
balansning katta qismi doim bo'sh qoladi va bot bir vaqtda bir nechta coinda savdo qila oladi.
Bu moliyaviy maslahat emas. Avval `paper` yoki `demo` rejimda sinab ko'ring.

## Strategiya
- Har bir yangi 5 daqiqalik sham yopilganda **20 ta coin** tahlil qilinadi
  (BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, DOT, LTC, TRX, NEAR, SUI, APT, ARB, OP, FIL, ATOM, AAVE)
- Signal: EMA9 / EMA21 kesishishi + RSI filtri
- Marja = balansning **1%**, leverage **10x**, isolated
- **TP**: narx **+3%** foyda tomonga yursa (Binance'da ROI ≈ +30%)
- **SL**: narx **−1%** qarshi tomonga yursa (ROI ≈ −10%)
- Bir vaqtda **5 tagacha** savdo, har bir coinda bittadan
- Yopilgan coin kamida bitta sham davomida qayta ochilmaydi
- Bugungi zarar balansning **3%** iga yetsa — ertagacha yangi savdo ochilmaydi (ochiqlari kuzatiladi)

### 5 000 USDT balansda bitta savdo
| | USDT |
|---|---|
| Marja (balansning 1%) | 50 |
| Pozitsiya (50 × 10x) | 500 |
| TP bo'lsa | ≈ +14.5 (komissiya bilan) |
| SL bo'lsa | ≈ −5.5 (komissiya bilan) |
| 5 ta savdo ochiq bo'lsa ham bo'sh qoladi | ≈ 4 750 |

## Buyruqlar
```bash
cd ~/YunusjonAI/mexc_bot
source .venv/bin/activate

caffeinate -i python3 allin_bot.py   # botni ishga tushirish (Mac uxlab qolmaydi)
python3 allin_bot.py --stats         # statistika
python3 allin_bot.py --close         # barcha ochiq pozitsiyalarni yopish
python3 allin_bot.py --close SOL     # faqat SOL ni yopish
```
`--stats` va `--close` ni bot ishlab turganda **yangi terminal oynasida** (Cmd+T) ishlating.

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
| `SL_PCT` | 1 | Narx necha % qarshi yursa yopiladi |
| `MAX_POSITIONS` | 5 | Bir vaqtda nechta savdo |
| `DAILY_LOSS_PCT` | 3 | Kunlik zarar limiti (balansdan %) |
| `TIMEFRAME` | 5m | Shamlar |
| `STATUS_MINUTES` | 5 | Holat qatori necha daqiqada bir |
| `SYMBOLS` | 20 ta coin | Masalan `BTC,ETH,SOL` |

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
- API kalitga **Withdraw ruxsatini bermang**, IP cheklovini qo'ying.
- SL/TP birjaga qo'yiladi; SL qo'yilmasa, pozitsiya darhol yopiladi (Binance).
- MEXC'da futures demo API yo'q — u yerda `paper` rejimdan foydalaning. MEXC live sinalmagan.
- Bot to'xtatilganda ochiq pozitsiyalar birjada SL/TP bilan qoladi: `--stats` bilan ko'ring, `--close` bilan yoping.
