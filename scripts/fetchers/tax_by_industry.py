"""Taxes by economic activity (added 2026-11-13, the «налоги по ОКЭД» request).

WHAT WAS LOOKED FOR AND NOT FOUND. The State Revenue Committee (КГД) publishes no table of tax
receipts by ОКЭД: its statistics (gov.kz project `kgd`, direction 655; portal.kgd.gov.kz, 403
content pages read) give receipts by budget code (КБК), by region and by month only; the one
KGD file with ОКЭД divisions 05-09 is «Среднеотраслевое значение КНН» -- tax-burden ratios in
per cent, not receipts. data.egov.kz has only taxpayer registers; the Minfin Statistical Bulletin
has no sheet by activity. The points checked are listed in config/sources.yaml
(TAX_RECEIPTS_BY_OKED, status not_found) and project_knowledge/UPDATE_LOG.md. Two official
publications come closest, and this module reads both:

1. fetch_env_taxes -- BNS «Экологические налоги по видам экономической деятельности»
   (stat.gov.kz element 478740, SEEA environmental-tax account): thousand KZT, calendar years
   2016 on, state budget plus National Fund, 19 ОКЭД sections + «прочие плательщики» + total,
   one sheet per tax group (energy, transport, pollution, resource use) and their sum.
   ONLY environmental taxes in the SEEA sense -- for mining mostly the export rent tax and
   excises under «энергоносители» and the mineral extraction tax under «использование
   ресурсов» -- NOT all taxes: corporate income tax, VAT, payroll taxes are outside it.
   Item <GROUP>.<section>: TOTAL.B, ENERGY.B, RESOURCE.B … Checked on every sheet and year:
   the sections and «прочие» add up to «Всего», the four groups add up to the total sheet.

2. fetch_industry_structure -- the Supreme Audit Chamber's chart «Структура налоговых
   поступлений бюджета (ГБ+НФ) в разрезе отраслей экономики, %» (source: Minfin), transcribed
   in config/tax_structure_by_industry.yaml: six groups, 2017-2025, per cent of the tax
   receipts of the state budget plus the National Fund. No ОКЭД divisions (no 06 / 07).
   The fetcher adds what the pipeline can compute: CONSOLIDATED_TAX = STATE_TAX_REVENUE_YTD in
   December + NF_OIL_DIRECT_TAXES_YTD in December (equal to the Chamber's own totals for
   2023-2025 to 0.1 bn), and <GROUP>.RECEIPTS = share x that total -- an estimate from a rounded
   share (±0.05 pp, about ±13 bn KZT in 2025), labelled as such.
"""
from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

import openpyxl
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import bns  # noqa: E402
from lib import dims, validation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_TAX_URL = "https://stat.gov.kz/api/iblock/element/{element}/file/ru/"
ENV_SHEETS = {  # sheet-name prefix (normalised): (group code, Russian name)
    "налоги на энергоносители": ("ENERGY", "Налоги на энергоносители"),
    "транспортные налоги": ("TRANSPORT", "Транспортные налоги"),
    "налоги на загрязнение": ("POLLUTION", "Налоги на загрязнение окружающей среды"),
    "налоги на исп": ("RESOURCE", "Налоги на использование ресурсов"),
    "экологические налоги": ("TOTAL", "Экологические налоги, всего"),
}
TOLERANCE = 0.001          # 0.1 %


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"{ds['agency']}/{ds['id']}: {what}")


def _num(cell) -> float | None:
    if isinstance(cell, (int, float)):
        return float(cell)
    if isinstance(cell, str):
        s = cell.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
        if s in ("-", "–", "—"):
            return 0.0                       # «-» явление отсутствует (the workbook's own legend)
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return float(s)
    return None


def env_tax_records(grids: dict[str, list[list]], ds: dict) -> list[dict]:
    sections = dims.load_dictionary("okved_sections")
    by_group: dict[str, dict[tuple[str, int], float]] = {}
    names: dict[str, str] = {}
    for sheet, grid in grids.items():
        key = " ".join(str(sheet).lower().split())
        hit = next((v for k, v in ENV_SHEETS.items() if key.startswith(k)), None)
        if hit is None:
            continue
        group, group_name = hit
        head = next((i for i, r in enumerate(grid) if sum(1 for c in r[1:] if re.fullmatch(r"(19|20)\d\d", str(c or "").strip())) >= 5), None)
        if head is None:
            _structural(ds, f"sheet {sheet!r}: no row of years")
        years = {j: int(str(c).strip()) for j, c in enumerate(grid[head]) if j and re.fullmatch(r"(19|20)\d\d", str(c or "").strip())}
        vals: dict[tuple[str, int], float] = {}
        for r in grid[head + 1:]:
            label = " ".join(str(r[0] or "").split())
            if not label:
                continue
            low = label.lower()
            if low.startswith("всего"):
                code, name = "ALL", "все виды деятельности"
            elif low.startswith("прочие плательщики"):
                code, name = "OTHER_PAYERS", "прочие плательщики налогов"
            else:
                m = dims.match_item(label, sections)
                if m is None or len(m[0]) != 1:
                    _structural(ds, f"sheet {sheet!r}: row {label!r} is not an ОКЭД section, «Прочие плательщики» or «Всего»")
                code, name = m
            for j, year in years.items():
                v = _num(r[j]) if j < len(r) else None
                if v is not None:
                    vals[(code, year)] = v
            names[f"{group}.{code}"] = f"{group_name}: {name}"
        for year in years.values():
            total = vals.get(("ALL", year))
            parts = sum(v for (c, y), v in vals.items() if y == year and c != "ALL")
            if total is None or abs(parts - total) > TOLERANCE * abs(total):
                _structural(ds, f"sheet {sheet!r}, {year}: the sections sum to {parts}, «Всего» is {total}")
        by_group[group] = vals
    missing = {g for g, _ in ENV_SHEETS.values()} - set(by_group)
    if missing:
        _structural(ds, f"sheets not found for {sorted(missing)} (got {list(grids)})")
    for (code, year), total in by_group["TOTAL"].items():
        parts = sum(by_group[g].get((code, year), 0.0) for g in ("ENERGY", "TRANSPORT", "POLLUTION", "RESOURCE"))
        if abs(parts - total) > TOLERANCE * max(abs(total), 1.0):
            _structural(ds, f"{code} {year}: the four tax groups sum to {parts}, the total sheet says {total}")
    return sorted(({"date": f"{year}-12-31", "region": dims.NATIONAL, "item_code": f"{g}.{code}", "item_name": names[f"{g}.{code}"],
                    "value": round(v / 1000, 4)} for g, vals in by_group.items() for (code, year), v in vals.items()),
                  key=lambda r: (r["item_code"], r["date"]))


