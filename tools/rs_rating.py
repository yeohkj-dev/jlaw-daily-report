"""RS Rating（IBD 式 1–99）：每天用量化系统的股票池（约 2,250 只美股，量化/data/stocks/）重新排名。

分数 = 2×(收盘 ÷ 63 天前收盘) + 收盘 ÷ 126 天前 + 收盘 ÷ 189 天前 + 收盘 ÷ 252 天前（最近一季权重加倍，同 IBD 常见近似）。
RS Rating = 分数在全部股票里的百分位（1–99，99 = 赢过 99% 的股票）。只排最新一天有收盘、且有 ≥253 根K线的股票。
股票池只含市值 ≥3 亿、日成交额 ≥1,000 万美元的股票（比 IBD 全市场严格），所以同一只股票的分数可能比 IBD 低几分。

用法：
  python tools/rs_rating.py .        计算并写 量化/data/rs_rating.json（含 1–99 门槛表，TradingView「RS 线」指标用同一张表）
  其他模块：from rs_rating import load, badge
"""
import datetime as dt
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.dirname(HERE)
QDATA = os.path.join(REPO, "量化", "data")
OUT = os.path.join(QDATA, "rs_rating.json")
FORMULA = "2*c/c[63] + c/c[126] + c/c[189] + c/c[252]"


def _score(c):
    if len(c) < 253 or any(x is None or x <= 0 for x in (c[-1], c[-64], c[-127], c[-190], c[-253])):
        return None
    return 2 * c[-1] / c[-64] + c[-1] / c[-127] + c[-1] / c[-190] + c[-1] / c[-253]


def percentile_table(scores):
    """第 k 个（k = 1..99）= 第 k 百分位的分数（numpy 默认线性插值）。"""
    import numpy as np
    return [float(np.percentile(scores, k)) for k in range(1, 100)]


def rate(x, table):
    """门槛表里 ≤ x 的个数，夹在 1..99（TradingView 版用同样的规则）。"""
    import bisect
    return max(1, min(99, bisect.bisect_right(table, x)))


