"""条件基准：不看K线形态，只看"位置/趋势"本身，60 天超额收益（相对同日全市场平均）。"""
import glob, json, os
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); TAG=os.environ.get("BT_TAG",""); CACHE=os.path.join(HERE,"..","cache"+TAG)
bl=pd.read_pickle(os.path.join(HERE,f"baseline{TAG}.pkl"))
spy=pd.DataFrame(json.load(open(os.path.join(CACHE,"SPY.json")))); spy["bull"]=spy.c>spy.c.rolling(200).mean(); reg=dict(zip(spy.d,spy.bull))
acc={}
def add(name,mask,x,bull):
    for tag,m in (("all",mask),("bull",mask&bull),("bear",mask&~bull)):
        v=x[m]; v=v[~np.isnan(v)]
        a=acc.setdefault((name,tag),[0,0.0,0]); a[0]+=len(v); a[1]+=v.sum(); a[2]+=(v>0).sum()
for f in glob.glob(os.path.join(CACHE,"*.json")):
    s=os.path.basename(f)[:-5]
    if s in("SPY","QQQ"):continue
    d=pd.DataFrame(json.load(open(f))).dropna()
    if len(d)<300:continue
    c,o,v=d.c,d.o,d.v
    s50,s150,s200=c.rolling(50).mean(),c.rolling(150).mean(),c.rolling(200).mean()
    ent=o.shift(-1)
    liquid=(c>=5)&((v*c).rolling(20).mean()>=5e6)
    idx=np.arange(len(d))>=200
    base=liquid&idx
    for k in (20,60):
        r=(c.shift(-k)/ent-1).values
        b=d.d.map(bl[f"r{k}"]).values
        x=np.clip(r-b,-0.8,0.8)
        bull=d.d.map(reg).fillna(True).values.astype(bool)
        hi252=c.rolling(252,min_periods=200).max()
        conds={
          "全部股票":base,
          "上升趋势(50>200, 价>50)":base&(c>s50)&(s50>s200),
          "Stage 2 (价>50>150>200, 150MA上升)":base&(c>s50)&(s50>s150)&(s150>s200)&(s150>s150.shift(20)),
          "距 52 周高点 <5%":base&(c>=hi252*0.95),
          "距 52 周高点 >30%":base&(c<=hi252*0.70),
          "价 < 200MA（下降趋势）":base&(c<s200),
          "近 3 个月涨幅 >30%":base&(c/c.shift(63)>1.3),
          "近 3 个月跌幅 >30%":base&(c/c.shift(63)<0.7),
        }
        for n,m in conds.items(): add(f"{n}|{k}",m.values,x,bull)
rows=[]
for (n,t),(cnt,sm,pos) in acc.items():
    nm,k=n.split("|"); rows.append([nm,int(k),t,cnt,round(sm/cnt*100,2) if cnt else None,round(pos/cnt*100,1) if cnt else None])
df=pd.DataFrame(rows,columns=["条件","天","大盘","n","超额%","跑赢%"])
df.to_csv(os.path.join(HERE,f"cond_base{TAG}.csv"),index=False,encoding="utf-8-sig")
pd.set_option("display.width",200)
print(df.pivot_table(index="条件",columns=["天","大盘"],values="超额%").round(2).to_string())
