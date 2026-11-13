# Update Log

Recent entries, oldest first; append new ones at the end. Entries from 2026-08-30 to «2026-09-27 — the quasi-fiscal block before 2022: budget lending by recipient, holdings' balance sheets, NBK surveys from 1997» are in docs/UPDATE_LOG_ARCHIVE.md in the
repository (not synced into the Claude Project). When this file grows past ~60 KB, move the oldest entries there.

## 2026-09-28 — official exchange rates back to the tenge's introduction (November 1993)

EXCHANGE_RATE, EXCHANGE_RATE_RUB (from 1993-11-18), EXCHANGE_RATE_CNY (from 1996-02-05) and
EXCHANGE_RATE_EUR (from 1999-01-04) now reach back before the NBK daily report, whose first usable
day is 1999-11-17. The history comes from the NBK archive workbook «Архив официальных курсов валют
с 1993 по 1999» (nationalbank.kz/file/download/22756): effective-date rows turned into the rate in
force on each weekday, the series' existing definition. The archive is re-read on every run and must
equal the report on all 33 weekdays of 1999-11-17..12-31 (0 differences), or the fetcher stops. USD at
year-end: 6.31 (1993), 54.26, 63.95, 73.30, 75.55, 83.80 (1998), 138.20 (1999), all equal to IMF IFS;
the float of April 1999 runs 87.50 (2 April) -> 100.00 (5 April) -> 118.00 (7 April). Monthly means
match the NBK's published averages within 0.05 except 1994-01, 1997-01 and 1998-01. The rouble is in
new (post-1998) roubles throughout: the archive's quote per 1000 roubles before 1998 is one new rouble
(13.00 on both sides of 1 January 1998). No euro before 1999: the archive's ECU and Deutsche mark are
not spliced. Rates were set once or twice a week before April 1999, so the early daily series is a
step function. Tests: tests/test_fx_history.py (14).

## 2026-09-28 — CIS Stat: the CIS countries since 1991, Kazakhstan migration before 2000

New fetcher `scripts/fetchers/cisstat.py` (agency `cisstat`) reads the JSON service of the CIS Stat
database «Статистика СНГ» (new.cisstat.org/consstat, no key) into four item-level datasets whose
`region` is the reporting country's ISO3 code: CIS_GDP_VOLUME_INDEX (fact 714662, real GDP % of the
previous year, 11 countries 1991-2025), CIS_CPI (fact 43370, December on December and annual average
as separate items, by consumer group), CIS_POPULATION (facts 44176/44177, 1 January and annual
average) and CIS_MIGRATION (facts 4650866/4679599 by flow, 44243/44245 by partner country from 2016;
net = arrivals - departures). Kazakhstan's GDP index equals BNS GDP_REAL in every year 1991-2025
(1991 89.0, 1992 94.7, 1993 90.8) and its Dec/Dec CPI equals BNS CPI_YOY in 2011-2025; the 1990s CPI
(1994: average 1 877%, Dec/Dec 1 158%) differs from the IMF's (1 402% / 855%). MIGRATION_ARRIVALS and
MIGRATION_DEPARTURES now start in 1991 (1994: 70 389 arrived, 477 068 left) via `gaps_filled_from`
CIS_MIGRATION; the sources agree on 2000-2025 except 2008 (CIS Stat 46 404 / 45 287, BNS 46 113 /
44 813), which `fill_gaps` now skips through the new `known_differences` key, keeping BNS's value.
Hard checks: header columns, every country/flow/group/base/sex/area label mapped, numeric values, no
conflicting duplicates, Kazakhstan present 1991-1999, and for Kazakhstan the partner sums and the two
migration facts' totals. Tests: tests/test_cisstat.py (19, no network).

## 2026-09-28 — national CPI back to 1991

CPI and CPI_YTD now start in January 1991 and CPI_YOY in January 1994 (BNS published no
year-on-year index for 1991-1993); before, all three started with Taldau in January 2011. The
240 (204) earlier months are BNS's own printed figures from three stat.gov.kz sources — «Цены в
Казахстане за 1991-2021 годы» (element 17216, docx: Dec/Dec 1991-2021, m/m 1992-2021), «Цены в
Казахстане в 1991-2000 гг.» (element 21933, pdf: m/m, since December and, from 1994, y/y) and the
140 monthly editions of publication 166775 (May 1999 – December 2010) — loaded by
`scripts/load_cpi_history.py` into `data/reference/bns_cpi_history.csv`. Every month two sources
print is the same number in both (228 of 240 m/m months have a second source; the editions equal
CPI_DETAIL on all 234 values 2004-07…2010-12), and the three measures satisfy the CPI identities
within rounding (chain of m/m = since-December; y/y = product of 12 m/m = ytd(t)/ytd(t−12)·Dec/Dec).
One printed inconsistency is kept as published: February 1993 m/m 131.9 where the since-December
figures imply 131.7. The fetcher prepends only months before 2011 and stops if the file differs
from Taldau on any of the 132 m/m months and 11 Decembers of 2011-2021 the docx repeats (all equal).
December/December: 1991 247.1, 1992 3060.8, 1993 2265.0, 1994 1258.3, 1995 160.3, 1996 128.7,
1997 111.2, 1998 101.9, 1999 117.8, 2000 109.8. Tests: tests/test_cpi_history.py (25).
The analysis and model layers keep their CPI sample from 2011: `model_data/spec.yaml` `cpi` has
`from: "2011-01-01"` (now applied before chaining, so the level is still 100 in 2011-01), and the CPI
targets of `scripts/analysis/seasonal_targets.py` / `forecast_targets.py` carry `sample_start`
(new, passed to `timeseries.prepare_level`). Move the start to 1996 only after checking the X-13
diagnostics; 1991-1995 hold m/m values up to 312.3 (source issue cpi_1991_1995_hyperinflation).
model_data's `usdkzt` now starts in 1994-01 (the NBK archive); 1999-11 is 139.63, the NBK's
published average, instead of 138.80 from the report's last 11 weekdays.

## 2026-09-28 — CPI groups (food, non-food, paid services) back to 1991 (user: «Сделай все три пункта»)

CPI_FOOD, CPI_NONFOOD and CPI_SERVICES (m/m) now start in January 1991 and their _YOY in January
1994, like the headline; before, all six started with Taldau in January 2011. The 240 (204) earlier
months come from the same three BNS publications, now read per group: «Цены в Казахстане за
1991-2021 годы» (element 17216, docx: tables 1.4-1.6 m/m 1992-2021 and the group columns of table
1.1 Dec/Dec), «Цены в Казахстане в 1991-2000 гг.» (element 21933, pdf columns 2-4) and the 140
monthly editions of publication 166775 (1999-05…2010-12; html rows «Продукты питания, напитки и
табачные изделия» / «Непродовольственные товары» / «Платные услуги», xls through the CPI_DETAIL
parser). `data/reference/bns_cpi_history.csv` gained an `item` column (TOTAL for the 838 headline
rows, values unchanged; 3 352 rows). Per group 228 of 240 m/m months have a second source, and
every month two sources print agrees except food June 2004: the docx and the edition's own m/m
table print 100.0, its summary row «Продукты питания, напитки и табачные изделия» 99.9 — kept as
100.0 and listed in the loader's PRINTED_DIFFERENCES (source issue cpi_food_2004_06_mom_two_prints).
The xls editions equal CPI_DETAIL on all 936 values 2004-07…2010-12. The identities hold within
rounding for every group with no slack (chain of m/m vs since-December at most 0.38 pp from 1995,
y/y vs 12 m/m at most 0.40 pp from 1996). The fetcher stops if the file differs from Taldau on any
of the 132 m/m months or 11 Decembers of 2011-2021 per group (all equal); no stored 2011-2026 value
changed. December/December, food: 1992 2108.3, 1993 2297.1, 1994 1155.7, 1995 158.7, 1999 120.6;
non-food: 1992 3897.8, 1993 1795.6, 1994 1159.9, 1995 133.5, 1999 119.8; paid services: 1992
3019.7, 1993 4143.4, 1994 2522.6, 1995 258.0, 1996 239.3, 1999 109.9. model_data keeps cpi_food /
cpi_nonfood / cpi_services from 2011 (`from: "2011-01-01"` in spec.yaml; the panels are unchanged).
CPI_UTILITIES and CPI_REGULATED_UTILITIES still start in 2011. Tests: tests/test_cpi_history.py (54).

