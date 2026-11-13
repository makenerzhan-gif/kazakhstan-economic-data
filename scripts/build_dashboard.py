#!/usr/bin/env python3
"""docs/dashboard.html: one self-contained page with the headline indicators (added 2026-11-13).

Rebuilt at the end of every run from the processed files, so it shows what the run has just
committed. No server and no external script: the series are embedded as JSON and drawn as
inline SVG by the page's own JavaScript (line charts with a crosshair tooltip, a range
filter, a table view per chart, light and dark themes). Open the file in a browser, or serve
the repository's docs/ folder with GitHub Pages.

The panels are listed in PANELS: (scalar agency, id) or (dims dataset, item code), at most
three series a chart -- the three leading slots of the palette are the ones validated for
every pair in both themes (dataviz palette, checked with its validator on 2026-11-13).
"""
from __future__ import annotations

import csv
import html
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import dims  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "docs" / "dashboard.html"
START = "2010-01-01"

# kind "s": scalar (agency, id, transform); kind "d": item-level (dataset, item)
PANELS = [
    {"id": "inflation", "title": "Инфляция и её базовые меры", "unit": "% за 12 месяцев", "digits": 1, "series": [
        ("ИПЦ", "s", "bns", "CPI_YOY", "minus100"),
        ("Усечённое среднее (15 %)", "d", "CORE_INFLATION_MEASURES", "TRIMMED_MEAN_15.YOY"),
        ("Взвешенная медиана", "d", "CORE_INFLATION_MEASURES", "WEIGHTED_MEDIAN.YOY")]},
    {"id": "rates", "title": "Ставки", "unit": "% годовых, среднее за месяц", "digits": 2, "series": [
        ("Базовая ставка", "d", "MONETARY_CONDITIONS", "BASE_RATE"),
        ("TONIA", "d", "MONETARY_CONDITIONS", "TONIA"),
        ("Реальная базовая ставка ex ante", "d", "MONETARY_CONDITIONS", "REAL_BASE_EX_ANTE")]},
    {"id": "fx", "title": "Курс доллара", "unit": "тенге за доллар США, среднее за месяц", "digits": 1, "series": [
        ("USD/KZT", "s", "nbk", "EXCHANGE_RATE", "monthly_mean")]},
    {"id": "oil", "title": "Нефть Brent", "unit": "долларов за баррель", "digits": 1, "series": [
        ("Brent", "s", "wb", "OIL_PRICE_BRENT", None)]},
    {"id": "gap", "title": "Разрыв выпуска", "unit": "% потенциального ВВП", "digits": 1, "zero": True, "series": [
        ("Среднее четырёх методов", "d", "OUTPUT_GAP", "MEAN"),
        ("Односторонний HP", "d", "OUTPUT_GAP", "HP_ONESIDED"),
        ("Модель ненаблюдаемых компонент", "d", "OUTPUT_GAP", "UC")]},
    {"id": "credit", "title": "Кредитный цикл", "unit": "п.п. ВВП", "digits": 1, "zero": True, "series": [
        ("Разрыв кредит/ВВП (Базель III)", "d", "CREDIT_GAP", "CREDIT_GAP"),
        ("Кредитный импульс", "d", "CREDIT_GAP", "CREDIT_IMPULSE")]},
    {"id": "curve", "title": "Наклон кривой доходности ГЦБ", "unit": "п.п.", "digits": 2, "zero": True, "series": [
        ("10 лет минус 1 год", "d", "YIELD_CURVE_SPREADS", "SLOPE_10Y_1Y"),
        ("TONIA минус базовая ставка", "d", "YIELD_CURVE_SPREADS", "TONIA_BASE_SPREAD")]},
    {"id": "dollar", "title": "Долларизация", "unit": "% в иностранной валюте", "digits": 1, "series": [
        ("Кредиты банков", "d", "DOLLARIZATION", "LOANS_FX_SHARE"),
        ("Все депозиты", "d", "DOLLARIZATION", "DEPOSITS_FX_SHARE"),
        ("Депозиты физических лиц", "d", "DOLLARIZATION", "INDIVIDUALS_DEPOSITS_FX_SHARE")]},
    {"id": "fiscal", "title": "Баланс государственного бюджета", "unit": "% ВВП (ненефтяной — % ненефтяного ВВП), за год", "digits": 1,
     "zero": True, "series": [
        ("Общий баланс", "d", "FISCAL_STANCE", "OVERALL_BALANCE_PCT"),
        ("Ненефтяной баланс", "d", "FISCAL_STANCE", "NON_OIL_BALANCE_PCT")]},
    {"id": "labour", "title": "Зарплата и производительность", "unit": "% к тому же кварталу прошлого года", "digits": 1, "zero": True,
     "series": [
        ("Реальная заработная плата", "d", "LABOUR_COST_INDICATORS", "REAL_WAGE_YOY"),
        ("Производительность труда", "d", "LABOUR_COST_INDICATORS", "PRODUCTIVITY_YOY"),
        ("Удельные издержки на труд", "d", "LABOUR_COST_INDICATORS", "ULC_YOY")]},
]
TILES = [("Инфляция, 12 мес.", "inflation", 0, "%"), ("Базовая ставка", "rates", 0, "%"), ("Реальная ставка ex ante", "rates", 2, "%"),
         ("USD/KZT", "fx", 0, "₸"), ("Brent", "oil", 0, "$"), ("Разрыв выпуска", "gap", 0, "%")]


