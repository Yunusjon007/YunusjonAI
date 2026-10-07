"""
Razgon bot — har daqiqada savdo ochib, foydaga chiqishi bilan yopadi.

Har yangi 1 daqiqalik sham yopilganda:
  - tanlangan coinlar ichidan (universe.py: top 50, grafigi o'xshashlari chiqarilgan; eng likvid
    RAZGON_SCAN_COINS tasi) 1 daqiqalik trendi eng kuchli coin olinadi:
    kuch = |EMA9 − EMA21| / narx, yo'nalish = EMA9 > EMA21 bo'lsa LONG, aks holda SHORT
    (RSI > 75 da LONG, RSI < 25 da SHORT ochilmaydi — haddan oshgan harakatga kirmaslik uchun)
  - shu coinda savdo ochiladi: marja = balansning RAZGON_MARGIN_PCT (5%) i × RAZGON_LEVERAGE (20x)
  - sof foyda (komissiyalardan keyin) pozitsiyaning RAZGON_PROFIT_PCT (0.1%) iga yetishi bilan yopiladi —
    bu narx birjaga TP sifatida qo'yiladi
  - himoya: narx RAZGON_SL_PCT (2%) qarshi yursa SL; bir vaqtda RAZGON_MAX_OPEN (5) tagacha savdo;
    bugungi zarar balansning RAZGON_DAILY_LOSS_PCT (20%) iga yetsa, ertagacha yangi savdo ochilmaydi

Asosiy bot (allin_bot.py) infratuzilmasi ishlatiladi: birja, brokerlar, jurnal, statistika.
Savdolar alohida faylga yoziladi: trades_razgon_<birja>_<rejim>.csv

Buyruqlar:
  python3 razgon_bot.py              ishga tushirish
  python3 razgon_bot.py --stats      razgon statistikasi
  python3 razgon_bot.py --close      barcha ochiq pozitsiyalarni yopish (--close SOL — bittasini)

Haqiqiy pulda (MODE=live) faqat .env da RAZGON_LIVE_OK=1 bo'lsa ishlaydi.
Asosiy bot bilan bir vaqtda, bitta hisobda ishga tushirmang.
"""
import argparse
import logging
import logging.handlers
import os
import sys

import ccxt

import allin_bot as core

log = logging.getLogger("bot")

MARGIN_PCT = core.env("RAZGON_MARGIN_PCT", 5.0, float)       # har savdoga balansning necha foizi marja
LEVERAGE = core.env("RAZGON_LEVERAGE", 20, int)
PROFIT_PCT = core.env("RAZGON_PROFIT_PCT", 0.1, float)       # sof foyda, pozitsiya hajmidan % (komissiyadan keyin)
SL_PCT = core.env("RAZGON_SL_PCT", 2.0, float)               # narx qarshi tomonga necha % yursa yopiladi
MAX_OPEN = core.env("RAZGON_MAX_OPEN", 5, int)               # bir vaqtda nechta savdo
DAILY_LOSS_PCT = core.env("RAZGON_DAILY_LOSS_PCT", 20.0, float)
SCAN_COINS = core.env("RAZGON_SCAN_COINS", 15, int)          # har daqiqada nechta eng likvid coin tekshiriladi


def configure():
    """Asosiy bot sozlamalarini razgon rejimiga moslaydi."""
    core.TIMEFRAME = "1m"
    core.LEVERAGE = LEVERAGE
    core.MARGIN_PCT = MARGIN_PCT
    core.TP_PCT = PROFIT_PCT + 2 * core.FEE_PCT  # sof foyda + kirish va chiqish komissiyasi
    core.SL_PCT = SL_PCT
    core.MARTINGALE_STEPS = 0
    core.MAX_POSITIONS = MAX_OPEN
    # sonini MAX_OPEN cheklaydi; marja limiti — zaxira bilan (komissiyalar balansni ozgina kamaytiradi)
    core.MAX_MARGIN_PCT = min(100.0, MARGIN_PCT * (MAX_OPEN + 1))
    core.DAILY_LOSS_PCT = DAILY_LOSS_PCT
    core.JOURNAL_PATH = core.HERE / f"trades_razgon_{core.EXCHANGE}_{core.MODE}.csv"
    core.LOG_PATH = core.HERE / f"razgon_{core.EXCHANGE}_{core.MODE}.log"
    core.scan = strongest_trend


