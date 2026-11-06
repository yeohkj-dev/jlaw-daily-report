"""全体股票在相同截断规则下的平均超额（理论应为 0，偏差来自截断）。按大盘牛/熊分开。"""
import glob, json, os
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); CACHE=os.path.join(HERE,"..","cache")
bl=pd.read_pickle(os.path.join(HERE,"baseline.pkl"))
spy=pd.DataFrame(json.load(open(os.path.join(CACHE,"SPY.json")))); spy["bull"]=spy.c>spy.c.rolling(200).mean(); reg=dict(zip(spy.d,spy.bull))
acc={}
for f in glob.glob(os.path.join(CACHE,"*.json")):
    s=os.path.basename(f)[:-5]
    if s in("SPY","QQQ"):continue
    d=pd.DataFrame(json.load(open(f))).dropna()
    if len(d)<300:continue
    c,o,v=d.c,d.o,d.v; ent=o.shift(-1)
    m=((c>=5)&((v*c).rolling(20).mean()>=5e6)).values&(np.arange(len(d))>=200)
    bull=d.d.map(reg).fillna(True).values.astype(bool)
    for k in (5,10,20,60):
        cap=0.8 if k==60 else 0.5
        x=np.clip((c.shift(-k)/ent-1).values-d.d.map(bl[f"r{k}"]).values,-cap,cap)
        for t,mm in (("all",m),("bull",m&bull),("bear",m&~bull)):
            v_=x[mm]; v_=v_[~np.isnan(v_)]; a=acc.setdefault(f"{k}_{t}",[0,0.0]); a[0]+=len(v_); a[1]+=v_.sum()
out={k:round(s/n*100,3) for k,(n,s) in acc.items()}
json.dump(out,open(os.path.join(HERE,"bias.json"),"w")); print(out)