def compute(repo=REPO):
    stocks = os.path.join(repo, "量化", "data", "stocks")
    uni = {r["name"]: r for r in json.load(open(os.path.join(repo, "量化", "data", "universe.json"), encoding="utf-8"))}
    data = {}
    for f in os.listdir(stocks):
        if f.endswith(".json"):
            d = json.load(open(os.path.join(stocks, f)))
            data[f[:-5]] = (d["d"], d["c"])
    # 排名日 = 最近一个 ≥90% 股票都有收盘的交易日（Yahoo 收盘后一段时间只有部分股票更新到当天）
    from collections import Counter
    cnt = Counter(x for dd, _ in data.values() for x in dd[-5:])
    newest = max(cnt)
    last = max(x for x, n in cnt.items() if n >= 0.9 * len(data))
    share = cnt[newest] / len(data)
    latest = newest          # 最新交易日：个股和 SPY（量化/data/macro.pkl，另外下载）取较新的
    try:
        import pandas as pd
        spy = pd.read_pickle(os.path.join(repo, "量化", "data", "macro.pkl"))["SPY"].dropna()
        latest = max(latest, spy.index[-1].strftime("%Y-%m-%d"))
    except Exception:
        pass
    rows = {}
    for s, (dd, cc) in data.items():
        if last not in dd[-5:]:
            continue
        k = len(dd) - dd[::-1].index(last)            # 截到排名日（含）
        cc = cc[:k]
        sc = _score(cc)
        if sc is not None:
            rows[s] = dict(score=sc, c=cc[-1], r3=cc[-1] / cc[-64] - 1, r6=cc[-1] / cc[-127] - 1, r12=cc[-1] / cc[-253] - 1,
                           hi=max(x for x in cc[-252:] if x is not None))
    table = percentile_table([r["score"] for r in rows.values()])
    for s, r in rows.items():
        r["rating"] = rate(r["score"], table)
        u = uni.get(s, {})
        r["exchange"], r["industry"], r["name"] = u.get("exchange") or "", u.get("industry") or "", u.get("description") or ""
    checks = []
    n = len(rows)
    checks.append(dict(name="RS Rating 股票数", ok=n >= 1500, detail=f"{last} 共 {n} 只参与排名", critical=False))
    age = (dt.date.today() - dt.date.fromisoformat(last)).days
    checks.append(dict(name="RS Rating 数据日期", ok=age <= 4, detail=f"最新收盘 {last}（{age} 天前）", critical=False))
    checks.append(dict(name="RS Rating 是否最新交易日", ok=last == latest, critical=False,
                       detail=f"用 {last} 收盘排名" + ("" if last == latest else f"，不是最新交易日 {latest}（Yahoo 只有 {cnt.get(latest, 0) / len(data):.0%} 股票有 {latest} 的数据）")))
    if last == newest:
        checks.append(tv_crosscheck(rows))
    else:
        checks.append(dict(name="RS Rating vs TradingView", ok=False, critical=False,
                           detail=f"Yahoo 只有 {share:.0%} 股票更新到 {newest}，排名改用 {last}，所以这次不和 TradingView 的最新价比"))
    out = dict(date=last, latest=latest, n=n, formula=FORMULA, thresholds=[round(x, 6) for x in table], stocks=rows, checks=checks,
               generated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def tv_crosscheck(rows, k=40):
    """前 k 名：收盘价逐只和 TradingView 选股器比（差 ≤0.5%）；3 个月涨幅看差距的中位数（≤5 个百分点，用来抓拆股之类的大错）。
    TradingView 的 Perf.3M 是日历月、这里是 63 根K线，个别强势股会差几个百分点，所以只看中位数。"""
    try:
        import statistics
        from common import tv_scan
        top = sorted(rows, key=lambda s: -rows[s]["score"])[:k]
        tick = [f'{rows[s]["exchange"]}:{s}' for s in top if rows[s]["exchange"]]
        data = tv_scan({"symbols": {"tickers": tick}, "columns": ["name", "close", "Perf.3M"]})
        px_bad, diffs, tot = [], [], 0
        for x in data:
            s, cl, p3 = x["d"][0], x["d"][1], x["d"][2]
            r = rows.get(s)
            if r is None or cl is None:
                continue
            tot += 1
            if abs(r["c"] / cl - 1) > 0.005:
                px_bad.append(f"{s}（{r['c']:.2f} vs TV {cl:.2f}）")
            if p3 is not None:
                diffs.append(abs(r["r3"] * 100 - p3))
        med = statistics.median(diffs) if diffs else 99
        good = tot >= 20 and len(px_bad) <= 0.1 * tot and med <= 5
        return dict(name="RS Rating vs TradingView", ok=good, critical=False,
                    detail=f"前 {tot} 名收盘价 {tot - len(px_bad)} 只一致（差 ≤0.5%），3 个月涨幅差距中位数 {med:.1f} 个百分点"
                           + (f"；收盘价不一致：{'、'.join(px_bad[:5])}" if px_bad else ""))
    except Exception as e:      # 核对失败不影响排名本身
        return dict(name="RS Rating vs TradingView", ok=False, detail=f"TradingView 取不到：{e}", critical=False)


def load(max_age_days=5):
    """读今天的 RS Rating；太旧或没有就返回 {}（各名单就不显示 RS）。"""
    try:
        d = json.load(open(OUT, encoding="utf-8"))
        if (dt.date.today() - dt.date.fromisoformat(d["date"])).days > max_age_days:
            return {}
        return d
    except (OSError, ValueError, KeyError):
        return {}


def stale_note(rs):
    """RS Rating 不是最新交易日的时候，名单上方显示红字提示；是最新就返回空字符串。"""
    if not rs or rs.get("date") == rs.get("latest", rs.get("date")):
        return ""
    return (f'<div style="margin:8px 0;padding:8px 12px;background:#FDECEA;border-left:4px solid #C62828;color:#C62828;font-size:13px;font-weight:600;">'
            f'⚠ 注意：股票旁的 RS 标记（带 *）是 {rs["date"]} 收盘的排名，不是最新交易日 {rs["latest"]}。'
            f'原因：Yahoo 当时还没有足够股票更新到 {rs["latest"]}，下次报告会更新。</div>')


def color(r):
    return "#1B5E20" if r >= 90 else "#2E7D32" if r >= 80 else "#666" if r >= 50 else "#C62828"


def tv_link(sym, rs=None, ex=None, bold=True):
    """股票代码 → TradingView 图表链接（交易所先用传进来的，其次 RS 档里的，都没有就只用代码，TradingView 也认得）。"""
    ex = ex or ((rs or {}).get("stocks") or {}).get(sym, {}).get("exchange") or ""
    url = "https://www.tradingview.com/chart/?symbol=" + (f"{ex}:{sym}" if ex else sym)
    t = html.escape(sym)
    return (f'<a href="{html.escape(url)}" target="_blank" rel="noopener" title="在 TradingView 打开 {t} 的图表" '
            f'style="color:#1565C0;text-decoration:none;{"font-weight:700;" if bold else ""}">{t} <span style="font-size:11px;">📈</span></a>')


def badge(rs, sym):
    """股票代码下面的小标记，例：RS 92。"""
    r = (rs.get("stocks") or {}).get(sym, {}).get("rating") if rs else None
    if r is None:
        return ""
    old = rs.get("date") != rs.get("latest", rs.get("date"))
    tip = f"RS Rating（1–99，IBD 式）：过去一年涨幅（最近一季加倍）赢过 {r}% 的美股；{rs['date']} 收盘" + ("，不是最新交易日" if old else "")
    return (f' <span title="{html.escape(tip)}" '
            f'style="display:inline-block;font-size:11px;font-weight:700;color:#fff;background:{color(r)};border-radius:3px;padding:0 4px;">RS {r}{"*" if old else ""}</span>')


def top_table(rs, n=30, url=None):
    """「RS Rating 前 n 名」表格。"""
    if not rs:
        return '<p style="color:#777;">RS Rating 今天没有数据。</p>'
    st = rs["stocks"]
    top = sorted(st, key=lambda s: -st[s]["score"])[:n]
    td = 'style="padding:6px 8px;border-bottom:1px solid #eee;white-space:nowrap;"'
    th = 'style="padding:6px 8px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;white-space:nowrap;"'
    pc = lambda x: f'<span style="color:{"#2E7D32" if x >= 0 else "#C62828"};">{x*100:+.0f}%</span>'
    body = ""
    for i, s in enumerate(top, 1):
        r = st[s]
        u = url(s, r["exchange"]) if url else f"https://www.tradingview.com/chart/?symbol={r['exchange']}:{s}"
        body += (f'<tr><td {td}>{i}</td><td {td}><a href="{html.escape(u)}" target="_blank" rel="noopener" style="color:#1565C0;text-decoration:none;font-weight:700;">{html.escape(s)} 📈</a>'
                 f'<br><span style="color:#888;font-size:11px;">{html.escape(r["name"][:22])}</span></td><td {td}>{html.escape(r["industry"][:22])}</td>'
                 f'<td {td}><b style="color:{color(r["rating"])};">{r["rating"]}</b></td><td {td}>{r["c"]:.2f}</td>'
                 f'<td {td}>{pc(r["r3"])}</td><td {td}>{pc(r["r6"])}</td><td {td}>{pc(r["r12"])}</td><td {td}>{(r["c"] / r["hi"] - 1) * 100:.0f}%</td></tr>')
    hd = "".join(f"<th {th}>{x}</th>" for x in ("#", "股票", "行业", "RS", "收盘", "3 个月", "6 个月", "12 个月", "距 52 周高"))
    return f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:13px;"><tr>{hd}</tr>{body}</table></div>'


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    o = compute(os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else REPO)
    print(o["date"], o["n"], "只")
    for c in o["checks"]:
        print(("✔" if c["ok"] else "⚠"), c["name"], c["detail"])
    for s in ("NVDA", "CROX", "AAPL", "MSFT", "MRVL"):
        if s in o["stocks"]:
            print(s, round(o["stocks"][s]["score"], 4), "RS", o["stocks"][s]["rating"])
