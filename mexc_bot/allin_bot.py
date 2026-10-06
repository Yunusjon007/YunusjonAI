"""
MEXC / Binance Futures — "All-in + yuqori leverage" scalping bot (ko'p coinli skaner).

DIQQAT: bu eng xavfli razgon usuli. Bitta xato savdo depozitning katta qismini
olib ketishi mumkin. Standart rejim MODE=paper (haqiqiy pul ishlatilmaydi).

Rejimlar:
  paper — haqiqiy narxlar, virtual balans (API kalit kerak emas)
  demo  — Binance Demo Trading hisobi (demo.binance.com kalitlari, virtual pul)
  live  — haqiqiy pul

Strategiya:
  - Har bir yangi shamda SYMBOLS ro'yxatidagi barcha coinlar (standart: 20 ta) tahlil qilinadi
  - 1 daqiqalik shamlarda EMA(9) va EMA(21) kesishishi + RSI filtri
  - EMA9 EMA21 ni pastdan yuqoriga kesib o'tsa va RSI < 70 -> LONG
  - EMA9 EMA21 ni yuqoridan pastga kesib o'tsa va RSI > 30 -> SHORT
  - Bir nechta coinda signal bo'lsa, ro'yxatda birinchisi (eng likvidi) tanlanadi
  - Bir vaqtda faqat BITTA pozitsiya: depozitning MARGIN_SHARE qismi (all-in), isolated margin
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


# Likvidlik bo'yicha tartiblangan 20 ta USDT perpetual (Binance va MEXC'da bor)
DEFAULT_SYMBOLS = (
    "BTC,ETH,SOL,BNB,XRP,DOGE,ADA,AVAX,LINK,DOT,"
    "LTC,TRX,NEAR,SUI,APT,ARB,OP,FIL,ATOM,AAVE"
)

EXCHANGE = env("EXCHANGE", "mexc").lower()       # mexc | binance
MODE = env("MODE", "paper").lower()              # paper | demo | live
SYMBOLS = [f"{c.strip().upper()}/USDT:USDT" for c in env("SYMBOLS", DEFAULT_SYMBOLS).split(",") if c.strip()]
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


def short(symbol):
    return symbol.split("/")[0]


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


def analyze(closes):
    """(signal, rsi, ema9_yuqorida) qaytaradi. signal: 'long', 'short' yoki None.
    Faqat yopilgan shamlar beriladi; ma'lumot yetmasa None."""
    if len(closes) < max(EMA_SLOW, RSI_PERIOD) + 2:
        return None
    fast, slow = ema(closes, EMA_FAST), ema(closes, EMA_SLOW)
    r = rsi(closes, RSI_PERIOD)
    side = None
    if fast[-2] <= slow[-2] and fast[-1] > slow[-1] and r < 70:
        side = "long"
    elif fast[-2] >= slow[-2] and fast[-1] < slow[-1] and r > 30:
        side = "short"
    return side, r, fast[-1] > slow[-1]


def signal(closes):
    result = analyze(closes)
    return result[0] if result else None


# ---------------------------------------------------------------- brokerlar

class PaperBroker:
    """Haqiqiy narxlar, lekin virtual balans."""

    def __init__(self, exchange, balance):
        self.ex = exchange
        self.cash = balance
        self.pos = None  # dict(symbol, side, contracts, entry, sl, tp, notional, margin)

    def setup(self, symbols):
        pass

    def balance(self):
        return self.cash

    def position_symbol(self):
        return self.pos["symbol"] if self.pos else None

    def open(self, symbol, side, contracts, price, sl, tp, notional):
        self.cash -= notional * FEE_PCT / 100
        self.pos = dict(symbol=symbol, side=side, contracts=contracts, entry=price, sl=sl, tp=tp,
                        notional=notional, margin=notional / LEVERAGE)

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
        self.symbols = []
        self.symbol = None  # ochiq pozitsiya coini

    def setup(self, symbols):
        self.symbols = symbols
        # Bot qayta ishga tushirilganda ochiq qolgan pozitsiyani topamiz
        for p in self.ex.fetch_positions(symbols):
            if float(p.get("contracts") or 0) > 0:
                self.symbol = p["symbol"]
                log.info("Ochiq pozitsiya topildi: %s — kuzatishda davom etaman.", short(self.symbol))
                break

    def balance(self):
        bal = self.ex.fetch_balance()
        return float(bal["USDT"]["total"] or 0)

    def _position(self):
        if not self.symbol:
            return None
        for p in self.ex.fetch_positions([self.symbol]):
            if float(p.get("contracts") or 0) > 0:
                return p
        return None

    def position_symbol(self):
        return self.symbol

    def open(self, symbol, side, contracts, price, sl, tp, notional):
        self.ex.create_order(
            symbol, "market", "buy" if side == "long" else "sell", contracts,
            params={
                "marginMode": "isolated",
                "leverage": LEVERAGE,
                # MEXC order/create maydonlari: birja tomonida SL/TP
                "stopLossPrice": float(self.ex.price_to_precision(symbol, sl)),
                "takeProfitPrice": float(self.ex.price_to_precision(symbol, tp)),
            },
        )
        self.symbol = symbol

    def check_exit(self, price):
        # SL/TP birjada turibdi; pozitsiya yo'qolgan bo'lsa — yopilgan.
        if self._position():
            return False
        self.symbol = None
        return True

    def close(self, price):
        p = self._position()
        if p:
            self.ex.create_order(
                self.symbol, "market", "sell" if p["side"] == "long" else "buy", float(p["contracts"]),
                params={"reduceOnly": True, "marginMode": "isolated", "leverage": LEVERAGE},
            )
        self.symbol = None


