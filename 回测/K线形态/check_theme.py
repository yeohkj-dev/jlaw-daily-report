"""核对主题 1（急跌反弹）是否因"之前是否在上升趋势"而不同，避免与 crash_study 结论矛盾。"""
import glob, json, os
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); CACHE=os.path.join(HERE,"..","cache")
bl=pd.read_pickle(os.path.join(HERE,"baseline.pkl")); B=json.load(open(os.path.join(HERE,"bias.json")))
out=[]
for f in glob.glob(os.path.join(CACHE,"*.json")):
    s=os.path.basename(f)[:-5]
    if s in("SPY","QQQ"):continue
    d=pd.DataFrame(json.load(open(f))).dropna().reset_index(drop=True)
    if len(d)<300:continue
    c,o=d.c,d.o; s200=c.rolling(200).mean(); ent=o.shift(-1)
    liq=(c>=5)&((d.v*c).rolling(20).mean()>=5e6)
    sig=(c/c.shift(1)-1<=-0.05)&(c.shift(1)/c.shift(21)-1<=-0.15)&liq&(np.arange(len(d))>=252)
    for i in np.where(sig.values)[0]:
        if i+21>=len(d):continue
        r={"d":d.d[i],"was_up":bool(c[i-25]>s200[i-25]),"r5_30":bool(c[i]/c[i-5]-1<=-0.30)}
        for k in (20,60):
            if i+k<len(d):
                cap=.8 if k==60 else .5
                r[f"x{k}"]=float(np.clip(c[i+k]/ent[i]-1-bl[f"r{k}"].get(d.d[i],np.nan),-cap,cap)-B[f"{k}_all"]/100)
                r[f"r{k}"]=float(c[i+k]/ent[i]-1)
        out.append(r)
e=pd.DataFrame(out)
def sm(g):return dict(n=len(g),x20=round(g.x20.mean()*100,2),x60=round(g.x60.mean()*100,2),r60med=round(g.r60.median()*100,1),up60=round((g.r60.dropna()>0).mean()*100,1))
res={"all":sm(e),"was_up":sm(e[e.was_up]),"was_down":sm(e[~e.was_up]),"was_up_5d30":sm(e[e.was_up&e.r5_30])}
json.dump(res,open(os.path.join(HERE,"theme1_split.json"),"w"),indent=1);print(res)
