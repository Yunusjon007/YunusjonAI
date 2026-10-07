"""
Swing bot — 2–3 kunlik trendlarni ushlab razgon qilish (trendga qo'shib borish / piramida).

Har yangi 1 soatlik sham yopilganda tanlangan coinlar (universe.py) tekshiriladi:
  - yo'nalish 4h grafikda: EMA50 > EMA200 bo'lsa faqat LONG, EMA50 < EMA200 bo'lsa faqat SHORT
  - kirish 1h grafikda: narx oxirgi SWING_BREAKOUT_BARS (48) soatning eng yuqori nuqtasini yorsa LONG
    (eng pastini yorsa SHORT). Bir nechta coin bo'lsa — yorish chuqurligi (ATR da) + trend kuchi bo'yicha
  - SL = SWING_STOP_ATR (2.5) × ATR(1h). Hajm risk bo'yicha: SL urilsa balansning SWING_RISK_PCT (2%) i ketadi
  - piramida (razgon): narx har +SWING_ADD_ATR (1) × ATR yurganda xuddi shunday yana bir qism qo'shiladi,
    jami SWING_MAX_UNITS (3) qismgacha; butun pozitsiya SL i oxirgi qo'shimchadan 2.5 × ATR ga ko'tariladi
  - chandelier: SL = eng yaxshi narx − SWING_TRAIL_ATR (3) × ATR, faqat foyda tomonga siljiydi. TP yo'q —
    trend tugaguncha ushlab turiladi
  - balans maqsadi: balans (ochiq savdolar bilan) boshlang'ichdan SWING_TARGET_PCT (10%) ga oshsa —
    hamma pozitsiya yopiladi, keyingi maqsad yangi balansdan hisoblanadi
  - bir vaqtda SWING_MAX_OPEN (3) coin, marja limiti SWING_MAX_MARGIN_PCT (80%), leverage SWING_LEVERAGE (10x),
    kunlik zarar limiti SWING_DAILY_LOSS_PCT (15%)

Buyruqlar:
  python3 swing_bot.py                ishga tushirish
  python3 swing_bot.py --stats        statistika
  python3 swing_bot.py --close        barcha ochiq pozitsiyalarni yopish (--close SOL — bittasini)
  python3 backtest.py --swing         shu strategiyani Binance tarixida sinash (standart 90 kun)

Haqiqiy pulda (MODE=live) faqat .env da SWING_LIVE_OK=1 bo'lsa ishlaydi.
Boshqa botlar bilan bir vaqtda, bitta hisobda ishga tushirmang.
"""
import argparse
import logging
import logging.handlers
import os
import sys

import ccxt

import allin_bot as core
import trend_bot as tb

log = logging.getLogger("bot")

BREAKOUT_BARS = core.env("SWING_BREAKOUT_BARS", 48, int)     # 1h shamlar (48 = 2 kun)
STOP_ATR = core.env("SWING_STOP_ATR", 2.5, float)            # boshlang'ich SL = 2.5 × ATR
TRAIL_ATR = core.env("SWING_TRAIL_ATR", 3.0, float)          # chandelier: eng yaxshi narx − 3 × ATR
ADD_ATR = core.env("SWING_ADD_ATR", 1.0, float)              # har +1 ATR da yangi qism
MAX_UNITS = core.env("SWING_MAX_UNITS", 3, int)              # 1 kirish + 2 qo'shimcha
RISK_PCT = core.env("SWING_RISK_PCT", 2.0, float)            # har qism uchun risk, balansdan %
LEVERAGE = core.env("SWING_LEVERAGE", 10, int)
MAX_OPEN = core.env("SWING_MAX_OPEN", 3, int)
MAX_MARGIN_PCT = core.env("SWING_MAX_MARGIN_PCT", 80.0, float)
TARGET_PCT = core.env("SWING_TARGET_PCT", 10.0, float)       # balans maqsadi (0 = o'chiq)
DAILY_LOSS_PCT = core.env("SWING_DAILY_LOSS_PCT", 15.0, float)
SCAN_COINS = core.env("SWING_SCAN_COINS", 20, int)

ENTRY_TF, TREND_TF = "1h", "4h"
ATR_PERIOD, EMA_FAST4, EMA_SLOW4 = 14, 50, 200
H4_HISTORY = 600   # EMA200 to'liq "yetilishi" uchun 4h shamlar soni
_baseline = [None]  # balans maqsadi hisoblanadigan boshlang'ich balans


