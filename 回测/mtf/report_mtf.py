"""多时间框架研究报告（HTML）：读 research21_stats.json（21 年日线 / 周线）、mtf_exit_stats.json（3 年 1 / 2 / 4 小时）。
用法：python 回测/mtf/report_mtf.py → 回测/mtf/多时间框架研究报告.html
"""
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
R21 = json.load(open(os.path.join(HERE, "research21_stats.json"), encoding="utf-8"))
S21, CNT = R21["stats"], R21["counts"]
SX = json.load(open(os.path.join(HERE, "mtf_exit_stats.json"), encoding="utf-8"))
NAMES = {"A0": "A0（J Law META 回调 + RS ≥ 90）", "META": "J Law META 回调（全部）", "BRK": "放量突破 50 日高", "C9": "C9（按课程规则）"}
ENT = {"D0": "次日开盘买（现在）", "D1": "日线收盘确认（收盘高于信号日最高价）", "D2": "盘中突破信号日最高价",
       "E0": "次日开盘买（现在）", "E2": "开盘区间突破（当天第一根K线高点被收盘突破）", "E3": "收盘重新站上 20 EMA"}
EXT = {"X0": "系统原本卖法（止损 + 拿 60 天）", "XM20": "日线收盘跌破 20 天线", "XM50": "日线收盘跌破 50 天线", "XW10": "周线收盘跌破 10 周线",
       "XD": "日线收盘止损 + 拿 60 天（现在）", "XLs": "同样的止损，但用小周期收盘判断", "XLt": "赚 10% 后，小周期收盘跌破小周期 20 EMA 就卖", "XDt": "赚 10% 后，日线收盘跌破 20 天线就卖"}
TFN = {0: "日线", 60: "1 小时", 120: "2 小时", 240: "4 小时"}


def pc(x, d=2):
    if x is None:
        return "—"
    col = "#2E7D32" if x > 0 else "#C62828" if x < 0 else "#555"
    return f'<span style="color:{col};">{x:+.{d}f}%</span>'


