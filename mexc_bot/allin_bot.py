"""
Binance / MEXC Futures — ko'p coinli scalping bot.

Har bir savdoga balansning kichik qismi (standart 1%) marja sifatida tikiladi, shuning
uchun balansning katta qismi doim bo'sh qoladi va bir vaqtda bir nechta coinda savdo
ochiladi. Standart rejim MODE=paper (haqiqiy pul ishlatilmaydi).

Rejimlar:
  paper — haqiqiy narxlar, virtual balans (API kalit kerak emas)
  demo  — Binance Demo Trading hisobi (demo.binance.com kalitlari, virtual pul)
  live  — haqiqiy pul

Coinlar (universe.py):
  - 24 soatlik hajm bo'yicha eng likvid TOP_COINS (50) ta USDT perpetual olinadi
  - Grafigi o'xshash coinlar chiqariladi: soatlik narx o'zgarishlari korrelyatsiyasi
    allaqachon tanlangan coin bilan CORR_MAX (0.8) dan yuqori bo'lsa (7 kunlik ma'lumot)
  - Ro'yxat har REFRESH_HOURS (6) soatda yangilanadi

Strategiya:
  - Har bir yangi shamda (standart 5m) tanlangan coinlar tahlil qilinadi
  - EMA9 EMA21 ni pastdan yuqoriga kesib o'tsa va RSI < 70 -> LONG
  - EMA9 EMA21 ni yuqoridan pastga kesib o'tsa va RSI > 30 -> SHORT
  - Marja = balansning MARGIN_PCT foizi (1%), leverage LEVERAGE (10x), isolated
  - TP: narx TP_PCT (3%) foyda tomonga yursa
  - Martingeyl (MARTINGALE_STEPS=2): narx kirishdan har MARTINGALE_STEP_PCT (1%) qarshi yurganda
    pozitsiyaga ×MARTINGALE_MULT (2) hajm qo'shiladi (1x → +2x → +4x). Martingeyl qilingan coinning
    sof foydasi MARTINGALE_PROFIT_USDT (+1$) ga yetishi bilan shu coindagi barcha savdolar yopiladi.
    Oxirgi himoya: kirishdan MARTINGALE_SL_PCT (3%) da SL. (Martingeyl o'chiq bo'lsa SL = SL_PCT)
  - Bir vaqtda MAX_POSITIONS (20) tagacha coin; barcha marja balansning MAX_MARGIN_PCT (50%) idan oshmaydi
  - Bugungi zarar balansning DAILY_LOSS_PCT (3%) iga yetsa, ertagacha yangi savdo ochilmaydi
  - Har bir yopilgan savdo trades_<birja>_<rejim>.csv fayliga yoziladi

Buyruqlar:
  python3 allin_bot.py              botni ishga tushirish
  python3 allin_bot.py --stats      statistika: balans, yutuq/zarar, kunlar va coinlar bo'yicha
  python3 allin_bot.py --coins      qaysi coinlar tanlangani va qaysilari nega chiqarilgani
  python3 allin_bot.py --close      barcha ochiq pozitsiyalarni bozor narxida yopish
  python3 allin_bot.py --close SOL  faqat bitta coinni yopish
"""
import argparse
import csv
import logging
import logging.handlers
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import ccxt
from dotenv import load_dotenv

import universe  # coinlarni tanlash (shu papkadagi universe.py)

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

log = logging.getLogger("bot")


def env(name, default, cast=str):
    value = os.getenv(name)
    return cast(value) if value not in (None, "") else default


EXCHANGE = env("EXCHANGE", "mexc").lower()       # mexc | binance
MODE = env("MODE", "paper").lower()              # paper | demo | live
# Bo'sh bo'lsa coinlar avtomatik tanlanadi; to'ldirilsa (masalan BTC,ETH,SOL) — shu ro'yxat ishlatiladi
SYMBOLS = [f"{c.strip().upper()}/USDT:USDT" for c in env("SYMBOLS", "").split(",") if c.strip()]
TOP_COINS = env("TOP_COINS", 50, int)            # hajm bo'yicha nechta eng likvid coin ko'rib chiqiladi
CORR_MAX = env("CORR_MAX", 0.8, float)           # korrelyatsiya shundan yuqori bo'lsa — "grafigi o'xshash"
CORR_TIMEFRAME = env("CORR_TIMEFRAME", "1h")     # o'xshashlik qaysi shamlar bo'yicha o'lchanadi
CORR_LOOKBACK = env("CORR_LOOKBACK", 168, int)   # nechta sham (168 × 1h = 7 kun)
MIN_COINS = env("MIN_COINS", 10, int)            # kamida nechta coin qolsin
REFRESH_HOURS = env("REFRESH_HOURS", 6, float)   # ro'yxat necha soatda bir yangilanadi
TIMEFRAME = env("TIMEFRAME", "5m")
LEVERAGE = env("LEVERAGE", 10, int)
MARGIN_PCT = env("MARGIN_PCT", 1.0, float)       # har savdoga balansning necha foizi marja (1 = 1%)
TP_PCT = env("TP_PCT", 3.0, float)               # narx foyda tomonga necha % yursa yopiladi
SL_PCT = env("SL_PCT", 1.0, float)               # narx qarshi tomonga necha % yursa yopiladi
MAX_POSITIONS = env("MAX_POSITIONS", 20, int)    # bir vaqtda nechta coinda pozitsiya
MAX_MARGIN_PCT = env("MAX_MARGIN_PCT", 50.0, float)  # barcha pozitsiyalar marjasi, balansdan % (martingeyl bilan)
MARTINGALE_STEPS = env("MARTINGALE_STEPS", 2, int)   # nechta martingeyl qadami (0 = o'chiq)
MARTINGALE_STEP_PCT = env("MARTINGALE_STEP_PCT", 1.0, float)  # narx kirishdan har necha % qarshi yursa qo'shiladi
MARTINGALE_MULT = env("MARTINGALE_MULT", 2.0, float)  # har qadamda hajm necha baravar (1x, 2x, 4x)
MARTINGALE_SL_PCT = env("MARTINGALE_SL_PCT", 3.0, float)  # martingeyldan keyingi oxirgi SL (kirishdan %)
MARTINGALE_PROFIT_USDT = env("MARTINGALE_PROFIT_USDT", 1.0, float)  # martingeyl coin shu foydada yopiladi
DAILY_LOSS_PCT = env("DAILY_LOSS_PCT", 3.0, float)  # kunlik zarar limiti, balansdan %
FEE_PCT = env("FEE_PCT", 0.05 if EXCHANGE == "binance" else 0.02, float)  # taker, har tomon %
EMA_FAST = env("EMA_FAST", 9, int)
EMA_SLOW = env("EMA_SLOW", 21, int)
RSI_PERIOD = env("RSI_PERIOD", 14, int)
MIN_BALANCE = env("MIN_BALANCE", 5.0, float)     # USDT, bundan kam qolsa yangi savdo ochilmaydi
POLL_SECONDS = env("POLL_SECONDS", 3, float)
STATUS_MINUTES = env("STATUS_MINUTES", 5, float)  # necha daqiqada bir holat (balans) chiqarilsin
PAPER_BALANCE = env("PAPER_BALANCE", 5000.0, float)