# ---------------------------------------------------------------- sof qoidalar (bot va backtest uchun umumiy)

def swing_decide(fast4, slow4, close, prev_high, prev_low, atr_value):
    """4h trend + 1h yorish bo'yicha qaror: dict(side, score, stop_pct, atr) yoki None."""
    if not atr_value or atr_value <= 0 or fast4 is None or slow4 is None or prev_high is None:
        return None
    if fast4 > slow4 and close > prev_high:
        side, depth = "long", (close - prev_high) / atr_value
    elif fast4 < slow4 and close < prev_low:
        side, depth = "short", (prev_low - close) / atr_value
    else:
        return None
    return dict(side=side, score=depth + abs(fast4 - slow4) / slow4 * 100,
                stop_pct=STOP_ATR * atr_value / close * 100, atr=atr_value)


def swing_signal(h1, h4):
    """Yopilgan 1h va 4h shamlar bo'yicha qaror."""
    if len(h1) < BREAKOUT_BARS + ATR_PERIOD + 2 or len(h4) < EMA_SLOW4 + 2:
        return None
    closes4 = [c[4] for c in h4]
    highs = [c[2] for c in h1]
    lows = [c[3] for c in h1]
    closes = [c[4] for c in h1]
    return swing_decide(core.ema(closes4, EMA_FAST4)[-1], core.ema(closes4, EMA_SLOW4)[-1], closes[-1],
                        max(highs[-BREAKOUT_BARS - 1:-1]), min(lows[-BREAKOUT_BARS - 1:-1]),
                        tb.atr(highs, lows, closes, ATR_PERIOD))


# ---------------------------------------------------------------- bot ulanishlari

def swing_scan(exchange, symbols):
    """Har yangi 1h shamda: trend bo'yicha yorish bo'lgan coinlar, kuchlisi birinchi."""
    found, longs, shorts = [], 0, 0
    for symbol in symbols:
        try:
            h1 = exchange.fetch_ohlcv(symbol, ENTRY_TF, limit=BREAKOUT_BARS + ATR_PERIOD + 10)
            h4 = exchange.fetch_ohlcv(symbol, TREND_TF, limit=H4_HISTORY + 1)
        except ccxt.BaseError as e:
            log.warning("%s: shamlarni olib bo'lmadi: %s", core.short(symbol), e)
            continue
        sig = swing_signal(h1[:-1], h4[:-1])  # oxirgi shamlar hali yopilmagan
        if not sig:
            continue
        longs, shorts = longs + (sig["side"] == "long"), shorts + (sig["side"] == "short")
        found.append((sig["score"], symbol, sig))
    found.sort(key=lambda x: -x[0])
    signals = [(symbol, sig["side"], {"stop_pct": sig["stop_pct"], "risk_pct": RISK_PCT,
                                      "meta": {"atr": sig["atr"], "add_tag": "P"}})
               for _, symbol, sig in found]
    return signals, f"48 soatlik yorish: {longs} ta LONG, {shorts} ta SHORT"


