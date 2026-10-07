"""
Trend bot — 5 daqiqalik razgon strategiyasi: kuchli trend bo'yicha kirish + har 1% foydada SL ni siljitish.

Har TREND_INTERVAL_MIN (15) daqiqada, 5 daqiqalik sham yopilganda:
  - tanlangan coinlar ichidan (universe.py; eng likvid TREND_SCAN_COINS tasi) eng kuchli trenddagisi olinadi:
      LONG:  EMA20 > EMA50, narx EMA20 dan yuqorida, RSI 50–75
      SHORT: EMA20 < EMA50, narx EMA20 dan pastda,  RSI 25–50
      kuch = |EMA20 − EMA50| / ATR14 + 0.5 × hajm nisbati (oxirgi sham / 20 sham o'rtachasi, max 3)
    mos coin bo'lmasa — o'sha navbat o'tkazib yuboriladi
  - marja = balansning TREND_MARGIN_PCT (10%) i × TREND_LEVERAGE (20x), isolated
  - boshlang'ich SL: narx TREND_SL_PCT (1%) qarshi
  - SL zinapoyasi: foyda har TREND_STEP_PCT (1%) ga yetganda SL bir pog'ona siljiydi:
      +1% → zararsiz nuqta (kirish + komissiya), +2% → SL +1%, +3% → SL +2%, ...
  - TP yo'q (TREND_TP_PCT=0): trend davom etguncha foyda o'sadi, SL orqasidan keladi
  - bir vaqtda TREND_MAX_OPEN (3) tagacha; bugungi zarar TREND_DAILY_LOSS_PCT (15%) ga yetsa ertagacha to'xtaydi

Buyruqlar:
  python3 trend_bot.py              ishga tushirish
  python3 trend_bot.py --stats      statistika
  python3 trend_bot.py --close      barcha ochiq pozitsiyalarni yopish (--close SOL — bittasini)
  python3 backtest.py               shu strategiyani Binance tarixida sinash

Haqiqiy pulda (MODE=live) faqat .env da TREND_LIVE_OK=1 bo'lsa ishlaydi.
Boshqa botlar bilan bir vaqtda, bitta hisobda ishga tushirmang.
"""
import argparse
import logging
import logging.handlers
import os
import sys
import time

import ccxt

import allin_bot as core

log = logging.getLogger("bot")

INTERVAL_MIN = core.env("TREND_INTERVAL_MIN", 15.0, float)   # necha daqiqada bir yangi savdo
MARGIN_PCT = core.env("TREND_MARGIN_PCT", 10.0, float)       # har savdoga balansning necha foizi marja
LEVERAGE = core.env("TREND_LEVERAGE", 20, int)
SL_PCT = core.env("TREND_SL_PCT", 1.0, float)                # boshlang'ich SL (narx %)
STEP_PCT = core.env("TREND_STEP_PCT", 1.0, float)            # har necha % foydada SL siljiydi
TP_PCT = core.env("TREND_TP_PCT", 0.0, float)                # 0 = TP yo'q
MAX_OPEN = core.env("TREND_MAX_OPEN", 3, int)
DAILY_LOSS_PCT = core.env("TREND_DAILY_LOSS_PCT", 15.0, float)
SCAN_COINS = core.env("TREND_SCAN_COINS", 20, int)

TIMEFRAME = "5m"
EMA_FAST, EMA_SLOW, ATR_PERIOD, VOL_PERIOD = 20, 50, 14, 20
HISTORY = EMA_SLOW * 3  # signal uchun nechta sham yuklanadi
CLOCK = time.time       # sinovlarda almashtiriladi
_last_entry = [None]    # oxirgi savdo navbati vaqti (soniya)


def be_pct():
    """Zararsiz nuqta: kirish + ikki tomon komissiyasi + sirpanish uchun zaxira (narx %)."""
    return 2 * core.FEE_PCT + 0.02


# ---------------------------------------------------------------- sof qoidalar (bot va backtest uchun umumiy)

