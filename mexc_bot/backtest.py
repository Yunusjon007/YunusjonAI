"""
Backtest — trend_bot.py (5m) yoki swing_bot.py (--swing, 1h/4h) strategiyasini Binance'ning haqiqiy
tarixida sinaydi.

Swing (--swing): swing_bot.swing_decide qoidasi, risk bo'yicha hajm, piramida (har +ATR da qism, trigger
narxida), chandelier SL, balans maqsadi, komissiya, 0.05% sirpanish va har soatda funding (0.01% / 8 soat).
Qism qo'shilgan shamning o'zida yangi SL urilgan deb hisoblanadi (ehtiyotkor taxmin).
  python3 backtest.py --swing                 # oxirgi 90 kun
  python3 backtest.py --swing --sweep         # SL / chandelier / qismlar sonini solishtirish

Trend (standart):

Botdagi aynan o'sha qoidalar (trend_bot.decide va trend_bot.trail_stop) ishlatiladi:
  - har --interval daqiqada eng kuchli trenddagi coin, marja --margin% × --leverage
  - boshlang'ich SL --sl%, har --step% foydada SL siljiydi, TP --tp% (0 = yo'q)
  - komissiya 0.05% + 0.05%, SL da 0.05% sirpanish, kunlik zarar limiti
  - sham ichida SL birinchi tekshiriladi (ehtiyotkor taxmin), SL siljishi keyingi shamdan kuchga kiradi

Ishlatish:
  python3 backtest.py                    # oxirgi 14 kun, standart sozlamalar
  python3 backtest.py --days 30          # 30 kun
  python3 backtest.py --sweep            # bir nechta sozlamani solishtirish
  python3 backtest.py --step 0.5 --sl 0.7 --interval 10

Natija backtest_trend.csv fayliga ham yoziladi. O'tmishdagi natija kelajakni kafolatlamaydi.
"""
import argparse
import csv
import logging
import sys
from collections import defaultdict
from datetime import datetime
from types import SimpleNamespace

import ccxt

import allin_bot as core
import swing_bot as sb
import trend_bot as tb

log = logging.getLogger("bot")
CANDLE_MS = 300_000
H1_MS, H4_MS = 3_600_000, 14_400_000


# ---------------------------------------------------------------- indikator qatorlari (tezlik uchun oldindan)

def rsi_series(closes, period):
    out = [None] * len(closes)
    gain_sum = loss_sum = avg_gain = avg_loss = 0.0
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        g, l = max(d, 0.0), max(-d, 0.0)
        if i <= period:
            gain_sum += g
            loss_sum += l
            if i < period:
                continue
            avg_gain, avg_loss = gain_sum / period, loss_sum / period
        else:
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + l) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def atr_series(highs, lows, closes, period):
    out = [None] * len(closes)
    trs = [0.0] + [max(h - l, abs(h - pc), abs(l - pc)) for h, l, pc in zip(highs[1:], lows[1:], closes[:-1])]
    value = None
    for i in range(1, len(closes)):
        if i < period:
            continue
        value = sum(trs[1:period + 1]) / period if value is None else (value * (period - 1) + trs[i]) / period
        out[i] = value
    return out


def indicators(candles):
    closes = [c[4] for c in candles]
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    vols = [c[5] or 0 for c in candles]
    avg_vol = [None] * len(candles)
    window = 0.0
    for i in range(len(candles)):
        if i >= 1:
            window += vols[i - 1]
        if i > tb.VOL_PERIOD:
            window -= vols[i - 1 - tb.VOL_PERIOD]
        if i >= tb.VOL_PERIOD:
            avg_vol[i] = window / tb.VOL_PERIOD
    return dict(fast=core.ema(closes, tb.EMA_FAST), slow=core.ema(closes, tb.EMA_SLOW),
                rsi=rsi_series(closes, core.RSI_PERIOD), atr=atr_series(highs, lows, closes, tb.ATR_PERIOD),
                avg_vol=avg_vol, close=closes, vol=vols)