class BinanceBroker(LiveBroker):
    """Binance USDT-M futures (demo yoki haqiqiy). SL/TP alohida algo orderlar sifatida."""

    def __init__(self, exchange):
        super().__init__(exchange)
        self.prepared = set()  # margin/leverage o'rnatilgan coinlar

    def _prepare(self, symbol):
        if symbol in self.prepared:
            return
        try:
            self.ex.set_margin_mode("isolated", symbol)
        except ccxt.MarginModeAlreadySet:
            pass  # allaqachon isolated
        self.ex.set_leverage(LEVERAGE, symbol)
        self.prepared.add(symbol)

    def _cancel_triggers(self, symbol):
        try:
            self.ex.cancel_all_orders(symbol, params={"trigger": True})
        except ccxt.BaseError as e:
            log.warning("%s: SL/TP orderlarni bekor qilib bo'lmadi: %s", short(symbol), e)

    def open(self, symbol, side, contracts, price, sl, tp, notional):
        self._prepare(symbol)
        entry_side, exit_side = ("buy", "sell") if side == "long" else ("sell", "buy")
        self.ex.create_order(symbol, "market", entry_side, contracts)
        self.symbol = symbol
        try:
            self.ex.create_order(symbol, "market", exit_side, contracts,
                                 params={"stopLossPrice": sl, "reduceOnly": True})
            self.ex.create_order(symbol, "market", exit_side, contracts,
                                 params={"takeProfitPrice": tp, "reduceOnly": True})
        except ccxt.BaseError as e:
            # Stop-losssiz all-in pozitsiyani ochiq qoldirmaymiz
            log.error("SL/TP qo'yilmadi (%s) — pozitsiya darhol yopiladi.", e)
            self.close(price)
            raise

    def check_exit(self, price):
        symbol = self.symbol
        if not super().check_exit(price):
            return False
        self._cancel_triggers(symbol)  # TP ishlasa SL qoladi (yoki aksincha) — tozalaymiz
        return True

    def close(self, price):
        symbol = self.symbol
        super().close(price)
        if symbol:
            self._cancel_triggers(symbol)


# ---------------------------------------------------------------- sozlash

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
    if not SYMBOLS:
        sys.exit("SYMBOLS bo'sh. Masalan: SYMBOLS=BTC,ETH,SOL")


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


def available_symbols(exchange, symbols):
    ok = [s for s in symbols if s in exchange.markets and exchange.markets[s].get("active", True) is not False]
    missing = [short(s) for s in symbols if s not in ok]
    if missing:
        log.warning("Birjada topilmadi, o'tkazib yuboriladi: %s", ", ".join(missing))
    return ok


def contracts_for(exchange, symbol, notional, price):
    market = exchange.market(symbol)
    size = market.get("contractSize") or 1
    return float(exchange.amount_to_precision(symbol, notional / (price * size)))


# ---------------------------------------------------------------- asosiy sikl

def scan(exchange, symbols):
    """Barcha coinlarni tahlil qiladi. (signallar[(symbol, side)], qisqa_hisobot) qaytaradi."""
    signals, ups, downs = [], 0, 0
    for symbol in symbols:
        try:
            candles = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=EMA_SLOW + RSI_PERIOD + 50)
        except ccxt.BaseError as e:
            log.warning("%s: shamlarni olib bo'lmadi: %s", short(symbol), e)
            continue
        closed = candles[:-1]  # oxirgi sham hali yopilmagan
        result = analyze([c[4] for c in closed])
        if not result:
            continue
        side, _, up = result
        ups, downs = ups + up, downs + (not up)
        if side:
            signals.append((symbol, side))
    report = f"{ups} ta coin EMA9 yuqorida, {downs} ta pastda"
    return signals, report