def tbl(head, rows):
    return ('<div class="tw"><table><tr>' + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table></div>")


def best_mark(v, best):
    return f"<b>⭐ {v}</b>" if best else v


def sys21(kind):
    rows = []
    keys = [k for k in S21 if k.startswith(kind + "|")]
    base = S21.get(f"{kind}|D0|X0")
    top = max(keys, key=lambda k: S21[k]["ex"] if S21[k]["n"] >= 0.3 * CNT[kind] else -99)
    for k in sorted(keys, key=lambda k: (k.split("|")[1], k.split("|")[2])):
        s = S21[k]
        _, e, x = k.split("|")
        en = ENT[e.replace("+W", "")] + ("＋周线升势" if "+W" in e else "")
        rows.append([best_mark(html.escape(en), k == top), html.escape(EXT[x]), f"{s['n']:,}", f"{s['take']:.0f}%", pc(s["ex"]),
                     f"{s['win']:.0f}%", f"{s['hold']:.0f} 天", pc(s["h1"]), pc(s["h2"]), f"{s['t']:.1f}"])
    return tbl(("买进", "卖出", "笔数", "信号里买到", "每笔比 SPY 多赚", "胜率", "平均持有", "2005–2015", "2016–2026", "可信度 t"), rows)


def sys3y(kind, test):
    rows = []
    keys = [k for k in SX if k.startswith(f"{kind}|{test}|")]
    for k in sorted(keys, key=lambda k: (k.split("|")[2], int(k.split("|")[3]))):
        s = SX[k]
        _, _, m, tf = k.split("|")
        rows.append([TFN[int(tf)], html.escape(ENT[m] if test == "entry" else EXT[m]), f"{s['n']:,}", pc(s["ex"]), f"{s['win']:.0f}%",
                     f"{s['hold']:.0f} 天", f"{s['total']:.1f}", f"{s['t']:.1f}" if s["t"] is not None else "—"])
    return tbl(("时间框架", "买进" if test == "entry" else "卖出", "笔数", "每笔比 SPY 多赚", "胜率", "平均持有", "合计（每笔超额加总）", "可信度 t"), rows)


def main():
    concl = """
<ol>
<li><b>最好的小周期 = 2 小时图，用来「买」，不要用来「卖」。</b>大周期（日线 / 周线）确认形态之后，在 2 小时图上等「开盘区间突破」再买，
对突破型系统最好：放量突破 50 日高，每笔比 SPY 多赚 <b>+1.27%</b>（次日开盘买是 +0.91%），而且合计赚得更多（少买 25%，但都是较好的）。
1 小时也有效（+1.09%），4 小时太慢（少买一半、效果变差）。</li>
<li><b>A0（META + RS ≥ 90）</b>：2 小时图收盘重新站上 20 EMA 再买，每笔 <b>+4.8%</b>（次日开盘 +3.8%），合计差不多（少买约 20%）。
改善方向一致，但样本只有约 250 笔，统计上还不算可靠。</li>
<li><b>「等确认」其实是过滤器，不是买得更便宜。</b>21 年同一批信号逐笔比：等确认平均要多付 1–2%（买得更高），但能避开一半以上会亏的信号。
所以信号多到买不完时（突破型一年约 900 个）很有用；信号少时（A0 一年约 38 个）差别不大。</li>
<li><b>卖出不要用太小的时间框架。</b>小周期移动止损（赚 10% 后跌破 1 / 2 / 4 小时 20 EMA 就卖）在每个系统都把赢家砍掉：A0 每笔从 +3.8% 掉到 +0.3–0.5%，
突破从 +0.9% 掉到负数。日线 20 天线也太紧。最好的卖法仍是日线 / 周线：A0 用「收盘跌破 50 天线」（+3.35%，原本 +2.49%）；
突破用原本的「收盘跌 15% 才卖、拿 60 天」。唯一有帮助的小周期卖法：<b>止损价改用 2 小时收盘判断</b>（A0 +4.4% vs +3.8%，比等日线收盘早一点出场）。</li>
<li><b>周线升势过滤</b>：对突破型有小帮助（+0.62% → +0.75%），对 A0 / META 没差（它们本身已在升势里）。</li>
<li><b>J Law META（全部）和 C9（按课程规则写成程序）</b>：不管哪个时间框架买卖，21 年都没有赢 SPY；2 小时开盘区间突破能把亏损减少一半，但仍是负的。
C9 的规则很多要靠看图判断（支撑、黑白C、UTE），程序版不一定代表真正的 C9。</li>
</ol>"""
    method = """<ul>
<li><b>信号（大周期确认）</b>：日线上的 A0、META、放量突破 50 日高、C9 突破；另测「周线升势」（周收盘 &gt; 10 周线 &gt; 40 周线、10 周线向上）。
<li><b>21 年测试（2005–2026，日线 / 周线）</b>：约 2,250 只现有美股，买进 3 种 × 周线过滤 × 卖出 4 种，约 57 万笔模拟交易。</li>
<li><b>3 年测试（2023-12 起，1 / 2 / 4 小时）</b>：免费的 60 分钟数据只有约 3 年（Yahoo），2 / 4 小时K线由 60 分钟合成；约 1,990 只股票、19 万笔。
已排除 60 分钟数据和日线收盘对不上的 5 只（例如 BNY 的 60 分钟数据是另一只证券）。</li>
<li><b>「每笔比 SPY 多赚」</b>：同一时间买卖 SPY，股票报酬减去 SPY 报酬。每投入 $1 万，+1% ≈ 多赚 $100。</li>
<li><b>可信度 t</b>：大约 ≥ 2 才算可靠；小于 2 可能是运气。</li>
<li><b>限制</b>：只有现在还在交易的股票（幸存者偏差）；没扣佣金和滑点；小周期测试只有 3 年（大部分是牛市）；C9 是按课程笔记写成程序的近似版本。</li>
</ul>"""
    ex_html = ("<h2>图表例子（真实回测交易）</h2><p class='note'>左边日线：大周期出现信号；右边 2 小时线：信号后 5 天内等小周期买点。"
               "灰色点划线是旧做法（次日开盘买）的价位，红色点线是止损。</p>"
               + "".join(f'<h3>{t}</h3><img src="charts/{f}.png" style="width:100%;border:1px solid #eee;border-radius:6px;" alt="{t}">'
                         for f, t in (("brk_rklb", "放量突破 + 2 小时开盘区间突破：比次日开盘买得更低，拿满 60 天 +203%"),
                                      ("brk_gehc", "放量突破后 2 小时没有突破：不买，避开 −38%"),
                                      ("a0_lite", "A0 + 2 小时收盘站上 20 EMA：拿满 60 天 +138%"),
                                      ("a0_coin", "A0 信号后 2 小时一直在 20 EMA 下：不买，避开 −26%"))))
    body = (f"<h2>结论</h2>{concl}" + ex_html
            + "<h2>1. 小周期买进（3 年，1 / 2 / 4 小时）</h2>"
            + "".join(f"<h3>{NAMES[k]}</h3>{sys3y(k, 'entry')}" for k in ("BRK", "A0", "META", "C9"))
            + "<h2>2. 小周期卖出（3 年；买进都用次日开盘）</h2>"
            + "".join(f"<h3>{NAMES[k]}</h3>{sys3y(k, 'exit')}" for k in ("BRK", "A0", "META", "C9"))
            + "<h2>3. 21 年：日线 / 周线的买进 × 卖出</h2><p class='note'>⭐ = 买到 ≥30% 信号的组合里每笔多赚最多的。</p>"
            + "".join(f"<h3>{NAMES[k]}（{CNT[k]:,} 个信号）</h3>{sys21(k)}" for k in ("BRK", "A0", "META", "C9"))
            + f"<h2>4. 方法与限制</h2>{method}")
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>多时间框架研究</title><style>
body{{margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222}}.w{{max-width:1100px;margin:0 auto;padding:16px}}
.c{{background:#fff;border:1px solid #e3e3e3;border-radius:8px;padding:16px 18px;line-height:1.65;font-size:14px}}
h1{{font-size:22px;margin:4px 0}}h2{{font-size:18px;color:#1F4E78;margin:22px 0 8px}}h3{{font-size:15px;margin:14px 0 6px}}
.tw{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:12.5px}}th{{background:#f5f5f5;text-align:left;padding:5px 7px;border-bottom:1px solid #ddd;white-space:nowrap}}
td{{padding:5px 7px;border-bottom:1px solid #eee;white-space:nowrap}}.note{{color:#666;font-size:12px}}ol li,ul li{{margin-bottom:6px}}
</style></head><body><div class="w"><div class="c"><div class="note">大周期（日线 / 周线）找趋势和形态，小周期（1 / 2 / 4 小时）找买卖点</div>
<h1>多时间框架研究：哪个时间框架买、哪个时间框架卖</h1>
<div class="note">系统：J Law META（A0 版和全部）、放量突破 50 日高、C9。21 年（2005–2026）日线 / 周线 + 3 年（2023-12 起）1 / 2 / 4 小时。仅供学习，不构成投资建议。</div>
{body}</div></div></body></html>"""
    out = os.path.join(HERE, "多时间框架研究报告.html")
    open(out, "w", encoding="utf-8").write(page)
    print(out)


if __name__ == "__main__":
    main()