The official quarterly accounts for 2026 Q2 (BNS, element 283161, due 28.10.2026) are picked up by the
daily update_all run; a check is scheduled for 29.10.2026 to compare them with the discrete estimate
(GVA_VOLUME_INDEX_BY_SECTION_DISCRETE: GDP 105.2) and rebuild model_data.

## 2026-09-28 — partner-currency rates back to 1993, import-weighted NEER from 1995

EXCHANGE_RATES_OFFICIAL_MONTHLY (18 currencies, KZT per one current unit, weekday means) now starts in
1993-11 instead of 2010-01. 1999-11..2009-12 come from the NBK daily report (read once in 10-year windows,
first usable day 1999-11-17, malformed October 1999 rows dropped); before the report, the NBK archive
«Архив официальных курсов валют с 1993 по 1999» (rate in force on each weekday) for the 11 currencies it
carries, equal to the report on every common weekday of 1999-11-17..12-31 for USD, EUR, CNY, RUB, GBP, CHF,
JPY and KGS (enforced). Printed figures below 1.0 are dropped in both sources, so TRY runs 1994-05..1996-02
then from 2005, UZS and BYN have 1990s fragments then start in 2014-02; KRW from 2000-05, AED 2001-07, PLN
2004-09, CZK 2009-03, EUR 1999-01, CNY 1996-02; INR, TJS and AZN still from 2011-2014. Redenominations are
listed in nbk_fx.REDENOMINATIONS and checked against the data: RUB 1998 (archive already per new rouble,
13.00 on both sides), TRY 2005 (TRL x10^6), BYN 2000 and 2016 (BYB x10^7; BYR x10^4 up to Friday 1 July 2016
inclusive -- the report's rate in force that day is still per 100 BYR, first BYN quote 2 July, step x10 162),
UZS 1994 (archive per 1000 coupons = one sum); any other step above x8 within a month stops the fetcher.
This corrects BYN 2016-07 (163.00 -> 171.00; NEER 2016-07 by -0.1, recorded in the revisions files); every
other stored month since 2010 is unchanged. USD/EUR/CNY/RUB equal the monthly means of the daily
EXCHANGE_RATE* series in every month. Monthly USD 1999-12 138.22, 2005-01 130.10, 2009-12 148.70; RUB 5.12,
4.66, 4.97; EUR 143.15, 171.38, 217.64; TRY 2005-01 96.07, 2009-12 98.70. IMPORTS_BY_PARTNER_COMTRADE now
starts in 1995 (Kazakhstan's first Comtrade year), so NEER_IMPORT_WEIGHTED starts in 1995-12 (NEER_TOTAL,
2020 = 100: 93.9; 1998-09 158.8 after the rouble crash, 1999-03 266.4, 1999-06 179.1 after the float) and
NEER_IMPORT_WEIGHTS in 1996; its monthly changes correlate 0.84 with the NBK's own NEER in 1996-2009. Before
1999 the euro-area partners have no rate (coverage 59-77%; 80-92% from 2000); CONSUMER 2000 is a partial
Comtrade conversion (36 mln USD) and is replaced by the 1999 structure; 1995-1999 CONSUMER includes passenger
cars (H0 conversion). Three archive typos (CHF 17.04.1995, 09.11.1998; KGS 09.08.1999) are kept as printed and
registered in source_issues. Tests: tests/test_fx_monthly_history.py (15).

## 2026-09-28 — weekend rows removed from the daily official USD rate (user: «Почисти записи за выходные в дневном ряде USD»)

EXCHANGE_RATE held four weekend rows (2026-08-22/23 at 456.88 and 2026-08-29/30 at 464.77, Friday's
rate repeated) written by an earlier fetcher; the fetch kept them because only the fresh report rows
were filtered to weekdays, not the stored history they were merged with. `nbk._fetch_official_rate`
now keeps weekdays only after the merge, for all four official-rate series (EUR, CNY and RUB had no
weekend rows). The August 2026 mean of the daily series moves from 463.96 to 464.55, equal to
EXCHANGE_RATES_OFFICIAL_MONTHLY USD (464.551429); model_data usdkzt 2026-08 likewise (usdkzt_yoy
-13.91 -> -13.80). Test: tests/test_fx_history.py::test_fetcher_drops_weekend_rows_already_stored.

## 2026-10-08 — the daily run's push now survives a GitHub outage (user: «почему прогон сломался?»)

The 2026-10-07 run collected everything (12:11-15:09 UTC, a commit of 1,740 files) and then lost it:
`git push` stopped in git-lfs's pre-push lock check ("Fatal error: Unable to verify locks"), which fell
into GitHub's 15:06-15:16 UTC outage of git operations and Actions (githubstatus.com). The runner image
and git were the same as in the green 2026-10-06 run. The repository never uses LFS file locking, so
`update.yml` now sets `lfs.locksverify false` (git-lfs then sends only the objects/batch upload request;
checked with GIT_TRACE), and retries pull --rebase + push after pauses of 1, 3, 10 and 20 minutes
(5 attempts over ~34 minutes). A rebase conflict still fails at once. The step was run against a local
remote for four cases: push failing twice then succeeding, a conflict, push failing every time, no
changes. The next run refetches every source; only the raw snapshots dated 2026-10-07 are lost, and
that day's logs/ and reports/ are in the run's diagnostics artifact until 2027-01-05.

## 2026-10-13 — the daily run unblocked; NBK form 324 found stale since 2023 (user: «проверь пайплайн, прогон сегодня не прошел»)

The 2026-10-13 run fetched everything and then withheld it: one test failed,
test_quarterly_current_account_sums_to_the_imf_calendar_year, 2023: four NBK quarters -9 315.5 mln USD
against the IMF's -8 284.3. The October 2026 WEO (country update 24.09.2026) had revised Kazakhstan's
2023-2025 current account; the NBK revised it too, in its workbook «Платежный баланс Республики Казахстан
за период с 2000 года по 1 полугодие 2026 года» (30.09.2026: 2023 -8 284.4, 2024 -6 819.4, 2025
-13 093.5), but its open-data formId=324, which feeds CURRENT_ACCOUNT_BALANCE and the four
BOP_* current-account lines, has not changed since 2026-09-26 and still differs from the workbook in every
quarter from 2023-Q1 (2026-Q1: -2 008.0 vs -796.1); it also lacks 2025-Q3 (-3 688.6) and 2026-Q2
(+3 171.0). 2000-2022 are equal in all three sources. The test now checks exact equality only on the
years before the IMF's last three actual years (2000-2022 today, 23 years; it still fails all 23 under
the source's own unshifted dating), since the two publications take revisions up at different times
(the WEO's 2024, -6 763.9, matches neither NBK vintage). The stale vintage is registered in
config/source_issues.yaml (nbk_bop_form_324_stale_2023_2026) and shows in DATA_CATALOG. No number was
changed. The run's failure was reproduced locally with the refetched IMF series, and the new test passes on it.

## 2026-10-16 — balance of payments from NBK form 481, with 324 filling in (user: «почему упал прогон»)

The runs of 2026-10-15 and 10-16 fetched everything and committed nothing: CURRENT_ACCOUNT_BALANCE
came out with 25-26 quarters instead of 104, so test_quarterly_current_account_sums_to_the_imf_calendar_year
(no quarters for 2000) and test_imf_current_account_is_nbks (25 < 100 shared quarters) failed. The NBK
had refreshed both of its balance-of-payments forms, unevenly. formId=481 (2000 on) now carries its
revision of 30.09.2026 in full: on 2026-10-16 all five current-account lines, 106 quarters 2000-Q1 to
2026-Q2, one amount each, every one equal to the NBK's workbook «Платежный баланс Республики Казахстан за
период с 2000 года по 1 полугодие 2026 года». formId=324 (2020 on) took the revision from 2024 and
added 2025-Q3 and 2026-Q2, but still carries the unrevised 2023 (current account Q1 -1 632.7 against
-1 405.2). The fetcher spliced 481 in only for the quarters before 2020 and only while 481 equalled 324
on every shared quarter, so the 2023 disagreement dropped 2000-2019 from all five series.

481 had been the more complete form all along (2025-Q3 was in it on 2026-09-26 and reached 324 on
2026-10-16; 2026-Q2 reached 481 on 10-14, 324 on 10-16), and the two-amounts-per-quarter defect that
once disqualified it is gone from the 2026-10-16 download. nbk._bop_merge now takes 481's amount for
every quarter where it has exactly one and 324's otherwise (where the two agree to 1e-6, 324's
value, which prints a seventh decimal, so only genuinely revised quarters enter the revisions files);
it raises, keeping the stored series, when
481 is empty, disagrees with 324 on the first four quarters both carry (2020: a wrong row, not a
revision), gives two amounts where 324 has none, or breaks goods + services + primary + secondary =
current account. The manifest note names the quarters where 324 differs. test_imf_current_account_is_nbks
no longer requires the last two shared quarters to agree: the IMF's quarterly BOP has the NBK's 2023
revision but not its 2024-2026 one (2026-Q1 -2 008.0 against -796.1); differences must now lie in the
last three years and NBK must reach the IMF's latest quarter. config/source_issues.yaml drops
nbk_bop_form_324_stale_2023_2026 (the series no longer uses 324's 2023). Run locally on the day's
download: all five series 106 quarters 2000-Q1 to 2026-Q2, identity holding in all 106, current
account 2023 -8 284.4, 2024 -6 819.4, 2025 -13 093.5, 2026-H1 +2 374.9 (equal to the NBK workbook);
the revisions files record 2023-Q1..2026-Q1 only; 830 tests pass on that data and on main's.

## 2026-10-19 — the IIP comparison with the IMF allows the revision window (user: «почему упал прогнон»)

The runs of 2026-10-18 and 10-19 committed nothing: test_imf_net_iip_is_nbks_one_day_earlier
failed. The IMF's quarterly IIP for Kazakhstan was updated on 2026-10-18: it now runs to end-2026-Q2
and revises net IIP from end-2024-Q1 on (-12 to -36 mln USD through end-2025-Q3; end-2025 -35 639.2
against the NBK's -34 458.7, end-2026-Q1 -39 373.9 against -38 741.7). NBK open-data formId=309, the
source of IIP_NET/IIP_ASSETS/IIP_LIABILITIES, had not changed: it still ends with the 1 April 2026
position and carries none of the revision. The test demanded equality on every
shared quarter. Like the two current-account comparisons fixed on 2026-10-13 and 10-16, it now
demands it on the settled quarters, those before the last three years of the shared range (8
quarters 2021-2022 today; the NBK series starts in 2021), and tolerates differences inside them.
The old test fails on the refreshed IMF series exactly as in CI; the new one passes on it and on
main's data. NBK's own workbook of 30.09.2026
(nationalbank.kz/file/download/136322) has the IMF's figures (end-2025 -35 639.21, end-2026-Q1
-39 373.94); forms 309, 320 and 321 all still end at 1 April 2026 without the revision, so
config/source_issues.yaml registers nbk_iip_forms_stale_2024_2026 (IIP_NET, IIP_ASSETS, IIP_LIABILITIES).

## 2026-10-19 — comparisons between publications no longer block the daily commit (user: «ок, 2»)

Five daily runs between 2026-10-13 and 10-19 committed nothing for the same reason: a test comparing
two publications failed because one had taken up the NBK's revision of 30.09.2026 and the other had
not yet (the WEO against NBK form 324, form 481 against 324, the IMF's quarterly IIP against NBK form
309). Each was a true statement about the sources, not a fault in the pipeline, yet it withheld
every series for the day. Tests that compare two publications revising on their own schedules are now
marked `cross_source` (tests/conftest.py registers the marker): the current account against the WEO
and against the IMF's quarterly BOP, net IIP against the IMF, WDI GDP against the WEO, NBK ROA/ROE and
capital adequacy against the IMF FSIs and the FSIs' coverage, the BNS CPI publication against the
Taldau series, and loans to business by creditor against form 445's series. The STB loan test was
split: its components-add-up-to-the-total part still blocks; the match with form 445's household
loans is cross-source. update_all.run_tests runs the two groups apart (pytest -m "not cross_source",
then -m cross_source): only the first decides the commit; each failure of the second is a GitHub
Actions warning, a job-summary line and a section of the update report («Cross-source checks failed:
N»), with pytest's message in full (COLUMNS=400). Checked on the real data with one settled IIP
quarter set wrong: 816 blocking tests pass, the IIP comparison fails and is reported as
`AssertionError: ['2021-04-01']`. 17 of 833 test cases are cross-source.

## 2026-10-20 — the resource-use check pinned on a final print (user: «прогон опять упал»)

The 2026-10-20 run committed nothing: test_resource_use_data_matches_the_publication (blocking: it
checks the parse of one BNS publication, not a comparison of two) expected coal exports January–July
2026 of 17 833.073 kt and found 17 771.911. BNS published the January–August 2026 edition of
«Ресурсы и использование…» (bns_resource_use_202608_2026-10-20.xlsx); like every monthly edition it
carries the cumulative figures for t, t-1 and t-12, and its «январь-июль 2026г.» column revises
January–July: coal exports -61.2 kt, coal resources 63 474.693 -> 63 475.592, wheat exports
4 947 050.527 -> 4 947 361.027 t. RESOURCE_USE_YTD keeps the latest print by design, so the data was
right and the test's assumption was not. It now pins January–July 2025 (coal production 63 330.303,
coal exports 16 428.615 kt, wheat exports 4 384 954.666 t), printed for the last time in the
«январь-июль 2025г.» column of the January–July 2026 edition and absent from the August one. The old
test fails on the refreshed dataset exactly as in CI; the new one passes on it and on main's data.

## 2026-10-29 — quarterly national accounts for 2026 Q2: not yet published; BNS withdrew its production release (scheduled check from «Сделай все три пункта», point 3)

The expenditure QNA (element 283161, the source of model_data's gdp, gdp_sa, gdp_nsa) was due on 28.10.2026;
on 29.10.2026 09:30 UTC its file is still the one of 28.07.2026, ending at 2026 Q1. The production QNA (283162)
carried 2026 Q1-Q2 from 16-17.10.2026 and was replaced on 20.10.2026 by a file ending at 2025 Q4, so the run of
2026-10-21 dropped 2026 from the seven QNA_GVA_* datasets (1 716 -> 1 664 records each for the level tables).
The withdrawn release had GDP Q2 2026 at 113.8 % of Q2 2025 in 2010 prices, H1 109.5 %, seasonally adjusted
Q2/Q1 +7.6 %; BNS's cumulative table 4439/4440 has GDP Q1 103.0 %, H1 104.1 %, Q2 alone 105.2 %
(GVA_VOLUME_INDEX_BY_SECTION_DISCRETE). Nominal Q2 growth agrees (+18.9 % QNA, +20.1 % table 4439); the
release's implied deflator, about 104.5 %, does not fit CPI 110.4 % or industrial producer prices 111-117 % y/y,
so the 13.8 % was most likely a deflation error, and the withdrawal is consistent with that. The income QNA
(283160, nominal only) keeps Q2 2026 from 16.10.2026: GDP 43 553.8 bn KZT, in line with the 2025 gap between the
QNA quarters and table 4439's. Registered as source issue qna_production_2026_withdrawn (caveat); the
GVA_VOLUME_INDEX_BY_SECTION_DISCRETE note now states the QNA's status. No data or model_data change: the
expenditure QNA has no Q2 to add. The check is re-armed.

## 2026-11-06 — quarterly national accounts for 2026 Q2 (expenditure, published 04.11.2026); «2025*» parse fix (scheduled check from «Сделай все три пункта», point 3)

BNS published element 283161 (GDP by expenditure, SA) with 2026 Q2 on 04.11.2026, a week after the 28.10 date.
The new file heads 2025 «2025*» (preliminary); YEAR_CELL did not read the asterisk, so the daily run of
2026-11-04 silently dropped all four 2025 quarters from the five non-SA QNA_GDP_EXPENDITURE* tables (2024 Q4 ->
2026 Q1, logged only as 457-day gap warnings). YEAR_CELL now accepts trailing asterisks, and
bns_dims.year_period_columns raises when the year cells are not consecutive, so an unreadable year can no longer
vanish (tests/test_qna.py, both fail without the fix). Reloaded: 66 quarters 2010 Q1 - 2026 Q2 again.

GDP, % of the same quarter a year earlier (QNA vs table 4439/4440 basis, GVA_VOLUME_INDEX_BY_SECTION_DISCRETE):
Q1 2026 101.4 (revised from 104.1) vs 103.0; Q2 108.2 vs 105.2; H1 105.1 vs 104.1. Seasonally adjusted, 2010
prices: Q1 -1.2 % q/q, Q2 +6.5 %. Nominal Q2 +17.0 %, implied Q2 deflator 108.2 % (CPI 110.4 %). The QNA moves
growth from Q1 into Q2 against the operational tables; over the half-year they differ by 1 pp. Q2 by component:
final consumption 99.9 (households 100.1), gross fixed capital formation 103.9, exports 106.0, imports 95.4 --
the quarter's growth is net exports. The production QNA (283162) still ends at 2025 Q4
(qna_production_2026_withdrawn stays). model_data rebuilt (first time since 2026-09-28): gdp/gdp_sa through
2026 Q2.

## 2026-11-07 — four datasets failing since mid-October fixed; natural-capital workflow limited to main

Four item-level datasets had kept their previous data in every daily run since mid-October (the run passes, the
dataset is reported as a structural change):

- **GRAIN_SOWN_AREA_BY_REGION** (since 22.10). On 21.10.2026 BNS reshuffled the crop tables of «Сельское, лесное
  и рыбное хозяйство → Динамические таблицы»: element 8154 is now «Валовый сбор основных с/х культур» (it was the
  sown area), 8159 «Уточненная посевная площадь», 8158 «Урожайность»; each workbook has one sheet per crop
  («зерновых и бобовых культур», «масличные», «овощей» …). The old harvest and yield elements 8160 and 8166 are no
  longer on the page but still serve their September files, so GRAIN_HARVEST_BY_REGION and GRAIN_YIELD_BY_REGION
  did not fail, they were reading files BNS no longer lists. All three now read 8154/8159/8158, sheet «зерновых и
  бобовых культур». The yield sheet has no «Всего» row over the first block, so group_blocks takes a new
  `initial_group` (TOTAL there). The values are identical to the stored ones (702 / 706 / 701 points, 2004-2025);
  only the source changes.
- **WB_COMMODITY_PRICE_FORECASTS, WB_COMMODITY_INDEX_FORECASTS** (since 28.10). The October 2026 CMO renamed the
  sheet 'Forecast' to 'Forecast vs CMO' (new `sheet_aliases`), added footnote numbers after some labels («Energy 2»,
  stripped in parse_forecasts) and spells out «United States» (dictionary regexes). Its third 'f' block holds the
  April forecasts; the parser already takes the first 'f' column per year. The April 2026 forecasts are replaced by
  October's and 2028 is added: Brent 91 / 79 / 70 $/bbl for 2026 / 2027 / 2028 (April: 86 / 70); the total index
  121.1 / 112.6 / 102.7 (April 113.7 / 99.8). 46 prices and 16 indices, as before.
- **LOANS_BY_CREDITOR_TYPE** (since 17.10). Form 445 renamed «other public sector» to «Other public sector
  entities» over the whole history; the 104 stored OPS values are unchanged. Both names map to OPS; four new
  values for 2026-09.

Tests: tests/test_dims.py (initial_group, the grain element ids), tests/test_wb_eia.py (October 2026 layout,
pick_sheet, «United States» labels), tests/test_policy_gaps.py (both creditor names).

.github/workflows/natural-capital.yml: the push trigger is limited to main. On 2026-11-07 a push of
claude/confident-dijkstra-kk47n5 (a fast-forward to main, so carrying the fetcher's changes) started a run that
committed its reports to that branch, which then diverged from main (PR #26).

## 2026-11-07 — 22 item-level datasets: housing prices, loans by industry and purpose, NBK operations, gross FDI, price chains, forecasts (the «11 пунктов» request)

Item-level datasets 243 -> 265 (config/dims.yaml). New fetchers: fetchers/nbk_cube.py (sums of the NBK's fully
disaggregated open-data forms), fetchers/nbk_operations.py (interventions, open position, deposit auctions),
fetchers/manual_vintages.py (hand-kept forecast vintages); taldau_dims.fetch_regional gained per-item index_id,
quarterly/annual dating, `flat_regions` + `region_terms` (city lists) and `segments` (an index whose dimensions changed).

1. **Housing prices** (Taldau 703083 / 703116, monthly, by city): HOUSING_PRICE_INDEX_BY_CITY (new, resale, rent; m/m and
   y/y), HOUSING_PRICE_M2_BY_CITY (KZT per m2). National 2026-08: new +0.6 % m/m, +13.1 % y/y; 625 435 KZT/m2.
   sources.yaml had the index as frozen at 2020: only its quarterly period is.
2. **Loans by industry and purpose, mortgages** (NBK forms 488 stock / 493 issued, monthly from 2023-01): LOANS_STOCK_BY_INDUSTRY,
   LOANS_STOCK_BY_PURPOSE, LOANS_ISSUED_BY_INDUSTRY, LOANS_ISSUED_BY_PURPOSE. Form 488's second-tier banks at 2026-09-01,
   42 825 457.5 mln KZT, equal BANK_LOANS_STB_TOTAL to the tenge. Housing loans to individuals: stock 8 195.6 bn KZT
   (2026-09-01), issued 265.1 bn in August 2026. Form 47 (LOAN_PORTFOLIO_QUALITY): debt by days past due and provisions.
3. **NBK operations**: NBK_FX_INTERVENTIONS (net, mln USD, 1996-01 on; gold-mirroring FX sales from 2025-01),
   NBK_OPEN_POSITION (balance and instruments, monthly average and end of month, 2020-01 on; 2026-11-05 balance
   -8 705.65 bn KZT), NBK_DEPOSIT_AUCTIONS (monthly volume, number, weighted yield, 2019-02 on),
   GOV_SECURITIES_OUTSTANDING_BY_TYPE (form 430, incl. NBK notes; 454 129 mln at 2025-01-01 = the open position's notes).
4. **Gross FDI inflow** (forms 286 / 287, quarterly 2005 Q1 on): by industry and by country; totals equal in all 86 quarters
   (2024 17.9 bn USD, 2025 20.4 bn).
5. **Wages by region**: WAGE_BY_REGION_QUARTERLY (Taldau 702972, 2016 Q1 on; 2026 Q2 national 486 386, Astana 647 920 KZT).
6. **Agricultural producer prices**: AGRI_PRODUCER_PRICE_INDEX_BY_REGION (Taldau 703025; Taldau has no 2026-08).
7. **Construction prices and tariffs**: CONSTRUCTION_PRICE_INDEX_BY_REGION (total, works, machinery), FREIGHT_TARIFF_INDEX_BY_REGION
   (two Taldau segments stitched at 2026-01), COMMUNICATION_TARIFF_INDEX.
8. **Legal entities**: LEGAL_ENTITIES_BY_REGION (registered / active, 2011-01 on; 559 558 / 451 479 on 1 October 2026).
9. **Household debt**: IMF_FSI_HOUSEHOLDS (debt/GDP 15.3 %, debt/income 80.9 %, debt service 5.5 %, 2023 Q4; the IMF series
   stops in 2024 Q1); current household lending by purpose and overdue from forms 488 / 47 above. Not machine-readable:
   the Financial Stability Report, First Credit Bureau dashboards, number of borrowers.
10. **NBK forecasts**: config/nbk_forecast_rounds.yaml -> NBK_FORECAST_ROUNDS, 16 rounds Dec-2022 … Aug-2026 (GDP and CPI
    ranges, Brent); every number found in its report's text.
11. **Government forecast (ПСЭР)**: config/gov_forecast_vintages.yaml -> GOV_MACRO_FORECAST_VINTAGES, 27 vintages 2015-2026
    (GDP, growth, implied exchange rate, Brent, CPI band, oil output); the implied rate comes out round in every forecast
    year, which checks the transcription. Both YAML files are maintained by hand: a new NBK round four times a year, a
    new Government vintage each August (gov.kz misfiles them; the 2027-2029 forecast is under record 1060939).

Big forms are fetched in full once and then from 6 months back (API startDate); their pages are archived gzipped.
Tests: tests/test_new_sources_2026_11.py (12 + 2 cross-source), tests/test_dims.py config checks.

## 2026-11-09 — the second batch of missing indicators: loan rates by purpose, securities market, vacancies, investment by source, KASE, KMG, FAO, UN population, transport by mode, consumer sentiment (the «сделай все» request)

Item-level datasets 265 -> 282. New fetchers: fetchers/kase_dims.py (KASE indices from the TradingView feed, corporate
bond volumes from the news API), fetchers/kmg.py (the KazMunayGas quarterly databook), fetchers/world_misc.py (FAO, UN WPP);
nbk_cube gained "" codes (a field contributing nothing to the item), `distinct` rates datasets and `field_aliases`;
bns_dims a `year_rows_months` layout; nbk_expectations derives the consumer sentiment index.

1. **Oil by project**: KMG_OIL_PRODUCTION_AND_TRANSPORT (KMG databook, 2015 Q1 on): production by asset in KMG's share and
   Tengiz / Kashagan / Karachaganak at 100 % from the shares (2025: 39.0 / 17.9 / 10.9 mln t); transport by КазТрансОйл,
   the Kazakhstan-China pipeline, МунайТас and the CPC; export / transit / domestic shares. Field-level monthly output
   (Ministry of Energy briefings, gov.kz answers 403 from the sandbox) and crude exports by route (KazTransOil press
   texts, CPC annual releases) are not machine-readable and stay out.
2. **Business tendency surveys**: BNS discontinued them after 2024 Q4 (last release 15.01.2025); not connected. The NBK
   enterprise survey stays the live source.
3. **Labour market, high frequency**: VACANCIES_BY_REGION_QUARTERLY (Taldau 703008 vacancies, 702998 hires),
   EMPLOYEE_SEPARATIONS_BY_REGION_QUARTERLY (703003), REGISTERED_UNEMPLOYED_SHARE (monthly, national),
   REGISTERED_UNEMPLOYED (annual). Wage arrears: no live BNS series since 2016.
4. **Government securities**: GOV_SECURITIES_PRIMARY_AUCTIONS (form 17) and GOV_SECURITIES_SECONDARY_MARKET (form 16),
   monthly volumes by instrument and term from 2022-12 (NBK notes 942 107 mln KZT placed in August 2026).
5. **Loan rates**: LOAN_RATES_BY_PURPOSE (form 27, 2022 on; mortgage 10.69 %, consumer 22.29 % in August 2026; by
   enterprise size and maturity), LOAN_RATES_BY_MATURITY (form 486, 1997 on, six maturity buckets).
6. **KASE**: KASE_INDICES (INDEX_KASE from 2000, KASE_TR, KASE_BMY / KASE_BMC corporate bond indices from 2017, MM_INDEX,
   CAPBILLS_KZT; monthly average and end of month), KASE_CORPORATE_BOND_VOLUMES (primary / secondary, 2019 on).
7. **Trade in services**: by type already in IMF_BOP_QUARTERLY (CD_T.S*, DB_T.S*); NBK forms 447 / 448 (by country) are
   empty on the API. Nothing added.
8. **Tax arrears**: kgd.gov.kz is gone; the new portal has only a semi-annual xlsx with the national total (1.07 trn KZT at
   01.01.2026, 1.18 trn at 01.07.2026) and no tax or regional split. Not connected; Minfin remains the source for receipts.
9. **Investment by source of financing**: INVESTMENT_BY_SOURCE_BY_REGION_YTD (Taldau 701827, dictionary 459, 2018-01 on,
   by region) and INVESTMENT_BY_SOURCE_BY_REGION (annual 2003-2025). The five sources add up to the total; the GDP model's
   hand-entered budget investment (manual_inputs iok_budget_private_split) is the January first release, the annual
   revised figures are 2.7 % (2024) and 1.5 % (2025) higher.
10. **FAO_FOOD_PRICE_INDEX**: nominal FFPI and five sub-indices, 1990-01 on (September 2026 135.6).
11. **UN_WPP_POPULATION**: WPP 2024 for Kazakhstan, every variant, sex, 0-14 / 15-64 / 65+, fertility, life expectancy,
    net migration, 1950-2100 (medium 2050: 26.5 mln).
12. **High-frequency activity**: FREIGHT_BY_MODE_MONTHLY and FREIGHT_TURNOVER_BY_MODE_MONTHLY (BNS 445258 / 3885, rail,
    road, pipeline, air, sea, inland water, discrete months from 2007-01; rail from 2025 excludes empty wagons -- source
    issue freight_rail_empty_wagons_2025). Electricity consumption (KEGOC map, a snapshot without history), rail loading
    (КТЖ texts) and fiscal-receipt data (none published) stay out.
13. **Consumer confidence**: the NBK's «Индекс потребительских настроений» is reproduced from the household survey the
    pipeline already fetches (INFLATION_EXPECTATIONS_SURVEY items CSI, CSI.CURRENT, CSI.EXPECTATIONS, CSI.Q9 … Q25):
    May 2022 104.1, December 2023 115.7, October 2025 99.1 as published; monthly 2016-2025, quarterly from 2026.

Tests: tests/test_new_sources_2026_11b.py (11 + 1 cross-source).

## 2026-11-10 — derived analytics (block A) and 17 new sources (block B)

**A. Analytics derived by this repository** (scripts/fetchers/analytics.py, agency `derived`, computed in update_dims from the
processed files of the same run; not published by any source -- every note says how):
1. CORE_INFLATION_MEASURES: trimmed means (15 % / 30 %), weighted median, diffusion indices over 21 CPI components with the
   2022 BNS weights held fixed; the components' weighted mean tracks the published CPI (correlation 0.982 m/m, 0.992 y/y).
   October 2026: trimmed mean 9.0 %, median 8.5 %, CPI 9.2 % y/y.
2. MONETARY_CONDITIONS: real ex-ante (household expectations) and ex-post base rate, real TONIA, MCI = real-rate gap
   + 1/3 x REER gap (2016+ means). September 2026 real ex-ante rate 4.1 %.
3. OUTPUT_GAP: HP, one-sided HP, Hamilton (h=8, p=4), unobserved components on SA real GDP; 2026 Q2 +2.2 … +7.3 % (mean
   +4.2 %) -- the BNS SA series jumps 6.5 % q/q in 2026 Q2. Potential growth (HP) 5.2 % a year.
4. CREDIT_GAP: credit-to-GDP 25.1 %, Basel gap (one-sided HP, lambda 400 000) +3.8 pp, credit impulse -0.35 pp (2026 Q2).
5. FISCAL_STANCE: non-oil GDP, oil-gas share 15.5 %, non-oil balance -8.7 % of non-oil GDP, fiscal impulse -1.0 pp (2025).

**B. New data**:
6. FRED (monthly means): VIX, USD_BROAD_INDEX, USD_EME_INDEX, US_BAA_SPREAD (Moody's Baa less 10y; the ICE BofA HY spread
   is licensed for internal use and FRED keeps only three years of it), US_NFCI.
7. IMF PCPS: URANIUM_PRICE (1992 on, 72.47 USD/lb in 2026-09), CHROMIUM_PRICE, MANGANESE_PRICE. PCPS now also carries
   Brent (POILBRE): sources.yaml corrected; OIL_PRICE_BRENT stays World Bank.
8. SOVEREIGN_RATINGS: 61 actions of S&P, Moody's, Fitch since 1996 (config/sovereign_ratings.yaml), monthly notch and outlook.
9. Social standards: SOCIAL_STANDARDS (MRP, MZP, legislated VPM, minimum and base pension by effective month, from 1999;
   config/social_standards.yaml) and SUBSISTENCE_MINIMUM_BY_REGION (BNS price-based, Taldau 704492, 2011 on; from 2025 under
   region dictionary 4843 -- taldau_regional segments now take national_term, region_pos, item_pos and items; items take
   measure_id).
10. Enterprises: ENTERPRISE_PROFIT_LOSS_QUARTERLY (profit and loss by NACE section and region, large and medium, 2015 Q1 on;
    2026 Q2 balance 6 114 bn KZT) and ENTERPRISE_LOSS_MAKING_SHARE_QUARTERLY (31.1 %).
11. Labour: INFORMAL_EMPLOYMENT_SHARE (annual 2012-2024, 12.0 % in 2024; no quarterly series exists) and
    UNPRODUCTIVE_SELF_EMPLOYED_SHARE (quarterly 2020 on, 7.3 %).
12. Sector accounts: SECTOR_ACCOUNTS (new bns_dims layout sector_accounts, bulletin 358455, 2010-2024: disposable income,
    consumption, saving, GFCF, net lending by sector; household saving rate -10.2 % in 2024) and NET_LENDING_BY_SECTOR
    (Taldau 701002, 1993-2024).
13. Agriculture: LIVESTOCK_STOCK_MONTHLY and LIVESTOCK_PRODUCTION_MONTHLY (head, slaughter, milk, eggs by region).
14. FUEL_PRICES_BY_CITY: AI-92/95/98, diesel, LPG in 21 cities, 2011 on (AI-92 240 KZT/l in 2026-06).
15. Quasi-state debt: EXTERNAL_DEBT_STATE_CONTROLLED (+ guaranteed part; NBK form 350, quarterly 2014 on, 29.3 bn USD at
    2026-07-01) and QUASI_STATE_DEBT_ANNUAL (Supreme Audit Chamber total 29.19 trn KZT in 2025; Samruk-Kazyna, Baiterek,
    KMG borrowings from IFRS). Minfin publishes no quasi-state table.
16. Tax expenditures: no published series (only officials' totals); not added.

Fix: Minfin's 2026-10-01 debt edition is listed only under activity 565; the debt fetchers now take both listings.

Tests: tests/test_analytics.py (6), tests/test_new_sources_2026_11c.py (11).

## 2026-11-13 — a faster daily run; dollarisation and yield-curve spreads

**Run time** (the run of 2026-11-12 took 101 minutes: BNS 12, NBK 16, Minfin 38, other scalars 7, item-level datasets 28):
1. Minfin workbooks are parsed once per process (`minfin._open_workbook` keeps plain rows keyed by content): 35 indicators
   re-opened every edition of the 50-sheet Statistical Bulletin, about 49 s each -- some 28 minutes. Rows are identical to
   the old parse (checked on archived bulletins).
2. `gravity._get` stops asking a host that timed out or answered 5xx in the same run (api.worldbank.org cost 5 x 120 s on
   2026-11-10 and 2026-11-12); a 4xx does not trip it. WDI / WGI datasets are refreshed every 30 days, not daily.
3. update.yml: pip cache.
4. Schedule (owner's decision, 2026-11-13): the full run is twice a week, Wednesday and Saturday 06:00 UTC, not daily.
   Daily series are downloaded with their history, so nothing is lost between runs; the accumulating sources keep several
   editions online. A release reaches the repository up to four days late; workflow_dispatch runs it on demand.
Not done (need a decision): updaters in parallel, logs out of the repository.

**New derived datasets** (scripts/fetchers/analytics.py):
4. DOLLARIZATION: FX share of bank loans (1996 on: 44.9 % in 2009-02, 10.0 % in 2026-10), of business loans (2022 on,
   31.8 %), of household deposits (2023 on, 17.9 %). All-deposit dollarisation needs corporate deposits by currency (not held).
5. YIELD_CURVE_SPREADS: slopes 10y-1y (-1.26 pp in 2026-11, inverted), 10y-3m, 5y-2y; 1-year yield and TONIA less the base
   rate; real 10-year yield on household expectations. The sovereign USD spread already exists (KZ_EUROBOND_SPREAD).

Tests: tests/test_run_speed.py (3), tests/test_analytics.py (+1).

## 2026-11-13 — stale series explained, a skipped bulletin, parallel updaters, PR tests, dashboard; eleven new datasets (the «сделай все» request)

**Found and fixed**: the Statistical Bulletin posted 2026-11-05 is titled «Statistical Bulletin …» (capital B); nine
case-sensitive title tests in minfin.py skipped it, so every bulletin series stood one edition behind.

**Stale series** (scripts/lib/staleness.py): a report section and an Actions warning for series whose newest observation is
older than the frequency allows (daily 20, monthly 150, quarterly 330, annual 700 days). The 30 found: in 29 the source has
nothing newer (15 NF_*_YTD -- Minfin has posted no National Fund statement after 1 July 2026; five NBK form-314 bank ratios
frozen since 2024-04 and already superseded; retail food / non-food on Taldau to 2026-04; IMF CTOT to 2026-05; FSI_ROA / ROE
to 2025-Q4; passenger turnover, doctors, beds); NBK_DEBT is blank at the source from 2026-01. Each says why in
config/indicators.yaml (`stale_ok`, or the `lifecycle` it had) and is listed quietly; a new unexplained one raises the warning.

**Run**: BNS, NBK, Minfin and the small agencies in separate processes (update_all.PARALLEL_GROUPS; UPDATE_ALL_SERIAL=1 for
the old order); model_data/ rebuilt and tested at the end of the run, the previous panel restored on any failure;
docs/dashboard.html rebuilt (scripts/build_dashboard.py: ten charts, six tiles); logs/ no longer committed.
**CI**: tests.yml runs pytest on every pull request; update.yml opens an issue (label pipeline-run) when a run or a dataset fails.

**New derived datasets**: MONEY_MULTIPLIER, MONEY_VELOCITY, LABOUR_COST_INDICATORS (unit labour cost, productivity, real wage,
profit balance to GDP), REAL_SOCIAL_STANDARDS (real MZP and minimum pension, Kaitz index); DOLLARIZATION gains all deposits,
legal entities and individuals from 1998 (68.8 % of deposits in FX at 2016-01-01, 18.7 % at 2026-10-01).

**New data**:
1. DEPOSITS_BY_CURRENCY (fetchers/nbk_deposits.py): the NBK deposits page records, 346 months from 1997-12, by currency and
   holder. Open-data form 62 is not used -- its legal-entity rows disagree with the page for 2022 and at the latest date.
2. SOCIAL_FOOD_PRICES_WEEKLY (2026 basket, 31 items) and SOCIAL_FOOD_PRICES_WEEKLY_2022_2025 (19 items): Taldau 703112,
   weekly period; taldau_regional now reads `frequency: weekly` (each ISO week dated its Wednesday) and `national_only`.
3. WAGE_ARREARS_QUARTERLY: overdue and total wage payables of large and medium enterprises, 2015 Q1 on (Taldau 703173 / 703172).
4. Annual budget plan, eight scalars (STATE_BUDGET_*_PLAN, REPUBLICAN_BUDGET_*_PLAN: revenue, tax revenue, expenditure,
   deficit) from the bulletin's «табл 2»; parsed offline from 12 archived editions, the first run is the live check.
Already in the pipeline: Government accounts with the NBK (NBK_SURVEY_HISTORY item CB.n_d_a_minus_obligation, 3.9 trn KZT at
2026-11-01) and monthly physical output (INDUSTRY_PRODUCTION_PHYSICAL_BY_REGION_MONTHLY). Not found in machine-readable
form: housing purchase-sale deals (only a monthly news text). Not connected: the period plan from Minfin's monthly budget
execution report; the National Fund oil taxes from the cash-control-account report.

Tests: tests/test_run_speed.py, tests/test_analytics.py, tests/test_new_sources_2026_11c.py (904 in all).

## 2026-11-13 — tax receipts by economic activity: no KGD table exists; the Audit Chamber's structure and BNS environmental taxes connected instead

**Asked for**: annual tax receipts by ОКЭД from the State Revenue Committee (КГД), 2018-2025, with section B and its divisions 05-09.
**Result: not published.** Points checked on 2026-11-13 (details in config/sources.yaml, TAX_RECEIPTS_BY_OKED):
1. gov.kz, project kgd: title searches «ОКЭД», «видам экономической деятельности», «отрасл» return nothing; direction 655
   «Статистика» holds receipts by budget code, by region and by month (activities 88070, 83555, 59629, 87705, 87371, 87372 …);
   the files opened have no activity breakdown. «Среднеотраслевое значение КНН» has ОКЭД divisions 05-09 but ratios, not receipts.
2. portal.kgd.gov.kz: 403 content pages read, nothing by ОКЭД; every old kgd.gov.kz URL redirects to the portal's home page.
   web.archive.org was NOT reachable from the sandbox, so an archived file is not excluded.
3. data.egov.kz: taxpayer registers and the tax calendar only.
4. Minfin Statistical Bulletin (49 sheets): revenue by budget code only.

**Connected** (scripts/fetchers/tax_by_industry.py):
- TAX_STRUCTURE_BY_INDUSTRY: the Supreme Audit Chamber's chart «Структура налоговых поступлений бюджета (ГБ+НФ) в разрезе
  отраслей экономики» (source Minfin), six groups, 2017-2025, transcribed from the PDFs' text into
  config/tax_structure_by_industry.yaml. Mining: 40.9 (2017), 47.0, 43.1, 29.6, 35.7, 46.2, 36.3, 34.2, 31.2 % (2025).
  The fetcher adds CONSOLIDATED_TAX = December of STATE_TAX_REVENUE_YTD + NF_OIL_DIRECT_TAXES_YTD -- equal to the Chamber's
  totals for 2023-2025 (23 469.6, 23 509.5, 26 913.4 bn KZT) -- and <GROUP>.RECEIPTS = share x total, an estimate
  (mining 5 213 bn in 2018, 9 814 in 2022, 8 397 in 2025; the Chamber's text says 9.8 and 8.5 trn for 2022 and 2023).
- ENVIRONMENTAL_TAXES_BY_OKED: BNS environmental-tax account by ОКЭД section (element 478740), 2016-2025, four tax groups.
  Mining 2 861.8 bn KZT in 2025 (68 % of all environmental taxes), 27-35 % of the mining receipts estimated above: it
  covers the rent tax, excises and the mineral extraction tax, not income tax or VAT.
Reconciliations: sections + other payers = total on every sheet and year (enforced, tolerance 0.1 %); the four groups = the
total sheet; direct oil taxes to the National Fund are 44-65 % of the mining estimate (2018-2025).
**Not available anywhere found**: the split of mining into oil and gas (06) and metal ores (07). The Chamber's 2024
conclusion has a non-ОКЭД «oil sector / ore-mining sector» table (7 194.3 / 2 038.5 bn in 2023) that does not reconcile
with the chart and is not connected.

Tests: tests/test_tax_by_industry.py (5 + 1 cross-source).

## 2026-11-13 — the budget's economic classification in full, its GFSM bridge, and subsoil payments split oil / non-oil

Follow-up to the ОКЭД search: the Minfin Statistical Bulletin classifies EXPENDITURE by type (the economic classification), not
by industry, and so does the IMF's GFSM 2014 -- neither has an ОКЭД dimension. But the bulletin's RECEIPTS by budget code split
subsoil payments into «организации нефтяного сектора» (paid into the National Fund) and everyone else (the budget).
scripts/fetchers/minfin_classification.py, two datasets, January-to-month, million KZT:
1. BUDGET_EXPENDITURE_ECONOMIC_YTD: «табл 6» (state budget, subclasses), «табл 10» (republican) and «таб 11» (local) with
   specifics -- 254 items against the three lines the pipeline had (wages, capital, subsidies). Adds interest (210 / 220),
   goods and services (140-160), employers' contributions (120), transfers to individuals (320, pensions 323), loans and
   financial assets. GFS.21 … GFS.32 regroup the subclasses to GFSM 2014 (compensation, goods and services, interest,
   subsidies, grants, social benefits, other, nonfinancial assets; loans and financial assets, which GFS keeps below the
   line while the Kazakh budget counts them in the deficit). A bridge by subclass on a cash basis for the budget only: it
   does not equal IMF_GFS_OPERATIONS_KZT (general government with the National Fund; IMF annual data end in 2023).
   Checked in every edition: subclasses = category, categories = total. STATE.110 equals STATE_GOV_WAGES_EXPENDITURE on all
   12 common months. January-May 2026, state budget: 14 519 bn in all, wages 1 866, interest 1 930, transfers to individuals 3 157.
2. RESOURCE_PAYMENTS_YTD: «табл 4» -- mineral extraction tax, excess profit tax, bonuses, rent tax, PSA share, historical
   costs of the non-oil sector (NON_OIL_SUBSOIL), export duties on crude and oil products; OIL_SECTOR_NF and OIL_TOTAL from
   NF_OIL_DIRECT_TAXES_YTD for the months the National Fund statement covers. January-September 2025: non-oil subsoil
   payments 858 bn against 4 061 bn for the oil sector; January-May 2026: non-oil MET 838 bn (386 bn by March). EXPORT_DUTY_CRUDE
   equals the scalar OIL_EXPORT_DUTY on all 12 common months. NOT ОКЭД 06 / 07: «oil sector» is the Government's list of
   producers, the rest lumps metal ores, coal, uranium and gas; income tax and VAT of mining companies are outside.
Both start with the 12 editions archived in the repository (2025-02 … 2026-05) -- built offline, the gov.kz listing is not
reachable from the development sandbox -- and grow with every run; earlier years need backfill_minfin_bulletins.py --dims.
The order that defined the classification (Minfin order 403 of 18.09.2014) was replaced in April 2025 (order 180); the new
text was not found on the Minfin site and the classification here is read from the bulletin's own tables.

Tests: tests/test_minfin_classification.py (6 + 1 cross-source).

## 2026-11-13 — budget receipts by every classification code (BUDGET_RECEIPTS_BY_CODE_YTD) (user: «Есть ли поступления в разрезе налогов?», «Да, подключи»)

**What.** `minfin_classification.fetch_receipts` (fetcher `minfin_receipts`) reads every row of the Statistical
Bulletin's «табл 4» (state budget, items `STATE.*`) and «табл 8 (дох)» (republican budget, `REP.*`): 518 items,
5 434 rows, 12 editions (2025-02 .. 2026-05, the ones archived in `data/raw/minfin/`). Item code = budget + the
classification code: `TOTAL`, `REVENUE`, category (1 digit), class (3), subclass (4), specific (6 = the full
budget code). The code is assembled from merged cells: a row prints only the levels that change, the rest is
inherited from the rows above; «L01 …» fillers and the numbering row are skipped; the republican sheet is one
column to the right (found by the numbering row «1 2 3 4»).

**Renumbering.** The 2026 Budget Code inserted «Специальные поступления» as category 4 and moved transfers 4 -> 5,
repayment of budget loans 5 -> 6, sale of financial assets 6 -> 7. A category is recognised by its name and stored
under its 2026 number in every year (`RECEIPT_CATEGORIES`); an unknown category name stops the load. Specifics
are not renumbered; 105316 was reused (environmental fee in 2025, plant-resources fee from 2026; the environmental
fee is 401101 now), 201907 and 204110 changed meaning inside 2025 — `item_name` is the label of the edition.

**Checks.** In all 24 sheets: specifics = subclass, subclasses = class, classes = category, categories 1-5 =
«ДОХОДЫ», 1-7 = «ПОСТУПЛЕНИЯ» (`check_receipts`; a break raises StructuralChangeError). Against the scalar layer,
12 common months each, no difference: STATE.1 = STATE_TAX_REVENUE_YTD, 1011 = STATE_CIT_YTD, 1012 = STATE_PIT_YTD,
1051 = STATE_VAT_YTD, 1052 = STATE_EXCISE_YTD, 103 = STATE_SOCIAL_TAX_YTD, REVENUE = STATE_BUDGET_REVENUE_YTD,
5 = STATE_TRANSFERS_RECEIVED_YTD, 106110 = OIL_EXPORT_DUTY; 105306 = RESOURCE_PAYMENTS_YTD/MET_NON_OIL.

**Numbers** (state budget, bn KZT, January-May 2026 / January-November 2025): receipts 12 997.6 / 26 978.4; taxes
10 934.5 / 20 588.1; CIT 2 792.2 / 5 070.2 (large business 1 990.0 / 3 638.4); PIT 1 181.3 / 2 590.6; VAT
3 478.3 / 5 809.5 (domestic 1 741.4 / 2 637.3, imports from third countries 902.7 / 1 775.5, from the EAEU
650.0 / 1 116.6); excises 460.8 / 934.1; non-oil MET 838.1 / 1 092.8; export duty on crude 625.5 / 1 493.3.
January-March, 2026 against 2025: VAT 1 962.5 against 1 320.6 (+48.6 %, the rate went from 12 to 16 %), domestic
VAT 1 001.4 against 544.6.

**Limits.** Built offline from the archived editions (gov.kz listing is 403 from the sandbox); the first workflow
run will read the live listing. No 2025-04, 2025-05, 2025-12, 2026-04; before 2025-02 needs
`backfill_minfin_bulletins.py`. A line with no receipts is absent, not zero. Oil-sector taxes go to the National
Fund and are not in these tables. Tests: 5 new in `tests/test_minfin_classification.py`.

## 2026-11-13 — statutory tax and contribution rates (TAX_RATES) (user: «Поищи ещё ставки по налогам?»)

**What.** `config/tax_rates.yaml` + dataset TAX_RATES (`manual_table`, `step: monthly`, agency `legal`): 22 items,
the rate in force in each month. VAT, CIT (standard; banks from 2026), PIT (base, top bracket, dividends), social
tax, social contributions, pension contributions of the employee and the employer, medical insurance (employer,
employee), MET on copper, zinc, gold, iron ore, uranium, coal, excises on cigarettes, petrol, diesel, the fixed
export duty on crude oil. Every value was read in the text of the act on zakon.uchet.kz (mirror of adilet.zan.kz,
which now serves an empty JavaScript shell); acts and articles are listed in the head of the yaml.

**Gaps instead of guesses.** `step_records` now takes `YYYY-MM: null`: the months after it are absent until the
next value. Used where the level was not read or there is no single rate: CIT 2009-2010, social tax 2002-2008
(regressive scales 2004-2008), dividends 2018-2022, metals MET 2018-2022, gold and uranium MET from 2026 (scales),
petrol excise 2018-01..2019-05, cigarettes 2011-2013, oil export duty before 2012 and from 2016-03 (price-linked).

**Numbers.** VAT 16 (2001-07), 15 (2004), 14 (2007), 13 (2008), 12 (2009), 16 (2026-01). Social tax 11 (2009), 9.5
(2018), 11 (2025), 6 (2026); net of social contributions it was 6 in 2018-2025 already. Social contributions 1.5
(2005), 2, 3, 4 (2009), 5 (2010), 3.5 (2018), 5 (2025). Employer pension contributions 1.5 / 2.5 / 3.5 (2024-2026).
Medical insurance: employer 1 (2017-07), 1.5, 2 (2020), 3 (2022); employee 1 (2020), 2 (2021). MET from 2023:
copper 8.55 (5.7 before), zinc 10.5 (7), iron ore 3.64 (2.8). Cigarettes 800 (2010-07) to 18 051 tenge per 1 000
(2026). Petrol 10 500 (2017-04), 24 435 (2020), 38 134 tenge per tonne (2022-04).

**Not found** (listed in the research note, not loaded): the month 20 % VAT began; the 2009-2010 CIT article; the
2002-2003 PIT and social-tax wording; original 2017-Code MET table; fuel excises before 2017-04; the oil export
duty acts of 2008-Q4 and of the 20 -> 40 step. Test: `test_tax_rates_step_series_and_gaps`.

## 2026-11-13 — TAX_RATES: the gaps of the first pass are filled (user: «Найди пропуски»)

**Source that unlocked it.** prg.kz keeps dated editions of each act (`prg.kz/m/amp/document/<edition id>/<page>/`,
«Данная редакция действовала до внесения изменений от …»); alta.ru/tamdoc shows customs and excise resolutions with
the superseded text. Both are commercial databases, not the official register; rate changes of 2002-2010 were
cross-checked against amending laws on zakon.uchet.kz. Notes: `docs/research_tax_gaps_A_2026-11-13.md`, `…_B_…`.

**Filled.** CIT 20 in 2009-2010 (Law 100-IV art. 4 suspended Code art. 147; 17.5 for 2010 and 15 from 2011 were
legislated and never applied); CIT 30 and VAT 20 from 1995-07. PIT 2002-2003 scale 5/10/20/30 (PIT is now the lowest
bracket, PIT_TOP the highest); dividends 15 in 2002-2006, 5 in 2018-2022. Social tax 21 in 2002-2003, first bracket
20 in 2004-2007 and 13 in 2008. MET metals unchanged 2009-2022 (copper 5.7, zinc 7, gold 5, iron ore 2.8); coal 0
to 2020, 2.7 from 2021; uranium 22 in 2009-2012 as in force (Law 61-V retroactively set 17.5 — not used), 18.5 in
2013-2022. New item MET_OIL_TOP: 18 in 2009-2026 (the 19 and 20 scheduled in 2008 never applied). Cigarettes 600
(2009), 800 (2010), 1 000, 1 250, 1 550 (2011-2013). Petrol 4 500 in 2009-2015, 10 500 from 25.11.2015 (PP 887,
not April 2017 as the first pass had it); diesel 540 to 2016-09. Oil export duty: 109.91 (from 17.05.2008), 203.8
(11.10.2008), 0 (26.01.2009), 20 (mid-August 2010), 40 (01.01.2011), 60 (mid-April 2013), 80 (12.03.2014), 60
(19.03.2015), 40 (2016-01).

**Corrections of the first pass.** EXCISE_CIGARETTES 800 starts 2010-01, not 2010-07; EXCISE_PETROL 10 500 starts
2015-12; oil-duty months moved to the month the rate applied for most of (2013-05, 2015-04). Order N 81 of 2016
was a step table; «duty = price» dates from Order 311-НҚ of 14.08.2023.

**Finding.** Tax Code 2025 art. 558 has no offset of social contributions against social tax (the 2017 Code art. 486
had one, and the 2001 Code art. 318 by July 2007). The nominal path 9.5 -> 11 -> 6 is therefore flat in net terms:
6 net in 2018-2025, 6 paid on top of contributions in 2026.

**Remaining gaps are structural** (no single rate): gold and uranium MET from 2026, diesel excise 2016-10..2022-03
(seasonal), oil export duty from 2016-03. Open: publication date of PP 805 (2008), PP 173 as signed, the 2017 Code
before the 19.04.2019 edition, the first three weeks of July 1995 for VAT. 23 items.

## 2026-11-13 — TAX_RATES re-verified independently (user: «Проверь ещё раз»)

A second reader re-fetched the acts for all 95 keys of `config/tax_rates.yaml` (note:
`docs/verify_tax_rates_2026-11-13.md`): 91 confirmed, no wrong number. Corrected: (1) EXCISE_PETROL and
EXCISE_DIESEL end at 2025-04 — PP of 28.04.2025 N 280 (in force 11.05.2025) made 38 134 and 35 726 a base plus 50 %
of the wholesale price above 214 584 / 284 350 tenge per tonne (95 % from 01.09.2026, PP 816), so there is no
single rate; the first pass had read «rates unchanged»; (2) OIL_EXPORT_DUTY_RATE 20 starts 2010-08 and 60 starts
2013-04 (the rate applied for most of those months); (3) PENSION_EMPLOYEE starts 2013-07 (Law 105-V): 10 % stood
in the 1997 law too, but the month it began was not read. Still resting on press only: the start days of the oil
duty in 2008-2009. Not re-read: PP 133 and PP 173 as signed, the 2017 Code before the 19.04.2019 edition.
Merging with PR #33 will conflict in six files (sources.yaml, update_dims.py, the two logs, DATA_CATALOG, the
unified file), not two.
