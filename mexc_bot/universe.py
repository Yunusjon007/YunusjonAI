"""
Coinlar ro'yxatini tanlash.

1. Birjadagi faol USDT perpetual coinlar olinadi (stablecoin, indeks, oltin/aksiya kabi
   coin bo'lmagan aktivlar chiqariladi).
2. 24 soatlik savdo hajmi bo'yicha eng likvid TOP tasi qoldiriladi.
3. Har bir coinning soatlik narx o'zgarishlari (log-returns) olinadi.
4. Coinlar likvidlik tartibida ko'rib chiqiladi: allaqachon tanlangan biror coin bilan
   korrelyatsiyasi CORR_MAX dan yuqori bo'lsa — "grafigi o'xshash" deb chiqariladi.
5. Bozor juda bir xil harakat qilgan kunlarda ham kamida MIN_COINS ta coin qoladi
   (eng kam o'xshashlari qaytariladi).
"""
import math

import ccxt

STABLECOINS = {
    "USDC", "USDT", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "USDE", "USD1", "PYUSD",
    "RLUSD", "USDS", "BFUSD", "XUSD", "EUR", "EURI", "GBP", "AEUR",
}
INDEXES = {"BTCDOM", "DEFI", "FOOTBALL", "BLUEBIRD", "ALL"}

# Hajm ma'lumoti olinmasa ishlatiladigan zaxira ro'yxat (likvidlik bo'yicha tartiblangan)
FALLBACK = (
    "BTC,ETH,SOL,XRP,BNB,DOGE,ADA,TRX,AVAX,LINK,SUI,DOT,LTC,BCH,NEAR,APT,ARB,OP,FIL,ATOM,"
    "AAVE,UNI,ETC,HBAR,XLM,ICP,INJ,TIA,SEI,WLD,ENA,ONDO,TON,RENDER,FET,TAO,JUP,PENDLE,LDO,CRV,"
    "STX,IMX,ALGO,VET,SAND,GALA,1000PEPE,1000SHIB,1000BONK,WIF"
).split(",")


def short(symbol):
    return symbol.split("/")[0]


def futures_universe(exchange):
    """Birjadagi faol, muddatsiz USDT-M (linear) coinlar."""
    out = []
    for symbol, m in exchange.markets.items():
        if not (m.get("swap") and m.get("linear") and m.get("quote") == "USDT" and m.get("settle") == "USDT"):
            continue
        if m.get("active") is False or m.get("expiry"):
            continue
        base = m.get("base") or short(symbol)
        if base in STABLECOINS or base in INDEXES:
            continue
        if exchange.id == "binance":
            info = m.get("info") or {}
            # oltin, indekslar, aksiyalar va boshqa coin bo'lmagan kontraktlar
            if info.get("underlyingType") not in (None, "COIN"):
                continue
            if info.get("contractType") not in (None, "PERPETUAL"):
                continue
        out.append(symbol)
    return out


def rank_by_volume(exchange, symbols):
    """24 soatlik USDT hajmi bo'yicha (kattadan kichikka). (tartiblangan_ro'yxat, {symbol: hajm})."""
    tickers = exchange.fetch_tickers(symbols)
    volumes = {s: float((tickers.get(s) or {}).get("quoteVolume") or 0) for s in symbols}
    ranked = sorted((s for s in symbols if volumes[s] > 0), key=lambda s: -volumes[s])
    return ranked, volumes


def log_returns(candles):
    """{sham_vaqti: log(close / oldingi_close)} — faqat yopilgan shamlar beriladi."""
    out = {}
    for prev, cur in zip(candles, candles[1:]):
        if prev[4] and cur[4] and prev[4] > 0 and cur[4] > 0:
            out[cur[0]] = math.log(cur[4] / prev[4])
    return out


def correlation(a, b, min_points):
    """Ikki coin narx o'zgarishlarining Pearson korrelyatsiyasi (-1..1). Ma'lumot yetmasa None."""
    common = [t for t in a if t in b]
    if len(common) < min_points:
        return None
    xs = [a[t] for t in common]
    ys = [b[t] for t in common]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def pick_diverse(ranked, returns, corr_max, min_points, min_coins):
    """Likvidlik tartibida: tanlanganlarga o'xshamagan coinlarni qoldiradi.
    (tanlandi, o'xshash[(coin, kimga_o'xshash, korrelyatsiya)], tarixi_qisqa) qaytaradi."""
    kept, similar, short_history = [], [], []
    for symbol in ranked:
        r = returns.get(symbol)
        if not r or len(r) < min_points:
            short_history.append(symbol)
            continue
        best = None
        for k in kept:
            c = correlation(r, returns[k], min_points)
            if c is not None and (best is None or c > best[1]):
                best = (k, c)
        if best and best[1] >= corr_max:
            similar.append((symbol, best[0], best[1]))
        else:
            kept.append(symbol)
    # Bozor juda bir xil harakat qilgan kunlarda ham kamida min_coins ta coin qolsin
    if len(kept) < min_coins and similar:
        extra = sorted(similar, key=lambda x: x[2])[:min_coins - len(kept)]
        kept += [s for s, _, _ in extra]
        similar = [x for x in similar if x not in extra]
        order = {s: i for i, s in enumerate(ranked)}
        kept.sort(key=order.get)
    return kept, similar, short_history


def select_coins(exchange, top, timeframe, lookback, corr_max, min_coins, symbols=None, log=None):
    """Asosiy funksiya. symbols berilsa (SYMBOLS sozlamasi) — hajm o'rniga shu ro'yxat va tartib ishlatiladi.

    Natija: dict(kept, similar, short, missing, volumes, source)."""
    universe = futures_universe(exchange)
    available = set(universe)
    volumes, missing = {}, []
    if symbols:
        source = "list"
        missing = [s for s in symbols if s not in available]
        ranked = [s for s in symbols if s in available]
    else:
        try:
            ranked, volumes = rank_by_volume(exchange, universe)
            source = "volume"
        except ccxt.BaseError as e:
            if log:
                log.warning("Savdo hajmlarini olib bo'lmadi (%s) — zaxira ro'yxat ishlatiladi.", e)
            ranked = [s for s in (f"{c}/USDT:USDT" for c in FALLBACK) if s in available]
            source = "fallback"
        ranked = ranked[:top]

    min_points = max(10, int(lookback * 0.7))
    returns = {}
    for symbol in ranked:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, limit=lookback + 2)
        except ccxt.BaseError as e:
            if log:
                log.warning("%s: %s shamlarini olib bo'lmadi: %s", short(symbol), timeframe, e)
            continue
        returns[symbol] = log_returns(candles[:-1])  # oxirgi sham hali yopilmagan

    kept, similar, short_history = pick_diverse(ranked, returns, corr_max, min_points, min_coins)
    return dict(kept=kept, similar=similar, short=short_history, missing=missing,
                volumes=volumes, source=source)
