# Minfin Statistical Bulletin, PDF editions of 2005-2012: what is loaded and what is not (2026-11-14)

Until 2012 the monthly bulletin was a PDF (text, not a scan), twelve a year inside the yearly RAR archives on gov.kz;
a few months of 2011-2012 are spreadsheets. `scripts/fetchers/minfin_pdf.py` turns a PDF into the sheets the
spreadsheet readers of `fetchers/minfin_classification.py` expect, and the same sum checks decide what is loaded.
Loading: `python scripts/backfill_minfin_bulletins.py --yearly 2005-2012 --dims …` (workflow «Backfill Minfin
bulletin datasets»; `--offline` for archives already unpacked).

## Loaded

| Dataset | Budget | Months of 96 |
|---|---|---|
| `BUDGET_RECEIPTS_BY_CODE_YTD` (receipts by budget code, tables 4 and 8) | state | 81 |
| | republican | 80 |
| `BUDGET_EXPENDITURE_ECONOMIC_2005_2012_YTD` (economic classification, tables 6/7 and 10) | state | 91 |
| | republican | 88 |
| `RESOURCE_PAYMENTS_YTD` (subsoil payments, lines of table 4) | state | 20 (2010-12 … 2012-12) |

- Values are printed in whole millions of tenge. A sum of n rounded terms may differ from its rounded total by
  n/2 million; the checks allow exactly that for tables of whole numbers and nothing for tables with decimals.
- Before 2013 a subclass that does not equal its specifics drops the table (the spreadsheet editions of 2015-2018
  are kept as «INCOMPLETE» in that case). In a PDF such a break is as likely a code read one row off.
- The economic classification was renumbered from 2013 (130 «Приобретение товаров» became «Выплата заработной
  платы отдельным категориям граждан…»), hence the separate dataset without the GFS bridge.
- Receipt codes are reused over time (105306 is «Роялти» until 2008, the mineral extraction tax from 2009).
- 2002-2004: the pre-2005 budget classification, not read.

## Independent checks

- State budget «ДОХОДЫ» equals `STATE_BUDGET_REVENUE` on all 20 common dates within 1 million (annual 2008-2012,
  quarterly 2010-2012, year-to-date 2011-2012).
- Decembers 2005-2007: «ДОХОДЫ» 2 098 511 / 2 338 034 / 2 887 838 against 2 098 532 / 2 338 034 / 2 887 874 in the
  earlier-year columns of the 2008-12 edition's summary table; tax receipts equal in all three years.
- Expenditure «Всего» equals receipts «ПОСТУПЛЕНИЯ» of the same budget and period in 151 of 152 budget-months
  (state 2011-12: 6 288 321 against 6 288 306).
- December «Всего» of 2008-2011 equals the earlier-year columns of the 2011-2012 spreadsheet editions
  (4 541 375 / 4 252 034 / 5 206 158 / 6 288 321).
- The mineral extraction tax of the non-oil sector in `RESOURCE_PAYMENTS_YTD` equals code 105306 in all 20 months.
- Names: of 4 733 code-months of 2012 compared with the names of the same codes in the 2013 editions, 19 differ
  materially (12 names in the May 2012 state table begin mid-sentence -- vertically centred cells; values are not
  affected).

## Not loaded, and why

April 2006 is not in the archive (11 editions). The rest:

| Table | What the source prints |
|---|---|
| 2005-12 state receipts | subclass 7 «1 176» over specifics 867; subclass 9 «309» over 6 988 |
| 2005-02 republican economic | «340 … 22 178» over 341 = 22 541 and 349 = 1 638 |
| 2005-03 state economic | «Капитальные затраты 44 150», subclasses sum to 44 131 |
| 2005-05 state and republican receipts | class 1 repeats the category «Погашение бюджетных кредитов»; republican «570 001» over a subclass of 57 |
| 2005-08 republican economic | «310 … 367 064» with 311 = 312 = 13 341; «410» equals the category above it |
| 2006-06, 2006-07 republican economic | «620» printed in the specifics column, the category equals 610 alone |
| 2006-09 state receipts | «Поступления трансфертов» has no category code |
| 2006-09, 2006-10 republican receipts | class 01 repeats category 5 |
| 2007-03 state receipts | three partial copies of the same pages; the rows from excises to state duty are not in the file |
| 2008-01 state economic | «Бюджетные кредиты 0» over 530 = 8 639; categories 4 and 5 against their subclasses |
| 2008-12 state receipts | one page (customs duties to state duty) has no code columns |
| 2010-03, 2010-04 republican receipts | subclass 7 printed twice with different values |
| 2010-04, 2010-10 republican economic | values one row off against the codes |
| 2011-04 state receipts | «Поступления трансфертов 290 000» without codes |
| 2011-05, 2011-06, 2011-07 state; 2011-10 republican receipts | one specific code printed twice with different values |
| 2011-09 state, 2011-10 republican economic | subclass 720 twice / missing |
| 2012-11 republican receipts | numbers cut off in bold rows («1 507» over 127 052 + 1 380 000) |

Dropped by the stricter rule or by the reader's limits (the source may be right):

| Table | Reason |
|---|---|
| 2006-01 state economic | a value with decimals («67,2») is not read |
| 2005-01, 2005-03, 2008-05 republican; 2009-02 state receipts | a value with decimals is not read, so a subclass is short |
| 2010-02 state; 2011-02, 2011-04, 2011-07, 2011-09 republican receipts | a subclass does not equal its specifics (a specific lost at a page break, the 2010-2011 muddle of subclasses 6/7, two not examined) |
| 2007-03 republican receipts | a word split without a hyphen in a category name |
| 2007-12 state receipts | the whole code column stands one table row too high |
| 2011-08 state receipts (xls) | a category code on a specific's row |

## Known limit

The sum checks cannot see two specifics of one subclass exchanging their values. The agent that finished the reader
found and fixed about 24 tables of that kind (codes one row off) by rules on the distance between lines; on this
corpus no other case is known, but the guarantee for a single specific of 2005-2012 is weaker than for a subclass.