def manage_swing(exchange, broker, balance):
    """Balans maqsadi, piramida (trendga qo'shish) va chandelier SL. Yopilganlarni qaytaradi."""
    closed = []
    if _baseline[0] is None:
        _baseline[0] = balance
    if TARGET_PCT > 0 and broker.positions and balance >= _baseline[0] * (1 + TARGET_PCT / 100):
        log.info("🎯 Balans %.2f USDT — maqsad bajarildi (+%.4g%%, boshlanish %.2f). Hamma pozitsiya yopiladi.",
                 balance, TARGET_PCT, _baseline[0])
        for symbol in list(broker.positions):
            try:
                closed.append(broker.close(symbol, "MAQSAD"))
            except (ccxt.AuthenticationError, ccxt.PermissionDenied):
                raise
            except ccxt.BaseError as e:
                log.error("%s: yopib bo'lmadi: %s", core.short(symbol), e)
        _baseline[0] = None  # keyingi maqsad yangi balansdan
        return closed

    cap = balance * core.MAX_MARGIN_PCT / 100
    for symbol, p in list(broker.positions.items()):
        if p.get("adopted") or not p.get("atr"):
            continue
        sign = 1 if p["side"] == "long" else -1
        atr, price = p["atr"], p["last"]
        p.setdefault("best", p["entry0"])
        p.setdefault("last_add", p["entry0"])
        if sign * (price - p["best"]) > 0:
            p["best"] = price
        try:
            # piramida: trend tasdiqlansa — yana bir qism
            if (p["adds"] < MAX_UNITS - 1 and p.get("pyr_failed") != p["adds"]
                    and sign * (price - p["last_add"]) >= ADD_ATR * atr):
                try:
                    contracts = float(exchange.amount_to_precision(symbol, p["base_contracts"]))
                    qty = contracts * core.contract_size(exchange, symbol)
                    if core.used_margin(broker) + qty * price / core.LEVERAGE > cap:
                        raise ccxt.InsufficientFunds(f"marja limiti ({core.MAX_MARGIN_PCT:.4g}%)")
                    broker.add(symbol, contracts, qty, price)
                except (ccxt.AuthenticationError, ccxt.PermissionDenied):
                    raise
                except ccxt.BaseError as e:
                    p["pyr_failed"] = p["adds"]
                    log.warning("%s: qism qo'shilmadi (%s) — pozitsiya shu holicha qoladi.", core.short(symbol), e)
                else:
                    p["last_add"] = price
                    new_sl = price - sign * STOP_ATR * atr
                    sl = new_sl if sign * (new_sl - p["sl"]) > 0 else p["sl"]
                    broker.protect(symbol, sl, p["tp"])
                    log.info("➕ %s %s: %d/%d qism qo'shildi @ %s | o'rtacha %s | SL %s",
                             core.short(symbol), p["side"].upper(), p["adds"] + 1, MAX_UNITS, core.fmt_price(price),
                             core.fmt_price(p["entry"]), core.fmt_price(sl))
                    continue
            # chandelier: eng yaxshi narxdan TRAIL_ATR × ATR orqada (0.25 ATR dan kam o'zgarish — e'tiborsiz)
            chandelier = p["best"] - sign * TRAIL_ATR * atr
            if sign * (chandelier - p["sl"]) >= 0.25 * atr:
                broker.protect(symbol, chandelier, p["tp"])
                p["trail_steps"] = p.get("trail_steps", 0) + 1
                locked = sign * (chandelier - p["entry"]) / p["entry"] * 100
                log.info("🔒 %s %s: SL %s ga siljidi (o'rtacha narxdan %+.2f%%)", core.short(symbol),
                         p["side"].upper(), core.fmt_price(chandelier), locked)
        except (ccxt.AuthenticationError, ccxt.PermissionDenied):
            raise
        except ccxt.BaseError as e:
            log.error("%s: pozitsiyani boshqarib bo'lmadi: %s", core.short(symbol), e)
    return closed


def log_settings(balance):
    log.info("📈 SWING: 4h trend (EMA%d/EMA%d) + 1h yorish (%d soat) | har qism riski %.4g%% balans | "
             "SL %.4g×ATR | piramida %d qismgacha (har +%.4g ATR) | chandelier %.4g×ATR | %dx | max %d coin | "
             "marja limiti %.4g%% | balans maqsadi %s | kunlik zarar limiti %.4g%%",
             EMA_FAST4, EMA_SLOW4, BREAKOUT_BARS, RISK_PCT, STOP_ATR, MAX_UNITS, ADD_ATR, TRAIL_ATR, LEVERAGE,
             MAX_OPEN, MAX_MARGIN_PCT, f"+{TARGET_PCT:.4g}%" if TARGET_PCT > 0 else "yo'q", DAILY_LOSS_PCT)
    risk = balance * RISK_PCT / 100
    log.info("Hozirgi balansda: bitta qism SL bo'lsa ≈ −%.2f USDT (komissiyasiz); %d qism to'liq bo'lsa, "
             "SL oxirgi qo'shimchadan %.4g ATR orqada turadi", risk, MAX_UNITS, STOP_ATR)


