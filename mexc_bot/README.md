# All-in scalping bot (MEXC / Binance futures)

⚠️ **Eng xavfli razgon usuli.** 20x leverage bilan narx ~4.6% qarshi yursa, butun marja ketadi.
Faqat yo'qotishga tayyor pul bilan ishlating. Bu moliyaviy maslahat emas.

## Rejimlar
| `MODE` | Nima | Kalit |
|---|---|---|
| `paper` | Haqiqiy narxlar, virtual balans (bot ichida) | kerak emas |
| `demo` | **Binance Demo Trading** — virtual pul, haqiqiy birja orderlari | demo.binance.com kalitlari |
| `live` | Haqiqiy pul | asosiy hisob kalitlari |

## Binance demo bilan sinash
1. https://demo.binance.com ga Binance akkauntingiz bilan kiring.
2. Profil → **API Management** → yangi API kalit yarating (bu demo kalit, asosiy hisobniki emas).
3. Futures demo hisobida USDT balans borligini tekshiring.
4. Futures sozlamalarida **One-way mode** yoqilgan bo'lsin (Hedge mode emas).
5. Ishga tushiring:

```bash
cd mexc_bot
pip install -r requirements.txt
cp .env.example .env      # EXCHANGE=binance, MODE=demo va kalitlarni yozing
python allin_bot.py
```

Bot ochgan pozitsiya va SL/TP orderlarni demo.binance.com da ko'rasiz.

## Strategiya
- Har daqiqada **20 ta coin** tahlil qilinadi (BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, DOT,
  LTC, TRX, NEAR, SUI, APT, ARB, OP, FIL, ATOM, AAVE). Ro'yxatni `.env` dagi `SYMBOLS` bilan o'zgartirish mumkin
- 1m shamlar: EMA9 / EMA21 kesishishi + RSI filtri
- Bir nechta coinda signal bo'lsa — ro'yxatdagi birinchisi (eng likvidi) tanlanadi
- Bir vaqtda faqat **bitta** pozitsiya (all-in)
- Depozitning 95% i marja, isolated, 20x
- TP +1% narx (≈ +20% depozit), SL −0.5% narx (≈ −10% depozit)
- SL/TP birjaga qo'yiladi; SL qo'yilmasa, pozitsiya darhol yopiladi (Binance)
- To'xtash: 4x maqsad, ketma-ket 3 zarar yoki balans < 5 USDT

## Sozlamalar (.env)
| O'zgaruvchi | Ma'nosi |
|---|---|
| `EXCHANGE` | `binance` yoki `mexc` |
| `SYMBOLS` | Coinlar ro'yxati, masalan `BTC,ETH,SOL` (bo'sh = 20 ta standart) |
| `LEVERAGE` | Leverage (bot SL likvidatsiyadan oldin turishini tekshiradi) |
| `MARGIN_SHARE` | Balansning qancha qismi bitta savdoga (1 = to'liq all-in) |
| `TP_PCT` / `SL_PCT` | Narx o'zgarishi foizi |
| `TARGET_X` | Balans necha baravar bo'lsa to'xtash |
| `MAX_LOSSES_IN_ROW` | Ketma-ket nechta zarardan keyin to'xtash |

## Xavfsizlik
- API kalitga **Withdraw ruxsatini bermang**, IP cheklovini qo'ying.
- MEXC'da futures demo API yo'q — u yerda `paper` rejimdan foydalaning.
- Bot to'xtatilganda ochiq pozitsiya va orderlarni ilovada tekshiring.
- Ochiq pozitsiyani darhol yopish: `python3 allin_bot.py --close` (SL/TP orderlar ham bekor qilinadi).