def _scalar(agency: str, indicator: str, transform: str | None) -> list[tuple[str, float]]:
    path = REPO_ROOT / "data" / "processed" / agency / f"{indicator.lower()}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        rows = [(r["date"][:10], float(r["value"])) for r in csv.DictReader(f) if r.get("value") not in (None, "")]
    if transform == "minus100":
        rows = [(d, v - 100) for d, v in rows]
    if transform == "monthly_mean":
        months: dict[str, list[float]] = {}
        for d, v in rows:
            months.setdefault(d[:7] + "-01", []).append(v)
        rows = [(m, sum(v) / len(v)) for m, v in months.items()]
    return sorted(rows)


def _item(dataset: str, item: str) -> list[tuple[str, float]]:
    return sorted((r["date"], float(r["value"])) for r in dims.load_processed(dataset)
                  if r["item_code"] == item and (r.get("region") or dims.NATIONAL) == dims.NATIONAL and r.get("value") not in (None, ""))


def panel_data() -> list[dict]:
    out = []
    for p in PANELS:
        series = []
        for spec in p["series"]:
            rows = _scalar(spec[2], spec[3], spec[4]) if spec[1] == "s" else _item(spec[2], spec[3])
            rows = [(d, round(v, 4)) for d, v in rows if d >= START]
            if rows:
                series.append({"name": spec[0], "points": rows})
        if series:
            out.append({"id": p["id"], "title": p["title"], "unit": p["unit"], "digits": p["digits"], "zero": bool(p.get("zero")),
                        "series": series})
    return out


CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--border:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--up:#006300;--down:#d03b3b}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--s3:#199e70;
--up:#0ca30c;--down:#e66767}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;
--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--s3:#199e70;--up:#0ca30c;--down:#e66767}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 20px}.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 16px}
.bar span{color:var(--ink2);margin-right:4px}button{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--border);
border-radius:6px;padding:5px 12px;cursor:pointer}button[aria-pressed="true"]{border-color:var(--ink);font-weight:600}
button:focus-visible{outline:2px solid var(--s1);outline-offset:2px}.spacer{flex:1}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:0 0 20px}
.tile,.card{background:var(--surface);border:1px solid var(--border);border-radius:10px}.tile{padding:12px 14px}
.tile .l{color:var(--ink2);font-size:12px}.tile .v{font-size:26px;font-weight:600;margin:2px 0}.tile .d{font-size:12px;color:var(--ink2)}
.tile .d b{font-weight:600}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:16px}
.card{padding:14px 14px 10px;min-width:0}.card h2{font-size:15px;margin:0}.card .u{color:var(--ink2);font-size:12px;margin:0 0 6px}
.head{display:flex;gap:8px;align-items:flex-start}.head div{flex:1;min-width:0}.head button{padding:2px 8px;font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink2);margin:0 0 4px}
.legend i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:6px;border-radius:1px}
.plot{position:relative}svg{display:block;width:100%;height:auto;overflow:visible}svg text{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
svg .end{fill:var(--ink2)}.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--border);border-radius:8px;
padding:8px 10px;font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.12);min-width:150px;display:none;z-index:2}
.tip .t{color:var(--ink2);margin-bottom:4px}.tip .r{display:flex;gap:8px;align-items:center}.tip .r i{width:12px;height:2px;border-radius:1px;flex:none}
.tip .r b{font-weight:600;font-variant-numeric:tabular-nums}.tip .r span{color:var(--ink2)}
.tablewrap{max-height:260px;overflow:auto;margin-top:6px}table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:3px 8px;border-bottom:1px solid var(--grid)}th:first-child,td:first-child{text-align:left}
th{position:sticky;top:0;background:var(--surface);color:var(--ink2);font-weight:600}footer{color:var(--ink2);font-size:12px;margin-top:24px}
"""

JS = r"""
const DATA = JSON.parse(document.getElementById('data').textContent);
const COLORS = ['--s1','--s2','--s3'];
const fmt = (v,d)=>v.toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});
const MONTHS=['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];
const label = d=>{const [y,m]=d.split('-');return MONTHS[+m-1]+' '+y};
const el = (tag,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(const k in attrs)n.setAttribute(k,attrs[k]); if(text!=null)n.textContent=text; return n};
const h = (tag,cls,text)=>{const n=document.createElement(tag); if(cls)n.className=cls; if(text!=null)n.textContent=text; return n};
let range = localStorageGet('range') || '5';
function localStorageGet(k){try{return localStorage.getItem('kzdash-'+k)}catch(e){return null}}
function localStorageSet(k,v){try{localStorage.setItem('kzdash-'+k,v)}catch(e){}}

function niceTicks(lo,hi,n){const span=hi-lo||1, raw=span/n, mag=Math.pow(10,Math.floor(Math.log10(raw)));
  const step=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=raw); const a=Math.floor(lo/step)*step, out=[];
  for(let v=a; v<=hi+step*0.5; v+=step) out.push(+v.toFixed(10)); return out}

