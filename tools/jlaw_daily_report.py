"""J Law 每日报告 —— 一个脚本跑完「大盘报告」和「每日选股」，合并成一个两个分页的 HTML。

步骤：
  1. 运行 market_regime.py（大盘体温计），更新 大盘报告/ 和 大盘历史.csv
  2. 运行 jlaw_daily_screen.py（每日选股），它会读取第 1 步更新后的大盘状态
  3. 把两份 HTML 合并到 每日报告/YYYY-MM-DD.html，并另存一份 每日报告/最新报告.html，然后自动用浏览器打开

用法：python jlaw_daily_report.py ["输出目录"] [--no-open] [--publish 网站目录]
  输出目录默认是 tools 的上一层（D:\\AI\\Claude AI）
  --publish：另外写一份网站版（index.html + archive/ 历史，保留最近 KEEP_DAYS 天），给 GitHub Pages 用
原来的两个脚本照样可以单独运行。仅供学习，不构成投资建议。
"""
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
import webbrowser

TOOLS = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[1:]
PUBLISH = argv[argv.index("--publish") + 1] if "--publish" in argv and argv.index("--publish") + 1 < len(argv) else None
args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1] == "--publish")]
OUT_DIR = args[0] if args else os.path.dirname(TOOLS)
OPEN = "--no-open" not in sys.argv
REPORT_DIR = os.path.join(OUT_DIR, "每日报告")
KEEP_DAYS = 60


