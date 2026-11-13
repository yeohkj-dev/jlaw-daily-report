"""主题研究用的补充日线：股票池里没有的主题股（多是 ADR）和主题 ETF。
Yahoo 日线（已按拆股调整，不含股息），2005 起，存 回测/主题/cache_extra/（格式同 回测/cache20，不进仓库）。
用法：python 回测/主题/download_extra.py
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
from common import fetch_json  # noqa: E402

OUT = os.path.join(HERE, "cache_extra")
os.makedirs(OUT, exist_ok=True)

STOCKS = ["CGC", "ACB", "CRON", "NIO", "NVO", "TSM", "ASML", "XPEV", "LI"]
ETFS = ["TAN", "ICLN", "LIT", "MJ", "SMH", "SOXX", "URA", "XLU", "IGV", "SKYY", "XBI", "QCLN", "NLR", "XLK", "XLE", "XLF", "XLV",
        "XLI", "XLY", "XLP", "XLB", "XLRE", "XLC", "ARKK", "BOTZ", "GDX", "XME", "KWEB", "IBB", "ITA", "XHB", "KRE", "XOP", "HACK", "ROBO",
        # 2026-11-13 加：更完整的主题 ETF 观察名单（主题现况 now.py 用）
        "WCLD", "CIBR", "QTUM", "XAR", "UFO", "ARKX", "URNM", "GRID", "PAVE", "DRIV", "HYDR", "COPX", "GDXJ", "SIL", "REMX", "SLX", "OIH", "FCG",
        "BLOK", "WGMI", "BITQ", "FINX", "ARKF", "ARKG", "IHI", "IHF", "PPH", "ITB", "KBE", "KIE", "IAI", "JETS", "XRT", "FDN", "ESPO", "INDA", "EWJ",
        "MSOS", "PHO", "MOO", "IFRA", "IYT", "SRVR", "AIQ", "IGM", "XSD", "DTCR", "SHLD", "NUKZ", "ARTY"]


def one(sym):
    path = os.path.join(OUT, sym + ".json")
    if os.path.exists(path):
        return "have"
    p1 = int(dt.datetime(2005, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    j = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1={p1}&period2={int(time.time())}&interval=1d&events=split")
    r = j["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    et = dt.timezone(dt.timedelta(hours=-5))
    out = dict(d=[], o=[], h=[], l=[], c=[], v=[])
    for i, t in enumerate(r.get("timestamp") or []):
        if q["close"][i] is None:
            continue
        out["d"].append(dt.datetime.fromtimestamp(t, et).strftime("%Y-%m-%d"))
        for k, kk in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
            out[k].append(q[kk][i])
        out["v"].append(q["volume"][i] or 0)
    json.dump(out, open(path, "w"))
    return f"{len(out['d'])} 根，{out['d'][0]} 起"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for s in STOCKS + ETFS:
        try:
            print(s, one(s))
        except Exception as e:
            print(s, "失败", e)
        time.sleep(0.3)