def atr(highs, lows, closes, period=ATR_PERIOD):
    trs = [max(h - l, abs(h - pc), abs(l - pc)) for h, l, pc in zip(highs[1:], lows[1:], closes[:-1])]
    if len(trs) < period:
        return 0.0
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def decide(fast, slow, close, rsi_value, atr_value, volume, avg_volume):
    """Indikatorlar bo'yicha qaror: ('long'|'short', kuch) yoki None."""
    if atr_value <= 0:
        return None
    if fast > slow and close > fast and 50 <= rsi_value <= 75:
        side = "long"
    elif fast < slow and close < fast and 25 <= rsi_value <= 50:
        side = "short"
    else:
        return None
    vol_ratio = volume / avg_volume if avg_volume > 0 else 1.0
    return side, abs(fast - slow) / atr_value + 0.5 * min(vol_ratio, 3.0)


def trend_signal(candles):
    """Yopilgan 5m shamlar [ts, o, h, l, c, v] bo'yicha qaror: (side, kuch) yoki None."""
    if len(candles) < EMA_SLOW + VOL_PERIOD + 2:
        return None
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    closes = [c[4] for c in candles]
    vols = [c[5] or 0 for c in candles]
    return decide(core.ema(closes, EMA_FAST)[-1], core.ema(closes, EMA_SLOW)[-1], closes[-1],
                  core.rsi(closes, core.RSI_PERIOD), atr(highs, lows, closes), vols[-1],
                  sum(vols[-VOL_PERIOD - 1:-1]) / VOL_PERIOD)


def trail_stop(side, entry, profit_pct, step_pct, be):
    """SL zinapoyasi. Foyda k pog'onaga (k × step) yetganda: (k, yangi SL narxi); hali yetmagan bo'lsa (0, None).
    k=1 → zararsiz nuqta (be %), k≥2 → (k−1) × step % foyda qulflanadi."""
    k = int(profit_pct // step_pct) if profit_pct > 0 else 0
    if k < 1:
        return 0, None
    lock = (k - 1) * step_pct if k > 1 else be
    sign = 1 if side == "long" else -1
    return k, entry * (1 + sign * lock / 100)


# ---------------------------------------------------------------- bot ulanishlari

def trend_scan(exchange, symbols):
    """Har INTERVAL_MIN daqiqada eng kuchli trenddagi bitta coinni qaytaradi."""
    now = CLOCK()
    if _last_entry[0] is not None and now - _last_entry[0] < INTERVAL_MIN * 60 - 30:
        left = INTERVAL_MIN - (now - _last_entry[0]) / 60
        return [], f"keyingi savdo navbati ~{left:.0f} daqiqadan keyin"
    best, longs, shorts = None, 0, 0
    for symbol in symbols:
        try:
            candles = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=HISTORY + 1)
        except ccxt.BaseError as e:
            log.warning("%s: shamlarni olib bo'lmadi: %s", core.short(symbol), e)
            continue
        sig = trend_signal(candles[:-1])  # oxirgi sham hali yopilmagan
        if sig is None:
            continue
        side, score = sig
        longs, shorts = longs + (side == "long"), shorts + (side == "short")
        if best is None or score > best[2]:
            best = (symbol, side, score)
    report = f"trend sharti: {longs} ta LONG, {shorts} ta SHORT"
    if best is None:
        return [], report + " — mos coin yo'q, navbat o'tkazildi"
    _last_entry[0] = now
    return [(best[0], best[1])], f"{report} | eng kuchli: {core.short(best[0])} (kuch {best[2]:.2f})"


def manage_trailing(exchange, broker, balance):
    """Har bir ochiq pozitsiyada foyda yangi pog'onaga yetsa — SL ni siljitadi (birjada ham)."""
    for symbol, p in list(broker.positions.items()):
        if p.get("adopted") or p.get("sl") is None:
            continue
        try:
            sign = 1 if p["side"] == "long" else -1
            profit = sign * (p["last"] - p["entry0"]) / p["entry0"] * 100
            k, new_sl = trail_stop(p["side"], p["entry0"], profit, STEP_PCT, be_pct())
            if k <= p.get("trail_steps", 0):
                continue
            if sign * (new_sl - p["sl"]) <= 0:  # SL faqat foyda tomonga siljiydi
                p["trail_steps"] = k
                continue
            broker.protect(symbol, new_sl, p["tp"])
            p["trail_steps"] = k
            locked = sign * (new_sl - p["entry0"]) / p["entry0"] * 100
            log.info("🔒 %s %s: foyda +%.1f%% → SL %s ga siljidi (%+.2f%% qulflandi)",
                     core.short(symbol), p["side"].upper(), profit, core.fmt_price(new_sl), locked)
        except (ccxt.AuthenticationError, ccxt.PermissionDenied):
            raise
        except ccxt.BaseError as e:
            log.error("%s: SL ni siljitib bo'lmadi: %s", core.short(symbol), e)
    return []


