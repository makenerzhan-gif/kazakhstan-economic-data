"""USGS Minerals Yearbook, Kazakhstan, Table 1 — all editions (xls 2007-2014, xlsx 2016-2023).
Returns {commodity: {year: value}} in the target units below; newer editions override older ones (revisions)."""
import glob, os, re

RAW = "" + str(__import__("pathlib").Path(__file__).resolve().parents[1] / "data/raw/resource_history/usgs_myb") + ""
TOP = ("aluminum", "copper", "ferroalloys", "gold", "iron ore", "iron and steel", "lead", "manganese", "silver",
       "titanium", "zinc", "coal", "natural gas", "petroleum", "chromium", "chromite", "phosphate rock", "sulfur",
       "uranium", "bismuth", "stone", "sand", "clays", "nitrogen")


def grids():
    import glob as _g
    old = []
    for f in _g.glob(os.path.join(UP_DIR, "*.pdf")):
        b = os.path.basename(f)
        m = re.search(r"94220(\d\d)\.pdf", b)
        if m:
            old.append((1900 + int(m.group(1)), f))
    for y, f in sorted(old):
        txt = open(f + ".txt", encoding="utf-8").read() if os.path.exists(f + ".txt") else ""
        g = pdf_grid(txt)
        if g:
            yield y, g
    for f in _g.glob(os.path.join(UP_DIR, "*cismyb04.xls")):
        yield 2004, cis_grid(f)
    files = []
    for f in glob.glob(os.path.join(RAW, "*.xls*")):
        m = re.search(r"myb3-(\d{4})", os.path.basename(f))
        files.append((int(m.group(1)), f))
    for y, f in sorted(files):
        if f.endswith(".xls"):
            import xlrd
            b = xlrd.open_workbook(f)
            sh = b.sheet_by_name("Table 1") if "Table 1" in b.sheet_names() else None
            if sh is None:
                continue
            yield y, [sh.row_values(i) for i in range(sh.nrows)]
        else:
            import openpyxl
            wb = openpyxl.load_workbook(f, data_only=True)
            ws = next((w for w in wb.worksheets if w.title.lower().replace(" ", "") == "table1"), None)
            if ws is None:
                continue
            yield y, [list(r) for r in ws.iter_rows(values_only=True)]


UNITS = ["thousand metric tons", "thousand tons", "million cubic meters", "thousand cubic meters", "kilograms",
         "42-gallon barrels", "thousand carats", "cubic meters", "do."]
UP_DIR = RAW


def pdf_grid(txt: str):
    """KAZAKHSTAN production table from an old yearbook PDF text -> grid rows [label, unit, v1..vN]."""
    m = re.search(r"KAZAK[H]?STAN:\s+(ESTIMATED )?PRODUCTION OF MINERAL COMMODITIES", txt)
    if not m:
        return []
    body = txt[m.start():]
    end = re.search(r"STRUCTURE OF THE MINERAL INDUSTRY|TABLE\s+2\b", body)
    body = body[:end.start()] if end else body
    grid, n = [], None
    for line in body.splitlines():
        if line.strip().startswith("Commodity"):
            ys = re.findall(r"(?:19|20)\d\d", line)
            if len(ys) >= 3:
                n = len(ys)
                grid.append(["Commodity", None] + ys)
            continue
        if n is None or not line.strip():
            continue
        if re.match(r"\s*(e/|r/|\d/|NA\s+Not|--\s+Zero|See footnotes|TABLE|KAZAK|\(Metric)", line):
            continue
        toks = [t for t in line.split() if not re.fullmatch(r"\d*[a-z]*/|\d+/\s*", t) and t not in ("e/", "r/")]
        # find first value token
        def isval(t):
            return re.fullmatch(r"-?[\d,]+(\.\d+)?", t) or t in ("--", "NA", "(5)", "XX")
        idx = next((i for i, t in enumerate(toks) if isval(t) and not re.fullmatch(r"\d", t) or (isval(t) and i > 0 and i == len(toks) - n)), None)
        label_toks = toks if idx is None else toks[:idx]
        vals = [] if idx is None else toks[idx:]
        label = " ".join(label_toks)
        unit = None
        for u in UNITS:
            if label.endswith(" " + u) or label == u:
                unit, label = u, label[: -len(u)].strip()
                break
        label = re.sub(r"\s+e/?$", "", label).replace("--Continued", "").strip()
        nums = []
        for t in vals:
            if t == "--":
                nums.append(0.0)
            elif isval(t) and t not in ("NA", "XX", "(5)"):
                nums.append(float(t.replace(",", "")))
            elif t in ("NA", "XX", "(5)"):
                nums.append(None)
        if nums and len(nums) > n:
            nums = nums[-n:]
        nums = [None] * (n - len(nums)) + nums if nums else []
        indent = len(line) - len(line.lstrip())
        if not nums:
            grid.append([(" " * indent) + label + ("" if label.endswith(":") else ":"), None] + [None] * n)
        else:
            grid.append([(" " * indent) + label, unit] + nums)
    return grid


