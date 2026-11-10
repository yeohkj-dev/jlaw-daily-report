"""盘中买点提醒（Telegram）：美股交易时段每 30 分钟检查一次「等 2 小时买点」名单（每日选股/pending.json）。

多时间框架研究（回测/mtf/）：日线出信号（大周期），之后 5 个交易日内在 2 小时图上找买点（小周期）：
  BRK 放量突破 50 日高：当天第一根 2 小时K线（美东 09:30–11:30）的最高价，被之后的 2 小时K线收盘突破
  A0  META + RS ≥ 90：2 小时K线收盘重新站上 2 小时 20 EMA（前一根在 20 EMA 下面）
只看已经收完的 2 小时K线（11:30、13:30、15:30、16:00 收）。同一只股票同一天只提醒一次（早报/_intraday_sent.json）。
价格用 Yahoo 60 分钟K线合成，再和 TradingView 现价核对（差 >1% 会在信息里标 ⚠）。
用法：python intraday_alerts.py [输出目录] [--dry-run] [--force-date YYYY-MM-DD --force-time HH:MM --pending 文件]（后面三个是测试用）
仅供学习，不构成投资建议。
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import tv_scan, yahoo_chart
import news_digest as nd
from telegram_send import split

argv = sys.argv[1:]
DRY = "--dry-run" in argv
args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1] in ("--pending", "--force-time", "--force-date"))]
OUT_DIR = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING = argv[argv.index("--pending") + 1] if "--pending" in argv else os.path.join(OUT_DIR, "每日选股", "pending.json")
SENT = os.path.join(OUT_DIR, "早报", "_intraday_sent.json")
TV = "https://www.tradingview.com/chart/?symbol="


def bars_2h(sym):
    """Yahoo 60 分钟K线 → 美东每天从 09:30 开始的 2 小时K线：[(日期, 开始, 结束, o, h, l, c)]，并附 20 EMA。"""
    bars, _ = yahoo_chart(sym.replace(".", "-"), "1mo", "60m")
    days = {}
    for b in bars:
        e = nd.to_et(dt.datetime.fromtimestamp(b["t"], dt.timezone.utc)).replace(tzinfo=None)
        if dt.time(9, 30) <= e.time() < dt.time(16, 0):
            days.setdefault(e.date(), []).append(dict(b, et=e))
    out = []
    for d in sorted(days):
        bs = days[d]
        for i in range(0, len(bs), 2):
            ch = bs[i:i + 2]
            end = min(ch[-1]["et"] + dt.timedelta(minutes=60), ch[-1]["et"].replace(hour=16, minute=0))
            out.append(dict(day=d, start=ch[0]["et"], end=end, o=ch[0]["o"], h=max(x["h"] for x in ch),
                            l=min(x["l"] for x in ch), c=ch[-1]["c"]))
    k, e = 2 / 21, None
    for b in out:
        e = b["c"] if e is None else b["c"] * k + e * (1 - k)
        b["ema"] = e
    return out


def check(p, now_et):
    """返回触发的那根 2 小时K线（今天、已收完、信号日之后），没有就 None。"""
    bars = [b for b in bars_2h(p["sym"]) if b["end"] <= now_et]
    today = [b for b in bars if b["day"] == now_et.date()]
    if not today or str(now_et.date()) <= p["sig"]:
        return None
    if p["kind"] == "BRK":
        first = today[0]
        for b in today[1:]:
            if b["c"] > first["h"]:
                return dict(b, why=f"第一根 2 小时K线高点 {first['h']:.2f} 被收盘突破")
        return None
    for i, b in enumerate(bars):
        if b["day"] != now_et.date() or i == 0:
            continue
        prev = bars[i - 1]
        if prev["c"] < prev["ema"] and b["c"] > b["ema"]:
            return dict(b, why=f"2 小时收盘 {b['c']:.2f} 重新站上 20 EMA {b['ema']:.2f}")
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    now = dt.datetime.now(dt.timezone.utc)
    now_et = nd.to_et(now).replace(tzinfo=None)
    if "--force-date" in argv:                               # 测试：重播过去某一天
        y, m, d = map(int, argv[argv.index("--force-date") + 1].split("-"))
        now_et = now_et.replace(year=y, month=m, day=d)
    if "--force-time" in argv:
        hh, mm = argv[argv.index("--force-time") + 1].split(":")
        now_et = now_et.replace(hour=int(hh), minute=int(mm))
    try:
        pend = json.load(open(PENDING, encoding="utf-8"))
    except (OSError, ValueError):
        print("没有「等 2 小时买点」名单")
        return 0
    try:
        sent = json.load(open(SENT, encoding="utf-8"))
    except (OSError, ValueError):
        sent = {}
    today = str(now_et.date())
    done = set(sent.get(today, []))
    hits = []
    for p in pend:
        key = f"{p['kind']}:{p['sym']}"
        if key in done:
            continue
        try:
            b = check(p, now_et)
        except Exception as ex:
            print(p["sym"], "取不到 60 分钟数据：", type(ex).__name__)
            continue
        if b:
            hits.append((p, b))
    print(f"美东 {now_et:%m-%d %H:%M}：检查 {len(pend)} 只，触发 {len(hits)} 只", [p["sym"] for p, _ in hits])
    if not hits:
        return 0
    # 和 TradingView 现价核对
    tvp = {}
    try:
        rows = tv_scan({"symbols": {"tickers": [f"{p['ex']}:{p['sym']}" if p["ex"] else p["sym"] for p, _ in hits]}, "columns": ["name", "close"]})
        tvp = {r["d"][0]: r["d"][1] for r in rows}
    except Exception:
        pass
    L = [f"<b>🔔 盘中买点提醒 · 美东 {now_et:%m-%d %H:%M}</b>", ""]
    for p, b in hits:
        px = b["c"]
        stop = px * (1 - p["stop_pct"])
        url = TV + urllib.parse.quote(f"{p['ex']}:{p['sym']}" if p["ex"] else p["sym"], safe=":")
        name = "放量突破 50 日高" if p["kind"] == "BRK" else f"A0（META + RS {p.get('rs') or '≥90'}）"
        t = tvp.get(p["sym"])
        chk = "" if not t else (f"（TradingView 现价 {t:.2f}）" if abs(t / px - 1) <= 0.01 else f"⚠ TradingView 现价 {t:.2f}，和 2 小时收盘差超过 1%，请先看图")
        L.append(f"🟢 <a href=\"{html.escape(url)}\"><b>{html.escape(p['sym'])}</b></a> {name}")
        L.append(f"  2 小时买点 <b>{px:.2f}</b>：{html.escape(b['why'])}（{b['start']:%H:%M}–{b['end']:%H:%M} 美东）{chk}")
        L.append(f"  止损：收盘跌破 <b>{stop:.2f}</b>（−{p['stop_pct'] * 100:.0f}%）就第二天开盘卖"
                 + (f"；预挂 {px * (1 - p['hard_pct']):.2f}（−{p['hard_pct'] * 100:.0f}%）保护单" if p.get("hard_pct") else "")
                 + f"；否则拿 60 个交易日。信号日 {p['sig'][5:]}")
        L.append("")
    L += ["<i>按多时间框架研究：日线信号 + 2 小时买点。仅供学习，不构成投资建议。</i>"]
    text = "\n".join(L)
    if DRY:
        print(text)
        return 0
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("没有设置 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，跳过发送")
        return 0
    for part in split(text):
        data = urllib.parse.urlencode({"chat_id": chat, "text": part, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
        try:
            r = json.load(urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=30))
        except Exception as ex:
            print("Telegram 发送失败：", type(ex).__name__)
            return 1
        if not r.get("ok"):
            print("Telegram 发送失败：", r.get("description"))
            return 1
    sent = {k: v for k, v in sent.items() if k >= str(now_et.date() - dt.timedelta(days=10))}
    sent[today] = sorted(done | {f"{p['kind']}:{p['sym']}" for p, _ in hits})
    os.makedirs(os.path.dirname(SENT), exist_ok=True)
    json.dump(sent, open(SENT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已发送")
    return 0


if __name__ == "__main__":
    sys.exit(main())
