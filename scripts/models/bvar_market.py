"""SVAR decompositions re-estimated on the MARKET core CPI: headline without fruit & vegetables,
petrol, coal (BNS base CPI 'без трех составляющих', Taldau 703082 + 55056856) and without regulated
utilities (removed with the official BNS weights, share 4.5-6.7 % of the core basket; sensitivity +-30 %).
Same models as bvar_sign.py (7 variables) and bvar_sign_ext.py (9 variables)."""
import sys, pickle
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bvar, bvar_sign as S, bvar_sign_ext as E, common
OUT = common.MODELS / "bvar_market"; OUT.mkdir(parents=True, exist_ok=True)
M = pd.read_csv(common.MODELS / "cpi_components" / "market_core_index.csv", index_col=0, parse_dates=True)
M.index = M.index.to_period("M")
def quarterly(col):
    s = M[col].copy(); s.index = s.index.to_timestamp()
    q = s.resample("QS").mean()[s.resample("QS").count() == 3]; q.index = pd.PeriodIndex(q.index, freq="Q"); return q
rng = np.random.default_rng(20260930)
res = {}
for tag in ["base", "low", "high"]:
    qd = E.build_quarterly(); qd["cpi_sa"] = quarterly(f"mkt_{tag}_sa")
    # 7-variable model
    r7 = bvar.estimate(qd, bvar.START, rng); i7 = S.identify(r7, rng); mt7, b7 = S.hd_table(i7)
    b7.to_csv(OUT / f"bands7_{tag}.csv", index=False, float_format="%.3f")
    # 9-variable model (G + tariffs)
    o = E.run(qd, rng); b9 = E.bands(o, E.AGG); b9.to_csv(OUT / f"bands9_{tag}.csv", index=False, float_format="%.3f")
    E.median_target(o).to_csv(OUT / f"median_target9_{tag}.csv", float_format="%.3f")
    res[tag] = (b7, b9)
    print(tag, "lambda", r7["lambda"], o["res"]["lambda"])
pickle.dump(res, open(OUT / "res.pkl", "wb"))
