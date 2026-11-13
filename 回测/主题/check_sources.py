"""主题雷达研究 ③：逐个实际抓取「价格以外的领先数据」，记录能不能免费、用程序取得。
每个来源记：网址、是否成功、取到的样本（证明真的取到）、限制。写 data/sources.json。
另外用 SEC XBRL 做一个小例子：微软 / 谷歌 / 亚马逊 / Meta / 甲骨文 历年资本开支（10-K 年报数字）。
用法：python 回测/主题/check_sources.py
"""
import datetime as dt
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
from common import fetch, fetch_json, sec_json, sec_text, tv_scan, yahoo_summary  # noqa: E402

OUT = os.path.join(HERE, "data")
os.makedirs(OUT, exist_ok=True)
RES = []


def test(key, name, url, fn):
    t0 = time.time()
    try:
        sample = fn()
        RES.append(dict(key=key, name=name, url=url, ok=True, sample=sample, sec=round(time.time() - t0, 1)))
        print("✔", name, "|", str(sample)[:200])
    except Exception as e:
        RES.append(dict(key=key, name=name, url=url, ok=False, sample=f"{type(e).__name__}: {e}"[:200], sec=round(time.time() - t0, 1)))
        print("✘", name, "|", type(e).__name__, str(e)[:200])


CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]
HYPER = {"MSFT": 789019, "GOOGL": 1652044, "AMZN": 1018724, "META": 1326801, "ORCL": 1341439}


