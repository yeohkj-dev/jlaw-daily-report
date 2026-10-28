"""J Law 每日报告 —— 一个脚本跑完所有报告，合并成一个多分页的 HTML。

平日（美东周一至周五）：大盘报告 → 每日选股 → 今日新闻 → 业绩与估值；每周展望显示最近一个周日的版本
周末（美东周六、周日）：周末新闻 → 业绩与估值 → 每周展望；大盘报告和每日选股显示周五的版本
合并到 每日报告/YYYY-MM-DD.html，另存 每日报告/最新报告.html，然后自动用浏览器打开。
顶部显示「数据核对」：新闻、业绩、展望各模块的核对结果；有严重问题时加 --strict 就不更新网站。

用法：python jlaw_daily_report.py ["输出目录"] [--no-open] [--publish 网站目录] [--strict] [--weekend | --weekday]
  输出目录默认是 tools 的上一层
  --publish：另外写一份网站版（index.html + archive/ 历史，保留最近 KEEP_DAYS 天），给 GitHub Pages 用
  --weekend / --weekday：不按今天星期几，强制跑周末版或平日版（测试用）
各个子脚本照样可以单独运行。仅供学习，不构成投资建议。
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
STRICT = "--strict" in sys.argv     # 严重问题时不更新网站，并以错误结束（GitHub 会发邮件通知）
FORCE = "weekend" if "--weekend" in sys.argv else "weekday" if "--weekday" in sys.argv else None
REPORT_DIR = os.path.join(OUT_DIR, "每日报告")
KEEP_DAYS = 30


def publish(page, today):
    """网站版：index.html 是最新一份，archive/ 存每天一份并附目录页。"""
    arch = os.path.join(PUBLISH, "archive")
    os.makedirs(arch, exist_ok=True)
    nav = '<a href="archive/" style="color:#93c5fd;font-size:12px;">历史报告</a>'
    with open(os.path.join(PUBLISH, "index.html"), "w", encoding="utf-8") as f:
        f.write(page.replace("<!--NAV-->", nav))
    # 历史版不存「业绩与估值」（每天变化不大、体积最大），让仓库不会越来越大
    slim = re.sub(r"<!--EV-START-->.*?<!--EV-END-->", '<div style="max-width:1080px;margin:16px auto;padding:16px;font-size:14px;">'
                  '历史报告不保存这一页，请看<a href="../">最新报告</a>。</div>', page, flags=re.S)
    with open(os.path.join(arch, f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(slim.replace("<!--NAV-->", '<a href="../" style="color:#93c5fd;font-size:12px;">最新报告</a>'))
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


def run(script, extra=()):
    """运行子脚本，返回 (结果 JSON, 错误信息, 秒数)。子脚本最后一行输出是 JSON。"""
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, os.path.join(TOOLS, script), OUT_DIR, *extra], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=1800)
    except subprocess.TimeoutExpired:
        return None, "运行超过 30 分钟，已停止", time.time() - t0
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
            f'color:#555;margin:8px 0 0;">{html.escape(err or "")}</pre></div>')


def latest_file(folder, pattern=r"\d{4}-\d{2}-\d{2}\.html$"):
    d = os.path.join(OUT_DIR, folder)
    if not os.path.isdir(d):
        return None
    files = sorted(f for f in os.listdir(d) if re.match(pattern, f))
    return os.path.join(d, files[-1]) if files else None


def note(text):
    return f'<div style="max-width:1080px;margin:12px auto 0;padding:8px 16px;font-size:12px;color:#555;">{html.escape(text)}</div>'


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(REPORT_DIR, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    et = now.astimezone(dt.timezone(dt.timedelta(hours=-5)))
    weekend = FORCE == "weekend" or (FORCE is None and et.weekday() in (5, 6))
    news_mode = ["--mode", "weekend" if weekend else "daily"]
    steps = ([] if weekend else [("mkt", "大盘报告", "market_regime.py", ()), ("scr", "每日选股", "jlaw_daily_screen.py", ())]) + [
        ("news", "周末新闻" if weekend else "今日新闻", "news_digest.py", news_mode),
        ("ev", "业绩与估值", "earnings_valuation.py", ())] + ([("wk", "每周展望", "weekly_outlook.py", ())] if weekend else [])
    res, errs = {}, {}
    for i, (key, label, script, extra) in enumerate(steps, 1):
        print(f"{i}/{len(steps)} {label} 运行中……", flush=True)
        r, e, secs = run(script, extra)
        res[key], errs[key] = r, e
        print(f"    {'完成' if r else '失败'}（{secs:.0f} 秒）", flush=True)

    tabs = []          # (id, 标题, 小字, 内容)
    mkt, scr = res.get("mkt"), res.get("scr")
    if weekend:
        for key, label in (("mkt", "大盘报告"), ("scr", "每日选股")):
            f = latest_file(label)
            body = (note(f"这一页是 {os.path.basename(f)[:10]} 的{label}，周末不重跑，下个交易日更新。") + body_of(f)) if f else error_box(label, "还没有报告")
            tabs.append((key, label, f"{os.path.basename(f)[5:10]} 版" if f else "没有", body))
        state, mkt_date = "未知", "—"
        hist = os.path.join(OUT_DIR, "大盘报告", "大盘历史.csv")
        if os.path.exists(hist):
            with open(hist, encoding="utf-8-sig") as fh:
                rows = fh.read().strip().splitlines()
            if len(rows) > 1:
                mkt_date, state = rows[-1].split(",")[:2]
    else:
        state = mkt["state"] if mkt else (scr or {}).get("market_state", "未知")
        mkt_date = mkt["date"] if mkt else "—"
        n_ready = (len(scr["meta_ready"]), len(scr["vcp_ready"])) if scr else None
        tabs.append(("mkt", "大盘报告", html.escape(state), body_of(mkt["html"]) if mkt else error_box("大盘报告", errs["mkt"])))
        tabs.append(("scr", "每日选股", f"META {n_ready[0]} · VCP {n_ready[1]}" if n_ready else "失败",
                     body_of(scr["html"]) if scr else error_box("每日选股", errs["scr"])))
    news = res.get("news")
    tabs.append(("news", "周末新闻" if weekend else "今日新闻",
                 f"{news['stories']} 条 · 多来源 {news['multi_source']}" if news else "失败",
                 body_of(news["html"]) if news else error_box("新闻", errs["news"])))
    ev = res.get("ev")
    tabs.append(("ev", "业绩与估值", f"最近公布 {len(ev['recent'])} 家" if ev else "失败",
                 ("<!--EV-START-->" + body_of(ev["html"]) + "<!--EV-END-->") if ev else error_box("业绩与估值", errs["ev"])))
    wk = res.get("wk")
    if wk:
        tabs.append(("wk", "每周展望", f"{wk['verdict']}（{wk['total']:+d}）", body_of(wk["html"])))
    elif weekend:
        tabs.append(("wk", "每周展望", "失败", error_box("每周展望", errs.get("wk"))))
    else:
        f = latest_file("每周展望")
        if f:
            with open(f[:-5] + ".json", encoding="utf-8") as fh:
                v = json.load(fh)
            tabs.append(("wk", "每周展望", f"{v.get('verdict', '')} · {os.path.basename(f)[5:10]} 版",
                         note(f"每周展望在每个周日晚上（美东）更新，这是 {os.path.basename(f)[:10]} 的版本。") + body_of(f)))

    # ---- 数据核对汇总 ----
    checks = [dict(c, module=lab) for key, lab in (("news", "新闻"), ("ev", "业绩估值"), ("wk", "每周展望"))
              for c in ((res.get(key) or {}).get("checks") or [])]
    crit = [c for c in checks if not c["ok"] and c.get("critical")]
    warn = [c for c in checks if not c["ok"] and not c.get("critical")]
    failed = [lab for key, lab, _, _ in steps if not res.get(key)]
    color = {"🔴": "#C62828", "🟡": "#B26A00", "🟢": "#2E7D32"}.get(state[:1], "#555")
    chk_color = "#C62828" if crit else "#B26A00" if (warn or failed) else "#2E7D32"
    chk_txt = (f"✘ 数据核对：{len(crit)} 项严重问题" if crit else
               f"⚠ 数据核对：{len(warn) + len(failed)} 项提醒" if (warn or failed) else "✔ 数据核对通过")
    chk_items = ("".join(f"<li>{'✘' if c.get('critical') else '⚠'} [{html.escape(c['module'])}] {html.escape(c['name'])}："
                         f"{html.escape(c['detail'])}</li>" for c in crit + warn)
                 + "".join(f"<li>⚠ {html.escape(x)} 运行失败</li>" for x in failed))
    ok_items = "".join(f"<li>✔ [{html.escape(c['module'])}] {html.escape(c['name'])}：{html.escape(c['detail'])}</li>"
                       for c in checks if c["ok"])
    chk_html = (f'<details class="chk"><summary style="color:{chk_color};">{chk_txt}</summary>'
                f'<ul>{chk_items}{ok_items}</ul></details>')

    btns = "".join(f'<button class="tab" role="tab" id="t-{k}" aria-controls="p-{k}" aria-selected="{"true" if i == 0 else "false"}">'
                   f'{html.escape(t)}<small>{sub}</small></button>' for i, (k, t, sub, _) in enumerate(tabs))
    panels = "".join(f'<div class="panel{" on" if i == 0 else ""}" id="p-{k}" role="tabpanel" aria-labelledby="t-{k}">{body}</div>'
                     for i, (k, _, _, body) in enumerate(tabs))
    today = et.date()
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>J Law 每日报告 {today}</title>
<style>
body{{margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222}}
.bar{{position:sticky;top:0;z-index:10;background:#1F2937;color:#fff;padding:10px 16px 0}}
.top{{max-width:1080px;margin:0 auto;display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px}}
.title{{font-size:17px;font-weight:700}}
.meta{{font-size:12px;color:#cbd5e1}}
.chk{{font-size:12px;background:#fff;border-radius:4px;padding:1px 8px}}
details.chk{{position:relative}} details.chk summary{{cursor:pointer}}
details.chk ul{{position:absolute;z-index:20;left:0;margin:4px 0 0;padding:8px 12px 8px 24px;background:#fff;color:#333;
border:1px solid #ddd;border-radius:6px;width:min(560px,88vw);max-height:60vh;overflow:auto;box-shadow:0 4px 12px rgba(0,0,0,.15);
list-style:none;line-height:1.7}}
.tabs{{max-width:1080px;margin:8px auto 0;display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}}
.tab{{flex:0 0 auto;border:0;cursor:pointer;padding:9px 14px;border-radius:8px 8px 0 0;background:#374151;color:#e5e7eb;
font:inherit;font-size:14px;text-align:left;line-height:1.3}}
.tab small{{display:block;font-size:11px;color:#cbd5e1}}
.tab[aria-selected=true]{{background:#f4f5f7;color:#111;font-weight:700}}
.tab[aria-selected=true] small{{color:#555}}
.panel{{display:none}}.panel.on{{display:block}}
@media (max-width:600px){{.tab{{padding:8px 10px;font-size:13px}}}}
</style></head><body>
<div class="bar"><div class="top"><span class="title">J Law 每日报告 · {today}{"（周末版）" if weekend else ""}</span>
<span class="meta">大盘数据 {html.escape(mkt_date)} · 大盘状态 <b style="color:#fff;background:{color};padding:1px 6px;border-radius:4px;">{html.escape(state)}</b></span>
{chk_html}<!--NAV--></div>
<div class="tabs" role="tablist">{btns}</div></div>
{panels}
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
    blocked = bool(crit) or (not weekend and not (mkt and scr))
    published = bool(PUBLISH) and not (STRICT and blocked)
    if published:
        publish(page, today)
    print(json.dumps({"report": dated, "latest": latest, "market_state": state, "weekend": weekend,
                      "ok": {k: bool(v) for k, v in res.items()}, "critical": [c["name"] for c in crit],
                      "warnings": [c["name"] for c in warn] + failed, "published": published}, ensure_ascii=False))
    if OPEN:
        webbrowser.open("file:///" + latest.replace("\\", "/"))
    if STRICT and blocked:
        sys.exit("数据核对没通过，网站保留上一份报告。")


if __name__ == "__main__":
    main()