def expectation():
    """Narx tasodifiy harakat qilsa: (yutuq ehtimoli, yutuq %, zarar %, o'rtacha %) — balansdan."""
    fee, tp, sl = core.FEE_PCT / 100, core.TP_PCT / 100, SL_PCT / 100
    size = MARGIN_PCT / 100 * LEVERAGE  # pozitsiya / balans
    p = sl / (tp + sl)
    win = size * (tp - fee - fee * (1 + tp))
    loss = -size * (sl + 0.0003 + fee + fee * (1 - sl))  # 0.03% — SL market orderidagi sirpanish
    return p, win * 100, loss * 100, (p * win + (1 - p) * loss) * 100


def strongest_trend(exchange, symbols):
    """1 daqiqalik trendi eng kuchli coinni tanlaydi. ([(symbol, side)] yoki [], hisobot) qaytaradi."""
    best, ups, downs = None, 0, 0
    for symbol in symbols:
        try:
            candles = exchange.fetch_ohlcv(symbol, "1m", limit=core.EMA_SLOW + core.RSI_PERIOD + 20)
        except ccxt.BaseError as e:
            log.warning("%s: shamlarni olib bo'lmadi: %s", core.short(symbol), e)
            continue
        closes = [c[4] for c in candles[:-1]]  # oxirgi sham hali yopilmagan
        if len(closes) < max(core.EMA_SLOW, core.RSI_PERIOD) + 2:
            continue
        fast = core.ema(closes, core.EMA_FAST)[-1]
        slow = core.ema(closes, core.EMA_SLOW)[-1]
        side = "long" if fast > slow else "short"
        ups, downs = ups + (side == "long"), downs + (side == "short")
        r = core.rsi(closes, core.RSI_PERIOD)
        if (side == "long" and r > 75) or (side == "short" and r < 25):
            continue
        strength = abs(fast - slow) / closes[-1]
        if best is None or strength > best[2]:
            best = (symbol, side, strength)
    report = f"{ups} ta coin o'smoqda, {downs} ta tushmoqda"
    if best is None:
        return [], report
    return [(best[0], best[1])], f"{report} | eng kuchli: {core.short(best[0])} {best[2] * 100:.2f}%"


def main():
    parser = argparse.ArgumentParser(description="Razgon bot: har daqiqada savdo, foydaga chiqishi bilan yopish")
    parser.add_argument("--stats", action="store_true", help="razgon statistikasi")
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

    if core.MODE == "live" and os.getenv("RAZGON_LIVE_OK") != "1":
        sys.exit("Razgon bot haqiqiy pulda faqat .env da RAZGON_LIVE_OK=1 bo'lsa ishlaydi. Avval demo'da sinang.")
    core.validate_config()
    exchange = core.make_exchange()
    broker = core.make_broker(exchange)
    if args.close:
        core.close_positions(exchange, broker, journal, None if args.close == "ALL" else args.close)
        return

    p, win, loss, ev = expectation()
    log.info("⚡ RAZGON: har daqiqada 1 ta savdo (eng kuchli 1m trend) | marja %.4g%% × %dx | sof +%.4g%% da yopish "
             "| SL −%.4g%% | max %d ta | kunlik zarar limiti %.4g%%",
             MARGIN_PCT, LEVERAGE, PROFIT_PCT, SL_PCT, MAX_OPEN, DAILY_LOSS_PCT)
    log.warning("⚠️  Hisob (narx tasodifiy bo'lsa): %.0f%% savdo yutuq (%+.3f%% balans), qolgani zarar (%+.2f%%) — "
                "o'rtacha har savdo %+.3f%% balans. Natijani yutuq foizidan emas, --stats dagi Sof natijadan baholang.",
                p * 100, win, loss, ev)
    log.warning("Asosiy bot (allin_bot.py) shu hisobda ishlayotgan bo'lsa — uni to'xtating, ikkalasi bir-biriga xalaqit beradi.")
    if core.MODE == "live":
        log.warning("⚠️  LIVE rejim: haqiqiy pul bilan savdo. To'xtatish uchun Ctrl+C.")
    try:
        core.run(exchange, broker, journal, pick_coins=lambda ex: core.choose_coins(ex)[:SCAN_COINS])
    except KeyboardInterrupt:
        if core.MODE == "paper":
            log.info("To'xtatildi. (paper rejim: virtual pozitsiyalar yopilmagan holda qoldi)")
        else:
            log.info("To'xtatildi. Ochiq pozitsiyalar birjada SL/TP bilan qoladi. "
                     "Ko'rish: python3 razgon_bot.py --stats, yopish: python3 razgon_bot.py --close")


if __name__ == "__main__":
    main()