def decide_at(ind, i):
    if ind["rsi"][i] is None or ind["atr"][i] is None or ind["avg_vol"][i] is None:
        return None
    return tb.decide(ind["fast"][i], ind["slow"][i], ind["close"][i], ind["rsi"][i], ind["atr"][i],
                     ind["vol"][i], ind["avg_vol"][i])


# ---------------------------------------------------------------- simulyatsiya

def default_cfg(balance=5000.0):
    return dict(balance=balance, interval_min=tb.INTERVAL_MIN, margin_pct=tb.MARGIN_PCT, leverage=tb.LEVERAGE,
                sl_pct=tb.SL_PCT, step_pct=tb.STEP_PCT, tp_pct=tb.TP_PCT, max_open=tb.MAX_OPEN,
                daily_loss_pct=tb.DAILY_LOSS_PCT, fee_pct=core.FEE_PCT, slip_pct=0.05, warmup=tb.HISTORY)


def simulate(data, cfg):
    """data: {symbol: yopilgan 5m shamlar}. Natija: dict(rows, final, max_dd, entries)."""
    fee, slip = cfg["fee_pct"] / 100, cfg["slip_pct"] / 100
    be = 2 * cfg["fee_pct"] + 0.02
    ind = {s: indicators(cs) for s, cs in data.items()}
    idx = {s: {c[0]: i for i, c in enumerate(cs)} for s, cs in data.items()}
    times = sorted({c[0] for cs in data.values() for c in cs})
    state = dict(bal=cfg["balance"])
    pos, rows, entries = {}, [], []
    cooldown, day_pnl, day_start = {}, defaultdict(float), {}
    last_entry, peak, max_dd = None, cfg["balance"], 0.0
    interval_ms = cfg["interval_min"] * 60_000

    def day(t):
        return datetime.fromtimestamp(t / 1000).strftime("%Y-%m-%d")

    def close(s, p, px, reason, t):
        gross = max(p["sign"] * p["qty"] * (px - p["entry"]), -p["margin"])  # isolated: marjadan ko'p emas
        fee_out = p["qty"] * px * fee
        state["bal"] += gross - fee_out
        pnl = gross - p["fee_in"] - fee_out
        day_pnl[day(t)] += pnl
        rows.append({
            "ochilgan": core.stamp(p["opened"]), "yopilgan": core.stamp(t), "coin": core.short(s),
            "yonalish": p["side"].upper(), "kirish": f"{p['entry']:.8g}", "chiqish": f"{px:.8g}",
            "hajm_usdt": f"{p['qty'] * p['entry']:.2f}", "marja_usdt": f"{p['margin']:.2f}",
            "natija_usdt": f"{pnl:.4f}", "roi_foiz": f"{100 * pnl / p['margin']:.2f}",
            "komissiya": f"{p['fee_in'] + fee_out:.4f}", "sabab": reason, "balans": f"{state['bal']:.2f}",
        })
        del pos[s]
        cooldown[s] = t + CANDLE_MS

    for t in times:
        # 1) ochiq pozitsiyalar: SL / TP / SL zinapoyasi
        for s, p in list(pos.items()):
            i = idx[s].get(t)
            if i is None:
                continue
            _, o, h, l, c, _ = data[s][i]
            sign = p["sign"]
            if (l <= p["sl"]) if sign > 0 else (h >= p["sl"]):
                px = (min(o, p["sl"]) if sign > 0 else max(o, p["sl"])) * (1 - sign * slip)
                close(s, p, px, "TRAIL" if p["k"] else "SL", t)
                continue
            if p["tp"] is not None and ((h >= p["tp"]) if sign > 0 else (l <= p["tp"])):
                close(s, p, p["tp"], "TP", t)
                continue
            best = h if sign > 0 else l
            k, new_sl = tb.trail_stop(p["side"], p["entry"], sign * (best - p["entry"]) / p["entry"] * 100,
                                      cfg["step_pct"], be)
            if k > p["k"] and sign * (new_sl - p["sl"]) > 0:
                p["k"], p["sl"] = k, new_sl
            p["last"] = c

        equity = state["bal"] + sum(p["sign"] * p["qty"] * (p["last"] - p["entry"]) for p in pos.values())
        peak = max(peak, equity)
        max_dd = min(max_dd, (equity - peak) / peak)

        # 2) yangi savdo: har interval daqiqada eng kuchli trend
        if len(pos) >= cfg["max_open"] or (last_entry is not None and t - last_entry < interval_ms - 1):
            continue
        d = day(t)
        day_start.setdefault(d, state["bal"])
        if day_pnl[d] < 0 and -day_pnl[d] >= cfg["daily_loss_pct"] / 100 * day_start[d]:
            continue
        best = None
        for s in data:
            if s in pos or cooldown.get(s, 0) > t:
                continue
            i = idx[s].get(t)
            if i is None or i < cfg["warmup"]:
                continue
            sig = decide_at(ind[s], i)
            if sig and (best is None or sig[1] > best[2]):
                best = (s, sig[0], sig[1], i)
        if best is None:
            continue
        s, side, _, i = best
        entry = data[s][i][4]
        margin = state["bal"] * cfg["margin_pct"] / 100
        if margin <= 0:
            continue
        notional = margin * cfg["leverage"]
        sign = 1 if side == "long" else -1
        fee_in = notional * fee
        state["bal"] -= fee_in
        pos[s] = dict(side=side, sign=sign, entry=entry, qty=notional / entry, margin=margin, fee_in=fee_in,
                      sl=entry * (1 - sign * cfg["sl_pct"] / 100),
                      tp=entry * (1 + sign * cfg["tp_pct"] / 100) if cfg["tp_pct"] > 0 else None,
                      k=0, opened=t, last=entry)
        entries.append(t)
        last_entry = t

    for s, p in list(pos.items()):
        close(s, p, p["last"], "oxiri", times[-1])
    return dict(rows=rows, final=state["bal"], max_dd=max_dd * 100, entries=entries)


