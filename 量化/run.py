"""量化系统一键运行：下载数据 → 市场状态模型和回测 → 进出场回测和今日信号 → 生成报告。

用法：python 量化/run.py [--no-fetch]
输出：
  量化/data/量化系统.html   完整报告（发布时复制成 docs/quant.html）
  量化/data/tab.html        每日报告「量化系统」分页的内容
  量化/data/checks.json     数据核对
私人持仓：只有设置了环境变量 QUANT_HOLDINGS（指向本机 Portfolio Dashboard 的 _engine 文件夹）才会显示，
GitHub 上不设置，所以公开网站不会出现任何持仓。
"""
import html
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from rs_rating import tv_link  # noqa: E402  股票代码 → TradingView 链接

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
env = dict(os.environ, PYTHONIOENCODING="utf-8")
SITE = "https://yeohkj-dev.github.io/jlaw-daily-report/quant.html"

steps = ([] if "--no-fetch" in sys.argv else ["fetch_data.py"]) + ["quant_lab.py", "signals.py", "oversold.py", "build_report.py"]
for s in steps:
    print("运行", s, flush=True)
    subprocess.run([sys.executable, os.path.join(HERE, s)], check=True, env=env)

o = json.load(open(os.path.join(DATA, "results.json"), encoding="utf-8"))
S = json.load(open(os.path.join(DATA, "signals.json"), encoding="utf-8"))
now, sn = o["now"], S["now"]


def pct(x, d=0, sign=False):
    return "–" if x is None else (f"{x*100:+.{d}f}%" if sign else f"{x*100:.{d}f}%")


reg = now["regime"]
rc = {"进攻": "#2E7D32", "中性": "#B26A00", "防守": "#C62828"}[reg]
gate = sn["gate"]
gc = {"进攻": "#2E7D32", "谨慎": "#B26A00", "现金": "#C62828"}[gate]
expo = {"进攻": "100%", "中性": "60%", "防守": "20%"}[reg]
gate_rule = {"进攻": "正常开新仓，单笔风险 1% 账户", "谨慎": "只做出现买点的强股，单笔风险 0.5%",
             "现金": "不开新仓，让止损把仓位自然清掉"}[gate]
lev_ok = now["score"] >= 75 and now["qqq_rv20"] < 0.25 and now["qqq_above200"]
lev = ("可以持有" if lev_ok else "减半" if now["score"] >= 45 and now["qqq_above200"] else "清仓换现金")
sig = "".join(f'<li style="color:{"#2E7D32" if v else "#C62828"}">{"✓" if v else "✗"} <span style="color:#333">{html.escape(k)}</span></li>'
              for k, v in now["signals"].items())
SECN = {"XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "医疗", "XLY": "可选消费", "XLP": "必需消费", "XLI": "工业", "XLU": "公用事业", "XLB": "原材料"}
secs = "、".join(f"{t} {SECN.get(t, '')}" for t in now["rot_picks"])
buys = [c for c in sn["cands"] if any("✓" in s for s in c["setup"])]
buy_rows = "".join(
    f'<tr><td>{tv_link(c["t"])}</td><td>{c["rank"]}</td><td>{html.escape(" / ".join(s for s in c["setup"] if "✓" in s))}</td>'
    f'<td style="text-align:right">{c["close"]:.2f}</td><td style="text-align:right">{c["stop"]:.2f}</td><td style="text-align:right">{c["ma50"]:.2f}</td></tr>'
    for c in buys) or '<tr><td colspan="6" style="color:#666">今天动量 Top 30 里没有出现回测过的买点 —— 没有买点就拿现金等。</td></tr>'
watch = "、".join(tv_link(c["t"], bold=False) for c in sn["cands"][:12])
best = S["grid"]["E3|X2|动量名单"]
card = 'style="background:#fff;border-radius:8px;padding:14px 16px;margin:12px 0;box-shadow:0 1px 2px rgba(0,0,0,.06)"'
sys.path.insert(0, HERE)
from simple import build as simple_build
tab = ('<div style="max-width:820px;margin:0 auto;padding:4px 16px 24px">'
       '<div style="margin:12px 0 0;padding:8px 12px;background:#E3F2FD;border-radius:8px;font-size:13px;color:#0D47A1">'
       '这一页只看量化。<b>最终今天怎么做，看「综合名单」分页</b>：它同时看量化红绿灯和 J Law 大盘灯（取较严的），再加上 J Law / Luk 名单和K线形态。</div>'
       + simple_build(o, S, SITE) + "</div>")
open(os.path.join(DATA, "tab.html"), "w", encoding="utf-8").write(tab)
summary = dict(date=now["date"], score=now["score"], regime=reg, gate=gate, buys=[c["t"] for c in buys])
json.dump(summary, open(os.path.join(DATA, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(json.dumps(summary, ensure_ascii=False))
