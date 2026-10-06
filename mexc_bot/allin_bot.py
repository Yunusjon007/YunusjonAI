"""
MEXC / Binance Futures — "All-in + yuqori leverage" scalping bot.

DIQQAT: bu eng xavfli razgon usuli. Bitta xato savdo depozitning katta qismini
olib ketishi mumkin. Standart rejim MODE=paper (haqiqiy pul ishlatilmaydi).

Rejimlar:
  paper — haqiqiy narxlar, virtual balans (API kalit kerak emas)
  demo  — Binance Demo Trading hisobi (demo.binance.com kalitlari, virtual pul)
  live  — haqiqiy pul

Strategiya:
  - 1 daqiqalik shamlarda EMA(9) va EMA(21) kesishishi + RSI filtri
  - EMA9 EMA21 ni pastdan yuqoriga kesib o'tsa va RSI < 70 -> LONG
  - EMA9 EMA21 ni yuqoridan pastga kesib o'tsa va RSI > 30 -> SHORT
  - Depozitning MARGIN_SHARE qismi bitta pozitsiyaga (all-in), isolated margin
  - Take-profit / stop-loss birjaga ham qo'yiladi, bot ham kuzatib turadi
  - Maqsad (TARGET_X) bajarilsa yoki ketma-ket MAX_LOSSES_IN_ROW zarar bo'lsa, bot to'xtaydi
"""
import logging
import os
import sys
import time

import ccxt
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("allin")


def env(name, default, cast=str):
    value = os.getenv(name)
    return cast(value) if value not in (None, "") else default


EXCHANGE = env("EXCHANGE", "mexc").lower()       # mexc | binance
MODE = env("MODE", "paper").lower()              # paper | demo | live
SYMBOL = env("SYMBOL", "BTC/USDT:USDT")
TIMEFRAME = env("TIMEFRAME", "1m")
LEVERAGE = env("LEVERAGE", 20, int)
MARGIN_SHARE = env("MARGIN_SHARE", 0.95, float)  # balansning qancha qismi marjaga (0.95 = 95%)
TP_PCT = env("TP_PCT", 1.0, float)               # narx o'zgarishi %, 20x da 1% = +20% depozit
SL_PCT = env("SL_PCT", 0.5, float)               # narx o'zgarishi %, 20x da 0.5% = -10% depozit
FEE_PCT = env("FEE_PCT", 0.05 if EXCHANGE == "binance" else 0.02, float)  # taker, har tomon %
EMA_FAST = env("EMA_FAST", 9, int)
EMA_SLOW = env("EMA_SLOW", 21, int)
RSI_PERIOD = env("RSI_PERIOD", 14, int)
TARGET_X = env("TARGET_X", 4.0, float)           # balans boshlang'ichdan necha baravar bo'lsa to'xtash
MAX_LOSSES_IN_ROW = env("MAX_LOSSES_IN_ROW", 3, int)
MIN_BALANCE = env("MIN_BALANCE", 5.0, float)     # USDT, bundan kam qolsa to'xtash
POLL_SECONDS = env("POLL_SECONDS", 3, float)
PAPER_BALANCE = env("PAPER_BALANCE", 100.0, float)

MAINTENANCE_MARGIN_PCT = 0.4  # taxminiy; likvidatsiya masofasini hisoblash uchun


# ---------------------------------------------------------------- indikatorlar

def ema(values, period):
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values, period):
    gains, losses = [], []
    for prev, cur in zip(values, values[1:]):
        diff = cur - prev
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def signal(closes):
    """'long', 'short' yoki None. Faqat yopilgan shamlar beriladi."""
    if len(closes) < max(EMA_SLOW, RSI_PERIOD) + 2:
        return None
    fast, slow = ema(closes, EMA_FAST), ema(closes, EMA_SLOW)
    r = rsi(closes, RSI_PERIOD)
    if fast[-2] <= slow[-2] and fast[-1] > slow[-1] and r < 70:
        return "long"
    if fast[-2] >= slow[-2] and fast[-1] < slow[-1] and r > 30:
        return "short"
    return None


# ---------------------------------------------------------------- brokerlar