# ---------------------------------------------------------------- swing simulyatsiyasi

def default_swing_cfg(balance=5000.0):
    return dict(balance=balance, risk_pct=sb.RISK_PCT, stop_atr=sb.STOP_ATR, trail_atr=sb.TRAIL_ATR,
                add_atr=sb.ADD_ATR, max_units=sb.MAX_UNITS, leverage=sb.LEVERAGE, max_open=sb.MAX_OPEN,
                max_margin_pct=sb.MAX_MARGIN_PCT, target_pct=sb.TARGET_PCT, daily_loss_pct=sb.DAILY_LOSS_PCT,
                fee_pct=core.FEE_PCT, slip_pct=0.05, funding_8h_pct=0.01,
                warmup=sb.BREAKOUT_BARS + sb.ATR_PERIOD + 2)


def swing_indicators(h1, h4):
    """1h: ATR, oldingi 48 shamning eng yuqori/past nuqtasi; 4h: EMA50/EMA200 (har 1h sham uchun —
    shu sham yopilganda tugagan oxirgi 4h sham bo'yicha)."""
    highs = [c[2] for c in h1]
    lows = [c[3] for c in h1]
    closes = [c[4] for c in h1]
    n, bars = len(h1), sb.BREAKOUT_BARS
    prev_high, prev_low = [None] * n, [None] * n
    for i in range(bars, n):
        prev_high[i] = max(highs[i - bars:i])
        prev_low[i] = min(lows[i - bars:i])
    closes4 = [c[4] for c in h4]
    f4, s4 = core.ema(closes4, sb.EMA_FAST4), core.ema(closes4, sb.EMA_SLOW4)
    fast, slow, k = [None] * n, [None] * n, -1
    for i in range(n):
        closed_at = h1[i][0] + H1_MS
        while k + 1 < len(h4) and h4[k + 1][0] + H4_MS <= closed_at:
            k += 1
        if k >= sb.EMA_SLOW4:
            fast[i], slow[i] = f4[k], s4[k]
    return dict(open=[c[1] for c in h1], high=highs, low=lows, close=closes,
                atr=atr_series(highs, lows, closes, sb.ATR_PERIOD), prev_high=prev_high, prev_low=prev_low,
                fast=fast, slow=slow)


