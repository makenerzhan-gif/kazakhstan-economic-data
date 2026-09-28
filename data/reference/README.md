# data/reference/

Static reference tables that no updater refreshes (their sources publish them as one-off
research releases). Written 2026-09-25 for the gravity model of Kazakhstan's trade; the
trade flows, partner GDP/population and tariffs they pair with are item-level datasets in
`config/dims.yaml` (KZ_EXPORTS_BY_PARTNER, WITS_KZ_*, WDI_*, KZ_TARIFF_*), keyed by the
same ISO3 codes.

| File | Rows | Source |
|---|---|---|
| `cepii_geodist_kaz.csv` | 224 partners of Kazakhstan | CEPII GeoDist (Mayer & Zignago 2011), `https://www.cepii.fr/distance/dist_cepii.zip`, rows with `iso_o = KAZ`: `dist` (km between the most populated cities), `distcap` (capitals), `distw`/`distwces` (population-weighted), `contig`, `comlang_off`, `comlang_ethno`, `colony`, `comcol`, `curcol`, `col45`, `smctry` |
| `cepii_gravity_kaz.csv` | 7 009 rows: partner × year, 1992–2021 | CEPII Gravity database V202211 (Conte, Cotterlaz & Mayer 2022), rows with `iso3_o = KAZ`: distances (`distw_harmonic` is the recommended one), contiguity, languages, religion, `col_dep_ever` (a former dependency relation; 0 for every KAZ pair in this release, so the gravity model codes the former USSR itself), `sibling_ever` (both ex-dependencies of the same hegemon, e.g. KAZ–KGZ), `fta_wto`/`rta_type` (trade agreements notified to the WTO), `gatt_d`/`wto_o`/`wto_d` (membership; Kazakhstan joined the WTO on 2015-11-30), `eu_d`, `diplo_disagreement`, `scaled_sci_2021` (Facebook social connectedness). Only years in which the partner existed (`country_exists_d = 1`) are kept; CEPII carries a second, non-existent row for a few split or merged states (DEU, ETH, IDN, MYS, PAK, SDN, VNM, YEM, ANT) |

Kazakhstan's EAEU membership (from 2015; customs union with Russia and Belarus from
2010) shows up in `fta_wto`/`rta_type`. Note that CEPII codes `sibling_ever = 0` for
KAZ–RUS because Russia was the hegemon itself; use `col_dep_ever` for that pair.

## io/

BNS symmetric input-output tables («Затраты - Выпуск», 68 products, sheets 1–10 incl. the
direct-requirements matrix A and the Leontief inverse) and supply-use tables («Ресурсы -
Использование», 125 products × 72 industries, sheets 1–8), 2021–2024, one long gzip CSV per
kind and year (`table, row_no, row_code, row_name, col_no, col_code, col_name, value`;
thousand KZT, coefficients in tables 9–10). Built by `scripts/build_io_tables.py`, which
also writes `editions.csv` (element id, publication date, the L = (I − A)⁻¹ check). BNS's A is
flows divided by total resources at basic prices (output + imports), not by output.

## nf_receipts_kgd_history.csv

National Fund receipts by tax, thousand KZT, year to date (`indicator_id, date, value_thousand_kzt,
source_url`; 1 433 rows, 2002–2025 without 2005–2006): KGD «Динамика поступлений налогов и платежей
в Национальный фонд» (https://kgd.gov.kz/ru/section/dinamika-postupleniy-nalogov-i-platezhey-v-nacionalnyy-fond),
one by-tax workbook per year, read by row label; a workbook is kept only if its tax rows add up to
«ИТОГО по налоговым поступлениям» in every month (2005 does not; there is no 2006 file). Loaded once
on 2026-09-26 by `scripts/load_nf_receipts_history.py` (the page has not been updated since May 2025);
the workbooks are archived as `data/raw/minfin/minfin_nf_receipts_history_kgd_<year>_2026-09-26.*`.
The Minfin fetcher prepends the months before 2018 to the seven `NF_*_YTD` tax series while KGD
equals Minfin in every December both cover (2018–2024: all seven taxes, to the thousand tenge).

## bns_cpi_history.csv

The national CPI (all goods and services) before Taldau, as BNS printed it (`date, measure,
value, source_url, source_note`; dates are the first day of the month; 838 rows): `mom`
(previous month = 100) and `ytd` (December of the previous year = 100) 1991-01 – 2010-12,
`yoy` (same month of the previous year = 100) 1994-01 – 2010-12 (nothing year on year was
published for 1991–1993). Sources, all on stat.gov.kz, in order of preference: «Цены в
Казахстане за 1991-2021 годы» (element 17216, docx, tables 1.1 Dec/Dec and 1.3 m/m), «Цены в
Казахстане в 1991-2000 гг.» (element 21933, pdf pp. 39–45: m/m, since December, and from 1994
year on year) and the monthly editions of «Индекс потребительских цен в Республике Казахстан»
(publication 166775, May 1999 – December 2010: html to June 2004, xls after). Every month two
or three of them print is the same number in all of them; `source_note` names the others.
The 154 rows from 2011-01 (every docx m/m month to 2021-12, and the Decembers of `ytd`/`yoy`)
are the overlap with Taldau 703076: the BNS fetcher prepends only the months before 2011 to
CPI, CPI_YTD and CPI_YOY and stops if any overlap month differs (`splice_cpi_history` in
`scripts/fetchers/bns.py`). Built by `scripts/load_cpi_history.py` (2026-09-28; the 142
archives are cached outside the repository, not in `data/raw`); the identities between the
three measures are checked there and in `tests/test_cpi_history.py`. December on December:
1991 247.1, 1992 3060.8, 1993 2265.0, 1994 1258.3, 1995 160.3, 1996 128.7, 1997 111.2,
1998 101.9, 1999 117.8, 2000 109.8.