def configure():
    """Asosiy bot sozlamalarini trend strategiyasiga moslaydi."""
    core.TIMEFRAME = TIMEFRAME
    core.LEVERAGE = LEVERAGE
    core.MARGIN_PCT = MARGIN_PCT
    core.TP_PCT = TP_PCT
    core.SL_PCT = SL_PCT
    core.MARTINGALE_STEPS = 0
    core.MAX_POSITIONS = MAX_OPEN
    core.MAX_MARGIN_PCT = min(100.0, MARGIN_PCT * (MAX_OPEN + 1))
    core.DAILY_LOSS_PCT = DAILY_LOSS_PCT
    core.JOURNAL_PATH = core.HERE / f"trades_trend_{core.EXCHANGE}_{core.MODE}.csv"
    core.LOG_PATH = core.HERE / f"trend_{core.EXCHANGE}_{core.MODE}.log"


def validate():
    core.validate_config()
    if STEP_PCT <= be_pct():
        sys.exit(f"TREND_STEP_PCT ({STEP_PCT}%) komissiya zaxirasidan ({be_pct():.2f}%) katta bo'lishi kerak.")
    if INTERVAL_MIN < 5:
        sys.exit("TREND_INTERVAL_MIN kamida 5 (bitta 5m sham) bo'lishi kerak.")


def main():
    parser = argparse.ArgumentParser(description="Trend bot: 5m trend + har 1% foydada SL siljitish")
    parser.add_argument("--stats", action="store_true", help="trend bot statistikasi")
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

    if core.MODE == "live" and os.getenv("TREND_LIVE_OK") != "1":
        sys.exit("Trend bot haqiqiy pulda faqat .env da TREND_LIVE_OK=1 bo'lsa ishlaydi. Avval demo'da sinang.")
    validate()
    exchange = core.make_exchange()
    broker = core.make_broker(exchange)
    if args.close:
        core.close_positions(exchange, broker, journal, None if args.close == "ALL" else args.close)
        return

    log.info("📈 TREND: har %.4g daqiqada eng kuchli trenddagi coin | marja %.4g%% × %dx | SL −%.4g%% | "
             "har +%.4g%% foydada SL siljiydi (+%.4g%% → zararsiz, +%.4g%% → +%.4g%% ...) | %s | max %d ta",
             INTERVAL_MIN, MARGIN_PCT, LEVERAGE, SL_PCT, STEP_PCT, STEP_PCT, 2 * STEP_PCT, STEP_PCT,
             f"TP +{TP_PCT:.4g}%" if TP_PCT > 0 else "TP yo'q", MAX_OPEN)
    log.warning("Strategiya foydasini avval tarixda tekshiring: python3 backtest.py  "
                "(boshqa botlar shu hisobda ishlayotgan bo'lsa — ularni to'xtating)")
    if core.MODE == "live":
        log.warning("⚠️  LIVE rejim: haqiqiy pul bilan savdo. To'xtatish uchun Ctrl+C.")
    try:
        core.run(exchange, broker, journal, pick_coins=lambda ex: core.choose_coins(ex)[:SCAN_COINS],
                 scan_fn=trend_scan, manage_fn=manage_trailing)
    except KeyboardInterrupt:
        if core.MODE == "paper":
            log.info("To'xtatildi. (paper rejim: virtual pozitsiyalar yopilmagan holda qoldi)")
        else:
            log.info("To'xtatildi. Ochiq pozitsiyalar birjada SL bilan qoladi (SL endi siljimaydi!). "
                     "Ko'rish: python3 trend_bot.py --stats, yopish: python3 trend_bot.py --close")


if __name__ == "__main__":
    main()