def simulate_swing(data, cfg):
    """data: {symbol: (yopilgan 1h shamlar, yopilgan 4h shamlar)}. Natija: dict(rows, final, max_dd, entries)."""
    fee, slip, fund = cfg["fee_pct"] / 100, cfg["slip_pct"] / 100, cfg["funding_8h_pct"] / 100 / 8
    lev = cfg["leverage"]
    liq = 100 / lev - core.MAINTENANCE_MARGIN_PCT
    ind = {s: swing_indicators(h1, h4) for s, (h1, h4) in data.items()}
    idx = {s: {c[0]: i for i, c in enumerate(h1)} for s, (h1, _) in data.items()}
    times = sorted({c[0] for h1, _ in data.values() for c in h1})
    st = dict(bal=cfg["balance"], base=cfg["balance"])
    pos, rows, entries = {}, [], []
    cooldown, day_pnl, day_start = {}, defaultdict(float), {}
    peak, max_dd = cfg["balance"], 0.0

    def day(t):
        return datetime.fromtimestamp(t / 1000).strftime("%Y-%m-%d")

    def used():
        return sum(q["margin"] for q in pos.values())

    def close(s, p, px, reason, t):
        gross = max(p["sign"] * p["qty"] * (px - p["entry"]), -p["margin"])  # isolated: marjadan ko'p emas
        fee_out = p["qty"] * px * fee
        st["bal"] += gross - fee_out
        cost = p["fee_in"] + fee_out + p["funding"]
        pnl = gross - cost
        day_pnl[day(t)] += pnl
        rows.append({
            "ochilgan": core.stamp(p["opened"]), "yopilgan": core.stamp(t), "coin": core.short(s),
            "yonalish": p["side"].upper(), "kirish": f"{p['entry']:.8g}", "chiqish": f"{px:.8g}",
            "hajm_usdt": f"{p['qty'] * p['entry']:.2f}", "marja_usdt": f"{p['margin']:.2f}",
            "natija_usdt": f"{pnl:.4f}", "roi_foiz": f"{100 * pnl / p['margin']:.2f}",
            "komissiya": f"{cost:.4f}", "sabab": f"{reason} P{p['units'] - 1}" if p["units"] > 1 else reason,
            "balans": f"{st['bal']:.2f}",
        })
        del pos[s]
        cooldown[s] = t + H1_MS

    def stop_out(s, p, o, t):
        sign = p["sign"]
        px = (min(o, p["sl"]) if sign > 0 else max(o, p["sl"])) * (1 - sign * slip)
        close(s, p, px, "TRAIL" if p["trailed"] else "SL", t)

    for t in times:
        # 1) ochiq pozitsiyalar: funding, SL, piramida, chandelier
        for s, p in list(pos.items()):
            i = idx[s].get(t)
            if i is None:
                continue
            x = ind[s]
            o, h, l, c = x["open"][i], x["high"][i], x["low"][i], x["close"][i]
            sign, atr = p["sign"], p["atr"]
            f = p["qty"] * c * fund
            st["bal"] -= f
            p["funding"] += f
            if (l <= p["sl"]) if sign > 0 else (h >= p["sl"]):
                stop_out(s, p, o, t)
                continue
            added = False
            while p["units"] < cfg["max_units"]:
                trigger = p["last_add"] + sign * cfg["add_atr"] * atr
                if not ((h >= trigger) if sign > 0 else (l <= trigger)):
                    break
                add_px = (max(trigger, o) if sign > 0 else min(trigger, o)) * (1 + sign * slip)
                margin_add = p["unit_qty"] * add_px / lev
                if used() + margin_add > st["bal"] * cfg["max_margin_pct"] / 100:
                    break
                fee_add = p["unit_qty"] * add_px * fee
                st["bal"] -= fee_add
                p["entry"] = (p["entry"] * p["qty"] + add_px * p["unit_qty"]) / (p["qty"] + p["unit_qty"])
                p["qty"] += p["unit_qty"]
                p["margin"] += margin_add
                p["fee_in"] += fee_add
                p["units"] += 1
                p["last_add"] = trigger
                new_sl = trigger - sign * cfg["stop_atr"] * atr
                if sign * (new_sl - p["sl"]) > 0:
                    p["sl"] = new_sl
                added = True
            if added and ((l <= p["sl"]) if sign > 0 else (h >= p["sl"])):
                stop_out(s, p, p["sl"], t)  # qo'shimchadan keyin shu shamda SL urildi (ehtiyotkor taxmin)
                continue
            best = h if sign > 0 else l
            if sign * (best - p["best"]) > 0:
                p["best"] = best
            chandelier = p["best"] - sign * cfg["trail_atr"] * atr
            if sign * (chandelier - p["sl"]) > 0:
                p["sl"], p["trailed"] = chandelier, True
            p["last"] = c

        equity = st["bal"] + sum(p["sign"] * p["qty"] * (p["last"] - p["entry"]) for p in pos.values())
        peak = max(peak, equity)
        max_dd = min(max_dd, (equity - peak) / peak)

        # 2) balans maqsadi
        if cfg["target_pct"] > 0 and pos and equity >= st["base"] * (1 + cfg["target_pct"] / 100):
            for s, p in list(pos.items()):
                close(s, p, p["last"] * (1 - p["sign"] * slip), "MAQSAD", t)
            st["base"] = st["bal"]
            continue

        # 3) yangi savdolar: 4h trend bo'yicha 48 soatlik yorish
        d = day(t)
        day_start.setdefault(d, st["bal"])
        if len(pos) >= cfg["max_open"]:
            continue
        if day_pnl[d] < 0 and -day_pnl[d] >= cfg["daily_loss_pct"] / 100 * day_start[d]:
            continue
        cands = []
        for s in data:
            if s in pos or cooldown.get(s, 0) > t:
                continue
            i = idx[s].get(t)
            if i is None or i < cfg["warmup"]:
                continue
            x = ind[s]
            sig = sb.swing_decide(x["fast"][i], x["slow"][i], x["close"][i], x["prev_high"][i], x["prev_low"][i],
                                  x["atr"][i])
            if sig:
                cands.append((sig["score"], s, sig, i))
        cands.sort(key=lambda z: -z[0])
        for _, s, sig, i in cands:
            if len(pos) >= cfg["max_open"]:
                break
            entry = ind[s]["close"][i]
            stop_pct = cfg["stop_atr"] * sig["atr"] / entry * 100
            if stop_pct >= liq:
                continue
            notional = st["bal"] * cfg["risk_pct"] / stop_pct
            margin = notional / lev
            if used() + margin > st["bal"] * cfg["max_margin_pct"] / 100:
                continue
            fee_in = notional * fee
            st["bal"] -= fee_in
            sign = 1 if sig["side"] == "long" else -1
            qty = notional / entry
            pos[s] = dict(side=sig["side"], sign=sign, entry=entry, qty=qty, unit_qty=qty, margin=margin,
                          fee_in=fee_in, sl=entry - sign * cfg["stop_atr"] * sig["atr"], atr=sig["atr"], best=entry,
                          last_add=entry, units=1, trailed=False, opened=t, last=entry, funding=0.0)
            entries.append(t)

    for s, p in list(pos.items()):
        close(s, p, p["last"], "oxiri", times[-1])
    return dict(rows=rows, final=st["bal"], max_dd=max_dd * 100, entries=entries)