def publish(page, today):
    """网站版：index.html 是最新一份，archive/ 存每天一份并附目录页。"""
    arch = os.path.join(PUBLISH, "archive")
    os.makedirs(arch, exist_ok=True)
    nav = '<a href="archive/" style="color:#93c5fd;font-size:12px;">历史报告</a>'
    with open(os.path.join(PUBLISH, "index.html"), "w", encoding="utf-8") as f:
        f.write(page.replace("<!--NAV-->", nav))
    with open(os.path.join(arch, f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(page.replace("<!--NAV-->", '<a href="../" style="color:#93c5fd;font-size:12px;">最新报告</a>'))
    days = sorted((x for x in os.listdir(arch) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.html", x)), reverse=True)
    for old in days[KEEP_DAYS:]:
        os.remove(os.path.join(arch, old))
    items = "".join(f'<li><a href="{d}">{d[:10]}</a></li>' for d in days[:KEEP_DAYS])
    with open(os.path.join(arch, "index.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" '
                'content="width=device-width,initial-scale=1"><title>J Law 历史报告</title></head>'
                '<body style="font-family:Arial,\'Microsoft YaHei\',sans-serif;max-width:640px;margin:0 auto;padding:16px;'
                'background:#f4f5f7;color:#222;"><h2>J Law 每日报告 · 历史</h2><p><a href="../">← 最新报告</a></p>'
                f'<ul style="line-height:1.9;">{items}</ul><p style="color:#888;font-size:12px;">保留最近 {KEEP_DAYS} 份。'
                '仅供学习，不构成投资建议。</p></body></html>')


def run(script):
    """运行子脚本，返回 (结果 JSON, 错误信息)。子脚本最后一行输出是 JSON。"""
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(TOOLS, script), OUT_DIR], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=1800)
    secs = time.time() - t0
    lines = [x for x in p.stdout.strip().splitlines() if x.strip()]
    if p.returncode == 0 and lines:
        try:
            return json.loads(lines[-1]), None, secs
        except json.JSONDecodeError:
            pass
    err = (p.stderr or p.stdout or "没有输出").strip()[-1500:]
    return None, err, secs


def body_of(path):
    with open(path, encoding="utf-8") as f:
        doc = f.read()
    m = re.search(r"<body[^>]*>(.*)</body>", doc, re.S | re.I)
    return m.group(1) if m else doc


def error_box(name, err):
    return (f'<div style="max-width:900px;margin:16px auto;padding:16px;background:#FDECEA;border-left:6px solid #C62828;'
            f'border-radius:6px;font-size:14px;"><b>{name}运行失败</b><pre style="white-space:pre-wrap;font-size:12px;'
            f'color:#555;margin:8px 0 0;">{html.escape(err)}</pre></div>')


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(REPORT_DIR, exist_ok=True)
    print("1/2 大盘报告 运行中……", flush=True)
    mkt, mkt_err, t1 = run("market_regime.py")
    print(f"    {'完成' if mkt else '失败'}（{t1:.0f} 秒）", flush=True)
    print("2/2 每日选股 运行中（要下载几百只股票的日线，约几分钟）……", flush=True)
    scr, scr_err, t2 = run("jlaw_daily_screen.py")
    print(f"    {'完成' if scr else '失败'}（{t2:.0f} 秒）", flush=True)

    today = dt.date.today()
    tab1 = body_of(mkt["html"]) if mkt else error_box("大盘报告", mkt_err)
    tab2 = body_of(scr["html"]) if scr else error_box("每日选股", scr_err)
    state = mkt["state"] if mkt else (scr or {}).get("market_state", "未知")
    key = state[:1] if state[:1] in "🔴🟡🟢" else ""
    color = {"🔴": "#C62828", "🟡": "#B26A00", "🟢": "#2E7D32"}.get(key, "#555")
    n_ready = (len(scr["meta_ready"]), len(scr["vcp_ready"])) if scr else None
    sub1 = html.escape(state)
    sub2 = f"META {n_ready[0]} · VCP {n_ready[1]}" if n_ready else "失败"
    mkt_date = mkt["date"] if mkt else "—"

    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>J Law 每日报告 {today}</title>
<style>
body{{margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222}}
.bar{{position:sticky;top:0;z-index:10;background:#1F2937;color:#fff;padding:10px 16px 0}}
.top{{max-width:1080px;margin:0 auto;display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px}}
.title{{font-size:17px;font-weight:700}}
.meta{{font-size:12px;color:#cbd5e1}}
.tabs{{max-width:1080px;margin:8px auto 0;display:flex;gap:4px}}
.tab{{flex:0 1 auto;border:0;cursor:pointer;padding:9px 16px;border-radius:8px 8px 0 0;background:#374151;color:#e5e7eb;
font:inherit;font-size:14px;text-align:left;line-height:1.3}}
.tab small{{display:block;font-size:11px;color:#cbd5e1}}
.tab[aria-selected=true]{{background:#f4f5f7;color:#111;font-weight:700}}
.tab[aria-selected=true] small{{color:#555}}
.panel{{display:none}}.panel.on{{display:block}}
@media (max-width:600px){{.tab{{flex:1 1 0;padding:8px 10px}}}}
</style></head><body>
<div class="bar"><div class="top"><span class="title">J Law 每日报告 · {today}</span>
<span class="meta">大盘数据 {mkt_date} · 大盘状态 <b style="color:#fff;background:{color};padding:1px 6px;border-radius:4px;">{html.escape(state)}</b></span><!--NAV--></div>
<div class="tabs" role="tablist">
<button class="tab" role="tab" id="t-mkt" aria-controls="p-mkt" aria-selected="true">大盘报告<small>{sub1}</small></button>
<button class="tab" role="tab" id="t-scr" aria-controls="p-scr" aria-selected="false">每日选股<small>{sub2}</small></button>
</div></div>
<div class="panel on" id="p-mkt" role="tabpanel" aria-labelledby="t-mkt">{tab1}</div>
<div class="panel" id="p-scr" role="tabpanel" aria-labelledby="t-scr">{tab2}</div>
<script>
var tabs=document.querySelectorAll('.tab');
function show(id){{tabs.forEach(function(t){{var on=t.id===id;t.setAttribute('aria-selected',on);
document.getElementById(t.getAttribute('aria-controls')).classList.toggle('on',on);}});
try{{localStorage.setItem('jlaw-tab',id);}}catch(e){{}}window.scrollTo(0,0);}}
tabs.forEach(function(t){{t.addEventListener('click',function(){{show(t.id);}});}});
try{{var s=localStorage.getItem('jlaw-tab');if(s&&document.getElementById(s))show(s);}}catch(e){{}}
</script></body></html>"""

    dated = os.path.join(REPORT_DIR, f"{today}.html")
    latest = os.path.join(REPORT_DIR, "最新报告.html")
    for p in (dated, latest):
        with open(p, "w", encoding="utf-8") as f:
            f.write(page)
    if PUBLISH:
        publish(page, today)
    print(json.dumps({"report": dated, "latest": latest, "market_state": state,
                      "market_ok": bool(mkt), "screen_ok": bool(scr),
                      "meta_ready": [x[0] for x in scr["meta_ready"]] if scr else None,
                      "vcp_ready": [x[0] for x in scr["vcp_ready"]] if scr else None}, ensure_ascii=False))
    if OPEN:
        webbrowser.open("file:///" + latest.replace("\\", "/"))


if __name__ == "__main__":
    main()
