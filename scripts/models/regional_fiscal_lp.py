"""Regional panel local projections: budget-financed fixed investment and regional CPI.

Shock: fixed investment financed by the republican + local budgets in region r, month t
(Taldau 701827, source of financing 451911/451916, monthly flows from 2018-01), in % of the
region's previous-year nominal GRP / 12. Outcome: cumulative 100*ln change of the regional CPI
(Taldau 703076, 20 regions) from t-1 to t+h. Fixed effects: month (absorbs everything national:
exchange rate, NBK rate, external prices, national tariff decisions), region x calendar month
(regional seasonality), and a separate region id after the June-2022 split for Almaty, Karaganda,
East Kazakhstan oblasts. Controls: 3 lags of regional m/m inflation and of the shock.
SE clustered by region. Identification: relative (cross-regional) effect -- a region that gets more
budget capex than usual this month, relative to other regions the same month."""
import pickle, sys
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
sys.path.insert(0, str(Path(__file__).resolve().parent)); import common
OUT = common.MODELS / "regional_fiscal"; OUT.mkdir(parents=True, exist_ok=True)
NAME = {'АКМОЛИНСКАЯ ОБЛАСТЬ':'AKM','АКТЮБИНСКАЯ ОБЛАСТЬ':'AKT','АЛМАТИНСКАЯ ОБЛАСТЬ':'ALM','АТЫРАУСКАЯ ОБЛАСТЬ':'ATY',
 'ЗАПАДНО-КАЗАХСТАНСКАЯ ОБЛАСТЬ':'ZKO','ЖАМБЫЛСКАЯ ОБЛАСТЬ':'ZHM','КАРАГАНДИНСКАЯ ОБЛАСТЬ':'KRG','КОСТАНАЙСКАЯ ОБЛАСТЬ':'KST',
 'КЫЗЫЛОРДИНСКАЯ ОБЛАСТЬ':'KZL','МАНГИСТАУСКАЯ ОБЛАСТЬ':'MNG','ПАВЛОДАРСКАЯ ОБЛАСТЬ':'PVL','СЕВЕРО-КАЗАХСТАНСКАЯ ОБЛАСТЬ':'SKO',
 'ВОСТОЧНО-КАЗАХСТАНСКАЯ ОБЛАСТЬ':'VKO','Г.АСТАНА':'AST','Г.АЛМАТЫ':'ALA','Г.ШЫМКЕНТ':'SHM','ТУРКЕСТАНСКАЯ ОБЛАСТЬ':'TRK',
 'ОБЛАСТЬ ЖЕТІСУ':'ZHT','ОБЛАСТЬ ҰЛЫТАУ':'ULT','ОБЛАСТЬ АБАЙ':'ABY'}
SPLIT = {'ALM','KRG','VKO'}
_c = pd.read_csv(common.MODELS / 'cpi_components' / 'regional_cpi_mm.csv', index_col=0, parse_dates=True)
_c.index = _c.index.to_period('M'); cpi = {k: _c[k].dropna() for k in _c}
_i = pd.read_csv(common.MODELS / 'cpi_components' / 'regional_budget_investment.csv', parse_dates=['date'])
_i['date'] = _i.date.dt.to_period('M')
inv = {(l, r): g.set_index('date').value for (l, r), g in _i.groupby(['level', 'region'])}
g = common.load_dims(['GRP_NOMINAL_BY_REGION']); g = g[g.item_code=='GDP']; g['year']=g.date.str[:4].astype(int)
grp = g.set_index(['region','year']).value  # million KZT
rows=[]
for nm, code in NAME.items():
    p = cpi.get(nm); 
    if p is None: continue
    budget = inv.get(('rep',nm), pd.Series(dtype=float)).add(inv.get(('loc',nm), pd.Series(dtype=float)), fill_value=0)
    loc = inv.get(('loc',nm), pd.Series(dtype=float))
    for t in p.index:
        if t < pd.Period('2018-01','M'): continue
        y = t.year-1
        G = grp.get((code,y), np.nan)
        rows.append({'r':code,'t':t,'mm':100*np.log(p[t]/100),
                     'shock':budget.get(t,np.nan)/1e6/(G/12)*100 if G==G else np.nan,
                     'shock_loc':loc.get(t,np.nan)/1e6/(G/12)*100 if G==G else np.nan})
D = pd.DataFrame(rows).sort_values(['r','t'])
D['rid'] = D.r + np.where(D.r.isin(SPLIT) & (D.t >= pd.Period('2022-06','M')), '_post', '')
D['cm'] = D.t.map(lambda x: x.month)
D.to_pickle(OUT/'panel.pkl')
print(D.groupby('r').agg(n=('mm','size'), shock_mean=('shock','mean'), shock_sd=('shock','std')).round(2).to_string())
def lp(shockcol, H=18):
    out=[]
    for h in range(H+1):
        X=[]
        for r, g in D.groupby('rid'):
            g=g.set_index('t').sort_index()
            lvl=g.mm.cumsum()
            y=lvl.shift(-h)-lvl.shift(1)
            f=pd.DataFrame({'y':y,'s':g[shockcol]})
            for k in (1,2,3): f[f'dy{k}']=g.mm.shift(k); f[f's{k}']=g[shockcol].shift(k)
            f['rid']=r; f['t']=g.index; f['cm']=g.cm.values
            X.append(f)
        f=pd.concat(X).dropna()
        f['rcm']=f.rid+'_'+f.cm.astype(str)
        dm=pd.get_dummies(f[['t','rcm']].astype(str),drop_first=True,dtype=float)
        Z=pd.concat([f[['s']+[c for c in f if c.startswith(('dy','s1','s2','s3'))]],dm],axis=1)
        m=sm.OLS(f.y,sm.add_constant(Z)).fit(cov_type='cluster',cov_kwds={'groups':pd.factorize(f.rid.str.replace('_post',''))[0]})
        out.append({'h':h,'b':m.params['s'],'se':m.bse['s'],'n':int(m.nobs),'sd_shock':f.s.std()})
    return pd.DataFrame(out)
res={}
for sc in ['shock','shock_loc']:
    r=lp(sc); r['lo90']=r.b-1.645*r.se; r['hi90']=r.b+1.645*r.se; r['t']=r.b/r.se
    res[sc]=r; r.to_csv(OUT/f'lp_{sc}.csv',index=False,float_format='%.4f')
    print(sc); print(r[r.h.isin([0,3,6,9,12,18])].round(3).to_string(index=False))
