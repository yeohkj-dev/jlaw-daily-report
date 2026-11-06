"""暴跌后研究：①个股 5 日跌幅 >30%（2250 只，2022-2026）②QQQ/SPY 单日大跌（1999 起）。"""
import glob, json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
from common import fetch_json
import urllib.parse
HERE=os.path.dirname(os.path.abspath(__file__)); CACHE=os.path.join(HERE,"..","cache")
bl=pd.read_pickle(os.path.join(HERE,"baseline.pkl"))
out={}
rows=[]
for f in glob.glob(os.path.join(CACHE,"*.json")):
    s=os.path.basename(f)[:-5]
    if s in("SPY","QQQ"):continue
    d=pd.DataFrame(json.load(open(f))).dropna().reset_index(drop=True)
    if len(d)<300:continue
    c=d.c; r5=c/c.shift(5)-1; liquid=(c>=5)&((d.v*c).rolling(20).mean()>=5e6)
    s200=c.rolling(200).mean()
    sig=(r5<-0.30)&(r5.shift(1)>=-0.30)&liquid
    for i in np.where(sig.values)[0]:
        if i+61>=len(d) or i<200:continue
        e=d.o[i+1]
        row={"sym":s,"d":d.d[i],"r5":r5[i],"above200_before":bool(c[i-5]>s200[i-5])}
        for k in (5,20,60):
            row[f"r{k}"]=c[i+k]/e-1; row[f"x{k}"]=row[f"r{k}"]-bl[f"r{k}"].get(d.d[i],np.nan)
        row["mdd20"]=d.l[i+1:i+21].min()/e-1
        rows.append(row)
df=pd.DataFrame(rows)
def sm(g):
    return {"n":len(g),**{f"r{k}":round(g[f"r{k}"].median()*100,1) for k in (5,20,60)},
            **{f"up{k}":round((g[f"r{k}"]>0).mean()*100,1) for k in (20,60)},
            "x60":round(g.x60.clip(-.8,.8).mean()*100,1),"mdd20":round(g.mdd20.median()*100,1)}
out["stock_crash"]={"all":sm(df),"was_uptrend":sm(df[df.above200_before]),"was_downtrend":sm(df[~df.above200_before])}
# 指数
for sym in ("QQQ","^GSPC"):
    j=fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=920000000&period2=1794000000&interval=1d")["chart"]["result"][0]
    qq=j["indicators"]["quote"][0]
    q=pd.DataFrame({"t":j["timestamp"],"o":qq["open"],"h":qq["high"],"l":qq["low"],"c":qq["close"]}).dropna().reset_index(drop=True)
    q["d"]=pd.to_datetime(q.t,unit="s").dt.strftime("%Y-%m-%d")
    q["r1"]=q.c/q.c.shift(1)-1; s200=q.c.rolling(200).mean()
    th=-0.05 if sym=="QQQ" else -0.04
    ev=q.index[(q.r1<=th)&(q.d<"2026-11-05")]
    rs=[]
    for i in ev:
        if i+61>=len(q):continue
        rs.append({"d":q.d[i],"r1":q.r1[i],"above200":bool(q.c[i]>s200[i]),**{f"r{k}":(q.c[i+k]/q.c[i]-1 if i+k<len(q) else np.nan) for k in (5,20,60,250)},
                   "mdd":q.l[i+1:i+61].min()/q.c[i]-1})
    e=pd.DataFrame(rs); print(sym,len(q),q.d.iloc[0],q.d.iloc[-1],len(e))
    def s2(g): return {"n":len(g),**{f"r{k}":round(g[f"r{k}"].median()*100,1) for k in (5,20,60,250)},**{f"up{k}":round((g[f"r{k}"].dropna()>0).mean()*100,1) for k in (20,60,250)},"mdd60":round(g.mdd.median()*100,1)}
    out[sym]={"th":th,"all":s2(e),"above200":s2(e[e.above200]),"below200":s2(e[~e.above200]),
              "recent":e[e.d>="2018-01-01"][["d","r1","r20","r60"]].round(3).values.tolist()}
json.dump(out,open(os.path.join(HERE,"crash.json"),"w"),indent=1,default=str); print(json.dumps(out,indent=1,default=str)[:3500])
