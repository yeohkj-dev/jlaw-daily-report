"""J Law META / VCP 信号（与网站同一份 analyse()），按 BT_TAG 选数据（20 = cache20，2005 起），存 jlaw_sig{TAG}.pkl。"""
import os, sys, pickle
import backtest as bt
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    TAG = os.environ.get("BT_TAG", "")
    meta, P, dates = bt.panel()
    print("股票", len(meta), "交易日", len(dates), dates[0].date(), "→", dates[-1].date(), flush=True)
    sig = bt.jlaw_signals(meta, bt.load_bars("SPY"), P)
    print("信号", len(sig), sig["kind"].value_counts().to_dict(), flush=True)
    pickle.dump(sig, open(os.path.join(bt.HERE, f"jlaw_sig{TAG}.pkl"), "wb"))
    print("完成")