def capex_annual(cik):
    """10-K 里的全年资本开支（按财年结束日）。返回 {财年结束年份: (金额, 财年结束日, 申报日)}。"""
    out = {}
    for tag in CAPEX_TAGS:
        try:
            j = sec_json(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json")
        except Exception:
            continue
        for x in j["units"]["USD"]:
            if x.get("form") != "10-K" or not x.get("start"):
                continue
            days = (dt.date.fromisoformat(x["end"]) - dt.date.fromisoformat(x["start"])).days
            if 350 <= days <= 380:
                y = x["end"][:4]
                if y not in out or x["filed"] < out[y][2]:          # 用最早申报的那一次（当时市场看到的）
                    out[y] = (x["val"], x["end"], x["filed"])
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    capex = {}

    def t_sec_concept():
        for s, cik in HYPER.items():
            capex[s] = capex_annual(cik)
        m = capex["MSFT"]
        y = max(m)
        return f"MSFT 财年 {m[y][1]} 资本开支 ${m[y][0]/1e9:.1f}B（{m[y][2]} 申报）；5 家公司都取到，最早 {min(min(v) for v in capex.values())} 年"
    test("sec_capex", "SEC EDGAR XBRL：单家公司资本开支（companyconcept）", "https://data.sec.gov/api/xbrl/companyconcept/CIK0000789019/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment.json", t_sec_concept)

    def t_sec_frames():
        j = sec_json("https://data.sec.gov/api/xbrl/frames/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment/USD/CY2024.json")
        d = sorted(j["data"], key=lambda x: -x["val"])
        return f"2024 年共 {len(d)} 家公司申报；最大 5 家：" + "、".join(f"{x['entityName'][:18]} ${x['val']/1e9:.0f}B" for x in d[:5])
    test("sec_frames", "SEC EDGAR XBRL：全部公司同一年的资本开支（frames）", "https://data.sec.gov/api/xbrl/frames/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment/USD/CY2024.json", t_sec_frames)

    def t_sec_sic():
        j = sec_json("https://data.sec.gov/submissions/CIK0001045810.json")
        return f"{j['name']}：SIC {j['sic']} {j['sicDescription']}（可把 frames 的公司按行业加总）"
    test("sec_sic", "SEC EDGAR：公司行业代码（submissions）", "https://data.sec.gov/submissions/CIK0001045810.json", t_sec_sic)

    ipo = {}

    def t_form_idx():
        out = []
        for y, q in ((2021, 1), (2023, 1), (2025, 1), (2026, 3)):
            txt = sec_text(f"https://www.sec.gov/Archives/edgar/full-index/{y}/QTR{q}/form.idx")
            n = sum(1 for ln in txt.splitlines() if ln.startswith("S-1 ") or ln.startswith("F-1 "))
            n424 = sum(1 for ln in txt.splitlines() if ln.startswith("424B4 "))
            ipo[f"{y}Q{q}"] = (n, n424)
            out.append(f"{y}Q{q}：S-1/F-1 {n} 份、424B4 {n424} 份")
        return "；".join(out)
    test("sec_ipo", "SEC EDGAR 季度申报索引：数 S-1 / F-1（上市申请）和 424B4（定价）", "https://www.sec.gov/Archives/edgar/full-index/2025/QTR1/form.idx", t_form_idx)

    def t_nasdaq_ipo():
        j = fetch_json("https://api.nasdaq.com/api/ipo/calendar?date=2025-06", headers={"Accept": "application/json", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}, timeout=20, tries=2)
        rows = j["data"]["priced"]["rows"] or []
        return f"2025-06 已定价 IPO {len(rows)} 宗，例：" + "、".join(f"{r['proposedTickerSymbol']}（{r['pricedDate']}，{r['dollarValueOfSharesOffered']}）" for r in rows[:3])
    test("nasdaq_ipo", "Nasdaq IPO 日历（网页用的接口，不是正式 API）", "https://api.nasdaq.com/api/ipo/calendar?date=2025-06", t_nasdaq_ipo)

    def t_yahoo_trend():
        r = yahoo_summary("NVDA", ["earningsTrend"])
        t = [x for x in r["earningsTrend"]["trend"] if x.get("period") == "+1y"][0]
        rv, et = t["epsRevisions"], t["epsTrend"]
        g = lambda d, k: (d.get(k) or {}).get("raw")
        return (f"NVDA 下一财年 EPS 预估：现在 {g(et, 'current')}，30 天前 {g(et, '30daysAgo')}，90 天前 {g(et, '90daysAgo')}；"
                f"近 30 天上调 {g(rv, 'upLast30days')} 位、下调 {g(rv, 'downLast30days')} 位分析师")
    test("yahoo_rev", "Yahoo 盈利预估修正（earningsTrend，要 crumb；只有当下，没有历史）", "https://query2.finance.yahoo.com/v10/finance/quoteSummary/NVDA?modules=earningsTrend", t_yahoo_trend)

    def t_tv_est():
        cols = ["name", "earnings_per_share_forecast_next_fq", "revenue_forecast_next_fq", "earnings_per_share_forecast_next_fy", "Recommend.All"]
        ok = []
        for c in cols[1:]:
            try:
                d = tv_scan({"symbols": {"tickers": ["NASDAQ:NVDA"]}, "columns": ["name", c]})
                ok.append(f"{c}={d[0]['d'][1]}")
            except Exception:
                ok.append(f"{c}=取不到")
        return "NVDA：" + "，".join(ok) + "（只有当下的预估值，没有「修正」字段，要自己每天存下来比）"
    test("tv_est", "TradingView 选股器：预估 EPS / 营收（当下值）", "https://scanner.tradingview.com/america/scan", t_tv_est)

    def t_congress():
        j = fetch_json("https://api.congress.gov/v3/bill?api_key=DEMO_KEY&format=json&limit=3&sort=updateDate+desc", timeout=20, tries=2)
        b = j["bills"]
        return f"取到最新法案 {len(b)} 条，例：{b[0]['type']}{b[0]['number']} {b[0]['title'][:60]}（{b[0]['latestAction']['actionDate']}）"
    test("congress", "Congress.gov API（法案；DEMO_KEY 可试，正式用要免费申请 key）", "https://api.congress.gov/v3/bill?api_key=DEMO_KEY", t_congress)

    def t_fedreg():
        j = fetch_json("https://www.federalregister.gov/api/v1/documents.json?per_page=3&conditions%5Bagencies%5D%5B%5D=nuclear-regulatory-commission&conditions%5Btype%5D%5B%5D=RULE&order=newest", timeout=20, tries=2)
        r = j["results"]
        return f"核管会（NRC）的最终规则共 {j['count']} 份，最新：{r[0]['publication_date']} {r[0]['title'][:60]}"
    test("fedreg", "Federal Register API（联邦法规、行政命令；不用 key）", "https://www.federalregister.gov/api/v1/documents.json?conditions[term]=nuclear", t_fedreg)

    def t_usaspending():
        body = {"group": "fiscal_year", "filters": {"keywords": ["semiconductor"], "time_period": [{"start_date": "2019-10-01", "end_date": "2025-09-30"}]}}
        j = fetch_json("https://api.usaspending.gov/api/v2/search/spending_over_time/", body=body, timeout=40, tries=2)
        return "关键词 semiconductor 的联邦合同 / 拨款按财年：" + "、".join(f"FY{r['time_period']['fiscal_year']} ${r['aggregated_amount']/1e9:.1f}B" for r in j["results"])
    test("usaspending", "USAspending API（联邦政府实际花出去的钱，按关键词 / 机构；不用 key）", "https://api.usaspending.gov/api/v2/search/spending_over_time/", t_usaspending)

    def t_ssga():
        raw = fetch("https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-xlu.xlsx", raw=True, timeout=40, tries=2)
        import io
        import pandas as pd
        df = pd.read_excel(io.BytesIO(raw), header=None)
        hdr = next(i for i in range(10) if "Shares Outstanding" in " ".join(str(x) for x in df.iloc[i].values))
        d = df.iloc[hdr + 1:].dropna(how="all")
        d.columns = [str(x).strip() for x in df.iloc[hdr].values]
        d = d[d["Date"].astype(str).str.match(r"\d{2}-[A-Za-z]{3}-\d{4}")]
        a, b = d.iloc[0], d.iloc[-1]
        return f"XLU 每日净值 + 流通份额 {len(d)} 天（{b['Date']} 至 {a['Date']}）；最新份额 {float(a['Shares Outstanding'])/1e6:.0f} 百万份。净流入 ≈ 份额变化 × 净值"
    test("ssga", "道富 SPDR 官网：行业 ETF 每日净值和流通份额历史（Excel）", "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-xlu.xlsx", t_ssga)

    def t_yahoo_etf():
        r = yahoo_summary("SMH", ["defaultKeyStatistics", "summaryDetail"])
        ta = (r.get("summaryDetail", {}).get("totalAssets") or r.get("defaultKeyStatistics", {}).get("totalAssets") or {}).get("raw")
        return f"SMH 总资产 ${ta/1e9:.1f}B（只有当下；每天存下来，资产变化 − 价格涨跌 ≈ 净流入）"
    test("yahoo_etf", "Yahoo：ETF 总资产（当下值，要 crumb）", "https://query2.finance.yahoo.com/v10/finance/quoteSummary/SMH?modules=summaryDetail", t_yahoo_etf)

    def t_census():
        txt = fetch("https://api.census.gov/data/timeseries/eits/vip?get=cell_value,time_slot_id,category_code,data_type_code&time=2025-06", timeout=30, tries=2)
        if not txt.lstrip().startswith("["):
            raise RuntimeError("不带 key 会被转到 missing_key 页面：现在要先免费申请 key（api.census.gov/data/key_signup.html），这次没有 key 所以没验证到数据")
        j = json.loads(txt)
        cats = sorted({r[2] for r in j[1:]})
        return f"2025-06 建筑支出 {len(j)-1} 行，{len(cats)} 个类别（含制造业厂房、电力、办公 / 数据中心所在的类别），例：{j[1]}"
    test("census", "美国普查局 API：每月建筑支出（工厂、电力、数据中心盖了多少；不用 key）", "https://api.census.gov/data/timeseries/eits/vip", t_census)

    def t_arxiv():
        txt = fetch("https://export.arxiv.org/api/query?search_query=all:%22small+modular+reactor%22&max_results=1", timeout=30, tries=1)
        n = re.search(r"totalResults[^>]*>(\d+)<", txt).group(1)
        return f"arXiv 含 small modular reactor 的论文共 {n} 篇（可按关键词、年份数论文数量）"
    test("arxiv", "arXiv API：按关键词数论文（技术热度；不用 key）", "http://export.arxiv.org/api/query", t_arxiv)

    def t_fred():
        txt = fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=PNFI", timeout=15, tries=1)
        return f"取到 {len(txt.splitlines())} 行"
    test("fred", "FRED（美联储经济数据库 CSV）", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=PNFI", t_fred)

    def t_ritter():
        txt = fetch("https://site.warrington.ufl.edu/ritter/ipo-data/", timeout=20, tries=2)
        n = len(re.findall(r"\.(?:pdf|xlsx?)", txt))
        return f"页面取到，含 {n} 个 PDF / Excel 链接（Jay Ritter 教授的历年 IPO 统计，按年、按行业，人工更新）"
    test("ritter", "Jay Ritter IPO 数据（佛罗里达大学；历年 IPO 数量和首日涨幅）", "https://site.warrington.ufl.edu/ritter/ipo-data/", t_ritter)

    def t_trends():
        txt = fetch("https://trends.google.com/trends/api/dailytrends?hl=en-US&geo=US&ns=15", timeout=15, tries=1)
        return f"取到 {len(txt)} 字"
    test("gtrends", "Google Trends（没有正式的免费 API，网页接口常被挡）", "https://trends.google.com/trends/api/dailytrends", t_trends)

    # 资本开支小例子
    years = sorted({y for v in capex.values() for y in v})
    table = {s: {y: dict(val=v[y][0], end=v[y][1], filed=v[y][2]) for y in v} for s, v in capex.items()}
    json.dump(dict(checked=dt.datetime.now().strftime("%Y-%m-%d %H:%M"), sources=RES, capex=table, capex_years=years, ipo=ipo),
              open(os.path.join(OUT, "sources.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    big4 = ["MSFT", "GOOGL", "AMZN", "META"]
    prev = None
    for y in years:
        if all(y in capex[s] for s in big4):
            tot = sum(capex[s][y][0] for s in big4)
            print(y, f"4 家合计 ${tot/1e9:.0f}B", "" if not prev else f"同比 {tot/prev*100-100:+.0f}%", "最晚申报", max(capex[s][y][2] for s in big4))
            prev = tot
        else:
            prev = None


if __name__ == "__main__":
    main()