function draw(card,p){
  const plot=card.querySelector('.plot'); plot.textContent='';
  const last=p.series.map(s=>s.points[s.points.length-1][0]).sort().pop();
  const from = range==='all' ? '0000' : (parseInt(last.slice(0,4))-parseInt(range))+last.slice(4);
  const series=p.series.map(s=>({name:s.name,pts:s.points.filter(q=>q[0]>=from)})).filter(s=>s.pts.length);
  const dates=[...new Set(series.flatMap(s=>s.pts.map(q=>q[0])))].sort();
  if(!dates.length) return;
  const W=560,H=250,L=44,R=64,T=10,B=26, t0=Date.parse(dates[0]), t1=Date.parse(dates[dates.length-1])||t0+1;
  let lo=Math.min(...series.flatMap(s=>s.pts.map(q=>q[1]))), hi=Math.max(...series.flatMap(s=>s.pts.map(q=>q[1])));
  if(p.zero){lo=Math.min(lo,0);hi=Math.max(hi,0)}
  const ticks=niceTicks(lo,hi,5); lo=Math.min(lo,ticks[0]); hi=Math.max(hi,ticks[ticks.length-1]);
  const x=d=>L+(Date.parse(d)-t0)/((t1-t0)||1)*(W-L-R), y=v=>T+(hi-v)/((hi-lo)||1)*(H-T-B);
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':p.title+', '+p.unit});
  const tickDigits=Math.max(0,-Math.floor(Math.log10((ticks[1]-ticks[0])||1)));
  for(const t of ticks){svg.append(el('line',{x1:L,x2:W-R,y1:y(t),y2:y(t),stroke:(p.zero&&t===0)?'var(--axis)':'var(--grid)','stroke-width':1}));
    svg.append(el('text',{x:L-6,y:y(t)+4,'text-anchor':'end'},fmt(t,Math.min(tickDigits,2))))}
  const y0=parseInt(dates[0]), y1=parseInt(dates[dates.length-1]), stepY=Math.max(1,Math.ceil((y1-y0+1)/7));
  for(let yr=y0+1; yr<=y1; yr+=stepY){const d=yr+'-01-01'; if(Date.parse(d)>=t0) svg.append(el('text',{x:x(d),y:H-8,'text-anchor':'middle'},yr))}
  const ends=[];
  series.forEach((s,i)=>{const c=`var(${COLORS[p.series.findIndex(q=>q.name===s.name)]})`;
    svg.append(el('path',{d:s.pts.map((q,j)=>(j?'L':'M')+x(q[0]).toFixed(1)+' '+y(q[1]).toFixed(1)).join(''),fill:'none',stroke:c,
      'stroke-width':2,'stroke-linejoin':'round','stroke-linecap':'round'}));
    const e=s.pts[s.pts.length-1]; svg.append(el('circle',{cx:x(e[0]),cy:y(e[1]),r:4,fill:c,stroke:'var(--surface)','stroke-width':2}));
    ends.push({y:y(e[1]),x:x(e[0]),text:fmt(e[1],p.digits)})});
  ends.sort((a,b)=>a.y-b.y); for(let i=1;i<ends.length;i++) if(ends[i].y-ends[i-1].y<13) ends[i].y=ends[i-1].y+13;
  for(const e of ends) svg.append(el('text',{x:e.x+9,y:e.y+4,class:'end'},e.text));
  const cross=el('line',{y1:T,y2:H-B,stroke:'var(--axis)','stroke-width':1,visibility:'hidden'}); svg.append(cross);
  const dots=series.map(s=>{const c=el('circle',{r:4,fill:`var(${COLORS[p.series.findIndex(q=>q.name===s.name)]})`,stroke:'var(--surface)',
    'stroke-width':2,visibility:'hidden'}); svg.append(c); return c});
  const hit=el('rect',{x:L,y:T,width:W-L-R,height:H-T-B,fill:'transparent',tabindex:0,'aria-label':'Значения по датам: '+p.title}); svg.append(hit);
  const tip=h('div','tip'); plot.append(svg,tip);
  let idx=dates.length-1;
  function show(i){idx=Math.max(0,Math.min(dates.length-1,i)); const d=dates[idx], px=x(d);
    cross.setAttribute('x1',px);cross.setAttribute('x2',px);cross.setAttribute('visibility','visible');
    tip.textContent=''; tip.append(h('div','t',label(d)));
    series.forEach((s,k)=>{const q=s.pts.find(z=>z[0]===d); const dot=dots[k];
      if(!q){dot.setAttribute('visibility','hidden');return}
      dot.setAttribute('cx',px);dot.setAttribute('cy',y(q[1]));dot.setAttribute('visibility','visible');
      const r=h('div','r'), key=h('i'); key.style.background=`var(${COLORS[p.series.findIndex(z=>z.name===s.name)]})`;
      r.append(key,h('b','',fmt(q[1],p.digits)),h('span','',s.name)); tip.append(r)});
    tip.style.display='block'; const box=plot.getBoundingClientRect(), fx=px/W*box.width;
    tip.style.left=(fx>box.width/2 ? Math.max(0,fx-tip.offsetWidth-12) : fx+12)+'px'; tip.style.top='8px'}
  function hide(){tip.style.display='none';cross.setAttribute('visibility','hidden');dots.forEach(c=>c.setAttribute('visibility','hidden'))}
  hit.addEventListener('pointermove',ev=>{const box=svg.getBoundingClientRect(), px=(ev.clientX-box.left)/box.width*W;
    const t=t0+(px-L)/(W-L-R)*(t1-t0); let best=0,bd=Infinity; dates.forEach((d,i)=>{const k=Math.abs(Date.parse(d)-t); if(k<bd){bd=k;best=i}}); show(best)});
  hit.addEventListener('pointerleave',hide); hit.addEventListener('blur',hide); hit.addEventListener('focus',()=>show(idx));
  hit.addEventListener('keydown',ev=>{if(ev.key==='ArrowLeft'){show(idx-1);ev.preventDefault()} if(ev.key==='ArrowRight'){show(idx+1);ev.preventDefault()}});
  const wrap=card.querySelector('.tablewrap'); wrap.textContent='';
  const table=h('table'), head=h('tr'); head.append(h('th','','Дата')); series.forEach(s=>head.append(h('th','',s.name)));
  const thead=h('thead'); thead.append(head); const tb=h('tbody');
  [...dates].reverse().forEach(d=>{const tr=h('tr'); tr.append(h('td','',label(d)));
    series.forEach(s=>{const q=s.pts.find(z=>z[0]===d); tr.append(h('td','',q?fmt(q[1],p.digits):'—'))}); tb.append(tr)});
  table.append(thead,tb); wrap.append(table);
}