def fetch_env_taxes(ds: dict) -> tuple[list[dict], dict]:
    url = ENV_TAX_URL.format(element=ds["element_id"])
    content = bns._download(url)
    bns._save_raw(ds["id"], content, "xlsx", {"source_url": url, "element_id": ds["element_id"]})
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    grids = {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    wb.close()
    records = env_tax_records(grids, ds)
    if len({r["date"] for r in records}) < ds.get("min_years", 8):
        _structural(ds, f"only {len({r['date'] for r in records})} years")
    return records, {"frequency": "annual", "source_url": url, "dataset_id": str(ds["element_id"]), "note": ds.get("note", "")}


# ---------------------------------------------------------------- the Audit Chamber's industry structure

GROUPS = {"MINING": "Горнодобывающая промышленность", "MANUFACTURING": "Обрабатывающая промышленность", "CONSTRUCTION": "Строительство",
          "TRADE": "Торговля", "TRANSPORT": "Транспорт", "OTHER": "Другие отрасли"}


def _december(agency: str, indicator: str) -> dict[int, float]:
    """{year: the year-to-date value of December} of a scalar series, million KZT."""
    path = REPO_ROOT / "data" / "processed" / agency / f"{indicator.lower()}.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {int(r["date"][:4]): float(r["value"]) for r in csv.DictReader(f) if r["date"][5:7] == "12" and r.get("value")}


def structure_records(doc: dict, ds: dict, state: dict[int, float], fund: dict[int, float]) -> list[dict]:
    out = []
    for year, shares in sorted(doc["shares"].items()):
        if set(shares) != set(GROUPS):
            _structural(ds, f"{year}: groups {sorted(shares)}, expected {sorted(GROUPS)}")
        if abs(sum(shares.values()) - 100) > 0.25:                   # six shares rounded to 0.1
            _structural(ds, f"{year}: the shares sum to {sum(shares.values())}")
        when = f"{year}-12-31"
        total = state[year] + fund[year] if year in state and year in fund else None
        published = (doc.get("published_total_bn") or {}).get(year)
        if published is not None:
            out.append({"date": when, "region": dims.NATIONAL, "item_code": "CONSOLIDATED_TAX.PUBLISHED",
                        "item_name": "Налоговые поступления в консолидированный бюджет по заключению ВАП, млрд тенге", "value": float(published)})
            if total is not None and abs(total / 1000 - published) > 0.5:
                _structural(ds, f"{year}: STATE_TAX_REVENUE_YTD + NF_OIL_DIRECT_TAXES_YTD = {total / 1000:.1f} bn, the Chamber prints {published}")
        if total is not None:
            out.append({"date": when, "region": dims.NATIONAL, "item_code": "CONSOLIDATED_TAX",
                        "item_name": "Налоговые поступления государственного бюджета и Национального фонда (расчёт: STATE_TAX_REVENUE_YTD + NF_OIL_DIRECT_TAXES_YTD за декабрь), млрд тенге",
                        "value": round(total / 1000, 3)})
        for code, share in shares.items():
            out.append({"date": when, "region": dims.NATIONAL, "item_code": f"{code}.SHARE",
                        "item_name": f"{GROUPS[code]}: доля в налоговых поступлениях (ГБ+НФ), %", "value": float(share)})
            if total is not None:
                out.append({"date": when, "region": dims.NATIONAL, "item_code": f"{code}.RECEIPTS",
                            "item_name": f"{GROUPS[code]}: налоговые поступления, оценка = доля x итог, млрд тенге", "value": round(share / 100 * total / 1000, 1)})
    return out


def fetch_industry_structure(ds: dict) -> tuple[list[dict], dict]:
    doc = yaml.safe_load((REPO_ROOT / ds["file"]).read_text(encoding="utf-8"))
    records = structure_records(doc, ds, _december("minfin", "STATE_TAX_REVENUE_YTD"), _december("minfin", "NF_OIL_DIRECT_TAXES_YTD"))
    return records, {"frequency": "annual", "source_url": doc.get("latest_url", ""), "dataset_id": ds["file"],
                     "note": ds.get("note", "") + " " + doc.get("source", "")}
