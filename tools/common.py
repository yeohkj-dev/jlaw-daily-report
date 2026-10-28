"""共用工具：带重试的 HTTP、Yahoo Finance（含 crumb）、TradingView 选股器、SEC EDGAR、HTML 小部件。"""
import html as _html
import http.cookiejar
import json
import threading
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
SEC_UA = "jlaw-daily-report research contact@example.com"
SCAN = "https://scanner.tradingview.com/america/scan"

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_crumb = None


def fetch(url, headers=None, data=None, timeout=40, tries=3, raw=False):
    h = {"User-Agent": UA}
    h.update(headers or {})
    last = None
    for k in range(tries):
        try:
            body = _opener.open(urllib.request.Request(url, headers=h, data=data), timeout=timeout).read()
            return body if raw else body.decode("utf-8", "replace")
        except Exception as e:     # 网络错误、限流：稍等再试
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


def fetch_json(url, headers=None, body=None, **kw):
    data = json.dumps(body).encode() if body is not None else None
    hh = dict(headers or {})
    if data is not None:
        hh["Content-Type"] = "application/json"
    return json.loads(fetch(url, hh, data, **kw))


def tv_scan(body):
    return fetch_json(SCAN, body=body)["data"]


# ---------- Yahoo Finance ----------
def yahoo_crumb():
    global _crumb
    if _crumb:
        return _crumb
    try:
        fetch("https://fc.yahoo.com", tries=1)
    except Exception:
        pass                         # 这个地址会返回 404，但会种下 cookie
    _crumb = fetch("https://query1.finance.yahoo.com/v1/test/getcrumb").strip()
    return _crumb


def yahoo_chart(sym, rng="1y", interval="1d"):
    """返回 (K 线, meta)。meta["splits"] = [(时间戳, 拆股比例)]，K 线本身已按拆股调整。"""
    d = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval={interval}&events=split")
    r = d["chart"]["result"][0]
    meta = r.get("meta", {})
    meta["splits"] = sorted((v["date"], v["numerator"] / v["denominator"]) for v in (r.get("events") or {}).get("splits", {}).values()
                            if v.get("denominator"))
    q = r["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(r.get("timestamp") or []):
        o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        if c is not None:
            out.append(dict(t=t, o=o, h=h, l=l, c=c, v=v or 0))
    return out, meta


def yahoo_summary(sym, modules):
    url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(sym)}"
           f"?modules={','.join(modules)}&crumb={urllib.parse.quote(yahoo_crumb())}")
    res = fetch_json(url)["quoteSummary"]["result"]
    return res[0] if res else {}


def yahoo_timeseries(sym, types, years=6):
    p2 = int(time.time())
    p1 = p2 - years * 365 * 86400
    url = (f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{urllib.parse.quote(sym)}"
           f"?type={','.join(types)}&period1={p1}&period2={p2}&crumb={urllib.parse.quote(yahoo_crumb())}")
    out = {}
    for r in fetch_json(url)["timeseries"]["result"]:
        k = r["meta"]["type"][0]
        out[k] = [(x["asOfDate"], x["reportedValue"]["raw"]) for x in (r.get(k) or []) if x and x.get("reportedValue")]
    return out


def raw(d, *keys):
    """安全取 Yahoo 的 {'raw': x} 值。"""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    if isinstance(d, dict):
        return d.get("raw")
    return d


# ---------- SEC EDGAR ----------
_sec_lock = threading.Lock()
_sec_last = [0.0]


def _sec_wait():
    """所有线程合计每秒最多约 5 次（SEC 上限 10 次，超过会封 IP 十分钟）。"""
    with _sec_lock:
        gap = time.time() - _sec_last[0]
        if gap < 0.2:
            time.sleep(0.2 - gap)
        _sec_last[0] = time.time()


def sec_json(url):
    _sec_wait()
    return fetch_json(url, headers={"User-Agent": SEC_UA, "Accept-Encoding": "identity"})


def sec_text(url):
    _sec_wait()
    return fetch(url, headers={"User-Agent": SEC_UA, "Accept-Encoding": "identity"})


# ---------- HTML 小部件（全部内联样式，和原报告一致）----------
esc = _html.escape
TD = 'style="padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top;"'
TDN = 'style="padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top;white-space:nowrap;"'
TH = 'style="padding:6px 8px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;white-space:nowrap;"'
GREEN, RED, AMBER, GREY, BLUE = "#2E7D32", "#C62828", "#B26A00", "#777", "#1F4E78"


def card(title_html, body_html, accent=BLUE, bg="#EEF4FA", sub=""):
    return (f'<div style="max-width:1080px;margin:0 auto;padding:16px;"><div style="background:#fff;border-radius:8px;'
            f'overflow:hidden;border:1px solid #e3e3e3;"><div style="background:{bg};border-left:6px solid {accent};'
            f'padding:16px 18px;">{sub}<div style="font-size:22px;font-weight:700;margin-top:4px;">{title_html}</div></div>'
            f'<div style="padding:16px 18px;font-size:14px;line-height:1.6;">{body_html}</div></div></div>')


def h3(text, color=BLUE):
    return f'<h3 style="margin:22px 0 8px;color:{color};">{text}</h3>'


def table(head, rows_html):
    hd = "".join(f"<th {TH}>{x}</th>" for x in head)
    return (f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:13px;">'
            f"<tr>{hd}</tr>{rows_html}</table></div>")


def pct(x, d=1, signed=True, color=True):
    if x is None:
        return '<span style="color:#aaa;">—</span>'
    s = f"{x:+.{d}f}%" if signed else f"{x:.{d}f}%"
    if not color:
        return s
    c = GREEN if x > 0 else RED if x < 0 else GREY
    return f'<span style="color:{c};">{s}</span>'


def check_list_html(checks):
    """checks: [dict(name, ok, critical, detail)]"""
    if not checks:
        return ""
    items = ""
    for c in checks:
        mark = f'<span style="color:{GREEN};">✔</span>' if c["ok"] else (
            f'<span style="color:{RED};">✘</span>' if c.get("critical") else f'<span style="color:{AMBER};">⚠</span>')
        items += f'<li>{mark} {esc(c["name"])}<span style="color:#888;font-size:12px;"> — {esc(c.get("detail", ""))}</span></li>'
    return f'<ul style="margin:0;padding-left:20px;list-style:none;">{items}</ul>'