function build(){
  const tiles=document.getElementById('tiles');
  for(const t of DATA.tiles){const p=DATA.panels.find(q=>q.id===t.panel); if(!p||!p.series[t.series])continue;
    const pts=p.series[t.series].points, a=pts[pts.length-1], b=pts.length>12?pts[pts.length-13]:pts[0];
    const n=h('div','tile'); n.append(h('div','l',t.label), h('div','v',fmt(a[1],p.digits)+(t.suffix==='%'?' %':t.suffix==='$'?' $':' ₸')));
    const d=h('div','d'), delta=a[1]-b[1]; const s=h('b','',(delta>0?'▲ +':delta<0?'▼ −':'')+fmt(Math.abs(delta),p.digits));
    d.append(s, document.createTextNode(' к '+label(b[0])+' · '+label(a[0]))); n.append(d); tiles.append(n)}
  const grid=document.getElementById('grid');
  for(const p of DATA.panels){const card=h('section','card'), head=h('div','head'), txt=h('div');
    txt.append(h('h2','',p.title), h('p','u',p.unit)); const tb=h('button','', 'Таблица'); tb.setAttribute('aria-pressed','false');
    head.append(txt,tb); card.append(head);
    if(p.series.length>1){const lg=h('div','legend'); p.series.forEach((s,i)=>{const it=h('span'), key=h('i'); key.style.background=`var(${COLORS[i]})`;
      it.append(key, document.createTextNode(s.name)); lg.append(it)}); card.append(lg)}
    const plot=h('div','plot'), wrap=h('div','tablewrap'); wrap.hidden=true; card.append(plot,wrap); grid.append(card);
    tb.addEventListener('click',()=>{wrap.hidden=!wrap.hidden; tb.setAttribute('aria-pressed',String(!wrap.hidden))});
    card._p=p; draw(card,p)}
  document.querySelectorAll('[data-range]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.range===range));
    b.addEventListener('click',()=>{range=b.dataset.range; localStorageSet('range',range);
      document.querySelectorAll('[data-range]').forEach(z=>z.setAttribute('aria-pressed',String(z===b)));
      document.querySelectorAll('.card').forEach(c=>draw(c,c._p))})});
  const th=document.getElementById('theme'); th.addEventListener('click',()=>{const root=document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme==='dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark'; localStorageSet('theme',root.dataset.theme)});
  const saved=localStorageGet('theme'); if(saved) document.documentElement.dataset.theme=saved;
}
build();
"""


def render(panels: list[dict], built: str) -> str:
    tiles = [{"label": t[0], "panel": t[1], "series": t[2], "suffix": t[3]} for t in TILES]
    payload = json.dumps({"panels": panels, "tiles": tiles}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Экономика Казахстана: ключевые индикаторы</title><style>{CSS}</style></head>
<body><main>
<h1>Экономика Казахстана: ключевые индикаторы</h1>
<p class="sub">Данные пайплайна kazakhstan-economic-data на {html.escape(built)}. Расчётные показатели (базовая инфляция, реальная ставка,
разрыв выпуска, кредитный цикл) — оценки репозитория, не официальная статистика; методика — в примечаниях датасетов.</p>
<div class="bar"><span>Период:</span><button data-range="3">3 года</button><button data-range="5">5 лет</button>
<button data-range="10">10 лет</button><button data-range="all">Всё с 2010</button><div class="spacer"></div>
<button id="theme" aria-label="Сменить тему">Светлая / тёмная</button></div>
<div class="tiles" id="tiles"></div>
<div class="grid" id="grid"></div>
<footer>Источники: БНС АСПР РК, Национальный Банк РК, Министерство финансов РК, KASE, Всемирный банк; расчёты — scripts/fetchers/analytics.py.
Страница собирается скриптом scripts/build_dashboard.py после каждого прогона.</footer>
</main><script type="application/json" id="data">{payload}</script><script>{JS}</script></body></html>
"""


def main() -> int:
    panels = panel_data()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(panels, date.today().isoformat()), encoding="utf-8")
    print(f"dashboard: {len(panels)} panels, {OUT.stat().st_size // 1024} KB -> {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
