"""白话版「今天怎么做」：每日报告的量化分页和完整报告最上面都用这一块。
只用 results.json / signals.json 的数据，不含任何持仓。"""
import html
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from rs_rating import load as _rs_load, tv_link  # noqa: E402

PLAIN = {   # 8 个信号的白话说法
    "趋势：SPY 在 200 日线上": "大盘长期趋势向上",
    "趋势：50 日线 > 200 日线": "大盘中期趋势向上",
    "动量：SPY 12 个月涨幅 > 现金": "大盘过去一年是赚钱的",
    "宽度：≥6/9 板块在 200 日线上": "大部分行业都在涨",
    "信用：高收益债/国债 在 100 日线上": "债市不担心公司还不起钱",
    "波动：VIX < 20": "市场不恐慌（VIX 低于 20）",
    "波动：VIX 期限结构正常（VIX<VIX3M）": "短期没有突发恐慌",
    "风险偏好：可选消费/必需消费 在 100 日线上": "大家愿意买进攻型股票",
}
LIGHT = {"进攻": ("#2E7D32", "#E8F5E9", "🟢 量化绿灯：量化这一项允许正常买"),
         "谨慎": ("#B26A00", "#FFF4E0", "🟡 量化黄灯：量化这一项说少买、挑最强的"),
         "现金": ("#C62828", "#FDECEA", "🔴 量化红灯：不买新股票，多拿现金")}
BUY = {"进攻": "可以。看下面「今天可以买的股票」，每笔最多亏账户的 1%。",
       "谨慎": "可以少量买。只买下面列出的股票，每笔最多亏账户的 0.5%（平时的一半）。",
       "现金": "不要买。等灯变黄或变绿再说。"}


def build(o, S, site=None):
    now, sn = o["now"], S["now"]
    gate = sn["gate"]
    fg, bg, head = LIGHT[gate]
    expo = {"进攻": "100%", "中性": "约 60%", "防守": "约 20%"}[now["regime"]]
    if now["score"] >= 75 and now["qqq_rv20"] < 0.25 and now["qqq_above200"]:
        lev = "可以拿着。"
    elif not now["qqq_above200"]:
        lev = "全部卖掉换现金。纳指已经跌到 200 日线下面，这时候拿杠杆 ETF 最容易大亏。"
    elif now["score"] >= 45:
        lev = "卖掉一半。市场不算好也不算坏，杠杆只拿一半。"
    else:
        lev = "全部卖掉换现金。"
    ok = sum(now["signals"].values())
    checks = "".join(
        f'<li style="margin:2px 0">{"✅" if v else "❌"} {html.escape(PLAIN.get(k, k))}</li>'
        for k, v in now["signals"].items())

    _RS = _rs_load()
    buys = [c for c in sn["cands"] if any("✓" in s for s in c["setup"])] if gate != "现金" else []
    if buys:
        rows = "".join(
            f'<tr><td style="padding:6px 8px">{tv_link(c["t"], _RS)}</td>'
            f'<td style="padding:6px 8px">{html.escape("、".join(s.replace(" ✓", "") for s in c["setup"] if "✓" in s))}</td>'
            f'<td style="padding:6px 8px;text-align:right">{c["close"]:.2f}</td>'
            f'<td style="padding:6px 8px;text-align:right">{c["stop"]:.2f}（−{1 - c["stop"] / c["close"]:.0%}）</td></tr>'
            for c in buys)
        buy_html = ('<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%;font-size:14px">'
                    '<tr style="color:#666;text-align:left;font-size:12px"><th style="padding:4px 8px">股票</th><th style="padding:4px 8px">为什么今天可以买</th>'
                    '<th style="padding:4px 8px;text-align:right">昨天收盘</th><th style="padding:4px 8px;text-align:right">止损价</th></tr>'
                    f'{rows}</table></div><div style="font-size:12px;color:#666;margin-top:4px">明天开盘买，买了马上设止损单。</div>')
    elif gate == "现金":
        buy_html = '<div style="color:#555">红灯，今天不列买入股票。</div>'
    else:
        buy_html = '<div style="color:#555">今天没有符合条件的股票。<b>不用硬买，等就好</b> —— 没有好机会时拿现金也是一种操作。</div>'

    g = S["grid"]["E3|X2|动量名单"]
    p0, p1 = o["pred"][0], o["pred"][-1]
    card = 'style="background:#fff;color:#222;border:1px solid #e3e6eb;border-radius:12px;padding:14px 16px;margin:12px 0"'
    qa = lambda q, a: (f'<div style="display:flex;gap:10px;padding:10px 0;border-top:1px solid #eee">'
                       f'<div style="flex:0 0 96px;font-weight:700">{q}</div><div style="flex:1">{a}</div></div>')
    link = (f'<div style="margin-top:6px"><a href="{site}" target="_blank" rel="noopener" style="color:#1565C0;font-weight:700">'
            f'想看详细研究和回测 ↗</a></div>') if site else ""
    return f"""<div style="font-size:15px;line-height:1.7;color:#222">
<div style="background:{bg};border:2px solid {fg};border-radius:12px;padding:14px 16px;margin:12px 0">
<div style="font-size:12px;color:#555">只看量化系统的话（{now["date"]} 收盘数据）· 最终灯号看页面最上面</div>
<div style="font-size:24px;font-weight:800;color:{fg};margin:2px 0 6px">{head}</div>
{qa("买新股票？", BUY[gate])}
{qa("手上的股票？", "每天收盘看一次：<b>收盘价跌破 50 日均线 → 第二天卖掉</b>；没跌破就继续拿，不用管涨跌。")}
{qa("杠杆 ETF？<div style='font-size:12px;font-weight:400;color:#666'>TQQQ、QLD 等</div>", lev)}
{qa("股票放多少？", f"总资金的 <b>{expo}</b> 放股票，其余放现金或短期国债。")}
</div>
<div {card}><b>今天可以买的股票</b><div style="margin-top:6px">{buy_html}</div></div>
<div {card}><b>为什么是这个灯？</b> 系统每天检查 8 件事，今天 <b>{ok} 件</b>是好的：
<ul style="list-style:none;padding:0;margin:6px 0 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0 12px">{checks}</ul>
<div style="font-size:13px;color:#555;margin-top:6px">这些检查<b>不是预测会涨还是跌</b>，是看<b>风险大不大</b>：历史上检查大多不通过时，3 个月内大跌 10% 以上的机会约 {p0["crash63"]:.0%}；大多通过时只有 {p1["crash63"]:.0%}。</div></div>
<div {card}><b>整套方法就 3 条规则</b>
<ol style="margin:6px 0 0;padding-left:22px">
<li><b>看灯：</b>绿灯正常买，黄灯少买，红灯不买。</li>
<li><b>只买最强的股：</b>过去一年涨得最稳的前 100 名里，等它<b>创 52 周新高、成交量放大</b>那天才买。</li>
<li><b>亏小钱就走：</b>买了马上设止损；收盘跌破 50 日均线就卖。</li>
</ol>
<div style="font-size:13px;color:#555;margin-top:6px">用过去 3 年 2,250 只美股测试：大约 {g["win"]:.0%} 的交易赚钱，看起来不高 —— 但赚的平均 <b>+{g["avg_win"]:.0%}</b>，亏的平均只 <b>{g["avg_loss"]:.0%}</b>。靠的是「赚大亏小」，不是每次都对。</div>
{link}</div>
<div style="font-size:12px;color:#888">规则自动计算，不是 AI 猜的。回测不代表未来，仅供学习，不构成投资建议。</div>
</div>"""
