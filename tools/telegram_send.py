"""把最新的早报发到 Telegram。token 和 chat ID 从环境变量读取（GitHub Secrets：TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID）。

同一份只发一次（早报记录在 早报/_sent.txt，盘前提醒记录在 早报/_premarket_sent.txt）；
--force 不管有没有发过都再发一次（测试用）；--dry-run 只显示不发送；--premarket 发盘前提醒；--weekend 发周末版（默认发早报）。
周末版记录在 早报/_weekend_sent.txt。
用法：python telegram_send.py [输出目录] [--premarket | --weekend] [--force] [--dry-run]
"""
import glob
import json
import os
import sys
import urllib.parse
import urllib.request

argv = sys.argv[1:]
FORCE, DRY, PRE, WKND = "--force" in argv, "--dry-run" in argv, "--premarket" in argv, "--weekend" in argv
args = [a for a in argv if not a.startswith("--")]
OUT_DIR = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEF_DIR = os.path.join(OUT_DIR, "早报")
KIND = "premarket" if PRE else "weekend" if WKND else "brief"
SENT = os.path.join(BRIEF_DIR, {"premarket": "_premarket_sent.txt", "weekend": "_weekend_sent.txt", "brief": "_sent.txt"}[KIND])
PATTERN = {"premarket": "盘前_20??-??-??.json", "weekend": "周末_20??-??-??.json", "brief": "20??-??-??.json"}[KIND]
WHAT = {"premarket": "盘前提醒", "weekend": "周末版早报", "brief": "早报"}[KIND]


def split(text, limit=3900):
    """Telegram 一则信息最多 4,096 字：太长就在空行（段落之间）切成几则，不会把链接切断。"""
    parts, cur = [], ""
    for block in text.split("\n\n"):
        piece = (cur + "\n\n" + block) if cur else block
        if len(piece) <= limit:
            cur = piece
            continue
        if cur:
            parts.append(cur)
        while len(block) > limit:                               # 单一段落也太长：按行切
            cut = block.rfind("\n", 0, limit)
            cut = cut if cut > 0 else limit
            parts.append(block[:cut])
            block = block[cut:].lstrip("\n")
        cur = block
    if cur:
        parts.append(cur)
    return parts


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    files = sorted(glob.glob(os.path.join(BRIEF_DIR, PATTERN)))
    if not files:
        print(f"没有{WHAT}可发")
        return 0
    brief = json.load(open(files[-1], encoding="utf-8"))
    sent = open(SENT, encoding="utf-8").read().strip() if os.path.exists(SENT) else ""
    if brief["date"] == sent and not FORCE:
        print(f"{brief['date']} 的{WHAT}已经发过，不重复发送")
        return 0
    text = brief["telegram_html"]
    if DRY:
        print(text)
        print(f"\n（dry-run：没有发送，{len(text)} 字）")
        return 0
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("没有设置 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，跳过发送")
        return 0
    for part in split(text):
        data = urllib.parse.urlencode({"chat_id": chat, "text": part, "parse_mode": "HTML",
                                       "disable_web_page_preview": "true"}).encode()
        try:
            r = json.load(urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=30))
        except urllib.error.HTTPError as e:
            # 只显示 Telegram 的错误说明，不显示网址（里面有 token）
            print("Telegram 发送失败：", json.loads(e.read() or b"{}").get("description", e.code))
            return 1
        except Exception as e:
            print("Telegram 发送失败：", type(e).__name__)
            return 1
        if not r.get("ok"):
            print("Telegram 发送失败：", r.get("description"))
            return 1
    with open(SENT, "w", encoding="utf-8") as f:
        f.write(brief["date"])
    print(f"已发送 {brief['date']} 的{WHAT}到 Telegram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