def configure():
    """Asosiy bot sozlamalarini swing strategiyasiga moslaydi."""
    core.TIMEFRAME = ENTRY_TF
    core.LEVERAGE = LEVERAGE
    core.TP_PCT = 0.0
    core.SL_PCT = min(3.0, 100 / LEVERAGE - core.MAINTENANCE_MARGIN_PCT - 0.5)  # faqat tekshiruv uchun
    core.MARTINGALE_STEPS = 0
    core.MAX_POSITIONS = MAX_OPEN
    core.MAX_MARGIN_PCT = MAX_MARGIN_PCT
    # run() dagi taxminiy marja tekshiruvi uchun: odatiy ~3% SL dagi bitta qism marjasi
    core.MARGIN_PCT = min(MAX_MARGIN_PCT, RISK_PCT / 3.0 * 100 / LEVERAGE)
    core.DAILY_LOSS_PCT = DAILY_LOSS_PCT
    core.JOURNAL_PATH = core.HERE / f"trades_swing_{core.EXCHANGE}_{core.MODE}.csv"
    core.LOG_PATH = core.HERE / f"swing_{core.EXCHANGE}_{core.MODE}.log"
    core.SETTINGS_LOGGER = log_settings


def validate():
    core.validate_config()
    if RISK_PCT <= 0 or STOP_ATR <= 0 or TRAIL_ATR <= 0 or ADD_ATR <= 0 or MAX_UNITS < 1:
        sys.exit("SWING_RISK_PCT, SWING_STOP_ATR, SWING_TRAIL_ATR, SWING_ADD_ATR 0 dan katta, "
                 "SWING_MAX_UNITS kamida 1 bo'lishi kerak.")
    if BREAKOUT_BARS < 5:
        sys.exit("SWING_BREAKOUT_BARS kamida 5 bo'lishi kerak.")


def main():
    parser = argparse.ArgumentParser(description="Swing bot: 2–3 kunlik trend + piramida (razgon)")
    parser.add_argument("--stats", action="store_true", help="swing bot statistikasi")
    parser.add_argument("--close", nargs="?", const="ALL", metavar="COIN",
                        help="ochiq pozitsiyalarni yopish (hammasi yoki bitta coin: --close SOL)")
    args = parser.parse_args()
    configure()

    handlers = [logging.StreamHandler()]
    if not args.stats:
        handlers.append(logging.handlers.RotatingFileHandler(core.LOG_PATH, maxBytes=5_000_000, backupCount=3,
                                                             encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
                        handlers=handlers)
    journal = core.Journal(core.JOURNAL_PATH)

    if args.stats:
        live = None
        if core.MODE != "paper" and core.has_keys():
            try:
                live = core.live_snapshot(core.make_exchange())
            except ccxt.BaseError as e:
                print(f"Birjaga ulanib bo'lmadi, faqat jurnal ko'rsatiladi: {e}")
        core.print_stats(journal, live)
        return

    if core.MODE == "live" and os.getenv("SWING_LIVE_OK") != "1":
        sys.exit("Swing bot haqiqiy pulda faqat .env da SWING_LIVE_OK=1 bo'lsa ishlaydi. Avval demo'da sinang.")
    validate()
    exchange = core.make_exchange()
    broker = core.make_broker(exchange)
    if args.close:
        core.close_positions(exchange, broker, journal, None if args.close == "ALL" else args.close)
        return
    if not getattr(broker, "supports_martingale", False):
        sys.exit("Swing bot faqat Binance (demo/live) yoki paper rejimda ishlaydi: MEXC'da SL ni siljitish va "
                 "pozitsiyaga qo'shish qo'llab-quvvatlanmaydi.")
    log.warning("Strategiya foydasini avval tarixda tekshiring: python3 backtest.py --swing  "
                "(boshqa botlar shu hisobda ishlayotgan bo'lsa — ularni to'xtating)")
    if core.MODE == "live":
        log.warning("⚠️  LIVE rejim: haqiqiy pul bilan savdo. To'xtatish uchun Ctrl+C.")
    try:
        core.run(exchange, broker, journal, pick_coins=lambda ex: core.choose_coins(ex)[:SCAN_COINS],
                 scan_fn=swing_scan, manage_fn=manage_swing)
    except KeyboardInterrupt:
        if core.MODE == "paper":
            log.info("To'xtatildi. (paper rejim: virtual pozitsiyalar yopilmagan holda qoldi)")
        else:
            log.info("To'xtatildi. Ochiq pozitsiyalar birjada SL bilan qoladi (SL endi siljimaydi, qism "
                     "qo'shilmaydi!). Ko'rish: python3 swing_bot.py --stats, yopish: python3 swing_bot.py --close")


if __name__ == "__main__":
    main()