# ---------------------------------------------------------------- ma'lumot

def data_exchange(source):
    ex = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    if source == "demo":
        ex.enable_demo_trading(True)
    return ex


def fetch_history(ex, symbol, days, timeframe=None, warmup_bars=None):
    timeframe = timeframe or tb.TIMEFRAME
    warmup_bars = tb.HISTORY + 5 if warmup_bars is None else warmup_bars
    since = (ex.milliseconds() - int(days * 86_400_000)
             - warmup_bars * ccxt.Exchange.parse_timeframe(timeframe) * 1000)
    out = []
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1500)
        batch = [c for c in batch if not out or c[0] > out[-1][0]]
        if not batch:
            break
        out += batch
        since = out[-1][0] + 1
        if len(batch) < 1000:
            break
    return out[:-1]  # oxirgi sham hali yopilmagan


def summary_line(cfg, res):
    s = core.summarize(res["rows"])
    pf = f"{s['profit_factor']:.2f}" if s["profit_factor"] is not None else "—"
    ret = (res["final"] / cfg["balance"] - 1) * 100
    return (f"{cfg['interval_min']:>5.0f}{cfg['sl_pct']:>6.2g}{cfg['step_pct']:>6.2g}{s['count']:>7}"
            f"{s['winrate']:>7.0f}%{pf:>7}{ret:>+9.1f}%{res['max_dd']:>8.1f}%")