MAINTENANCE_MARGIN_PCT = 0.4  # taxminiy; likvidatsiya masofasini hisoblash uchun
LEGACY_KEYS = ("MARGIN_SHARE", "TARGET_X", "MAX_LOSSES_IN_ROW", "SYMBOL")
SETTINGS_LOGGER = None  # boshqa strategiya o'z sozlamalar qatorini berishi mumkin: f(balance)
JOURNAL_PATH = HERE / f"trades_{EXCHANGE}_{MODE}.csv"
LOG_PATH = HERE / f"bot_{EXCHANGE}_{MODE}.log"


def short(symbol):
    return symbol.split("/")[0]


def now_ms():
    return int(time.time() * 1000)


def stamp(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def fmt_price(x):
    if x is None:
        return "—"
    return f"{x:.4f}".rstrip("0").rstrip(".") if x >= 1 else f"{x:.8f}".rstrip("0").rstrip(".")


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


# ---------------------------------------------------------------- pozitsiyalar

def new_position(symbol, side, contracts, qty, entry, sl, tp, margin, fee=0.0, opened_at=None):
    """qty — coin miqdori (kontrakt × contractSize); margin — tikilgan USDT; fee — to'langan kirish komissiyasi;
    entry — o'rtacha kirish narxi, entry0 — birinchi kirish narxi; adds — nechta martingeyl qadami qilingan."""
    return dict(symbol=symbol, side=side, contracts=contracts, qty=qty, entry=entry, sl=sl, tp=tp,
                margin=margin, fee=fee, opened_at=opened_at or now_ms(), last=entry, upnl=0.0,
                entry0=entry, base_contracts=contracts, adds=0)


def merge_fill(p, contracts, qty, price, fee):
    """Martingeyl qo'shimchasini pozitsiyaga qo'shadi: o'rtacha narx, hajm, marja, komissiya yangilanadi."""
    total = p["qty"] + qty
    p["entry"] = (p["entry"] * p["qty"] + price * qty) / total
    p["qty"], p["contracts"] = total, p["contracts"] + contracts
    p["margin"] += qty * price / LEVERAGE
    p["fee"] += fee
    p["adds"] += 1


def pnl_at(p, price):
    sign = 1 if p["side"] == "long" else -1
    return p["qty"] * (price - p["entry"]) * sign


def net_pnl(p, price):
    """Shu narxda yopilsa — barcha komissiyalardan keyingi sof natija (USDT)."""
    return pnl_at(p, price) - p["fee"] - p["qty"] * price * FEE_PCT / 100


def martingale_tp(p):
    """Sof foyda (komissiyalardan keyin) MARTINGALE_PROFIT_USDT ga teng bo'ladigan narx."""
    f = FEE_PCT / 100
    target = MARTINGALE_PROFIT_USDT + p["fee"]
    if p["side"] == "long":
        return (target + p["qty"] * p["entry"]) / (p["qty"] * (1 - f))
    return (p["qty"] * p["entry"] - target) / (p["qty"] * (1 + f))


def label(p, reason):
    """Jurnal uchun sabab: pozitsiyaga qo'shimcha qilingan bo'lsa soni qo'shiladi
    (martingeyl 'TP M2', piramida 'TRAIL P2' — belgi p['add_tag'] da)."""
    return f"{reason} {p.get('add_tag', 'M')}{p['adds']}" if p.get("adds") else reason


def used_margin(broker):
    return sum(p["margin"] for p in broker.positions.values())


def martingale_on(broker):
    return MARTINGALE_STEPS > 0 and getattr(broker, "supports_martingale", False)


def classify(p, exit_price):
    """Pozitsiya qayerda yopilganini aniqlaydi: TP, SL, TRAIL (siljitilgan SL) yoki boshqa (qo'lda/likvidatsiya)."""
    if exit_price is None or p.get("sl") is None:
        return "?"
    if p.get("tp") is not None:
        tolerance = abs(p["tp"] - p["sl"]) * 0.1
        if abs(exit_price - p["tp"]) <= tolerance:
            return "TP"
    else:
        tolerance = p["sl"] * 0.004  # TP yo'q: SL atrofida 0.4%
    if abs(exit_price - p["sl"]) <= tolerance:
        return "TRAIL" if p.get("trail_steps") else "SL"
    return "boshqa"


def closed_trade(p, exit_price, pnl, fee, reason):
    return dict(p, exit=exit_price, pnl=pnl, fee=fee, reason=reason, closed_at=now_ms())


def contract_size(exchange, symbol):
    return exchange.market(symbol).get("contractSize") or 1


# ---------------------------------------------------------------- brokerlar

class PaperBroker:
    """Haqiqiy narxlar, virtual balans. SL/TP ni bot o'zi simulyatsiya qiladi."""

    supports_martingale = True

    def __init__(self, exchange, balance):
        self.ex = exchange
        self.cash = balance
        self.positions = {}
        self.closed_queue = []

    def setup(self):
        pass

    def max_notional(self, symbol):
        return None  # cheklov yo'q

    def balance(self):
        return self.cash + sum(p["upnl"] for p in self.positions.values())

    def open(self, symbol, side, contracts, qty, price, sl, tp):
        fee = qty * price * FEE_PCT / 100
        self.cash -= fee
        self.positions[symbol] = new_position(symbol, side, contracts, qty, price, sl, tp,
                                              qty * price / LEVERAGE, fee)

    def add(self, symbol, contracts, qty, price):
        fee = qty * price * FEE_PCT / 100
        self.cash -= fee
        merge_fill(self.positions[symbol], contracts, qty, price, fee)

    def protect(self, symbol, sl, tp):
        self.positions[symbol]["sl"], self.positions[symbol]["tp"] = sl, tp

    def poll(self):
        """Ochiq pozitsiyalarni yangilaydi; yopilganlarini qaytaradi."""
        closed, self.closed_queue = self.closed_queue, []
        try:
            for symbol, p in list(self.positions.items()):
                price = self.ex.fetch_ticker(symbol)["last"]
                p["last"], p["upnl"] = price, pnl_at(p, price)
                tp, sl = p["tp"], p["sl"]
                if p["side"] == "long":
                    hit_tp, hit_sl = tp is not None and price >= tp, price <= sl
                else:
                    hit_tp, hit_sl = tp is not None and price <= tp, price >= sl
                if hit_sl or hit_tp:
                    reason = ("TRAIL" if p.get("trail_steps") else "SL") if hit_sl else "TP"
                    closed.append(self._settle(symbol, sl if hit_sl else tp, label(p, reason)))
        except Exception:
            self.closed_queue = closed + self.closed_queue  # yopilganlar yo'qolmasin
            raise
        return closed

    def close(self, symbol, reason="qo'lda"):
        return self._settle(symbol, self.ex.fetch_ticker(symbol)["last"], reason)

    def _settle(self, symbol, price, reason):
        p = self.positions.pop(symbol)
        gross = max(pnl_at(p, price), -p["margin"])  # isolated: marjadan ko'p yo'qotilmaydi
        exit_fee = p["qty"] * price * FEE_PCT / 100
        self.cash += gross - exit_fee
        return closed_trade(p, price, gross - p["fee"] - exit_fee, p["fee"] + exit_fee, reason)


class LiveBroker:
    """MEXC USDT-M futures (haqiqiy hisob). SL/TP kirish orderi bilan birga birjaga yuboriladi.
    Martingeyl MEXC uchun qo'llab-quvvatlanmaydi (pozitsiya SL/TP sini o'zgartirish sinalmagan)."""

    supports_martingale = False

    def __init__(self, exchange):
        self.ex = exchange
        self.positions = {}
        self.closed_queue = []  # favqulodda yopilgan savdolar — keyingi poll() da qaytariladi

    def setup(self):
        """Bot qayta ishga tushirilganda birjada ochiq qolgan barcha USDT-M pozitsiyalarni topadi."""
        for lp in self.ex.fetch_positions():
            contracts = float(lp.get("contracts") or 0)
            symbol = lp.get("symbol") or ""
            if contracts <= 0 or not symbol.endswith(":USDT"):
                continue
            entry = float(lp.get("entryPrice") or 0)
            qty = contracts * contract_size(self.ex, symbol)
            margin = float(lp.get("initialMargin") or 0) or qty * entry / LEVERAGE
            self.positions[symbol] = new_position(symbol, lp["side"], contracts, qty, entry, None, None, margin)
            self.positions[symbol]["adopted"] = True  # martingeyl holati noma'lum — qo'shimcha qilinmaydi
            log.info("Ochiq pozitsiya topildi: %s %s — kuzatishda davom etaman (martingeylsiz).",
                     short(symbol), lp["side"].upper())

    def max_notional(self, symbol):
        return None  # MEXC cheklovini birja o'zi tekshiradi

    def balance(self):
        return float(self.ex.fetch_balance()["USDT"]["total"] or 0)

    def _live(self):
        """Birjadagi ochiq pozitsiyalar: symbol -> ccxt position (faqat kuzatilayotganlari)."""
        if not self.positions:
            return {}
        return {lp["symbol"]: lp for lp in self.ex.fetch_positions(list(self.positions))
                if float(lp.get("contracts") or 0) > 0}

    def poll(self):
        closed, self.closed_queue = self.closed_queue, []
        try:
            live = self._live()
            for symbol, p in list(self.positions.items()):
                lp = live.get(symbol)
                if lp is None:
                    closed.append(self._settle(symbol, None))
                    continue
                p["entry"] = float(lp.get("entryPrice") or p["entry"])
                p["contracts"] = float(lp.get("contracts") or p["contracts"])
                p["qty"] = p["contracts"] * contract_size(self.ex, symbol)
                p["last"] = float(lp.get("markPrice") or p["last"])
                upnl = lp.get("unrealizedPnl")
                p["upnl"] = float(upnl) if upnl is not None else pnl_at(p, p["last"])
                if p.get("unprotected"):
                    log.warning("%s: SL/TP yo'q pozitsiya — yana yopishga urinaman.", short(symbol))
                    closed.append(self.close(symbol, "SL xato"))
        except Exception:
            self.closed_queue = closed + self.closed_queue  # yopilganlar yo'qolmasin
            raise
        return closed

    def _settle(self, symbol, reason):
        p = self.positions[symbol]
        exit_price, pnl, fee = self._realized(p)  # xato bo'lsa pozitsiya kuzatuvda qoladi
        del self.positions[symbol]
        return closed_trade(p, exit_price, pnl, fee, reason or label(p, classify(p, exit_price)))

    def _realized(self, p):
        """Taxminiy natija (oxirgi narx bo'yicha)."""
        price = self.ex.fetch_ticker(p["symbol"])["last"]
        fee = p["qty"] * (p["entry"] + price) * FEE_PCT / 100
        return price, pnl_at(p, price) - fee, fee

    def open(self, symbol, side, contracts, qty, price, sl, tp):
        opened_at = now_ms()
        params = {
            "marginMode": "isolated",
            "leverage": LEVERAGE,
            # MEXC order/create maydonlari: birja tomonida SL/TP
            "stopLossPrice": float(self.ex.price_to_precision(symbol, sl)),
        }
        if tp is not None:
            params["takeProfitPrice"] = float(self.ex.price_to_precision(symbol, tp))
        self.ex.create_order(symbol, "market", "buy" if side == "long" else "sell", contracts, params=params)
        self.positions[symbol] = new_position(symbol, side, contracts, qty, price, sl, tp,
                                              qty * price / LEVERAGE, qty * price * FEE_PCT / 100,
                                              opened_at=opened_at)

    def add(self, symbol, contracts, qty, price):
        raise ccxt.NotSupported("MEXC uchun martingeyl qo'llab-quvvatlanmaydi")

    def protect(self, symbol, sl, tp):
        raise ccxt.NotSupported("MEXC uchun SL/TP ni yangilash qo'llab-quvvatlanmaydi")

    def close(self, symbol, reason="qo'lda"):
        lp = self._live().get(symbol)
        if lp:
            self.ex.create_order(
                symbol, "market", "sell" if lp["side"] == "long" else "buy", float(lp["contracts"]),
                params={"reduceOnly": True, "marginMode": "isolated", "leverage": LEVERAGE},
            )
        return self._settle(symbol, reason)


class BinanceBroker(LiveBroker):
    """Binance USDT-M futures (demo yoki haqiqiy). SL/TP alohida algo orderlar sifatida."""

    supports_martingale = True

    def __init__(self, exchange):
        super().__init__(exchange)
        self.prepared = set()  # margin/leverage o'rnatilgan coinlar
        self.caps = {}         # coin -> shu leverage'da ruxsat etilgan maksimal pozitsiya (USDT)

    def max_notional(self, symbol):
        """Binance leverage bracket: LEVERAGE bilan ochish mumkin bo'lgan eng katta pozitsiya."""
        if symbol not in self.caps:
            try:
                tiers = self.ex.fetch_market_leverage_tiers(symbol)
                caps = [t["maxNotional"] for t in tiers
                        if t.get("maxNotional") and (t.get("maxLeverage") or 0) >= LEVERAGE]
                self.caps[symbol] = max(caps) if caps else 0
            except ccxt.BaseError as e:
                log.warning("%s: pozitsiya limitini olib bo'lmadi: %s", short(symbol), e)
                return None
        return self.caps[symbol]

    def _prepare(self, symbol):
        """Isolated margin (bir marta) va leverage — har yangi savdodan oldin, Binance ilovasida qo'lda
        o'zgartirilgan bo'lsa ham bot sozlamasi (LEVERAGE) qaytariladi: pozitsiya hajmi shunga qarab hisoblanadi."""
        if symbol not in self.prepared:
            try:
                self.ex.set_margin_mode("isolated", symbol)
            except ccxt.MarginModeAlreadySet:
                pass  # allaqachon isolated
            self.prepared.add(symbol)
        self.ex.set_leverage(LEVERAGE, symbol)

    def _cancel_triggers(self, symbol):
        try:
            self.ex.cancel_all_orders(symbol, params={"trigger": True})
        except ccxt.BaseError as e:
            log.warning("%s: SL/TP orderlarni bekor qilib bo'lmadi: %s", short(symbol), e)

    def open(self, symbol, side, contracts, qty, price, sl, tp):
        self._prepare(symbol)
        entry_side, exit_side = ("buy", "sell") if side == "long" else ("sell", "buy")
        opened_at = now_ms()
        try:
            order = self.ex.create_order(symbol, "market", entry_side, contracts)
        except ccxt.NetworkError:
            # Javob kelmadi, lekin order bajarilgan bo'lishi mumkin — birjadan tekshiramiz
            try:
                filled = any(float(lp.get("contracts") or 0) > 0 for lp in self.ex.fetch_positions([symbol]))
            except ccxt.BaseError:
                log.error("%s: order holatini tekshirib bo'lmadi — Binance'da pozitsiyani qo'lda tekshiring!",
                          short(symbol))
                raise
            if not filled:
                raise
            order = {}
        fill = float(order.get("average") or 0) or price
        self.positions[symbol] = new_position(symbol, side, contracts, qty, fill, sl, tp,
                                              qty * fill / LEVERAGE, qty * fill * FEE_PCT / 100,
                                              opened_at=opened_at)
        self.protect(symbol, sl, tp, cancel_old=False)

    def add(self, symbol, contracts, qty, price):
        """Martingeyl: shu yo'nalishda qo'shimcha market order (one-way rejimda pozitsiyaga qo'shiladi)."""
        p = self.positions[symbol]
        order = self.ex.create_order(symbol, "market", "buy" if p["side"] == "long" else "sell", contracts)
        fill = float((order or {}).get("average") or 0) or price
        merge_fill(p, contracts, qty, fill, qty * fill * FEE_PCT / 100)

    def protect(self, symbol, sl, tp, cancel_old=True):
        """Butun pozitsiya hajmiga SL va TP qo'yadi (eskilari bekor qilinadi). Qo'yilmasa — pozitsiya yopiladi."""
        p = self.positions[symbol]
        exit_side = "sell" if p["side"] == "long" else "buy"
        if cancel_old:
            self._cancel_triggers(symbol)
        try:
            self.ex.create_order(symbol, "market", exit_side, p["contracts"],
                                 params={"stopLossPrice": sl, "reduceOnly": True})
            if tp is not None:
                self.ex.create_order(symbol, "market", exit_side, p["contracts"],
                                     params={"takeProfitPrice": tp, "reduceOnly": True})
        except ccxt.BaseError as e:
            # Stop-losssiz pozitsiyani ochiq qoldirmaymiz
            log.error("%s: SL/TP qo'yilmadi (%s) — pozitsiya darhol yopiladi.", short(symbol), e)
            p["unprotected"] = True
            try:
                self.closed_queue.append(self.close(symbol, "SL xato"))
            except ccxt.BaseError as e2:
                log.error("%s: yopib bo'lmadi (%s) — keyingi tsiklda yana urinaman.", short(symbol), e2)
            raise
        p["sl"], p["tp"] = sl, tp

    def _realized(self, p):
        """Aniq natija: Binance savdolaridagi realizedPnl va komissiyalar."""
        try:
            trades = self.ex.fetch_my_trades(p["symbol"], since=p["opened_at"] - 5000)
        except ccxt.BaseError as e:
            log.warning("%s: savdolar tarixini olib bo'lmadi (%s) — natija taxminiy.", short(p["symbol"]), e)
            return super()._realized(p)
        exit_side = "sell" if p["side"] == "long" else "buy"
        closing = [t for t in trades if t["side"] == exit_side and t.get("amount")]
        if not closing:
            return super()._realized(p)
        qty = sum(t["amount"] for t in closing)
        exit_price = sum(t["amount"] * t["price"] for t in closing) / qty
        pnl = sum(float((t.get("info") or {}).get("realizedPnl") or 0) for t in trades)
        fee = sum(float(t["fee"]["cost"]) for t in trades
                  if t.get("fee") and t["fee"].get("cost") and t["fee"].get("currency") == "USDT")
        return exit_price, pnl - fee, fee

    def _settle(self, symbol, reason):
        trade = super()._settle(symbol, reason)
        self._cancel_triggers(symbol)  # TP ishlasa SL qoladi (yoki aksincha) — tozalaymiz
        return trade


# ---------------------------------------------------------------- jurnal va statistika

class Journal:
    """Yopilgan savdolar CSV fayli (Excel/Numbers'da ham ochiladi)."""

    FIELDS = ["ochilgan", "yopilgan", "coin", "yonalish", "kirish", "chiqish", "hajm_usdt",
              "marja_usdt", "natija_usdt", "roi_foiz", "komissiya", "sabab", "balans"]

    def __init__(self, path):
        self.path = Path(path)
        self._size = -1
        self._rows = []

    @property
    def rows(self):
        """Fayldan o'qiydi (boshqa jarayon, masalan --close, yozgan bo'lsa ham yangilanadi)."""
        size = self.path.stat().st_size if self.path.exists() else 0
        if size != self._size:
            self._size = size
            self._rows = []
            if size:
                with open(self.path, newline="", encoding="utf-8") as f:
                    self._rows = list(csv.DictReader(f))
        return self._rows

    def add(self, t, balance):
        """Savdoni yozadi. Shu savdo boshqa jarayon (masalan, --close) tomonidan yozilgan bo'lsa,
        qayta yozmaydi: coin, yo'nalish, kirish narxi va hajm bir xil, yopilish vaqti 2 daqiqa ichida."""
        row = {
            "ochilgan": stamp(t["opened_at"]),
            "yopilgan": stamp(t["closed_at"]),
            "coin": short(t["symbol"]),
            "yonalish": t["side"].upper(),
            "kirish": f"{t['entry']:.8g}",
            "chiqish": f"{t['exit']:.8g}" if t["exit"] is not None else "",
            "hajm_usdt": f"{t['qty'] * t['entry']:.2f}",
            "marja_usdt": f"{t['margin']:.2f}",
            "natija_usdt": f"{t['pnl']:.4f}",
            "roi_foiz": f"{100 * t['pnl'] / t['margin']:.2f}" if t["margin"] else "",
            "komissiya": f"{t['fee']:.4f}",
            "sabab": t["reason"],
            "balans": f"{balance:.2f}",
        }
        key = ("coin", "yonalish", "kirish", "hajm_usdt")
        for r in self.rows[-20:]:
            if all(r[k] == row[k] for k in key):
                closed = datetime.strptime(r["yopilgan"], "%Y-%m-%d %H:%M:%S").timestamp() * 1000
                if abs(closed - t["closed_at"]) < 120_000:
                    return None
        new = not self.path.exists() or self.path.stat().st_size == 0
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS)
            if new:
                writer.writeheader()
            writer.writerow(row)
        return row

    def today_rows(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return [r for r in self.rows if r["yopilgan"].startswith(today)]


def summarize(rows):
    pnls = [float(r["natija_usdt"]) for r in rows]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    peak = cum = max_dd = 0.0
    for x in pnls:
        cum += x
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    return dict(
        count=len(pnls), wins=len(wins), losses=len(losses), pnl=sum(pnls),
        winrate=100 * len(wins) / len(pnls) if pnls else 0.0,
        avg_win=sum(wins) / len(wins) if wins else 0.0,
        avg_loss=sum(losses) / len(losses) if losses else 0.0,
        profit_factor=sum(wins) / -sum(losses) if sum(losses) < 0 else None,
        fees=sum(float(r["komissiya"] or 0) for r in rows),
        max_dd=max_dd,
    )


def report_close(t, journal):
    s = summarize(journal.rows)
    roi = 100 * t["pnl"] / t["margin"] if t["margin"] else 0.0
    log.info("%s %s %s yopildi (%s) @ %s: %+.2f USDT (ROI %+.1f%%) | jami: %d savdo, %.0f%% yutuq, %+.2f USDT",
             "✅" if t["pnl"] > 0 else "❌", short(t["symbol"]), t["side"].upper(), t["reason"],
             fmt_price(t["exit"]), t["pnl"], roi, s["count"], s["winrate"], s["pnl"])


def report_status(broker, journal):
    opened = ", ".join(f"{short(s)} {p['side'].upper()} {p['upnl']:+.2f}" + (f" M{p['adds']}" if p.get("adds") else "")
                       for s, p in broker.positions.items())
    today = summarize(journal.today_rows())
    log.info("📊 Balans %.2f USDT | marja %.0f USDT | ochiq %d/%d: %s | bugun: %d savdo, %+.2f USDT",
             broker.balance(), used_margin(broker), len(broker.positions), MAX_POSITIONS, opened or "yo'q",
             today["count"], today["pnl"])


def print_stats(journal, live=None):
    """`--stats`: jurnal bo'yicha to'liq statistika. live — birjadan olingan joriy holat (ixtiyoriy)."""
    rows = journal.rows
    print(f"\n========== 📊 STATISTIKA — {EXCHANGE.upper()} {MODE} ==========")
    print(f"Fayl: {journal.path.name}")
    if live:
        print(f"\nHozir (birjadan): balans {live['total']:.2f} USDT | bo'sh {live['free']:.2f} USDT")
        for p in live["positions"]:
            print(f"  ochiq: {short(p['symbol'])} {p['side'].upper()}  {float(p.get('unrealizedPnl') or 0):+.2f} USDT")
    if not rows:
        print("\nHali yopilgan savdo yo'q.\n")
        return
    s = summarize(rows)
    best = max(rows, key=lambda r: float(r["natija_usdt"]))
    worst = min(rows, key=lambda r: float(r["natija_usdt"]))
    pf = f"{s['profit_factor']:.2f}" if s["profit_factor"] is not None else "—"
    print(f"Davr: {rows[0]['ochilgan'][:16]} → {rows[-1]['yopilgan'][:16]}\n")
    print(f"Jami savdolar ........ {s['count']}")
    print(f"Yutuq / zarar ........ {s['wins']} / {s['losses']}  ({s['winrate']:.1f}% yutuq)")
    print(f"Sof natija ........... {s['pnl']:+.2f} USDT")
    print(f"Komissiyalar ......... {s['fees']:.2f} USDT")
    print(f"O'rtacha yutuq ....... {s['avg_win']:+.2f} USDT")
    print(f"O'rtacha zarar ....... {s['avg_loss']:+.2f} USDT")
    print(f"Profit factor ........ {pf}  (1 dan katta = foydali)")
    print(f"Eng yaxshi savdo ..... {float(best['natija_usdt']):+.2f} USDT ({best['coin']} {best['yonalish']})")
    print(f"Eng yomon savdo ...... {float(worst['natija_usdt']):+.2f} USDT ({worst['coin']} {worst['yonalish']})")
    print(f"Eng katta pasayish ... {s['max_dd']:.2f} USDT")
    print(f"Oxirgi balans ........ {rows[-1]['balans']} USDT")

    by_day = defaultdict(list)
    for r in rows:
        by_day[r["yopilgan"][:10]].append(r)
    print("\nKunlar bo'yicha (oxirgi 7 kun):")
    for day in sorted(by_day)[-7:]:
        d = summarize(by_day[day])
        print(f"  {day}  {d['count']:>4} savdo  {d['winrate']:>3.0f}% yutuq  {d['pnl']:>+10.2f} USDT")

    by_coin = defaultdict(list)
    for r in rows:
        by_coin[r["coin"]].append(r)
    print("\nCoinlar bo'yicha:")
    print(f"  {'COIN':<6}{'SAVDO':>6}{'YUTUQ':>8}{'NATIJA':>12}")
    for coin, coin_rows in sorted(by_coin.items(), key=lambda kv: -summarize(kv[1])["pnl"]):
        c = summarize(coin_rows)
        print(f"  {coin:<6}{c['count']:>6}{c['winrate']:>7.0f}%{c['pnl']:>+12.2f}")

    print("\nOxirgi 10 ta savdo:")
    for r in rows[-10:]:
        print(f"  {r['yopilgan'][5:16]}  {r['coin']:<5} {r['yonalish']:<5} {r['sabab']:<7} "
              f"{float(r['natija_usdt']):>+9.2f} USDT")
    print()


# ---------------------------------------------------------------- sozlash

def validate_config():
    liq_distance = 100 / LEVERAGE - MAINTENANCE_MARGIN_PCT
    if SL_PCT >= liq_distance:
        sys.exit(f"SL_PCT={SL_PCT}% likvidatsiya masofasidan (~{liq_distance:.2f}%) katta yoki teng. "
                 f"SL_PCT ni kamaytiring yoki LEVERAGE ni pasaytiring.")
    if TP_PCT < 0 or SL_PCT <= 0:
        sys.exit("TP_PCT 0 yoki undan katta (0 = TP yo'q), SL_PCT esa 0 dan katta bo'lishi kerak.")
    if EXCHANGE not in ("mexc", "binance"):
        sys.exit("EXCHANGE faqat 'mexc' yoki 'binance' bo'lishi mumkin.")
    if MODE not in ("paper", "demo", "live"):
        sys.exit("MODE faqat 'paper', 'demo' yoki 'live' bo'lishi mumkin.")
    if MODE == "demo" and EXCHANGE != "binance":
        sys.exit("demo rejim faqat Binance uchun (MEXC futures demo API bermaydi). MODE=paper ishlating.")
    if not 0 < MARGIN_PCT <= 100:
        sys.exit("MARGIN_PCT 0 dan katta va 100 dan kichik yoki teng bo'lishi kerak (1 = balansning 1%).")
    if MAX_POSITIONS < 1:
        sys.exit("MAX_POSITIONS kamida 1 bo'lishi kerak.")
    if not 0 < MAX_MARGIN_PCT <= 100 or MARGIN_PCT > MAX_MARGIN_PCT:
        sys.exit("MAX_MARGIN_PCT 0..100 oralig'ida va MARGIN_PCT dan kichik bo'lmasligi kerak.")
    if not 0 <= MARTINGALE_STEPS <= 5:
        sys.exit("MARTINGALE_STEPS 0 dan 5 gacha bo'lishi kerak (0 = martingeyl o'chiq).")
    if MARTINGALE_STEPS:
        if MARTINGALE_STEP_PCT <= 0 or MARTINGALE_MULT < 1 or MARTINGALE_PROFIT_USDT <= 0:
            sys.exit("MARTINGALE_STEP_PCT va MARTINGALE_PROFIT_USDT 0 dan katta, MARTINGALE_MULT kamida 1 bo'lsin.")
        if MARTINGALE_SL_PCT <= MARTINGALE_STEP_PCT * MARTINGALE_STEPS:
            sys.exit(f"MARTINGALE_SL_PCT ({MARTINGALE_SL_PCT}%) oxirgi martingeyl qadamidan "
                     f"({MARTINGALE_STEP_PCT * MARTINGALE_STEPS:g}%) uzoqroq bo'lishi kerak.")
        if MARTINGALE_SL_PCT >= liq_distance:
            sys.exit(f"MARTINGALE_SL_PCT={MARTINGALE_SL_PCT}% likvidatsiya masofasidan (~{liq_distance:.2f}%) "
                     f"katta. LEVERAGE ni pasaytiring.")
    if not 0 < CORR_MAX <= 1:
        sys.exit("CORR_MAX 0 dan katta va 1 dan kichik yoki teng bo'lishi kerak (1 = o'xshashlik filtri o'chiq).")
    if TOP_COINS < 1 or MIN_COINS < 1 or CORR_LOOKBACK < 24:
        sys.exit("TOP_COINS va MIN_COINS kamida 1, CORR_LOOKBACK kamida 24 bo'lishi kerak.")
    for name, tf in (("TIMEFRAME", TIMEFRAME), ("CORR_TIMEFRAME", CORR_TIMEFRAME)):
        try:
            ccxt.Exchange.parse_timeframe(tf)
        except Exception:
            sys.exit(f"{name}={tf} noto'g'ri. Masalan: 1m, 5m, 15m, 1h")


def has_keys():
    prefix = EXCHANGE.upper()
    return bool(os.getenv(f"{prefix}_API_KEY") and os.getenv(f"{prefix}_SECRET"))


def make_exchange():
    config = {"enableRateLimit": True, "options": {"defaultType": "swap"}}
    if MODE != "paper":
        if not has_keys():
            prefix = EXCHANGE.upper()
            sys.exit(f"{MODE} rejim uchun .env faylida {prefix}_API_KEY va {prefix}_SECRET kerak.")
        config.update(apiKey=os.getenv(f"{EXCHANGE.upper()}_API_KEY"), secret=os.getenv(f"{EXCHANGE.upper()}_SECRET"))
    exchange = getattr(ccxt, EXCHANGE)(config)
    if MODE == "demo":
        exchange.enable_demo_trading(True)
    return exchange


def make_broker(exchange):
    if MODE == "paper":
        return PaperBroker(exchange, PAPER_BALANCE)
    return BinanceBroker(exchange) if EXCHANGE == "binance" else LiveBroker(exchange)


def select(exchange):
    log.info("🪙 Coinlar tanlanmoqda: hajm va %s shamlar yuklanmoqda (10–30 soniya)...", CORR_TIMEFRAME)
    return universe.select_coins(exchange, TOP_COINS, CORR_TIMEFRAME, CORR_LOOKBACK, CORR_MAX, MIN_COINS,
                                 symbols=SYMBOLS or None, log=log)


def selection_title(res):
    if res["source"] == "list":
        return f"SYMBOLS ro'yxatidagi {len(SYMBOLS)} ta coin"
    return f"hajm bo'yicha top {TOP_COINS}" + (" (zaxira ro'yxat)" if res["source"] == "fallback" else "")


def choose_coins(exchange):
    """Savdo qilinadigan coinlar: eng likvidlari, grafigi o'xshashlari chiqarilgan."""
    res = select(exchange)
    kept = res["kept"]
    log.info("🪙 Coinlar: %s → grafigi o'xshashlar chiqarildi (korrelyatsiya ≥ %.2f) → %d ta coin",
             selection_title(res), CORR_MAX, len(kept))
    log.info("   Tanlandi: %s", ", ".join(short(s) for s in kept) or "—")
    if res["similar"]:
        log.info("   O'xshash, chiqarildi (%d): %s", len(res["similar"]),
                 ", ".join(f"{short(s)}~{short(k)} {c:.2f}" for s, k, c in res["similar"]))
    if res["short"]:
        log.info("   Tarixi yetarli emas (%d): %s", len(res["short"]), ", ".join(short(s) for s in res["short"]))
    if res["missing"]:
        log.warning("   Birjada topilmadi: %s", ", ".join(short(s) for s in res["missing"]))
    return kept


def print_coins(exchange):
    """`--coins`: tanlangan va chiqarilgan coinlar jadvali."""
    exchange.load_markets()
    res = select(exchange)
    vols = res["volumes"]

    def volume(s):
        return f"{vols[s] / 1e6:>10,.0f} mln $" if vols.get(s) else ""

    print(f"\n========== 🪙 COINLAR — {EXCHANGE.upper()} {MODE} ==========")
    print(f"{selection_title(res)} → o'xshashlik chegarasi {CORR_MAX:.2f} "
          f"({CORR_TIMEFRAME} × {CORR_LOOKBACK} sham)\n")
    print(f"✅ Tanlandi ({len(res['kept'])}):")
    for s in res["kept"]:
        print(f"  {short(s):<10}{volume(s)}")
    if res["similar"]:
        print(f"\n❌ Grafigi o'xshash — chiqarildi ({len(res['similar'])}):")
        for s, k, c in res["similar"]:
            print(f"  {short(s):<10} ~ {short(k):<10} korrelyatsiya {c:.2f}")
    if res["short"]:
        print(f"\n⏳ Tarixi yetarli emas ({len(res['short'])}): " + ", ".join(short(s) for s in res["short"]))
    if res["missing"]:
        print("\n⚠️  Birjada topilmadi: " + ", ".join(short(s) for s in res["missing"]))
    print()


def log_settings(balance, mart):
    if SETTINGS_LOGGER:  # boshqa strategiya (masalan swing_bot) o'z sozlamalarini o'zi yozadi
        return SETTINGS_LOGGER(balance)
    margin = balance * MARGIN_PCT / 100
    notional = margin * LEVERAGE
    sl_pct = MARTINGALE_SL_PCT if mart else SL_PCT
    tp_text = f"TP +{TP_PCT:.4g}%" if TP_PCT > 0 else "TP yo'q"
    log.info("Sozlamalar: har savdoga balansning %.4g%% i × %dx | %s | SL -%.4g%% | %s shamlar | "
             "max %d coin | marja limiti %.4g%% | kunlik zarar limiti %.4g%%",
             MARGIN_PCT, LEVERAGE, tp_text, sl_pct, TIMEFRAME, MAX_POSITIONS, MAX_MARGIN_PCT, DAILY_LOSS_PCT)
    log.info("Hozirgi balansda bitta savdo: marja ≈ %.2f USDT → pozitsiya %.0f USDT | TP ≈ %s | "
             "SL ≈ %+.2f USDT (komissiyasiz)", margin, notional,
             f"{notional * TP_PCT / 100:+.2f} USDT" if TP_PCT > 0 else "—", -notional * sl_pct / 100)
    if mart:
        worst = sum(notional * MARTINGALE_MULT ** k * (MARTINGALE_SL_PCT - k * MARTINGALE_STEP_PCT) / 100
                    for k in range(MARTINGALE_STEPS + 1))
        log.info("Martingeyl: %d qadam (har −%.4g%% da ×%.4g) | martingeyldan keyin +%.4g$ foydada yopiladi | "
                 "eng yomon holatda bitta coin ≈ %.2f USDT", MARTINGALE_STEPS, MARTINGALE_STEP_PCT,
                 MARTINGALE_MULT, MARTINGALE_PROFIT_USDT, -worst)
    elif MARTINGALE_STEPS:
        log.warning("Martingeyl bu birja/rejimda qo'llab-quvvatlanmaydi — o'chirildi (SL = %.4g%%).", SL_PCT)
    log.info("Coin tanlash: top %d (hajm bo'yicha), o'xshashlik chegarasi %.2f (%s × %d), kamida %d ta, "
             "har %.4g soatda yangilanadi", TOP_COINS, CORR_MAX, CORR_TIMEFRAME, CORR_LOOKBACK, MIN_COINS,
             REFRESH_HOURS)
    legacy = [k for k in LEGACY_KEYS if os.getenv(k)]
    if legacy:
        log.warning("⚠️  .env faylida eski versiya sozlamalari bor (%s). Ular endi ishlatilmaydi, lekin "
                    "LEVERAGE/TP_PCT/SL_PCT/TIMEFRAME ham eski qiymatda qolgan bo'lishi mumkin — "
                    "README'dagi '.env ni yangilash' bo'limiga qarang.", ", ".join(legacy))


# ---------------------------------------------------------------- savdo

def scan(exchange, symbols):
    """Coinlarni tahlil qiladi. (signallar[(symbol, side)], qisqa_hisobot) qaytaradi."""
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


def open_trade(exchange, broker, symbol, side, balance, stop_pct=None, risk_pct=None, meta=None):
    """Signal bo'yicha savdo ochadi. Ochilsa True.
    Oddiy holat: marja = balansning MARGIN_PCT foizi, SL = SL_PCT.
    stop_pct va risk_pct berilsa (swing_bot): SL = stop_pct, hajm shunday tanlanadiki SL urilsa
    balansning risk_pct foizi yo'qotiladi. meta — pozitsiyaga qo'shiladigan qo'shimcha ma'lumot (masalan ATR)."""
    try:
        price = exchange.fetch_ticker(symbol)["last"]
        if stop_pct and risk_pct:
            liq = 100 / LEVERAGE - MAINTENANCE_MARGIN_PCT
            if stop_pct >= liq:
                log.info("%s: SL (%.2f%%) likvidatsiyadan (%.2f%%) uzoq — o'tkazib yuborildi.", short(symbol),
                         stop_pct, liq)
                return False
            notional = balance * risk_pct / stop_pct
            sl_pct = stop_pct
        else:
            notional = balance * MARGIN_PCT / 100 * LEVERAGE
            sl_pct = MARTINGALE_SL_PCT if martingale_on(broker) else SL_PCT
        cap = broker.max_notional(symbol)
        if cap is not None and notional > cap * 0.98:
            if cap <= 0:
                log.warning("%s: %dx leverage bilan savdo mumkin emas — o'tkazib yuborildi.", short(symbol), LEVERAGE)
                return False
            log.info("%s: Binance limiti %dx da %.0f USDT — pozitsiya kichraytirildi.", short(symbol), LEVERAGE, cap)
            notional = cap * 0.98
        size = contract_size(exchange, symbol)
        try:
            contracts = float(exchange.amount_to_precision(symbol, notional / (price * size)))
        except ccxt.InvalidOrder:
            contracts = 0.0
        qty = contracts * size
        limits = exchange.market(symbol).get("limits") or {}
        min_cost = (limits.get("cost") or {}).get("min") or 0
        min_amount = (limits.get("amount") or {}).get("min") or 0
        if contracts <= 0 or contracts < min_amount or qty * price < min_cost:
            log.info("%s: savdo hajmi (%.2f USDT) birja minimumidan kichik — o'tkazib yuborildi.",
                     short(symbol), notional)
            return False
        if used_margin(broker) + qty * price / LEVERAGE > balance * MAX_MARGIN_PCT / 100:
            log.info("%s: marja limiti (%.4g%%) — o'tkazib yuborildi.", short(symbol), MAX_MARGIN_PCT)
            return False
        sign = 1 if side == "long" else -1
        tp = price * (1 + sign * TP_PCT / 100) if TP_PCT > 0 else None
        sl = price * (1 - sign * sl_pct / 100)
        broker.open(symbol, side, contracts, qty, price, sl, tp)
    except (ccxt.AuthenticationError, ccxt.PermissionDenied):
        raise  # kalit xato — davom etib bo'lmaydi
    except ccxt.BaseError as e:
        log.error("%s: savdo ochilmadi: %s", short(symbol), e)
        return False
    p = broker.positions[symbol]
    if meta:
        p.update(meta)
    log.info("🟢 %s %s ochildi @ %s | marja %.2f USDT × %dx = %.0f USDT | TP %s | SL %s | ochiq %d/%d",
             short(symbol), side.upper(), fmt_price(p["entry"]), p["margin"], LEVERAGE, p["qty"] * p["entry"],
             fmt_price(tp), fmt_price(sl), len(broker.positions), MAX_POSITIONS)
    return True


def manage_martingale(exchange, broker, balance):
    """Martingeyl: narx birinchi kirishdan har MARTINGALE_STEP_PCT qarshi yurganda pozitsiyaga ×MARTINGALE_MULT
    hajm qo'shiladi (MARTINGALE_STEPS martagacha). Martingeyl qilingan coinning sof foydasi
    MARTINGALE_PROFIT_USDT ga yetishi bilan shu coindagi barcha savdolar yopiladi. Yopilganlarni qaytaradi."""
    closed = []
    if not martingale_on(broker):
        return closed
    cap = balance * MAX_MARGIN_PCT / 100
    for symbol, p in list(broker.positions.items()):
        if p.get("adopted"):
            continue
        try:
            price = p["last"]
            if p["adds"] and net_pnl(p, price) >= MARTINGALE_PROFIT_USDT:
                closed.append(broker.close(symbol, f"+{MARTINGALE_PROFIT_USDT:g}$ M{p['adds']}"))
                continue
            if p["adds"] >= MARTINGALE_STEPS or p.get("mart_failed") == p["adds"]:
                continue
            sign = 1 if p["side"] == "long" else -1
            adverse = sign * (p["entry0"] - price) / p["entry0"] * 100
            if adverse < MARTINGALE_STEP_PCT * (p["adds"] + 1):
                continue
            try:
                contracts = float(exchange.amount_to_precision(
                    symbol, p["base_contracts"] * MARTINGALE_MULT ** (p["adds"] + 1)))
            except ccxt.InvalidOrder:
                continue
            qty = contracts * contract_size(exchange, symbol)
            if used_margin(broker) + qty * price / LEVERAGE > cap:
                if not p.get("cap_logged"):
                    p["cap_logged"] = True
                    log.warning("%s: marja limiti (%.4g%%) — martingeyl qo'shilmadi, pozitsiya SL bilan qoladi.",
                                short(symbol), MAX_MARGIN_PCT)
                continue
            broker.add(symbol, contracts, qty, price)
            sl = p["entry0"] * (1 - sign * MARTINGALE_SL_PCT / 100)
            tp = martingale_tp(p)
            broker.protect(symbol, sl, tp)
            log.info("🔁 %s %s martingeyl %d/%d: +%.0f USDT @ %s | o'rtacha %s | +%.4g$ da yopiladi: %s | SL %s",
                     short(symbol), p["side"].upper(), p["adds"], MARTINGALE_STEPS, qty * price, fmt_price(price),
                     fmt_price(p["entry"]), MARTINGALE_PROFIT_USDT, fmt_price(tp), fmt_price(sl))
        except (ccxt.AuthenticationError, ccxt.PermissionDenied):
            raise
        except ccxt.BaseError as e:
            p["mart_failed"] = p["adds"]  # shu qadam qayta urinilmaydi (log to'lib ketmasin)
            log.error("%s: martingeyl xatosi (bu qadam o'tkazib yuborildi): %s", short(symbol), e)
    return closed


def run(exchange, broker, journal, pick_coins=choose_coins, scan_fn=None, manage_fn=None,
        sleep=time.sleep, clock=time.time, max_loops=None):
    """Asosiy sikl. scan_fn — signal topish (standart: scan), manage_fn — ochiq pozitsiyalarni boshqarish
    (standart: manage_martingale). Boshqa strategiyalar (razgon_bot, trend_bot) o'zinikini beradi."""
    exchange.load_markets()
    broker.setup()
    log.info("%s | rejim=%s | balans %.2f USDT", EXCHANGE.upper(), MODE, broker.balance())
    log_settings(broker.balance(), martingale_on(broker))
    coins = pick_coins(exchange)
    if not coins:
        sys.exit("Birorta coin tanlanmadi — SYMBOLS yoki TOP_COINS sozlamasini tekshiring.")
    candle_seconds = ccxt.Exchange.parse_timeframe(TIMEFRAME)
    state = dict(last_candle=None, last_status=None, paused_day=None, cooldown={}, coins=coins, coins_at=clock(),
                 cap_logged=False)

    def refresh_coins():
        state["coins_at"] = clock()
        try:
            new = pick_coins(exchange)
        except ccxt.BaseError as e:
            log.warning("Coinlar ro'yxatini yangilab bo'lmadi (%s) — eskisi bilan davom etaman.", e)
            return
        if not new:
            log.warning("Yangi coinlar ro'yxati bo'sh chiqdi — eskisi bilan davom etaman.")
            return
        added = [short(s) for s in new if s not in state["coins"]]
        removed = [short(s) for s in state["coins"] if s not in new]
        if added or removed:
            log.info("🪙 Coinlar ro'yxati yangilandi: qo'shildi %s | chiqarildi %s",
                     ", ".join(added) or "—", ", ".join(removed) or "—")
        state["coins"] = new

    def step():
        closed = broker.poll()
        closed += (manage_fn or manage_martingale)(exchange, broker, broker.balance())
        for trade in closed:
            # Yopilgan coin kamida bitta to'liq sham davomida qayta ochilmaydi
            state["cooldown"][trade["symbol"]] = clock() + candle_seconds
            if journal.add(trade, broker.balance()) is not None:
                report_close(trade, journal)
        if state["last_status"] is None or clock() - state["last_status"] >= STATUS_MINUTES * 60:
            state["last_status"] = clock()
            report_status(broker, journal)
        if clock() - state["coins_at"] >= REFRESH_HOURS * 3600:
            refresh_coins()

        if len(broker.positions) >= MAX_POSITIONS:
            return None
        balance = broker.balance()
        if balance < MIN_BALANCE:
            if not broker.positions:
                log.info("Balans %.2f USDT — juda kam. Bot to'xtadi.", balance)
                return "broke"
            return None
        today = summarize(journal.today_rows())["pnl"]
        if today < 0 and -today >= DAILY_LOSS_PCT / 100 * (balance - today):
            day = datetime.now().strftime("%Y-%m-%d")
            if state["paused_day"] != day:
                state["paused_day"] = day
                log.warning("⛔ Bugungi zarar %.2f USDT — limit (%.4g%%) ga yetdi. Ertagacha yangi savdo "
                            "ochilmaydi, ochiq pozitsiyalar kuzatiladi.", today, DAILY_LOSS_PCT)
            return None
        cap, base_margin = balance * MAX_MARGIN_PCT / 100, balance * MARGIN_PCT / 100
        if used_margin(broker) + base_margin > cap:
            if not state["cap_logged"]:
                state["cap_logged"] = True
                log.info("Marja limiti (%.4g%%) to'ldi — yangi savdo ochilmaydi, ochiqlari kuzatiladi.", MAX_MARGIN_PCT)
            return None
        state["cap_logged"] = False

        # Yangi sham yopilmaguncha qayta skan qilmaymiz (birinchi coin bo'yicha tekshiramiz)
        coins = state["coins"]
        head = exchange.fetch_ohlcv(coins[0], TIMEFRAME, limit=2)
        if len(head) < 2 or head[-2][0] == state["last_candle"]:
            return None
        candidates = [s for s in coins
                      if s not in broker.positions and state["cooldown"].get(s, 0) <= clock()]
        signals, report = (scan_fn or scan)(exchange, candidates)
        state["last_candle"] = head[-2][0]
        if not signals:
            log.info("Skan: %d ta coin | signal yo'q | %s | ochiq %d/%d",
                     len(candidates), report, len(broker.positions), MAX_POSITIONS)
            return None

        log.info("Skan: signallar — %s", ", ".join(f"{short(sig[0])} {sig[1].upper()}" for sig in signals))
        for sig in signals:
            symbol, side = sig[0], sig[1]
            extra = sig[2] if len(sig) > 2 else {}  # strategiya qo'shimcha parametr berishi mumkin
            if len(broker.positions) >= MAX_POSITIONS:
                log.info("Bo'sh joy qolmadi (%d/%d) — qolgan signallar o'tkazib yuborildi.",
                         MAX_POSITIONS, MAX_POSITIONS)
                break
            if used_margin(broker) + base_margin > cap:
                log.info("Marja limiti (%.4g%%) — qolgan signallar o'tkazib yuborildi.", MAX_MARGIN_PCT)
                break
            open_trade(exchange, broker, symbol, side, balance, **extra)
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
        except (ccxt.AuthenticationError, ccxt.PermissionDenied):
            raise  # kalit xato — davom etib bo'lmaydi
        except ccxt.ExchangeError as e:
            log.error("Birja xatosi, davom etaman: %s", e)
            sleep(POLL_SECONDS)
            continue
        if result:
            return result
        sleep(POLL_SECONDS)
    return "max_loops"


def close_positions(exchange, broker, journal, coin=None):
    """`--close [COIN]` — ochiq pozitsiyalarni bozor narxida yopadi va SL/TP ni bekor qiladi."""
    if MODE == "paper":
        sys.exit("paper rejimda birjada pozitsiya yo'q (virtual pozitsiyalar bot to'xtaganda yo'qoladi).")
    exchange.load_markets()
    broker.setup()
    targets = [s for s in list(broker.positions) if coin is None or short(s) == coin.upper()]
    if not targets:
        log.info("Ochiq pozitsiya yo'q.")
        return
    for symbol in targets:
        trade = broker.close(symbol, "qo'lda")
        if journal.add(trade, broker.balance()) is not None:
            report_close(trade, journal)


def live_snapshot(exchange):
    """--stats uchun birjadagi joriy balans va ochiq pozitsiyalar."""
    exchange.load_markets()
    bal = exchange.fetch_balance()["USDT"]
    positions = [p for p in exchange.fetch_positions()
                 if float(p.get("contracts") or 0) > 0 and (p.get("symbol") or "").endswith(":USDT")]
    return dict(total=float(bal.get("total") or 0), free=float(bal.get("free") or 0), positions=positions)


def main():
    parser = argparse.ArgumentParser(description="Binance/MEXC futures scalping bot")
    parser.add_argument("--stats", action="store_true", help="statistikani ko'rsatish")
    parser.add_argument("--close", nargs="?", const="ALL", metavar="COIN",
                        help="ochiq pozitsiyalarni yopish (hammasi yoki bitta coin: --close SOL)")
    parser.add_argument("--coins", action="store_true",
                        help="qaysi coinlar tanlangani va qaysilari nega chiqarilganini ko'rsatish")
    args = parser.parse_args()

    handlers = [logging.StreamHandler()]
    if not (args.stats or args.coins):
        handlers.append(logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=5_000_000, backupCount=3,
                                                             encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
                        handlers=handlers)
    journal = Journal(JOURNAL_PATH)

    if args.stats:
        live = None
        if MODE != "paper" and has_keys():
            try:
                live = live_snapshot(make_exchange())
            except ccxt.BaseError as e:
                print(f"Birjaga ulanib bo'lmadi, faqat jurnal ko'rsatiladi: {e}")
        print_stats(journal, live)
        return

    validate_config()
    exchange = make_exchange()
    if args.coins:
        print_coins(exchange)
        return
    broker = make_broker(exchange)
    if args.close:
        close_positions(exchange, broker, journal, None if args.close == "ALL" else args.close)
        return
    if MODE == "live":
        log.warning("⚠️  LIVE rejim: haqiqiy pul bilan savdo. To'xtatish uchun Ctrl+C.")
    try:
        run(exchange, broker, journal)
    except KeyboardInterrupt:
        if MODE == "paper":
            log.info("To'xtatildi. (paper rejim: virtual pozitsiyalar yopilmagan holda qoldi)")
        else:
            log.info("To'xtatildi. Ochiq pozitsiyalar birjada SL/TP bilan qoladi. "
                     "Ko'rish: --stats, yopish: --close")


if __name__ == "__main__":
    main()