class PaperBroker:
    """Haqiqiy MEXC narxlari, lekin virtual balans."""

    def __init__(self, exchange, balance):
        self.ex = exchange
        self.cash = balance
        self.pos = None  # dict(side, contracts, entry, sl, tp, margin)

    def balance(self):
        return self.cash

    def has_position(self):
        return self.pos is not None

    def open(self, side, contracts, price, sl, tp, notional):
        margin = notional / LEVERAGE
        self.cash -= notional * FEE_PCT / 100
        self.pos = dict(side=side, contracts=contracts, entry=price, sl=sl, tp=tp,
                        notional=notional, margin=margin)

    def check_exit(self, price):
        """Birjadagi SL/TP ni simulyatsiya qiladi. Yopilsa True qaytaradi."""
        p = self.pos
        hit_tp = price >= p["tp"] if p["side"] == "long" else price <= p["tp"]
        hit_sl = price <= p["sl"] if p["side"] == "long" else price >= p["sl"]
        if hit_tp or hit_sl:
            self.close(p["tp"] if hit_tp else p["sl"])
            return True
        return False

    def close(self, price):
        p = self.pos
        move = (price - p["entry"]) / p["entry"]
        if p["side"] == "short":
            move = -move
        pnl = max(p["notional"] * move, -p["margin"])  # isolated: marjadan ko'p yo'qotilmaydi
        self.cash += pnl - p["notional"] * FEE_PCT / 100
        self.pos = None


class LiveBroker:
    """Haqiqiy MEXC USDT-M futures hisobi."""

    def __init__(self, exchange):
        self.ex = exchange

    def setup(self):
        pass

    def balance(self):
        bal = self.ex.fetch_balance()
        return float(bal["USDT"]["total"] or 0)

    def _position(self):
        for p in self.ex.fetch_positions([SYMBOL]):
            if float(p.get("contracts") or 0) > 0:
                return p
        return None

    def has_position(self):
        return self._position() is not None

    def open(self, side, contracts, price, sl, tp, notional):
        self.ex.create_order(
            SYMBOL, "market", "buy" if side == "long" else "sell", contracts,
            params={
                "marginMode": "isolated",
                "leverage": LEVERAGE,
                # MEXC order/create maydonlari: birja tomonida SL/TP
                "stopLossPrice": float(self.ex.price_to_precision(SYMBOL, sl)),
                "takeProfitPrice": float(self.ex.price_to_precision(SYMBOL, tp)),
            },
        )

    def check_exit(self, price):
        # SL/TP birjada turibdi; pozitsiya yo'qolgan bo'lsa — yopilgan.
        return not self.has_position()

    def close(self, price):
        p = self._position()
        if not p:
            return
        self.ex.create_order(
            SYMBOL, "market", "sell" if p["side"] == "long" else "buy", float(p["contracts"]),
            params={"reduceOnly": True, "marginMode": "isolated", "leverage": LEVERAGE},
        )


class BinanceBroker(LiveBroker):
    """Binance USDT-M futures (demo yoki haqiqiy). SL/TP alohida algo orderlar sifatida."""

    def setup(self):
        self.ex.set_margin_mode("isolated", SYMBOL)
        self.ex.set_leverage(LEVERAGE, SYMBOL)

    def _cancel_triggers(self):
        try:
            self.ex.cancel_all_orders(SYMBOL, params={"trigger": True})
        except ccxt.BaseError as e:
            log.warning("SL/TP orderlarni bekor qilib bo'lmadi: %s", e)

    def open(self, side, contracts, price, sl, tp, notional):
        entry_side, exit_side = ("buy", "sell") if side == "long" else ("sell", "buy")
        self.ex.create_order(SYMBOL, "market", entry_side, contracts)
        try:
            self.ex.create_order(SYMBOL, "market", exit_side, contracts,
                                 params={"stopLossPrice": sl, "reduceOnly": True})
            self.ex.create_order(SYMBOL, "market", exit_side, contracts,
                                 params={"takeProfitPrice": tp, "reduceOnly": True})
        except ccxt.BaseError as e:
            # Stop-losssiz all-in pozitsiyani ochiq qoldirmaymiz
            log.error("SL/TP qo'yilmadi (%s) — pozitsiya darhol yopiladi.", e)
            self.close(price)
            raise

    def check_exit(self, price):
        if self.has_position():
            return False
        self._cancel_triggers()  # TP ishlasa SL qoladi (yoki aksincha) — tozalaymiz
        return True

    def close(self, price):
        super().close(price)
        self._cancel_triggers()


# ---------------------------------------------------------------- asosiy sikl

def validate_config():
    liq_distance = 100 / LEVERAGE - MAINTENANCE_MARGIN_PCT
    if SL_PCT >= liq_distance:
        sys.exit(f"SL_PCT={SL_PCT}% likvidatsiya masofasidan (~{liq_distance:.2f}%) katta yoki teng. "
                 f"SL_PCT ni kamaytiring yoki LEVERAGE ni pasaytiring.")
    if EXCHANGE not in ("mexc", "binance"):
        sys.exit("EXCHANGE faqat 'mexc' yoki 'binance' bo'lishi mumkin.")
    if MODE not in ("paper", "demo", "live"):
        sys.exit("MODE faqat 'paper', 'demo' yoki 'live' bo'lishi mumkin.")
    if MODE == "demo" and EXCHANGE != "binance":
        sys.exit("demo rejim faqat Binance uchun (MEXC futures demo API bermaydi). MODE=paper ishlating.")
    if not 0 < MARGIN_SHARE <= 1:
        sys.exit("MARGIN_SHARE 0 dan katta va 1 dan kichik yoki teng bo'lishi kerak.")