def swing_summary_line(cfg, res):
    s = core.summarize(res["rows"])
    pf = f"{s['profit_factor']:.2f}" if s["profit_factor"] is not None else "—"
    ret = (res["final"] / cfg["balance"] - 1) * 100
    return (f"{cfg['stop_atr']:>6.2g}{cfg['trail_atr']:>7.2g}{cfg['max_units']:>6}{s['count']:>7}"
            f"{s['winrate']:>7.0f}%{pf:>7}{ret:>+9.1f}%{res['max_dd']:>8.1f}%")


def write_csv(name, rows):
    with open(core.HERE / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=core.Journal.FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Savdolar ro'yxati: {name}")


def run_swing(ex, coins, args):
    days = args.days or 90
    print(f"\n{len(coins)} ta coinning {days:g} kunlik 1h va 4h tarixi yuklanmoqda...")
    data = {}
    for s in coins:
        try:
            h1 = fetch_history(ex, s, days, "1h", sb.BREAKOUT_BARS + sb.ATR_PERIOD + 10)
            h4 = fetch_history(ex, s, days, "4h", sb.H4_HISTORY + 5)
        except ccxt.BaseError as e:
            print(f"  {core.short(s)}: yuklab bo'lmadi ({e.__class__.__name__}) — o'tkazildi")
            continue
        if len(h1) > sb.BREAKOUT_BARS + 20 and len(h4) > sb.EMA_SLOW4 + 2:
            data[s] = (h1, h4)
    if not data:
        sys.exit("Ma'lumot yuklanmadi.")

    cfg = default_swing_cfg(args.balance)
    cfg.update(risk_pct=args.risk, stop_atr=args.stop_atr, trail_atr=args.trail_atr, max_units=args.units,
               target_pct=args.target, leverage=args.leverage or sb.LEVERAGE, max_open=args.max_open or sb.MAX_OPEN)
    res = simulate_swing(data, cfg)
    first = min(h1[cfg["warmup"]][0] for h1, _ in data.values() if len(h1) > cfg["warmup"])
    last = max(h1[-1][0] for h1, _ in data.values())
    print(f"\nDavr: {core.stamp(first)[:16]} → {core.stamp(last)[:16]} | coinlar: "
          + ", ".join(core.short(s) for s in data))
    print(f"Sozlamalar: 4h trend + 1h {sb.BREAKOUT_BARS} soatlik yorish | har qism riski {cfg['risk_pct']:g}% | "
          f"SL {cfg['stop_atr']:g}×ATR | {cfg['max_units']} qismgacha (har +{cfg['add_atr']:g} ATR) | "
          f"chandelier {cfg['trail_atr']:g}×ATR | {cfg['leverage']}x | max {cfg['max_open']} coin | "
          + (f"balans maqsadi +{cfg['target_pct']:g}%" if cfg["target_pct"] > 0 else "balans maqsadi yo'q"))
    core.print_stats(SimpleNamespace(rows=res["rows"], path=SimpleNamespace(name="backtest_swing.csv")))
    print(f"Balans: {cfg['balance']:.2f} → {res['final']:.2f} USDT ({(res['final'] / cfg['balance'] - 1) * 100:+.1f}%) | "
          f"eng katta pasayish (ochiq savdolar bilan): {res['max_dd']:.1f}% | 'Komissiyalar' ga funding ham kirgan")
    write_csv("backtest_swing.csv", res["rows"])

    if args.sweep:
        print("\n========== SOZLAMALARNI SOLISHTIRISH (natija bo'yicha) ==========")
        print(f"{'SL×ATR':>6}{'trail':>7}{'qism':>6}{'savdo':>7}{'yutuq':>8}{'PF':>7}{'natija':>10}{'pasayish':>9}")
        results = []
        for stop_atr in (2.0, 2.5, 3.0):
            for trail_atr in (2.5, 3.0, 4.0):
                for units in (1, 3):
                    c = dict(cfg, stop_atr=stop_atr, trail_atr=trail_atr, max_units=units)
                    r = simulate_swing(data, c)
                    results.append((r["final"], swing_summary_line(c, r)))
        for _, line in sorted(results, reverse=True):
            print(line)
        print("Eslatma: eng yaxshi qator o'tmishga 'moslashib qolgan' bo'lishi mumkin — demo'da tasdiqlang.")


def main():
    ap = argparse.ArgumentParser(description="trend_bot (5m) yoki swing_bot (--swing) strategiyasini Binance tarixida sinash")
    ap.add_argument("--swing", action="store_true", help="swing_bot strategiyasi (1h/4h, standart 90 kun)")
    ap.add_argument("--days", type=float, default=None, help="necha kunlik tarix (trend: 14, swing: 90)")
    ap.add_argument("--coins", type=int, default=tb.SCAN_COINS, help="nechta coin")
    ap.add_argument("--leverage", type=int, default=None)
    ap.add_argument("--max-open", type=int, default=None)
    ap.add_argument("--balance", type=float, default=5000.0)
    ap.add_argument("--sweep", action="store_true", help="bir nechta sozlamani solishtirish")
    ap.add_argument("--source", choices=["binance", "demo"], default="binance", help="ma'lumot manbasi")
    trend = ap.add_argument_group("trend (5m)")
    trend.add_argument("--interval", type=float, default=tb.INTERVAL_MIN, help="necha daqiqada savdo")
    trend.add_argument("--margin", type=float, default=tb.MARGIN_PCT, help="marja, balansdan %%")
    trend.add_argument("--sl", type=float, default=tb.SL_PCT, help="boshlang'ich SL, narx %%")
    trend.add_argument("--step", type=float, default=tb.STEP_PCT, help="SL siljish qadami, narx %%")
    trend.add_argument("--tp", type=float, default=tb.TP_PCT, help="TP, narx %% (0 = yo'q)")
    swing = ap.add_argument_group("swing (--swing)")
    swing.add_argument("--risk", type=float, default=sb.RISK_PCT, help="har qism riski, balansdan %%")
    swing.add_argument("--stop-atr", type=float, default=sb.STOP_ATR, help="SL = shuncha × ATR")
    swing.add_argument("--trail-atr", type=float, default=sb.TRAIL_ATR, help="chandelier = shuncha × ATR")
    swing.add_argument("--units", type=int, default=sb.MAX_UNITS, help="piramida: nechta qismgacha")
    swing.add_argument("--target", type=float, default=sb.TARGET_PCT, help="balans maqsadi %% (0 = yo'q)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    ex = data_exchange(args.source)
    try:
        ex.load_markets()
    except ccxt.BaseError as e:
        if args.source == "demo":
            sys.exit(f"Binance'ga ulanib bo'lmadi: {e}")
        print(f"Binance asosiy serveriga ulanib bo'lmadi ({e.__class__.__name__}) — demo serverdan olinadi.")
        ex = data_exchange("demo")
        ex.load_markets()

    coins = core.choose_coins(ex)[:args.coins]
    if args.swing:
        return run_swing(ex, coins, args)
    days = args.days or 14
    print(f"\n{len(coins)} ta coinning {days:g} kunlik 5m tarixi yuklanmoqda...")
    data = {}
    for s in coins:
        try:
            data[s] = fetch_history(ex, s, days)
        except ccxt.BaseError as e:
            print(f"  {core.short(s)}: yuklab bo'lmadi ({e.__class__.__name__}) — o'tkazildi")
    if not data:
        sys.exit("Ma'lumot yuklanmadi.")

    cfg = default_cfg(args.balance)
    cfg.update(interval_min=args.interval, margin_pct=args.margin, leverage=args.leverage or tb.LEVERAGE,
               sl_pct=args.sl, step_pct=args.step, tp_pct=args.tp, max_open=args.max_open or tb.MAX_OPEN)
    res = simulate(data, cfg)
    first = min(cs[tb.HISTORY][0] for cs in data.values() if len(cs) > tb.HISTORY)
    last = max(cs[-1][0] for cs in data.values())
    print(f"\nDavr: {core.stamp(first)[:16]} → {core.stamp(last)[:16]} | coinlar: "
          + ", ".join(core.short(s) for s in data))
    print(f"Sozlamalar: har {cfg['interval_min']:g} daqiqa | marja {cfg['margin_pct']:g}% × {cfg['leverage']}x | "
          f"SL −{cfg['sl_pct']:g}% | har +{cfg['step_pct']:g}% da SL siljiydi | "
          + (f"TP +{cfg['tp_pct']:g}%" if cfg["tp_pct"] > 0 else "TP yo'q") + f" | max {cfg['max_open']} ta")
    core.print_stats(SimpleNamespace(rows=res["rows"], path=SimpleNamespace(name="backtest_trend.csv")))
    print(f"Balans: {cfg['balance']:.2f} → {res['final']:.2f} USDT ({(res['final'] / cfg['balance'] - 1) * 100:+.1f}%) | "
          f"eng katta pasayish (ochiq savdolar bilan): {res['max_dd']:.1f}%")
    write_csv("backtest_trend.csv", res["rows"])

    if args.sweep:
        print("\n========== SOZLAMALARNI SOLISHTIRISH (natija bo'yicha) ==========")
        print(f"{'daq':>5}{'SL%':>6}{'qadam':>6}{'savdo':>7}{'yutuq':>8}{'PF':>7}{'natija':>10}{'pasayish':>9}")
        results = []
        for interval in (10, 15):
            for sl in (0.7, 1.0, 1.5):
                for step in (0.5, 1.0, 2.0):
                    c = dict(cfg, interval_min=interval, sl_pct=sl, step_pct=step)
                    r = simulate(data, c)
                    results.append((r["final"], summary_line(c, r)))
        for _, line in sorted(results, reverse=True):
            print(line)
        print("Eslatma: eng yaxshi qator o'tmishga 'moslashib qolgan' bo'lishi mumkin — demo'da tasdiqlang.")


if __name__ == "__main__":
    main()