def cis_grid(f):
    import xlrd
    b = xlrd.open_workbook(f)
    sh = b.sheet_by_name("Table1")
    rows = [sh.row_values(i) for i in range(sh.nrows)]
    out, on = [], False
    for r in rows:
        first = str(r[0]).strip() if r else ""
        if first.lower().startswith("country and commodity"):
            out.append(["Commodity"] + r[1:])
            continue
        if first.isupper() and len(first) > 3 and not first.startswith(("TABLE", "COMMONWEALTH")):
            on = first.startswith("KAZAKHSTAN")
            continue
        if on:
            out.append(r)
    return out


def unit_scale(u: str) -> float:
    u = (u or "").lower()
    if "kilogram" in u:
        return 1e-3
    if "thousand" in u:
        return 1e3
    if "million" in u:
        return 1e6
    return 1.0


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and re.fullmatch(r"\s*-?[\d.]+\s*", v):
        return float(v)
    return None


def parse():
    out = {}  # path -> {year: value in base units (t, m3, bbl)}
    for ed, g in grids():
        years = None
        stack = []
        last_unit = ""
        for row in g:
            cells = list(row) + [None] * 3
            first = cells[0]
            if isinstance(first, str) and first.strip().lower().startswith("commodity"):
                ys = [(j, int(float(c))) for j, c in enumerate(cells) if c not in (None, "") and re.fullmatch(r"(19|20)\d\d(\.0)?", str(c).strip())]
                if len(ys) >= 3:
                    years = ys
                continue
            if years is None or not isinstance(first, str) or not first.strip():
                continue
            label = first.strip()
            if label.isupper() or label.startswith(("See footnotes", "TABLE", "KAZAKHSTAN", "(")):
                if label.isupper():
                    stack = []
                continue
            clean = re.sub(r"(?<=[a-z\)])e?\d+(,\s*\d+)*$", "", label)   # trailing footnote digits
            clean = clean.rstrip(":").strip()
            # unit: first text cell between label and first year column
            unit = None
            for c in cells[1:years[0][0]]:
                if isinstance(c, str) and c.strip():
                    unit = c.strip()
                    break
            if unit == "do.":
                unit = last_unit
            vals = {y: num(cells[j]) for j, y in years if j < len(cells) and num(cells[j]) is not None}
            if label.endswith(":") and not vals:
                if re.match(r"(metals|industrial minerals|mineral fuels)", clean.lower()):
                    stack = []
                    continue
                if clean.lower().startswith(TOP):
                    stack = [clean]
                else:
                    stack = stack[:1] + [clean]
                continue
            if not vals:
                continue
            last_unit = unit or ""
            sc = unit_scale(unit)
            path = " / ".join(stack + [clean])
            out.setdefault(path, {}).update({y: v * sc for y, v in vals.items()})
    return out


