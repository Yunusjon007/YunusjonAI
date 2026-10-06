# MEXC All-in scalping bot

⚠️ **Eng xavfli razgon usuli.** 20x leverage bilan narx ~4.6% qarshi yursa, butun marja ketadi.
Faqat yo'qotishga tayyor pul bilan ishlating. Bu moliyaviy maslahat emas.

## Ishga tushirish

```bash
cd mexc_bot
pip install -r requirements.txt
cp .env.example .env      # sozlamalarni tahrirlang
python allin_bot.py       # MODE=paper — virtual 100 USDT bilan
```

Kamida 1–2 hafta `paper` rejimda kuzating. Keyin `.env` da `MODE=live` va API kalitlarni yozing.

## Strategiya
- 1m shamlar: EMA9 / EMA21 kesishishi + RSI filtri
- Depozitning 95% i marja, isolated, 20x
- TP +1% narx (≈ +20% depozit), SL −0.5% narx (≈ −10% depozit)
- To'xtash: 4x maqsad, ketma-ket 3 zarar yoki balans < 5 USDT

## Sozlamalar (.env)
| O'zgaruvchi | Ma'nosi |
|---|---|
| `LEVERAGE` | Leverage (bot SL likvidatsiyadan oldin turishini tekshiradi) |
| `MARGIN_SHARE` | Balansning qancha qismi bitta savdoga (1 = to'liq all-in) |
| `TP_PCT` / `SL_PCT` | Narx o'zgarishi foizi |
| `TARGET_X` | Balans necha baravar bo'lsa to'xtash |
| `MAX_LOSSES_IN_ROW` | Ketma-ket nechta zarardan keyin to'xtash |

## Xavfsizlik
- API kalitga **Withdraw ruxsatini bermang**, IP cheklovini qo'ying.
- SL/TP birjaga ham qo'yiladi, lekin birinchi live savdoda MEXC ilovasida ko'rinishini tekshiring.
- Bot to'xtatilganda ochiq pozitsiyani ilovada tekshiring.