def run(exchange, broker, symbols=None, sleep=time.sleep, max_loops=None):
    exchange.load_markets()
    symbols = available_symbols(exchange, symbols or SYMBOLS)
    if not symbols:
        sys.exit("Ro'yxatdagi birorta coin birjada topilmadi.")
    broker.setup(symbols)
    start = broker.balance()
    state = dict(losses_in_row=0, last_candle=None, entry_balance=start)
    log.info("%s | rejim=%s | %d ta coin | %dx | boshlang'ich balans %.2f USDT | maqsad %.1fx",
             EXCHANGE.upper(), MODE, len(symbols), LEVERAGE, start, TARGET_X)
    log.info("Coinlar: %s", ", ".join(short(s) for s in symbols))

    def step():
        open_symbol = broker.position_symbol()
        if open_symbol:
            price = exchange.fetch_ticker(open_symbol)["last"]
            if broker.check_exit(price):
                bal = broker.balance()
                result = bal - state["entry_balance"]
                state["losses_in_row"] = state["losses_in_row"] + 1 if result < 0 else 0
                log.info("%s pozitsiya yopildi: %+.2f USDT | balans %.2f USDT (%.2fx)",
                         short(open_symbol), result, bal, bal / start)
            sleep(POLL_SECONDS)
            return None

        bal = broker.balance()
        if bal >= start * TARGET_X:
            log.info("🎯 Maqsad bajarildi: %.2f USDT (%.2fx). Bot to'xtadi.", bal, bal / start)
            return "target"
        if bal < MIN_BALANCE:
            log.info("Balans %.2f USDT — juda kam. Bot to'xtadi.", bal)
            return "broke"
        if state["losses_in_row"] >= MAX_LOSSES_IN_ROW:
            log.info("Ketma-ket %d ta zarar. Bugun savdo yetarli — bot to'xtadi.", state["losses_in_row"])
            return "loss_limit"

        # Yangi sham yopilmaguncha qayta skan qilmaymiz (birinchi coin bo'yicha tekshiramiz)
        head = exchange.fetch_ohlcv(symbols[0], TIMEFRAME, limit=2)
        if len(head) < 2 or head[-2][0] == state["last_candle"]:
            sleep(POLL_SECONDS)
            return None

        signals, report = scan(exchange, symbols)
        state["last_candle"] = head[-2][0]
        if not signals:
            log.info("Skan: %d ta coin | signal yo'q | %s", len(symbols), report)
            sleep(POLL_SECONDS)
            return None

        log.info("Skan: signallar — %s", ", ".join(f"{short(s)} {d.upper()}" for s, d in signals))
        symbol, side = signals[0]
        price = exchange.fetch_ticker(symbol)["last"]
        notional = bal * MARGIN_SHARE * LEVERAGE
        contracts = contracts_for(exchange, symbol, notional, price)
        if contracts <= 0:
            log.warning("%s: balans minimal kontrakt uchun yetmaydi.", short(symbol))
            sleep(POLL_SECONDS)
            return None
        sign = 1 if side == "long" else -1
        tp = price * (1 + sign * TP_PCT / 100)
        sl = price * (1 - sign * SL_PCT / 100)
        state["entry_balance"] = bal
        broker.open(symbol, side, contracts, price, sl, tp, notional)
        log.info("%s %s ochildi @ %s | %.0f USDT pozitsiya | TP %s | SL %s",
                 short(symbol), side.upper(), exchange.price_to_precision(symbol, price), notional,
                 exchange.price_to_precision(symbol, tp), exchange.price_to_precision(symbol, sl))
        sleep(POLL_SECONDS)
        return None

    loops = 0
    while max_loops is None or loops < max_loops:
        loops += 1
        try:
            result = step()
        except ccxt.NetworkError as e:
            log.warning("Tarmoq xatosi, 10s dan keyin qayta urinaman: %s", e)
            sleep(10)
            continue
        if result:
            return result
    return "max_loops"


def close_now(exchange, broker):
    """`python3 allin_bot.py --close` — ochiq pozitsiyani bozor narxida yopadi va SL/TP ni bekor qiladi."""
    if MODE == "paper":
        sys.exit("paper rejimda birjada pozitsiya yo'q.")
    exchange.load_markets()
    broker.setup(available_symbols(exchange, SYMBOLS))
    symbol = broker.position_symbol()
    if not symbol:
        log.info("Ochiq pozitsiya yo'q.")
        return
    broker.close(exchange.fetch_ticker(symbol)["last"])
    log.info("%s pozitsiya bozor narxida yopildi. Balans: %.2f USDT", short(symbol), broker.balance())


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    validate_config()
    exchange = make_exchange()
    broker = make_broker(exchange)
    if "--close" in sys.argv:
        close_now(exchange, broker)
        return
    if MODE == "live":
        log.warning("⚠️  LIVE rejim: haqiqiy pul bilan savdo. To'xtatish uchun Ctrl+C.")
    try:
        run(exchange, broker)
    except KeyboardInterrupt:
        log.info("To'xtatildi. Ochiq pozitsiya bo'lsa, %s ilovasida tekshiring!", EXCHANGE.upper())


if __name__ == "__main__":
    main()
