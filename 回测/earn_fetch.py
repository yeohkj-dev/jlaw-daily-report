"""抓 META + RS≥90 交易里每只股票的历史财报日（yfinance get_earnings_dates，Yahoo 约 24 年），存 earnings_dates.json：
{sym: ["2026-08-26 AMC", "2026-05-20 BMO", ...]}，AMC = 收盘后公布（反应在下一个交易日），BMO = 开盘前 / 盘中（反应在当天）。"""
import json, os, time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "earnings_dates.json")


def one(sym):
    for k in range(3):
        try:
            d = yf.Ticker(sym.replace(".", "-")).get_earnings_dates(limit=100)
            if d is None or not len(d):
                return sym, []
            out = []
            for ts in d.index:
                ts = pd.Timestamp(ts)
                out.append(f"{ts:%Y-%m-%d} {'AMC' if ts.hour >= 12 else 'BMO'}")
            return sym, sorted(set(out))
        except Exception:
            time.sleep(3 * (k + 1))
    return sym, None


if __name__ == "__main__":
    T = pd.read_pickle(os.path.join(HERE, "meta_more20.pkl"))
    syms = sorted(T[T.rs >= 90].sym.unique())
    have = json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo = [s for s in syms if have.get(s) is None]
    print("要抓", len(todo), "/", len(syms), flush=True)
    with ThreadPoolExecutor(4) as ex:
        for i, (s, v) in enumerate(ex.map(one, todo), 1):
            have[s] = v
            if i % 50 == 0:
                json.dump(have, open(OUT, "w")); print(i, flush=True)
    json.dump(have, open(OUT, "w"))
    print("完成；没取到", [s for s in syms if have.get(s) is None], "；空的", sum(1 for s in syms if have.get(s) == []))
