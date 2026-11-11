"""每日报告 —— 一个脚本跑完所有报告，合并成一个多分页的 HTML。

平日（美东周一至周五）：大盘报告 → 每日选股 → 今日新闻 → 业绩与估值 → 本周重大事件（放在今日新闻分页最上面）；每周展望显示最近一个周日的版本
周末（美东周六、周日）：周末新闻 → 业绩与估值 → 本周回顾 → 每周展望；大盘报告和每日选股显示周五的版本
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
import shutil
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
    q = os.path.join(OUT_DIR, "量化", "data", "量化系统.html")       # 完整量化报告（公开版，没有持仓）
    if os.path.exists(q) and time.time() - os.path.getmtime(q) < 36 * 3600:
        shutil.copyfile(q, os.path.join(PUBLISH, "quant.html"))
    rsj = os.path.join(OUT_DIR, "量化", "data", "rs_rating.json")      # RS Rating 门槛表（TradingView「RS 线」指标用）
    if os.path.exists(rsj) and time.time() - os.path.getmtime(rsj) < 36 * 3600:
        with open(rsj, encoding="utf-8") as fh:
            d = json.load(fh)
        with open(os.path.join(PUBLISH, "rs_table.json"), "w", encoding="utf-8") as fh:
            json.dump({k: d[k] for k in ("date", "n", "formula", "thresholds")}, fh)
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
                'content="width=device-width,initial-scale=1"><title>每日报告 · 历史</title></head>'
                '<body style="font-family:Arial,\'Microsoft YaHei\',sans-serif;max-width:640px;margin:0 auto;padding:16px;'
                'background:#f4f5f7;color:#222;"><h2>每日报告 · 历史</h2><p><a href="../">← 最新报告</a></p>'
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


def published_panel(key):
    """从网站上一份报告（docs/index.html）取出某个分页的内容。"""
    try:
        with open(os.path.join(PUBLISH or os.path.join(OUT_DIR, "docs"), "index.html"), encoding="utf-8") as f:
            doc = f.read()
    except OSError:
        return None
    m = re.search(rf'<div class="panel[^"]*" id="p-{key}"[^>]*>(.*?)</div>(?:<div class="panel|\s*<script>)', doc, re.S)
    return m.group(1) if m else None


def pos_part(pos):
    """「大资金在哪里买卖」（tools/positioning.py）接在大盘报告后面。"""
    if not pos or not pos.get("fragment"):
        return ""
    return ('<div style="max-width:960px;margin:0 auto;padding:0 16px 16px;"><div style="background:#fff;border:1px solid #e3e3e3;'
            'border-radius:8px;padding:4px 18px 14px;font-size:14px;line-height:1.6;">' + pos["fragment"] + "</div></div>")


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


MY_TZ = dt.timezone(dt.timedelta(hours=8))          # 马来西亚 / 新加坡时间
RISK_URL = os.environ.get("RISK_URL", "https://yeohkj-dev.github.io/risk-calculator/")   # 用户自己的仓位风险计算器
RISK_LIGHT = {"🟢": ("green", "绿灯", "0.5%"), "🟡": ("yellow", "黄灯", "0.35%"), "🔴": ("red", "红灯", "0.25%")}


def risk_tab(state):
    """「风险计算」分页：嵌入仓位风险计算器，按今天的大盘状态预选灯号。数值只存在用户自己的浏览器里。"""
    light = RISK_LIGHT.get(state[:1])
    url = RISK_URL + (f"?light={light[0]}" if light else "")
    head = (f"今天大盘：<b>{html.escape(state)}</b> → 计算器已预选 <b>{light[1]}</b>（每笔风险 {light[2]}），可以在下面改。"
            if light else "今天的大盘状态未知，请在计算器里自己选灯号。")
    body = (f'<div style="max-width:1080px;margin:12px auto 0;padding:8px 16px;font-size:13px;color:#444;line-height:1.6;">{head} '
            f'账户金额等数值只存在你自己的浏览器里，不会上传。'
            f'<a href="{html.escape(url)}" target="_blank" rel="noopener" style="color:#1565C0;">在新分页打开 ↗</a></div>'
            f'<iframe id="riskfr" src="{html.escape(url)}" title="仓位风险计算器" '
            f'style="display:block;width:100%;max-width:1080px;margin:0 auto;border:0;height:1500px;background:transparent;"></iframe>'
            '<script>(function(){var f=document.getElementById("riskfr");function fit(){try{var h=Math.ceil(f.contentDocument.body.getBoundingClientRect().height);'
            'if(h>200&&Math.abs(h+40-f.offsetHeight)>4)f.style.height=(h+40)+"px";}catch(e){}}f.addEventListener("load",fit);setInterval(fit,1500);})();</script>')
    return ("risk", "风险计算", f"{light[1]} {light[2]}" if light else "仓位计算器", body)
# 4 大类分页（顺序 = 显示顺序；每类第一个是默认小分页）
GROUPS = [("today", "今天怎么做", ["combo", "brief", "risk"]),
          ("mkt", "大盘", ["mkt", "quant", "wk"]),
          ("pick", "选股", ["scr", "luk"]),
          ("news", "新闻·业绩", ["news", "ev"])]
QUANT = os.path.join(OUT_DIR, "量化", "data")      # 量化/run.py 的输出（GitHub 上由 daily.yml 在本程序之前运行）


def quant_tab():
    """「量化系统」分页：市场状态分、个股交易开关、今天的买点；完整报告在 docs/quant.html。"""
    f = os.path.join(QUANT, "tab.html")
    if os.path.exists(f) and time.time() - os.path.getmtime(f) < 36 * 3600:
        with open(os.path.join(QUANT, "summary.json"), encoding="utf-8") as fh:
            s = json.load(fh)
        with open(f, encoding="utf-8") as fh:
            return ("quant", "量化系统", f"{s['score']:.0f} 分 · {s['gate']}", fh.read())
    old = published_panel("quant")
    if old:
        if "这次没有更新" not in old:
            old = note("量化系统这次没有更新（数据下载或计算失败），这是上一份。") + old
        return ("quant", "量化系统", "上一份", old)
    return ("quant", "量化系统", "失败", error_box("量化系统", "还没有结果"))


def combined_tab():
    """「综合名单」分页：量化红绿灯 + J Law + Luk + 回测有效的K线形态（量化/combined.py）。
    要在每日选股、Luk 选股跑完之后才运行，才会用到当天的名单。量化数据超过 36 小时就不跑，改用上一份。"""
    res_json = os.path.join(QUANT, "results.json")
    if os.path.exists(res_json) and time.time() - os.path.getmtime(res_json) < 36 * 3600:
        try:
            p = subprocess.run([sys.executable, os.path.join(OUT_DIR, "量化", "combined.py")], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=600, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            lines = [x for x in p.stdout.strip().splitlines() if x.strip()]
            if p.returncode == 0 and lines:
                s = json.loads(lines[-1])
                with open(os.path.join(QUANT, "combined.html"), encoding="utf-8") as fh:
                    return ("combo", "综合名单", (f"买点 {len(s['A'])} · 红灯先观察" if s["gate"] == "现金" else f"可买 {len(s['A'])} · 等 {len(s['B'])}"), fh.read())
            print("综合名单失败：", (p.stderr or p.stdout)[-800:], flush=True)
        except (subprocess.TimeoutExpired, ValueError, OSError) as e:
            print("综合名单失败：", e, flush=True)
    old = published_panel("combo")
    if old:
        if "这次没有更新" not in old:
            old = note("综合名单这次没有更新（量化数据或计算失败），这是上一份。") + old
        return ("combo", "综合名单", "上一份", old)
    return ("combo", "综合名单", "失败", error_box("综合名单", "还没有结果"))


def quant_checks():
    try:
        with open(os.path.join(QUANT, "checks.json"), encoding="utf-8") as fh:
            return [dict(c, module="量化", critical=False) for c in json.load(fh)]   # 量化出问题不阻止整份报告发布
    except (OSError, ValueError):
        return []


WEEK_ZH = "一二三四五六日"


def next_run(now):
    """下一次排程（与 .github/workflows/daily.yml 一致）：UTC 周一至五 22:30 平日版、周日 23:00 周末版。"""
    for i in range(8):
        d = (now + dt.timedelta(days=i)).date()
        hm = (22, 30) if d.weekday() <= 4 else (23, 0) if d.weekday() == 6 else None
        if hm:
            t = dt.datetime(d.year, d.month, d.day, *hm, tzinfo=dt.timezone.utc)
            if t > now:
                return t
    return None


def update_html(now):
    """页头：这次几点更新、下次几点更新、更新时间表。"""
    gen = now.astimezone(MY_TZ)
    nxt = next_run(now)
    n8 = nxt.astimezone(MY_TZ) if nxt else None
    nxt_txt = f"{n8:%m-%d} 周{WEEK_ZH[n8.weekday()]} {n8:%H:%M}" if n8 else "—"
    stale = int((nxt + dt.timedelta(hours=3)).timestamp() * 1000) if nxt else 0
    return (f'<span class="meta" id="upd" data-gen="{int(now.timestamp() * 1000)}" data-stale="{stale}">'
            f'🕒 更新于 <b style="color:#fff;">{gen:%m-%d %H:%M}</b>（GMT+8）<span id="ago"></span>'
            f' · 下次约 <b style="color:#fff;">{nxt_txt}</b></span>'
            '<details class="chk"><summary style="color:#555;">更新时间表</summary><ul>'
            '<li>📅 <b>平日版</b>：每周二至周六早上 <b>06:30</b>（GMT+8），即美股周一至周五收盘后约 1.5 小时。'
            '包含早报、大盘报告、每日选股、Luk 选股、今日新闻、业绩与估值、本周重大事件。</li>'
            '<li>📅 <b>周末版</b>：每周一早上 <b>07:00</b>（GMT+8），即美东周日晚上。'
            '包含周末新闻、本周回顾、业绩与估值、每周展望。</li>'
            '<li>⏳ GitHub 的排程常会晚 10–60 分钟才开始，跑完约需 2–5 分钟。</li>'
            '<li>⚠ 数据核对有严重问题时，网站不会更新，会继续显示上一份报告。若超过下次更新时间 3 小时还没更新，页头会出现提示。</li>'
            '</ul></details>')


def note(text):
    return f'<div style="max-width:1080px;margin:12px auto 0;padding:8px 16px;font-size:12px;color:#555;">{html.escape(text)}</div>'


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(REPORT_DIR, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    rs_checks = []
    try:            # RS Rating（tools/rs_rating.py）：要在每日选股、Luk、综合名单之前算好，它们会读
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import rs_rating
        rso = rs_rating.compute(OUT_DIR)
        rs_checks = rso["checks"]
        print(f"RS Rating：{rso['date']} 共 {rso['n']} 只", flush=True)
    except Exception as e:
        rs_checks = [dict(name="RS Rating", ok=False, detail=f"今天计算失败（{e}），各名单沿用上一次的排名并显示提示", critical=False)]
    et = now.astimezone(dt.timezone(dt.timedelta(hours=-5)))
    weekend = FORCE == "weekend" or (FORCE is None and et.weekday() in (5, 6))
    news_mode = ["--mode", "weekend" if weekend else "daily"]
    steps = ([] if weekend else [("mkt", "大盘报告", "market_regime.py", ()), ("scr", "每日选股", "jlaw_daily_screen.py", ()),
                            ("luk", "Luk 选股", "luk_screens.py", ()), ("pos", "资金持仓", "positioning.py", ())]) + [
        ("news", "周末新闻" if weekend else "今日新闻", "news_digest.py", news_mode),
        ("ev", "业绩与估值", "earnings_valuation.py", ()),
        ("eopt", "财报期权", "earnings_options.py", ()),
        ("we", "本周回顾" if weekend else "本周重大事件", "weekly_events.py", news_mode)] + ([("wk", "每周展望", "weekly_outlook.py", ()), ("wbrief", "周末版早报", "weekend_brief.py", ("--force",) if FORCE == "weekend" else ())] if weekend else
                                                                                      [("brief", "早报", "morning_brief.py", ())])
    res, errs = {}, {}
    for i, (key, label, script, extra) in enumerate(steps, 1):
        print(f"{i}/{len(steps)} {label} 运行中……", flush=True)
        r, e, secs = run(script, extra)
        res[key], errs[key] = r, e
        print(f"    {'完成' if r else '失败'}（{secs:.0f} 秒）", flush=True)

    tabs = []          # (id, 标题, 小字, 内容)
    mkt, scr = res.get("mkt"), res.get("scr")
    if weekend:
        state, mkt_date = "未知", "—"
        hist = os.path.join(OUT_DIR, "大盘报告", "大盘历史.csv")
        if os.path.exists(hist):
            with open(hist, encoding="utf-8-sig") as fh:
                rows = fh.read().strip().splitlines()
            if len(rows) > 1:
                mkt_date, state = rows[-1].split(",")[:2]
        for key, label, folder in (("mkt", "大盘报告", "大盘报告"), ("scr", "每日选股", "每日选股"), ("luk", "Luk 选股", "Luk选股")):
            f = latest_file(folder)
            old = published_panel(key) if not f else None      # GitHub 上没有这些 HTML，沿用网站上一份的内容
            day = os.path.basename(f)[:10] if f else mkt_date
            if f or old:
                body = old or body_of(f)
                if "周末不重跑" not in body:
                    body = note(f"这一页是 {day} 的{label}，周末不重跑，下个交易日更新。") + body
                tabs.append((key, label, f"{day[5:]} 版", body))
            else:
                tabs.append((key, label, "没有", error_box(label, "还没有报告")))
    else:
        state = mkt["state"] if mkt else (scr or {}).get("market_state", "未知")
        mkt_date = mkt["date"] if mkt else "—"
        n_ready = (len(scr["meta_ready"]), len(scr["vcp_ready"])) if scr else None
        tabs.append(("mkt", "大盘报告", html.escape(state) + (f" · 恐贪 {mkt['fear']}" if mkt and mkt.get("fear") is not None else ""), (body_of(mkt["html"]) + pos_part(res.get("pos"))) if mkt else error_box("大盘报告", errs["mkt"])))
        tabs.append(("scr", "每日选股", f"META {n_ready[0]} · VCP {n_ready[1]}" if n_ready else "失败",
                     body_of(scr["html"]) if scr else error_box("每日选股", errs["scr"])))
        luk = res.get("luk")
        tabs.append(("luk", "Luk 选股", f"强势 {luk['totals']['strong']} · 跳空 {luk['totals']['gap']}" if luk else "失败",
                     body_of(luk["html"]) if luk else error_box("Luk 选股", errs["luk"])))
    news, we = res.get("news"), res.get("we")
    we_body = body_of(we["html"]) if we else error_box("本周重大事件", errs["we"])
    tabs.append(("news", "周末新闻" if weekend else "今日新闻",
                 (f"本周 SPY {we['spy_week']:+.1f}% · " if we and we.get("spy_week") is not None else "")
                 + (f"{news['stories']} 条新闻" if news else "新闻失败"),
                 we_body + (body_of(news["html"]) if news else error_box("新闻", errs["news"]))))
    ev = res.get("ev")
    tabs.append(("ev", "业绩与估值", f"最近公布 {len(ev['recent'])} 家" if ev else "失败",
                 ((res.get("eopt") or {}).get("fragment") or "") +
                 (("<!--EV-START-->" + body_of(ev["html"]) + "<!--EV-END-->") if ev else error_box("业绩与估值", errs["ev"]))))
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

    tabs.append(combined_tab())
    tabs.append(quant_tab())
    tabs.append(risk_tab(state))

    # ---- 早报：放在第一个分页（周末沿用最近一个交易日的）----
    brief, wbrief = res.get("brief"), res.get("wbrief")
    if weekend and wbrief and wbrief.get("html"):
        # 周末：换成周末版（周末新闻、周日晚期货、上周回顾、下周要看什么）
        tabs.insert(0, ("brief", "早报", f"周末版 · 周一 {wbrief['next_monday'][5:]}", body_of(wbrief["html"])))
    elif brief:
        tabs.insert(0, ("brief", "早报", f"标普 {brief['spy']:+.1f}% · 纳指 {brief['qqq']:+.1f}%" if brief.get("spy") is not None else "昨晚美股",
                        body_of(brief["html"])))
    elif not weekend:
        tabs.insert(0, ("brief", "早报", "失败", error_box("早报", errs.get("brief"))))
    else:
        f = latest_file("早报")
        old = published_panel("brief") if not f else None
        if f or old:
            day = os.path.basename(f)[:10] if f else ""
            tabs.insert(0, ("brief", "早报", f"{day[5:]} 版" if day else "上一个交易日",
                            (note(f"这是上一个交易日（{day}）的早报，周末不更新。") if day else "") + (old or body_of(f))))

    # ---- 数据核对汇总 ----
    checks = [dict(c, module=lab) for key, lab in (("brief", "早报"), ("wbrief", "周末版"), ("mkt", "大盘"), ("luk", "Luk 选股"), ("news", "新闻"), ("we", "本周事件"), ("ev", "业绩估值"), ("pos", "资金持仓"), ("eopt", "财报期权"), ("wk", "每周展望"))
              for c in ((res.get(key) or {}).get("checks") or [])] + quant_checks() + [dict(c, module="RS Rating") for c in rs_checks]
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

    # 分页分成 4 大类，每类下面有小分页；面板本身仍是平的 p-<key>（published_panel 靠这个取上一份）
    by_key = {k: (t, sub) for k, t, sub, _ in tabs}
    groups = [(g, name, [k for k in keys if k in by_key]) for g, name, keys in GROUPS]
    groups = [x for x in groups if x[2]]
    first = groups[0][2][0]
    btns = "".join(f'<button class="tab" role="tab" id="g-{g}" data-first="{keys[0]}" aria-selected="{"true" if i == 0 else "false"}">'
                   f'{html.escape(name)}<small>{by_key[keys[0]][1]}</small></button>' for i, (g, name, keys) in enumerate(groups))
    subs = "".join(f'<div class="subs{" on" if i == 0 else ""}{" one" if len(keys) == 1 else ""}" id="s-{g}">' + "".join(
                   f'<button class="stab" id="t-{k}" data-group="{g}" aria-controls="p-{k}" aria-selected="{"true" if k == first else "false"}">'
                   f'{html.escape(by_key[k][0])}<small>{by_key[k][1]}</small></button>' for k in keys) + "</div>"
                   for i, (g, name, keys) in enumerate(groups))
    panels = "".join(f'<div class="panel{" on" if k == first else ""}" id="p-{k}" role="tabpanel" aria-labelledby="t-{k}">{body}</div>'
                     for k, _, _, body in tabs)
    today = et.date()
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>每日报告 {today}</title>
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
.subs{{display:none;max-width:1080px;margin:0 auto;padding:8px 16px 0;gap:6px;overflow-x:auto;scrollbar-width:none}}.subs.on{{display:flex}}.subs.one{{display:none!important}}
.stab{{flex:0 0 auto;border:1px solid #d6d9de;background:#fff;color:#333;border-radius:99px;padding:5px 12px;cursor:pointer;font:inherit;font-size:13px;line-height:1.25;text-align:left}}
.stab small{{display:block;font-size:10.5px;color:#777}}
.stab[aria-selected=true]{{background:#1F2937;border-color:#1F2937;color:#fff;font-weight:700}}.stab[aria-selected=true] small{{color:#cbd5e1}}
@media (max-width:600px){{.tab{{padding:8px 10px;font-size:13px}}}}
</style></head><body>
<div class="bar"><div class="top"><span class="title">每日报告 · {today}{"（周末版）" if weekend else ""}</span>
<span class="meta">大盘数据 {html.escape(mkt_date)} · 大盘状态 <b style="color:#fff;background:{color};padding:1px 6px;border-radius:4px;">{html.escape(state)}</b></span>
{chk_html}{update_html(dt.datetime.now(dt.timezone.utc))}<!--NAV--></div>
<div class="tabs" role="tablist">{btns}</div></div>
{subs}
{panels}
<script>
var tabs=document.querySelectorAll('.tab'),subs=document.querySelectorAll('.stab'),last={{}};
function show(id){{var b=document.getElementById(id);if(!b)return;var g=b.dataset.group||'';
document.querySelectorAll('.panel').forEach(function(p){{p.classList.toggle('on',p.id===b.getAttribute('aria-controls'));}});
subs.forEach(function(x){{if(x.dataset.group===g)x.setAttribute('aria-selected',x.id===id);}});
tabs.forEach(function(t){{t.setAttribute('aria-selected',t.id==='g-'+g);}});
document.querySelectorAll('.subs').forEach(function(x){{x.classList.toggle('on',x.id==='s-'+g);}});
last[g]=id;try{{localStorage.setItem('jlaw-tab2',id);}}catch(e){{}}window.scrollTo(0,0);}}
tabs.forEach(function(t){{t.addEventListener('click',function(){{show(last[t.id.slice(2)]||'t-'+t.dataset.first);}});}});
subs.forEach(function(x){{x.addEventListener('click',function(){{show(x.id);}});}});
(function(){{var u=document.getElementById('upd');if(!u)return;var g=+u.dataset.gen,st=+u.dataset.stale,n=Date.now();
var m=Math.round((n-g)/60000),txt=m<60?m+' 分钟前':m<2880?Math.round(m/60)+' 小时前':Math.round(m/1440)+' 天前';
document.getElementById('ago').textContent='，'+txt;
if(st&&n>st&&location.pathname.indexOf("/archive/")<0){{var w=document.createElement('b');w.style.cssText='color:#fff;background:#C62828;padding:1px 6px;border-radius:4px;margin-left:6px;';
w.textContent='⚠ 已过预定更新时间，可能更新失败';u.appendChild(w);}}}})();
try{{var s=localStorage.getItem('jlaw-tab2');if(s&&document.getElementById(s))show(s);}}catch(e){{}}
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