def make_exchange():
    config = {"enableRateLimit": True, "options": {"defaultType": "swap"}}
    if MODE != "paper":
        prefix = EXCHANGE.upper()
        key, secret = os.getenv(f"{prefix}_API_KEY"), os.getenv(f"{prefix}_SECRET")
        if not key or not secret:
            sys.exit(f"{MODE} rejim uchun .env faylida {prefix}_API_KEY va {prefix}_SECRET kerak.")
        config.update(apiKey=key, secret=secret)
    exchange = getattr(ccxt, EXCHANGE)(config)
    if MODE == "demo":
        exchange.enable_demo_trading(True)
    return exchange


def make_broker(exchange):
    if MODE == "paper":
        return PaperBroker(exchange, PAPER_BALANCE)
    return BinanceBroker(exchange) if EXCHANGE == "binance" else LiveBroker(exchange)


def contracts_for(exchange, notional, price):
    market = exchange.market(SYMBOL)
    size = market.get("contractSize") or 1
    return float(exchange.amount_to_precision(SYMBOL, notional / (price * size)))


def run(exchange, broker, sleep=time.sleep, max_loops=None):
    exchange.load_markets()
    start = broker.balance()
    losses_in_row = 0
    last_candle = None
    entry_balance = None
    loops = 0
    log.info("%s | rejim=%s %s %dx | boshlang'ich balans %.2f USDT | maqsad %.1fx",
             EXCHANGE.upper(), MODE, SYMBOL, LEVERAGE, start, TARGET_X)

    while max_loops is None or loops < max_loops:
        loops += 1
        price = exchange.fetch_ticker(SYMBOL)["last"]

        if broker.has_position():
            if broker.check_exit(price):
                bal = broker.balance()
                result = bal - entry_balance
                losses_in_row = losses_in_row + 1 if result < 0 else 0
                log.info("Pozitsiya yopildi: %+.2f USDT | balans %.2f USDT (%.2fx)",
                         result, bal, bal / start)
            sleep(POLL_SECONDS)
            continue

        bal = broker.balance()
        if bal >= start * TARGET_X:
            log.info("🎯 Maqsad bajarildi: %.2f USDT (%.2fx). Bot to'xtadi.", bal, bal / start)
            return "target"
        if bal < MIN_BALANCE:
            log.info("Balans %.2f USDT — juda kam. Bot to'xtadi.", bal)
            return "broke"
        if losses_in_row >= MAX_LOSSES_IN_ROW:
            log.info("Ketma-ket %d ta zarar. Bugun savdo yetarli — bot to'xtadi.", losses_in_row)
            return "loss_limit"

        candles = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=EMA_SLOW + RSI_PERIOD + 50)
        closed = candles[:-1]  # oxirgi sham hali yopilmagan
        if not closed or closed[-1][0] == last_candle:
            sleep(POLL_SECONDS)
            continue
        last_candle = closed[-1][0]

        side = signal([c[4] for c in closed])
        if side:
            notional = bal * MARGIN_SHARE * LEVERAGE
            contracts = contracts_for(exchange, notional, price)
            if contracts <= 0:
                log.warning("Balans minimal kontrakt uchun yetmaydi.")
                sleep(POLL_SECONDS)
                continue
            sign = 1 if side == "long" else -1
            tp = price * (1 + sign * TP_PCT / 100)
            sl = price * (1 - sign * SL_PCT / 100)
            entry_balance = bal
            broker.open(side, contracts, price, sl, tp, notional)
            log.info("%s ochildi @ %.2f | %.0f USDT pozitsiya | TP %.2f | SL %.2f",
                     side.upper(), price, notional, tp, sl)

        sleep(POLL_SECONDS)
    return "max_loops"


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    validate_config()
    exchange = make_exchange()
    broker = make_broker(exchange)
    if MODE == "live":
        log.warning("⚠️  LIVE rejim: haqiqiy pul bilan savdo. To'xtatish uchun Ctrl+C.")
    try:
        if MODE != "paper":
            exchange.load_markets()
            broker.setup()
        run(exchange, broker)
    except KeyboardInterrupt:
        log.info("To'xtatildi. Ochiq pozitsiya bo'lsa, %s ilovasida tekshiring!", EXCHANGE.upper())


if __name__ == "__main__":
    main()