SEL = {
    "oil_t": [r"^Petroleum, crude$", r"Petroleum, crude / Gravimetric units$", r"Petroleum / Crude oil and gas condensate / In gravimetric units"],
    "gas_m3": [r"^Natural gas, (marketable|gross)$", r"^Natural gas$", r"^Natural gas / Total$", r"Coal / Natural gas$"],
    "coal_t": [r"^Coal$", r"^Coal / Total$"],
    "uranium_t": [r"Uranium concentrate, U content$", r"Uranium / U content", r"Uranium.*/ ?U content$", r"Uranium, mine.*U content"],
    "iron_ore_t": [r"Iron ore, marketable$", r"Iron ore.*/ Gross weight$"],
    "chromite_t": [r"(^| / )Chromite$", r"Chromite, mine production / Crude ore", r"chromite / Ore$"],
    "manganese_t": [r"Manganese ore / Crude$", r"Manganese ore, crude ore / Gross weight", r"Lead / Crude ore / Gross weight", r"Manganese, mine / Crude ore / Gross weight"],
    "bauxite_t": [r"^Bauxite$", r"Aluminum / Bauxite$"],
    "alumina_t": [r"^Alumina$", r"Aluminum / Alumina$"],
    "aluminium_t": [r"Aluminum / (Aluminum metal, primary|Metal, primary)$"],
    "copper_mine_t": [r"Copper / Mine output, metal content$", r"Copper / Mine output, Cu content$", r"Copper / Mine, concentrate, Cu content / Total$", r"Copper / Mine, Cu content / Total$"],
    "copper_ref_t": [r"Copper / Metal / Refined, primary$", r"Copper / Refinery production, primary$", r"Copper / Refinery, primary / Total$"],
    "gold_t": [r"^Gold, mine output", r"Gold / Mine output, metal content$", r"Gold / Mine.*Au content$"],
    "silver_t": [r"^Silver$", r"Silver / Mine output, metal content$", r"Silver, mine output, Ag content", r"Silver / Mine.*Ag content$"],
    "zinc_t": [r"Zinc / Mine output, metal content$", r"Zinc / Mine.*Zn content$"],
    "lead_t": [r"Lead / Mine output, metal content$", r"Lead / Concentrate, Pb content$", r"Lead / Mine.*Pb content$"],
    "ferroalloys_t": [r"Ferroalloys / Total$"],
    "ti_sponge_t": [r"^Titanium, metal$", r"Titanium / Sponge$"],
    "phosphate_t": [r"^Phosphate rock$", r"Phosphate rock / Gross weight$"],
    "asbestos_t": [r"Asbestos"],
    "barite_t": [r"^Barite"],
    "molybdenum_t": [r"Molybdenum.*Mo con"],
}


def series():
    P = parse()
    global SEL
    SEL = {k: [re.sub(r"\$$", "e?$", x) for x in v] for k, v in SEL.items()}
    SEL["oil_t"].append(r"Petroleum / Crude.*/ Gravimetric units$")
    SEL["ti_sponge_t"] += [r"Titanium, sponge$", r"(^|/ )Titanium, metal$"]
    out = {}
    for key, pats in SEL.items():
        merged = {}
        for path, vals in P.items():
            if any(re.search(p, path, re.I) for p in pats):
                merged.setdefault("_paths", []).append(path)
                for y, v in vals.items():
                    merged[y] = v      # editions iterate oldest→newest inside parse; path order follows first appearance
        # fix override order: recompute per edition order (parse keeps update order already per path)
        out[key] = merged
    # copper mine 2012-2017 = concentrate + SX where no total
    conc = {}
    sx = {}
    for path, vals in P.items():
        if re.search(r"Copper / (Mine production, concentrate, Cu content|Mine / Concentrates, Cu content|Mine, Cu content / Concentrates)$", path):
            conc.update(vals)
        if re.search(r"Copper / (Leaching, electrowon|Mine / Solvent extraction|Mine, Cu content / Solvent extraction)$", path):
            sx.update(vals)
    for y in conc:
        if y in sx and y not in out["copper_mine_t"]:
            out["copper_mine_t"][y] = conc[y] + sx[y]
    ref_l = {}
    ref_o = {}
    for path, vals in P.items():
        if path == "Copper / Refinery, primary / Leaching, electrowon":
            ref_l.update(vals)
        if path == "Copper / Refinery, primary / Other":
            ref_o.update(vals)
    for y in ref_l:
        if y in ref_o and y not in out["copper_ref_t"]:
            out["copper_ref_t"][y] = ref_l[y] + ref_o[y]
    # unit fixes for older editions
    out["silver_t"] = {y: (v / 1000 if v > 20000 else v) for y, v in out["silver_t"].items() if y != "_paths"} | {"_paths": out["silver_t"].get("_paths", [])}
    out["gas_m3"] = {y: (v * 1000 if v < 1e9 else v) for y, v in out["gas_m3"].items() if y != "_paths"} | {"_paths": out["gas_m3"].get("_paths", [])}
    out["phosphate_t"] = {y: v for y, v in out["phosphate_t"].items() if y == "_paths" or y >= 2000}
    return out, P


if __name__ == "__main__":
    s, P = series()
    for k, v in s.items():
        paths = v.pop("_paths", [])
        ys = sorted(v)
        print(f"{k:14s} {ys[0] if ys else '-'}-{ys[-1] if ys else '-'} n={len(ys)}  ", {y: round(v[y] / 1e3, 1) for y in ys if y % 4 == 3 or y in (2003, 2023)}, paths[:4])
