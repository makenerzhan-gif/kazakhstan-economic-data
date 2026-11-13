# Kazakhstan tax SCHEDULES (non-single rates) — machine-readable tables, 2026-11-13

Read-only research. Every value below was read on a fetched page in this pass.

## How the texts were read (new: the official register has a JSON API with all dated editions)

adilet.zan.kz is a JavaScript shell, but it loads its data from an open API that `curl` can call directly:

- `https://adilet.zan.kz/api/documents/by-ngr/<NGR>?language=rus` → current edition (field `document.text_content`, HTML) and metadata (`publication_reference` = where and when published).
- `https://adilet.zan.kz/api/documents/<uuid>/versions?page=1&page_size=500` → EVERY dated edition (`revision_date`, `status` new/upd/yts, `document_id`).
- `https://adilet.zan.kz/api/documents/<uuid>` → the text of that edition.
- `POST https://adilet.zan.kz/api/search` with JSON `{"query":"…","search_in":["title"],"filters":{"language":"rus"},"page":1,"page_size":40}` → search (this is how Order 169-НҚ was found: NGR `G26TI000169`).

`revision_date` is in UTC, i.e. one day before the Astana date (2019-12-12 = act of 13.12.2019; 2025-12-31 = edition of 01.01.2026).
Helper scripts and all saved texts: `/tmp/claude-0/-home-user-kazakhstan-economic-data/75b92fb2-b6fa-5dc2-bf44-15a6ab5a8c77/scratchpad/scales/` (`ad.py versions|get|all`, `art.py <file> <article>`).
Source label used below: **ADILET** = adilet.zan.kz API (official register), human URL `https://adilet.zan.kz/rus/docs/<NGR>`. News items are marked **SECOND-HAND**.

Corrections to the existing notes found in this pass (details in the sections):
1. MET on oil, bracket 9 (5–10 mln t): **14 % in 2009–2010, 15 % only from 2011** — docs/research_tax_gaps_B says 15 for 2009–2010. The scale was NOT identical throughout.
2. Rent-tax RATE articles are **art. 303** (2008 Code) and **art. 716** (2017 Code), not 304 / 717 (those are "Налоговый период").
3. Rent tax on coal: 2.1 % only until 2017; **4.7 % in 2018–2020**; abolished from 2021.
4. Order 311-НҚ: published 15.08.2023 → formula in force 26.08.2023 (confirmed from the register's publication field). Order 169-НҚ: published 23.04.2026 → in force 04.05.2026.

---

## 1. Mineral extraction tax on crude oil and gas condensate

### 1.1 Scale by annual output — block A: 2009-01 … 2010-12

Act: Law of 10.12.2008 N 100-IV "О введении в действие Налогового кодекса", art. 7 пп. 1) (suspends parts 1–2 of art. 336 of the Code). Source: ADILET `Z080000100_`, editions of 10.12.2008 (as enacted) and 16.11.2009 / 30.12.2009 (after Law 200-IV) — https://adilet.zan.kz/rus/docs/Z080000100_

| # | lower bound, t/year (exclusive) | upper bound, t/year (inclusive) | rate, % |
|---|---|---|---|
| 1 | 0 | 250 000 | 5 |
| 2 | 250 000 | 500 000 | 7 |
| 3 | 500 000 | 1 000 000 | 8 |
| 4 | 1 000 000 | 2 000 000 | 9 |
| 5 | 2 000 000 | 3 000 000 | 10 |
| 6 | 3 000 000 | 4 000 000 | 11 |
| 7 | 4 000 000 | 5 000 000 | 12 |
| 8 | 5 000 000 | 7 000 000 | 13 |
| 9 | 7 000 000 | 10 000 000 | **14** |
| 10 | 10 000 000 | — | 18 |

Quote (edition as enacted): «Статья 7. Приостановить до 1 января 2011 года действие частей первой и второй статьи 336 и части первой статьи 339 … | Объем годовой добычи | Ставки, в % с 1 января 2009 года | с 1 января 2010 года | 1. до 250 000 тонн включительно | 5 | 6 | … | 8. до 7 000 000 тонн включительно | 13 | 14 | 9. до 10 000 000 тонн включительно | 14 | 15 | 10. Свыше 10 000 000 тонн | 18 | 19».
Edition after Law of 16.11.2009 N 200-IV: «Приостановить до 1 января 2014 года … с 1 января 2009 года | с 1 января 2013 года» — same two columns of numbers; footnote «Статья 7 с изменениями, внесенными Законом РК от 16.11.2009 № 200-IV (вводятся в действие с 01.01.2009)». Edition of 26.11.2010: «Статья 7. Исключена Законом РК от 26.11.2010 № 356-IV (вводится в действие с 01.01.2011)».
Never applied: the second column (6, 8, 9, 10, 11, 12, 13, 14, 15, 19) and the Code's own art. 336 table as adopted (7, 9, 10, 11, 12, 13, 14, 15, 17, 20 — ADILET `K080000099_`, edition of 10.12.2008).

### 1.2 Scale by annual output — block B: 2011-01 … 2026-12 (one table, three codes)

| # | lower bound, t/year (exclusive) | upper bound, t/year (inclusive) | rate, % |
|---|---|---|---|
| 1 | 0 | 250 000 | 5 |
| 2 | 250 000 | 500 000 | 7 |
| 3 | 500 000 | 1 000 000 | 8 |
| 4 | 1 000 000 | 2 000 000 | 9 |
| 5 | 2 000 000 | 3 000 000 | 10 |
| 6 | 3 000 000 | 4 000 000 | 11 |
| 7 | 4 000 000 | 5 000 000 | 12 |
| 8 | 5 000 000 | 7 000 000 | 13 |
| 9 | 7 000 000 | 10 000 000 | **15** |
| 10 | 10 000 000 | — | 18 |

| Period | Act, article | Editions read (ADILET) | URL |
|---|---|---|---|
| 2011-01 … 2017-12 | Tax Code of 10.12.2008 N 99-IV, art. 336 part 1, table as restated by Law of 26.11.2010 N 356-IV (in force 01.01.2011) | 31.12.2010, 31.12.2012, 31.12.2015, 31.12.2016, final (01.01.2018) — identical | https://adilet.zan.kz/rus/docs/K080000099_ |
| 2018-01 … 2025-12 | Tax Code of 25.12.2017 N 120-VI, art. 743 п. 1 | as enacted (25.12.2017), 01.01.2021, 01.01.2023, 01.01.2025, final (01.01.2026) — identical; the article carries no amendment footnote at all | https://adilet.zan.kz/rus/docs/K1700000120 |
| 2026-01 … 2026-12 | Tax Code of 18.07.2025 N 214-VIII, art. 778 п. 1 пп. 1) «с 1 января 2026 года по 31 декабря 2026 года включительно» (rates printed 5,0 … 18,0) | as enacted (18.07.2025) and current (01.07.2026) — art. 778 byte-identical | https://adilet.zan.kz/rus/docs/K2500000214 |

Footnote of art. 336 (2008 Code, final): «Статья 336 с изменениями, внесенными законами РК от 16.11.2009 № 200-IV (вводятся в действие с 01.01.2009); от 26.11.2010 № 356-IV (вводятся в действие с 01.01.2011); … от 22.06.2012 № 21-V» (the 2012 law added only the third paragraph on oil sent for tolling abroad, valid until 01.01.2017).

**Answer to "identical throughout?"** Ten brackets with the same bounds from 2009 to 2026: yes. Rates: nine of ten identical; bracket 9 was 14 % in 2009–2010 and 15 % from 2011-01.

### 1.3 Matrix by output AND price — block C: from 2027-01

Act: Tax Code 2025, art. 778 п. 1 пп. 2) «с 1 января 2027 года». Header: «Объем годовой добычи | Стоимость нефти за баррель, долларов США | 20 | 30 | … | 200». Rate in %. Source: ADILET `K2500000214` (as enacted = current).

| # | output, t/year | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 | 140 | 150 | 160 | 170 | 180 | 190 | 200 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | до 250 000 | 19 | 19 | 19 | 26 | 30 | 33 | 35 | 36 | 38 | 40 | 42 | 43 | 46 | 47 | 48 | 51 | 52 | 54 | 53 |
| 2 | до 500 000 | 21 | 21 | 21 | 28 | 32 | 35 | 37 | 38 | 40 | 42 | 44 | 45 | 48 | 49 | 50 | 53 | 54 | 56 | 55 |
| 3 | до 1 000 000 | 22 | 22 | 22 | 29 | 33 | 36 | 38 | 39 | 41 | 43 | 45 | 46 | 49 | 50 | 51 | 54 | 55 | 57 | 56 |
| 4 | до 2 000 000 | 23 | 23 | 23 | 30 | 34 | 37 | 39 | 40 | 42 | 44 | 46 | 47 | 50 | 51 | 52 | 55 | 56 | 58 | 57 |
| 5 | до 3 000 000 | 24 | 24 | 24 | 31 | 35 | 38 | 40 | 41 | 43 | 45 | 47 | 48 | 51 | 52 | 53 | 56 | 57 | 59 | 58 |
| 6 | до 4 000 000 | 25 | 25 | 25 | 32 | 36 | 39 | 41 | 42 | 44 | 46 | 48 | 49 | 52 | 53 | 54 | 57 | 58 | 60 | 59 |
| 7 | до 5 000 000 | 26 | 26 | 26 | 33 | 37 | 40 | 42 | 43 | 45 | 47 | 49 | 50 | 53 | 54 | 55 | 58 | 59 | 61 | 60 |
| 8 | до 7 000 000 | 27 | 27 | 27 | 34 | 38 | 41 | 43 | 44 | 46 | 48 | 50 | 51 | 54 | 55 | 56 | 59 | 60 | 62 | 61 |
| 9 | до 10 000 000 | 29 | 29 | 29 | 36 | 40 | 43 | 45 | 46 | 48 | 50 | 52 | 53 | 56 | 57 | 58 | 61 | 62 | 64 | 63 |
| 10 | свыше 10 000 000 | 32 | 32 | 32 | 39 | 43 | 46 | 48 | 49 | 51 | 53 | 55 | 56 | 59 | 60 | 61 | 64 | 65 | 67 | 66 |

As a regular list: row r (r = 1…10), column price p ∈ {20,30,…,200}; rate = base_r + add_p, where base = (19, 21, 22, 23, 24, 25, 26, 27, 29, 32) and add = (0,0,0,7,11,14,16,17,19,21,23,24,27,28,29,32,33,35,34) — checked against all 190 cells.

Notes
- The law gives only the bare column heads 20 … 200; it does not say "до … включительно" or how prices between two heads are treated. In the 2027 table the output rows read «до 250 000 тонн» (the word «включительно» is absent, unlike 2026).
- Printed as in the law: the rate at 200 is ONE POINT LOWER than at 190 in every row (53 vs 54 etc.). Looks like a drafting slip, but it is the text.
- These are 4–5 times the 2026 rates: from 2027 the MET on oil evidently absorbs other levies (art. 746, as suspended by art. 835 until 01.01.2027, keeps MET payers liable to rent tax only until then; after that «недропользователями, являющимися плательщиками налога на добычу полезных ископаемых по углеводородам или альтернативного налога» are excluded from rent tax).
- Price: «мировой цены, определенной в соответствии с пунктом 3 статьи 776» — arithmetic mean of daily quotations (mean of daily min and max) over the tax period (quarter) of «Юралс Средиземноморье (Urals Med - CIF Augusta)», «Kazakh Export Blend Crude Oil (Kebco - CIF Augusta)» or «North Sea Dated/Датированный Брент (Brent Dtd)», source «Argus Crude» компании «Argus Media Ltd».
- п. 2: for fields classed as low-margin the Government sets the rates.

### 1.4 Domestic-sales coefficient

| Period | Coefficient | Wording / source |
|---|---|---|
| 2009-01 … 2026-12 | 0.5 on the scale rate | 2009 (Law 100-IV art. 7, as enacted): «В случае реализации сырой нефти и газового конденсата на внутреннем рынке Республики Казахстан в порядке, предусмотренном подпунктами 1) - 3) пункта 2 статьи 332 … к установленным ставкам применяется понижающий коэффициент 0,5». From Law 200-IV (retroactive to 01.01.2009), 2008 Code art. 336, 2017 Code art. 743, 2025 Code art. 778 п.1 пп.1): «В случае реализации и (или) передачи … на внутреннем рынке Республики Казахстан, в том числе в натуральной форме в счет уплаты налога на добычу полезных ископаемых, рентного налога на экспорт, роялти и доли Республики Казахстан по разделу продукции получателю от имени государства, или использования на собственные производственные нужды … к установленным ставкам применяется понижающий коэффициент 0,5» |
| 2027-01 … | not a number in the law | art. 778 п.1 пп.2): «…применяется выравнивающий коэффициент, определяемый в порядке, определенном уполномоченным органом в области налоговой политики по согласованию с уполномоченным органом в области углеводородов» |

### 1.5 Natural gas

| Period | Rate | Domestic sales, by annual output | Source |
|---|---|---|---|
| 2009-01 … 2017-12 | 10 % («природный газ») | ≤ 1.0 bcm: 0.5 %; ≤ 2.0 bcm: 1.0 %; > 2.0 bcm: 1.5 % | 2008 Code art. 336 (editions 2008, 2009, 2010, 2012, 2015, 2016 — same) |
| 2018-01 … 2026 → | 10 % («сырой газ») | same three steps | 2017 Code art. 743 п. 1; 2025 Code art. 778 п. 1 (text after the 2027 matrix, not time-limited) |

Quote (2025 Code): «Ставка налога на добычу полезных ископаемых на сырой газ составляет 10 процентов. При реализации сырого газа на внутреннем рынке … | 1. до 1,0 млрд. куб. м включительно | 0,5 | 2. до 2,0 млрд. куб. м включительно | 1,0 | 3. свыше 2,0 млрд. куб. м | 1,5».

---

## 2. MET on gold, silver and uranium from 2026-01 — Tax Code 2025, art. 781 п. 1 пп. 2)–4)

Source: ADILET `K2500000214`, art. 781 identical in the edition as enacted (18.07.2025) and the current one — https://adilet.zan.kz/rus/docs/K2500000214. Valid from 2026-01 (Code in force 01.01.2026, art. 848), no end date.

### 2.1 Gold — «3) золото в зависимости от цены», column «Среднебиржевая цена на золото»

| # | lower bound, USD/troy oz (exclusive) | upper bound (inclusive) | rate, % |
|---|---|---|---|
| 1 | 0 | 2 800 | 7.5 |
| 2 | 2 800 | 3 000 | 8 |
| 3 | 3 000 | 3 200 | 8.5 |
| 4 | 3 200 | 3 400 | 9 |
| 5 | 3 400 | 3 600 | 9.5 |
| 6 | 3 600 | 3 800 | 10 |
| 7 | 3 800 | — | 11 |

Quote: «1. до 2 800 долларов включительно за тройскую унцию | 7,5 | 2. до 3000 … | 8 | 3. до 3200 … | 8,5 | 4. до 3 400 … | 9 | 5. до 3 600 … | 9,5 | 6. до 3800 … | 10 | 7. свыше 3800 долларов за тройскую унцию | 11».

### 2.2 Silver — «4) серебро в зависимости от цены», column «Среднебиржевая цена на серебро»

| # | lower bound, USD/troy oz (exclusive) | upper bound (inclusive) | rate, % |
|---|---|---|---|
| 1 | 0 | 28 | 7.5 |
| 2 | 28 | 30 | 8 |
| 3 | 30 | 32 | 8.5 |
| 4 | 32 | 34 | 9 |
| 5 | 34 | 36 | 9.5 |
| 6 | 36 | 38 | 10 |
| 7 | 38 | — | 11 |

(Row 7 is printed «свыше 38 долларов включительно за тройскую унцию» — sic.) Platinum and palladium stay in the fixed table at 6.5 %.

### 2.3 Uranium — «2) уран (извлеченный из продуктивных растворов, шахтный метод) в зависимости от объемов годовой добычи и цены на концентрат природного урана (U3O8)»

Base rate by annual output:

| # | lower bound, t/year (exclusive) | upper bound (inclusive) | rate, % |
|---|---|---|---|
| 1 | 0 | 500 | 4 |
| 2 | 500 | 1 000 | 6 |
| 3 | 1 000 | 2 000 | 9 |
| 4 | 2 000 | 3 000 | 12 |
| 5 | 3 000 | 4 000 | 15 |
| 6 | 4 000 | — | 18 |

Price add-on («…ставка … увеличивается на следующий размер»), percentage points added to the base rate:

| # | weighted-average U3O8 price, USD/lb | add-on, p.p. |
|---|---|---|
| 0 | ≤ 70 | 0 |
| 1 | > 70 | 0.5 |
| 2 | > 80 | 1.0 |
| 3 | > 90 | 1.5 |
| 4 | > 100 | 2.0 |
| 5 | > 110 | 2.5 |

So the total rate ranges from 4 to 20.5 %. Output is the planned annual volume per contract, corrected to actual in the Q4 return (art. 780).

### 2.4 How the prices are defined (art. 780)

- Gold (also platinum, palladium): «Средняя биржевая цена на золото, платину, палладий определяется как произведение среднеарифметического значения ежедневных усредненных котировок цен за налоговый период и среднеарифметического официального курса валюты за соответствующий налоговый период»; «Р1, P2,..., Pn – ежедневная усредненная котировка цен на золото, платину, палладий в дни, за которые были объявлены и опубликованы котировки цен Лондонской ассоциацией рынка драгоценных металлов». I.e. LBMA daily averaged quotations, averaged over the quarter (the Code does not spell out what is averaged within the day). The tax base is in tenge, but the scale thresholds are in USD/oz.
- Silver: «…среднеарифметического значения ежедневных котировок цен на серебро за налоговый период … опубликованы котировки цен Лондонской ассоциацией рынка драгоценных металлов» (one daily LBMA quotation).
- General source clause: «котировка цены на полезное ископаемое в иностранной валюте, зафиксированную на Лондонской бирже металлов или Лондонской ассоциации рынка драгоценных металлов и публикуемую в журнале "MetalBulletin" …, журнале "Metal-pages"».
- Uranium: «исходя из средневзвешенной цены за килограмм урана в форме концентрата природного урана (U3O8), определяемой как произведение среднеарифметического значения месячных котировок цен за фунт урана … за каждый месяц налогового периода с учетом перевода фунтов в килограммы … и среднеарифметического официального курса валюты»; «месячный индикатор спотовой цены за фунт концентрата природного урана (U3O8), действующий на последний день месяца … "Ux Weekly" компании "Ux Consulting LLC" (США) и "The Nuclear Market Review" компании "TradeTech LLC" (США)»; «К – коэффициент перевода фунтов в килограммы, установленный в размере 2,59978». The add-on table itself is in USD per pound.
- Tax period: quarter.

Other rows of the art. 781 fixed table read in passing (2026): chrome ore 21.06; manganese ore 3.25; iron ore 3.64; copper 8.55; zinc 10.5; lead 10.4; platinum, palladium 6.5; aluminium 0.38; tin 3.9; nickel 7.8; coking coal, anthracite 4.05; other hard coal, brown coal, oil shale 2.7 (× 0.01 for eight listed uses: natural monopolies, power plants, own processing, schools and hospitals, etc.).

---

## 3. Excise on diesel fuel, producers' wholesale, tenge per tonne — monthly calendar 2016-10 … 2022-04

Row: «Оптовая реализация производителями бензина (за исключением авиационного) и дизельного топлива собственного производства». All from ADILET: amending resolutions themselves (`P1600000557`, `P1700000144`, `P1900000331`, `P1900000928`, `P2100000220`, `P2100000841`, `P2200000155`) and all 16 dated editions of `P1800000173` plus 5 of `P1500000133`.

### 3.1 Rules by act

| In force from … to | Act | Months at 9 300 | Months at 540 | Petrol (same row) | Quote |
|---|---|---|---|---|---|
| 2015-01-01 … 2015-11-24 | PP 13.03.2015 N 133, as enacted | — | all | 4 500 | «4500 | 540» |
| 2015-11-25 … 2016-10-14 | PP 06.11.2015 N 887 | — | all | 10 500 | «10 500 | 540» |
| 2016-10-15 … 2017-03-31 | PP 30.09.2016 N 557 («вводится в действие с 15 октября 2016 года») | April–October | November–March | 10 500 | «(апрель – октябрь) | 10500 | 9300 … (ноябрь – март) | 10500 | 540» |
| 2017-04-01 … 2017-12-31 | PP 31.03.2017 N 144 («с 1 апреля 2017 года») | June–October | November–May | 10 500 | «(июнь – октябрь) | 10500 | 9300 … (ноябрь – май) | 10500 | 540» |
| 2018-01-01 … 2019-05-31 | PP 06.04.2018 N 173, as enacted («вводится в действие с 1 января 2018 года» — signed in April, backdated; PP 133/557/144 repealed from 01.01.2018) | June–October | November–May | 10 500 | edition of 06.04.2018: «(июнь – октябрь) | 10500 | 9300 … (ноябрь – май) | 10500 | 540». Edition after PP 29.11.2018 N 793: producer rows unchanged |
| 2019-06-01 … 2019-12-31 | PP 29.05.2019 N 331 («с 1 июня 2019 года») | July–November | December–June | 10 500 | «(июль – ноябрь) | 10500 | 9300 … (декабрь – июнь) | 10500 | 540» |
| 2020-01-01 … 2021-12-31 | PP 13.12.2019 N 928 («с 1 января 2020 года») | July–November | December–June | 24 435 | «(июль – ноябрь) | 24 435 | 9300 … (декабрь – июнь) | 24 435 | 540» |
| (2021-04) | PP 08.04.2021 N 220 (10 days after publication) | — | — | — | touches only rows 8–10 (tolling: «(июль – ноябрь) | 24 435 | 9300», «(декабрь – июнь) | 24 435 | 540», new row 10 at 0). Producer rows unchanged |
| 2022-01-01 … 2022-04-04 | PP 25.11.2021 N 841 («с 1 января 2022 года»; adds a third column for gasohol etc.) | July–November | December–June | 24 435 | «(июль-ноябрь) | 24 435 | 9 300 | 24 435 … (декабрь-июнь) | 24 435 | 540 | 24 435» |
| 2022-04-05 … | PP 24.03.2022 N 155 (10 calendar days after first publication; published in the reference bank 25.03.2022 → 05.04.2022) | none — one row, no season | — | 38 134 | «38 134 | 35 726 | 38 134» |

### 3.2 Monthly series (diesel, tenge per tonne)

| Months | Rate | Governing act |
|---|---|---|
| 2016-10 | 540 on 1–14 Oct, **9 300** on 15–31 Oct (17 of 31 days) | PP 887 → PP 557 |
| 2016-11 … 2017-03 | 540 | PP 557 |
| 2017-04, 2017-05 | 540 | PP 144 (under PP 557 April and May would have been 9 300; PP 144 took effect on 1 April) |
| 2017-06 … 2017-10 | 9 300 | PP 144 |
| 2017-11, 2017-12 | 540 | PP 144 |
| 2018-01 … 2018-05 | 540 | PP 173 |
| 2018-06 … 2018-10 | 9 300 | PP 173 |
| 2018-11 … 2019-05 | 540 | PP 173 |
| 2019-06 | 540 | PP 331 (under PP 173 June would have been 9 300; PP 331 took effect on 1 June) |
| 2019-07 … 2019-11 | 9 300 | PP 331 |
| 2019-12 … 2020-06 | 540 | PP 331, PP 928 |
| 2020-07 … 2020-11 | 9 300 | PP 928 |
| 2020-12 … 2021-06 | 540 | PP 928 |
| 2021-07 … 2021-11 | 9 300 | PP 928 |
| 2021-12 … 2022-03 | 540 | PP 928, PP 841 |
| 2022-04 | 540 on 1–4 Apr, **35 726** from 5 Apr (26 of 30 days) | PP 841 → PP 155 |

Count of 9 300 months: 2016: 1 (Oct, partial); 2017: 5; 2018: 5; 2019: 5; 2020: 5; 2021: 5.

Caveats
- PP 05.10.2022 N 786 restated the table with the same 38 134 / 35 726 and is marked «вводится в действие с 01.01.2022» — formally it backdates the flat rate to January 2022. The economically applied rates in January–March 2022 are those above.
- Edition of 20.02.2023 of PP 173 carries a note: «Для служебного пользования. В ставки акцизов предусмотрено изменение постановлением Правительства РК от 20.02.2023 № 146 (действует до 01.01.2024)» — an unpublished (restricted) change valid in 2023; its content is not in the register. The published producer row stayed 38 134 / 35 726.
- PP 13.11.2024 N 959 only added a row (benzanol producers, 0 / 0 / 3 000).

---

## 4. Excise on petrol and diesel from May 2025 — price-linked formula

Sources (all ADILET): `P2500000280` (as enacted) and editions of `P1800000173` of 28.04.2025 and 05.12.2025; `P2500001049` — 13 stored editions, 4 distinct texts (as signed; after PP 615; after PP 773; after PP 816); `P2600000615` п. 101; `P2600000773`; `P2600000816`. URLs: https://adilet.zan.kz/rus/docs/P2500000280 , …/P2500001049 , …/P2600000615 , …/P2600000773 , …/P2600000816

Dating
- PP 28.04.2025 N 280: «вводится в действие по истечении десяти календарных дней после дня его первого официального опубликования»; published in the reference bank 30.04.2025 → **11.05.2025**. Lapsed with PP 173 on 01.01.2026.
- PP 05.12.2025 N 1049: «вводится в действие после его официального опубликования, но не ранее 1 января 2026 года»; published 09.12.2025 → **01.01.2026**. Legal basis: Tax Code 2025 art. 537 п. 6 пп. 2).
- PP 14.07.2026 N 615 (omnibus «тенге → теңге» spelling act, п. 101): «вводится в действие со дня его первого официального опубликования»; published 17.07.2026 → **17.07.2026**.
- PP 27.08.2026 N 773: «вводится в действие со дня его первого официального опубликования и распространяется на правоотношения, возникшие с 17 июля 2026 года»; published 31.08.2026.
- PP 11.09.2026 N 816: «вводится в действие по истечении десяти календарных дней после дня его первого официального опубликования и распространяется на правоотношения, возникшие с 1 сентября 2026 года»; published 11.09.2026 → in force 22.09.2026, applies from **01.09.2026**.

Below the threshold price the flat rate of the table applies (38 134 petrol, 35 726 diesel; retail by producers and own use 38 634 / 35 786). No cap is set in any of the texts.

### 4.1 Petrol (producers' wholesale, import, tolling transfers)

| Parameter | 2025-05-11 … 2025-12-31 (PP 280) | 2026-01-01 … 2026-07-16 (PP 1049 as signed) | 2026-07-17 … 2026-08-31 (PP 615, then PP 773 backdated to 17.07) | 2026-09-01 … (PP 816) |
|---|---|---|---|---|
| Base rate, tenge/t | 38 134 (retail/own use 38 634) | 38 134 (38 634) | 38 134 (38 634) | 38 134 (38 634) |
| Which fuel | «бензина марки Аи-92 и Аи-93 (за исключением авиационного), газохола, бензанола, нефраса, смеси легких углеводородов и экологического топлива» | «бензина (за исключением авиационного), газохола, бензанола, нефраса, смеси легких углеводородов и экологического топлива» — no grade restriction | same | same |
| Trigger | «по цене выше 214584 тенге за тонну» | «по цене выше 214 584 тенге за тонну» | same | same |
| Amount subtracted from the price | 214 584 | 214 584 / 1,12 (= 191 592.86) | 214 584 / 1,12 | 214 584 / 1,12 |
| Share of the excess | 50 % | 50 % | 50 % | **95 %** |
| Formula | «Аб = 38134 + (Цср-214584) * 50 %» | «Аб = 38 134 + (Цсрв-214 584/1,12) * 50 %» | «Аб = 38134 + (Цсрв-214584/1,12) * 50 %» | «Аб = 38 134 + (Цсрв – 214 584/1,12) * 95%» |
| Price | Цср — «средняя оптовая цена за отчетный месяц, предоставляемая уполномоченным органом … в сферах нефтегазовой, нефтегазохимической промышленности, в уполномоченный орган в области государственного регулирования оборота нефтепродуктов и биотоплива» (VAT not mentioned) | Цсрв — «средневзвешенная оптовая цена без учета налога на добавленную стоимость обладателей ключевой мощности на рынке оптовой реализации нефтепродуктов, предоставляемая [Minenergo] … до 1 числа месяца, предшествующего отчетному, исходя из фактических цен и плановых объемов поставки нефтепродуктов за месяц, предшествующий периоду поставки»; Цсрв = Σ(Ц·V)/ΣV over «АО "Национальная компания КазМунайГаз" и ТОО "KC energy group"» at АНПЗ, ПНХЗ, ПКОП | 17.07–30.08.2026 as published: formula kept but the definition of Цсрв DROPPED (text ends «Аб – ставка акциза, теңге за тонну.»); PP 773 restored the definition verbatim, retroactive to 17.07.2026 | same definition as PP 773 |
| Cap | none | none | none | none |

### 4.2 Diesel

| Parameter | 2025-05-11 … 2025-12-31 (PP 280) | 2026-01-01 … 2026-07-16 (PP 1049 as signed) | 2026-07-17 … 2026-08-31 (PP 615 / PP 773) | 2026-09-01 … (PP 816) |
|---|---|---|---|---|
| Base rate, tenge/t | 35 726 (retail/own use 35 786) | 35 726 (35 786) | 35 726 (35 786) | 35 726 (35 786) |
| Which fuel | «дизельного топлива (летнее, межсезонное)» — winter diesel stays at the flat rate | «дизельного топлива» — no seasonal-grade restriction | same | same |
| Trigger | «по цене выше 284350 тенге за тонну» | «по цене выше 284 350 тенге за тонну» | same | same |
| Amount subtracted from the price | 284 350 | 284 350 / 1,12 (= 253 883.93) | 284 350 / 1,12 | 284 350 / 1,12 |
| Share of the excess | 50 % | 50 % | 50 % | **95 %** |
| Formula | «Адт = 35726 + (Цср-284350) * 50 %» | «Адт = 35 726 + (Цсрв-284 350/1,12) * 50%» | «Адт = 35726 + (Цсрв-284350/1,12) * 50%» | «Адт = 35 726 + (Цсрв – 284 350/1,12) * 95%» |
| Price | Цср — same wording as for petrol | Цсрв — «средневзвешенная оптовая цена с учетом цен реализации дизельного топлива для сельскохозяйственных товаропроизводителей без стоимости доставки и учета налога на добавленную стоимость обладателей ключевой мощности …» — same submission rule and weights, «с учетом сельскохозяйственных товаропроизводителей» | definition dropped by PP 615, restored by PP 773 | same as PP 773 |
| Cap | none | none | none | none |

Notes
- The divisor is 1,12 in every 2026 text although the standard VAT rate has been 16 % since 01.01.2026: the threshold was converted to a net-of-VAT figure at the old 12 % rate. Read as written.
- Table codes: diesel column since PP 280 is «код ТН ВЭД ЕАЭС 2710 19 421 0 – 2710 19 425 0» (before: 2710 19 310 0 – 2710 19 480 0).
- Litre-to-tonne conversion in the note to PP 1049: petrol 0,730 kg/l, diesel 0,769 kg/l.
- Monthly values of Цср / Цсрв are not in the acts; they are supplied by the Ministry of Energy to the tax authority. No published series was looked for.

---

## 5. Export customs duty on crude oil (HS 2709 00 900 9), from 1 March 2016

### 5.1 Step table: 2016-03-01 … 2023-08-25

Act: Order of the Minister of National Economy of 17.02.2016 N 81 (registered 24.02.2016 N 13217; published in «Әділет» 25.02.2016), Annex 1 to the Rules, «Ставки вывозных таможенных пошлин на сырую нефть». Source: ADILET `V1600013217`, edition as enacted — https://adilet.zan.kz/rus/docs/V1600013217. List row: «2709 00 900 9 | Нефть сырая | 40 долларов за 1 тонну | 40 долларов за 1 тонну | До 1 марта 2016 года | В соответствии с Правилами … | С 1 марта 2016 года постоянно».

| # | average price from, USD/bbl | to, USD/bbl | duty, USD/t |
|---|---|---|---|
| 1 | 0 | 25 | 0 |
| 2 | 25 | 30 | 10 |
| 3 | 30 | 35 | 20 |
| 4 | 35 | 40 | 35 |
| 5 | 40 | 45 | 40 |
| 6 | 45 | 50 | 45 |
| 7 | 50 | 55 | 50 |
| 8 | 55 | 60 | 55 |
| 9 | 60 | 65 | 60 |
| 10 | 65 | 70 | 65 |
| 11 | 70 | 75 | 70 |
| 12 | 75 | 80 | 75 |
| 13 | 80 | 85 | 80 |
| 14 | 85 | 90 | 85 |
| 15 | 90 | 95 | 90 |
| 16 | 95 | 100 | 95 |
| 17 | 100 | 105 | 100 |
| 18 | 105 | 115 | 115 |
| 19 | 115 | 125 | 130 |
| 20 | 125 | 135 | 145 |
| 21 | 135 | 145 | 160 |
| 22 | 145 | 155 | 176 |
| 23 | 155 | 165 | 191 |
| 24 | 165 | 175 | 206 |
| 25 | 175 | 185 | 221 |
| 26 | 185 | — | 236 |

The order says «с 25 до 30 долларов США за баррель» etc. and does not state which band a price exactly on a boundary falls into.

**Every later edition checked.** All 26 stored editions of Order N 81 were downloaded and the 26 crude rows compared by hash: identical in all 22 editions from 17.02.2016 through 24.05.2023 (06.10.2016, 30.01.2017, 19.04.2017, 02.03.2018, 28.12.2018, 24.05.2019, 11.06.2019, 03.04.2020, 10.04.2020, 03.08.2020, 25.12.2020, 31.12.2020, 19.03.2021, 09.06.2021, 07.10.2021, 01.03.2022, 31.05.2022, 07.11.2022, 20.01.2023, 13.02.2023, 24.05.2023). What did change next to it:
- 06.10.2016 N 441: п. 4 — the average price «математически округляется до второго знака после запятой».
- 11.06.2019 N 54: a second column for light oil products appears in the same table (40,5 at the 45–50 row, i.e. 0.9 × the crude rate of 45); 25.12.2020 N 310-НҚ: 13,5 at the same row (0.3 ×); 13.02.2023 N 70-НҚ: 45 (= crude). None of this touches the crude column.
- 13.02.2023 N 70-НҚ: п. 3 — the price basket changes from «URALS (MED) и BRENT (DTD)» to «KEBCO и BRENT».

### 5.2 Formula: 2023-08-26 … (Order N 81 until 14.08.2026; Order 169-НҚ from 04.05.2026)

Act: Order of the acting Minister of Trade and Integration of 14.08.2023 N 311-НҚ (registered 14.08.2023 N 33273; published in the reference bank 15.08.2023; in force «по истечении десяти календарных дней после дня его первого официально опубликования» → 26.08.2023) — new edition of the Rules. First month computed by formula: September 2023.
Then: Order of the Minister of Trade and Integration of **17.04.2026 N 169-НҚ** (ADILET `G26TI000169`, https://adilet.zan.kz/rus/docs/G26TI000169; published 23.04.2026; in force 10 calendar days after publication → 04.05.2026) — same rule, same table; not registered with the Ministry of Justice (title carries no registration number). Its later amendments 24.08.2026 N 240-НҚ (row 17 of section 1, metals) and 28.09.2026 N 273-НҚ (list of goods restated) leave the Rules untouched (checked by diff). Order N 81 repealed by Order of 29.07.2026 N 228-НҚ (registered 30.07.2026 N 39445), 10 days after publication.

| # | average price, USD/bbl | duty, USD/t |
|---|---|---|
| 1 | below 25 | 0 |
| 2 | 25 … 105 | = average price × K, K = 1 (average price rounded to a whole number) |
| 3 | 105 … 115 | 115 |
| 4 | 115 … 125 | 130 |
| 5 | 125 … 135 | 145 |
| 6 | 135 … 145 | 160 |
| 7 | 145 … 155 | 176 |
| 8 | 155 … 165 | 191 |
| 9 | 165 … 175 | 206 |
| 10 | 175 … 185 | 221 |
| 11 | 185 and above | 236 |

Quotes (Rules, edition of 14.08.2023; identical in 169-НҚ): «3. … 1) при значении средней рыночной цены сырой нефти до 25 долларов … за баррель – размер ставки вывозной таможенной пошлины равен 0; 2) при значении … от 25 до 105 долларов США за баррель – … ВТП=Ср*К, где: ВТП – размер ставки вывозной таможенной пошлины на сырую нефть и нефтепродукты, в долларах США за тонну; Ср – средняя рыночная цена сырой нефти за предшествующий период; К – поправочный коэффициент 1. 3) при значении … свыше 105 долларов США за баррель применяется одна из ставок … указанных в приложении 2»; «6. Результаты расчетов, произведенных по формулам, указанным в пункте 5 настоящих Правил, математически округляются до целого числа» (п. 7 in 169-НҚ).
Exemptions (п. 7 / п. 8): countries with duty-exemption treaties; PSAs concluded before 01.01.2009; subsoil contracts with a duty exemption (except royalty payers); from 2027 offshore Caspian contracts when the price is below 95 / 100 / 105 / 110 USD/bbl (2027–2031 / 2032–2036 / 2037–2041 / from 2042).

### 5.3 Averaging period and when a rate takes effect

| Period | Rule | Quote |
|---|---|---|
| 2016-03 … 2023-08 | One rate for a calendar month, chosen by the average price of the "preceding period" = from the 20th two months earlier to the 20th of the month before. Daily value = mean of (min+max)/2 for Urals (Med) and (min+max)/2 for Brent (Dtd); from 02.2023 Kebco instead of Urals. Published by the 25th of the preceding month on the site of «уполномоченного органа в области реализации налоговой и таможенной политики» | «Предшествующий период – начинается с 20 числа за два месяца, до 20 числа месяца, предшествующего месяцу применения вывозных таможенных пошлин»; «5. … в течении месяца применяется одна из ставок … в зависимости от значения средней рыночной цены на сырую нефть за предшествующий период» |
| 2023-09 … | Same window; published by the 28th by «уполномоченный орган в сфере таможенного дела» (the State Revenue Committee) on its site. 169-НҚ adds the source: «"Argus Crude" компании "Argus Media Ltd"», fallback S&P Global «Crude Oil Market Wire» | «1) предшествующий период – период времени, начиная с 20 числа за два месяца до текущего месяца по 20 число месяца, предшествующего текущему месяцу; 2) текущий месяц – календарный месяц применения вывозных таможенных пошлин»; «2) не позднее 28 числа месяца, предшествующего месяцу применения вывозных таможенных пошлин, размещает на своем официальном интернет-ресурсе информацию о средней рыночной цене сырой нефти за предшествующий период» |

Example read in the press: rate for November 2026 ← window 20 September – 20 October 2026.

### 5.4 Is the actual monthly rate published? Yes — as the monthly average price, by the State Revenue Committee (KGD)

- The ministry does not issue a monthly order. The official publication is KGD's page «Средняя рыночная цена сырой нефти» (monthly average price, USD/bbl, since March 2016), from which the rate follows mechanically (table until 08.2023, the rounded price itself after). Old addresses: `https://kgd.gov.kz/ru/content/srednyaya-rynochnaya-cena-syroy-nefti-1` and `https://kgd.gov.kz/ru/node/5453`; described by cdb.kz on 11.03.2016 (https://cdb.kz/sistema/novosti/ob-ofitsialnoy-publikatsii-rynochnoy-tseny-na-syruyu-neft/): «Комитет государственных доходов … ежемесячно не позднее 25-го числа месяца на своем официальном портале публикует среднюю рыночную цену сырой нефти … Главная страница / Деятельность / Таможенное администрирование / Таможенное оформление / Средняя рыночная цена сырой нефти».
- **The page could not be read**: kgd.gov.kz now 301-redirects every old path to the new portal `portal.kgd.gov.kz` (a React application; no such page found in its menu), regional mirrors (`krg.kgd.gov.kz`) do not answer, web.archive.org is not reachable from this environment. A search engine still shows fragments of the table (2016: March 30,7597 … ; 2017: January 50,4908 … December 60,7593; 2018: January 62,9202, February 67,6538, December 71,5140; 2019: January 59,6148, December 61,7653; 2020: January 64,9616, February 65,1874, May 20,6484, December 40,6301; 2026: January–June 63, 64, 69, 90, 122, 118) — these are SEARCH SNIPPETS, NOT READ on a page, and must not be stored. They show the series exists back to 2016-03 with four decimals until 2023 and whole numbers after.
- Monthly news: Reuters (Russian service, reprinted by The Moscow Times), Interfax-Kazakhstan, Argus, inbusiness.kz report each month's rate "по данным мониторинга комитета госдоходов".

### 5.5 Actual monthly rates read in the press (all SECOND-HAND), USD per tonne

| Month | Rate | Avg price, USD/bbl (window) | Source read |
|---|---|---|---|
| 2023-11 | 92 | — | Reuters 28.11.2023 via https://ru.themoscowtimes.com/2023/11/28/eksportnye-poshliny-na-neft-i-nefteprodukty-snizyatsya-v-kazakhstane-na-65-v-deknoya-a114446 («в декабре … до $86 за тонну с $92») |
| 2023-12 | 86 | 86 (20.10–20.11) | same |
| 2024-01 | 79 | 79 (20.11–20.12) | Reuters 27.12.2023 via https://ru.themoscowtimes.com/2023/12/27/eksportnye-poshliny-na-neft-i-nefteprodukty-v-kazakhstane-snizyatsya-na-8-v-yanvdek-a117338 |
| 2024-06 | 86 | — | Reuters 28.06.2024 via https://ru.themoscowtimes.com/2024/06/28/kazakhstan-snizit-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-4-v-iyuliyun-24g-a135296 |
| 2024-07 | 82 | 82 (20.05–20.06) | same |
| 2024-09 | 82 | 82 | Argus, https://www.argusmedia.com/ru/news-and-insights/latest-market-news/2614944-eksportnaya-poshlina-na-neft-v-kazahstane-v-oktyabre-snizilas («в октябре уменьшилась до $77/т с $82/т — в сентябре») |
| 2024-10 | 77 | 77 | same; Reuters 30.10.2024 |
| 2024-11 | 76 | 76 (20.09–20.10) | Reuters 30.10.2024 via https://ru.themoscowtimes.com/2024/10/30/kazakhstan-snizit-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-1-v-noyaokt-a146311 |
| 2024-12 | 74 | — | Reuters 29.12.2024 via https://ru.themoscowtimes.com/2024/12/29/kazakhstan-snizil-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-14-v-yanvdek-a151667 ; https://inbusiness.kz/ru/last/neftyanye-dohody-kazahstana-v-dekabre-upadut |
| 2025-01 | 73 | 73 (20.11–20.12) | same Reuters item |
| 2025-02 | 77 | 77 | Reuters 27.02.2025 via https://ru.themoscowtimes.com/2025/02/27/kazakhstan-povysit-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-08-v-marfev-a156567 ; Argus https://www.argusmedia.com/ru/news-and-insights/latest-market-news/2667202-eksportnaya-poshlina-na-neft-v-kazahstane-v-marte-vyrosla |
| 2025-03 | 78 | 78 (20.01–20.02) | same |
| 2025-04 | 73 | — | Reuters 28.04.2025 via https://ru.themoscowtimes.com/2025/04/28/kazakhstan-snizit-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-v-mae-na-3-k-aprelyu-a162248 |
| 2025-05 | 71 | 71 (20.03–20.04) | same |
| 2025-06 | 65 | 65 (20.04–20.05) | Reuters 27.05.2025 via https://ru.themoscowtimes.com/2025/05/27/kazakhstan-snizit-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-v-iyune-na-85-k-mayu-a164430 |
| 2025-07 | 70 | 70 (20.05–20.06) | Reuters 27.06.2025 via https://ru.themoscowtimes.com/2025/06/27/kazakhstan-povysit-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-v-iyule-na-77-k-iyunyu-a167282 |
| 2025-12 | 64 | — | Reuters 29.12.2025 via https://ru.themoscowtimes.com/2025/12/29/kazakhstan-snizit-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-16-v-yanvdek-a183883 |
| 2026-01 | 63 | 63 (20.11–20.12) | same |
| 2026-02 | 64 | 64 (20.12.2025–20.01.2026) | https://arbatmedia.kz/news-kz/kazaxstan-vpervye-za-mesyacy-podnyal-eksportnuyu-poslinu-na-neft-6532 ; Reuters 02.03.2026 |
| 2026-03 | 69 | 69 (20.01–20.02) | Reuters 02.03.2026 via https://ru.themoscowtimes.com/2026/03/02/kazakhstan-povysil-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-8-v-marfev-26g-a188508 |
| 2026-04 | 90 | 90 (20.02–20.03) | Reuters 27.03.2026 via https://ru.themoscowtimes.com/2026/03/27/kazakhstan-povysil-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-30-v-aprmar-26g-a191045 ; Interfax-Kazakhstan https://www.interfax.kz/ru/financial-and-economic-news/135407 («сообщили в Комитете госдоходов Минфина») |
| 2026-05 | 130 | 122 (20.03–20.04) → band 115–125 | Reuters 28.04.2026 via https://ru.themoscowtimes.com/2026/04/28/kazakhstan-povysit-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-44-v-maeapr-26g-a193915 («до рекордных $130») |
| 2026-06 | 130 | — | https://nationalbusiness.kz/news/kazahstan-snizit-poshlini-na-eksport-nefti-pochti-na-chetvert-247854/ («с июля … со 130 до 99 долларов за тонну», citing Reuters) |
| 2026-07 | 99 | — | same; Reuters 28.07.2026 |
| 2026-08 | 76 | — | Reuters 28.07.2026 via https://ru.themoscowtimes.com/2026/07/28/kazakhstan-snizit-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-23-v-avgiyul-26g-a202000 |
| 2026-09 | 94 | 94 (20.07–20.08) | Reuters 17.09.2026 via https://ru.themoscowtimes.com/2026/09/17/kazakhstan-povysil-eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-na-24-v-senavg-26g-a206319 |
| 2026-10 | **115** | 109 (20.08–20.09) → band 105–115 | Reuters 30.10.2026 («с $115 за тонну в октябре») via https://ru.themoscowtimes.com/2026/10/30/eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-v-kazakhstane-vyrastut-na-26-v-noyaokt-26g-a210075 . CONFLICT: Reuters of 29.09.2026 said «до $109 за тонну» (https://ru.themoscowtimes.com/2026/09/29/eksportnye-poshliny-na-neft-i-svetlye-nefteprodukty-v-kazakhstane-vyrastut-na-16-v-oktsen-26g-a207252) — that applied the formula above its 105 limit; the rule gives 115 and Reuters itself used 115 a month later |
| 2026-11 | 145 | 129 (20.09–20.10) → band 125–135 | Reuters 30.10.2026, same URL |

28 months read. NOT found: 2016-03 … 2023-10 (92 months; no monthly press series located for the step-table years), 2024-02 … 2024-05, 2024-08, 2025-08 … 2025-11.
Consistency check: in every month with both figures the rate equals the reported price (formula) or the band rate (above 105).

---

## 6. Rent tax on export

### 6.1 Crude oil and gas condensate — one scale, 2009-01 … 2026 (no change of any number)

| # | world price from, USD/bbl (exclusive) | to (inclusive) | rate, % |
|---|---|---|---|
| 1 | 0 | 20 | 0 |
| 2 | 20 | 30 | 0 |
| 3 | 30 | 40 | 0 |
| 4 | 40 | 50 | 7 |
| 5 | 50 | 60 | 11 |
| 6 | 60 | 70 | 14 |
| 7 | 70 | 80 | 16 |
| 8 | 80 | 90 | 17 |
| 9 | 90 | 100 | 19 |
| 10 | 100 | 110 | 21 |
| 11 | 110 | 120 | 22 |
| 12 | 120 | 130 | 23 |
| 13 | 130 | 140 | 25 |
| 14 | 140 | 150 | 26 |
| 15 | 150 | 160 | 27 |
| 16 | 160 | 170 | 29 |
| 17 | 170 | 180 | 30 |
| 18 | 180 | 190 | 32 |
| 19 | 190 | — | 32 |

(Row 19 is printed «До 200 долларов США за баррель и выше | 32».)

| Period | Act, article | Editions read (ADILET) | Wording of the object |
|---|---|---|---|
| 2009-01 … 2015-12 | Tax Code 2008, **art. 303** | 10.12.2008 (as enacted), 30.12.2009, 31.12.2010, 31.12.2012 — identical | «При экспорте сырой нефти, газового конденсата рентный налог на экспорт исчисляется по следующим ставкам» |
| 2016-01 … 2017-12 | same, as amended by Law of 03.12.2015 N 432-V (in force 01.01.2016) | 31.12.2015, 31.12.2016, final | «При экспорте нефти сырой и нефтепродуктов сырых …» (only the name of the object changed) |
| 2018-01 … 2025-12 | Tax Code 2017, **art. 716** | as enacted, 31.12.2018, 31.12.2019, 01.01.2021, 01.01.2023, 01.01.2025, final — table identical | same |
| 2026-01 … | Tax Code 2025, art. 749 | as enacted = current | same; «Для целей настоящего раздела нефтью сырой и нефтепродуктами сырыми признаются товары, классифицируемые в субпозиции 2709 00 …» (art. 746) |

World price: 2025 Code art. 748 → art. 776 п. 3 (same Argus quotations as in 1.3), converted with the weighted-average barrel factor of the exported lots. Tax period: calendar quarter (art. 750). Who pays in 2026: art. 835 — until 01.01.2027 only payers of the alternative subsoil-use tax are excluded; from 2027 MET payers on hydrocarbons are excluded too.

### 6.2 Coal

| Period | Rate, % of the export value | Act | Quote |
|---|---|---|---|
| 2009-01 … 2017-12 | 2.1 | Tax Code 2008 art. 303, last paragraph (all seven editions read) | «При экспорте угля рентный налог на экспорт исчисляется по ставке 2,1 процента.» |
| 2018-01 … 2020-12 | **4.7** | Tax Code 2017 art. 716 as enacted (editions 25.12.2017, 31.12.2018, 31.12.2019) | «При экспорте угля рентный налог на экспорт исчисляется по ставке 4,7 процента.» |
| 2021-01 … | abolished | Law of 10.12.2020 N 382-VI; footnote: «Статья 716 с изменением, внесенным Законом РК от 10.12.2020 № 382-VI (вводится в действие с 01.01.2021)»; edition of 01.01.2021 has no coal sentence; art. 713 names only exporters of crude oil; Tax Code 2025 art. 746–749 have no coal | — |

(The abolition coincides with MET on coal rising from 0 to 2.7 % on 01.01.2021 by the same law.)

---

## 7. Reduced VAT rates — Tax Code 2025, art. 503

Source: ADILET `K2500000214`, art. 503 identical as enacted (18.07.2025) and current — https://adilet.zan.kz/rus/docs/K2500000214. Code in force 01.01.2026.

| Rate, % | From | To | Applies to | Paragraph |
|---|---|---|---|---|
| 16 | 2026-01 | — | standard: taxable turnover and taxable import | п. 1 |
| 5 | 2026-01 | 2026-12 | sale and import of medicines; medical devices, their components and technical aids for the disabled; medical services | п. 2 |
| 10 | 2027-01 | — | the same goods and services | п. 2 |
| 10 | 2026-01 | — | sale of domestic periodical print publications | п. 3 |
| 0 | 2026-01 | — | turnovers listed in chapter 47 (exports etc.) | п. 4 |

No other reduced rate exists in the Code (all other references to art. 503 point to these paragraphs).

Exact wording
- п. 1: «Если иное не установлено настоящей статьей, ставка налога на добавленную стоимость составляет 16 процентов и применяется к размеру облагаемого оборота и облагаемого импорта.»
- п. 2: «Ставка налога на добавленную стоимость составляет с 1 января 2026 года – 5 процентов, с 1 января 2027 года – 10 процентов и применяется: 1) к размеру облагаемого оборота по реализации и импорта: лекарственных средств, за исключением товаров, предусмотренных подпунктом 28) статьи 474 настоящего Кодекса и подпунктом 17) пункта 1 статьи 479 настоящего Кодекса; медицинских изделий, комплектующих медицинских изделий, а также технических вспомогательных (компенсаторных) средств в соответствии с законодательством Республики Казахстан о социальной защите. Перечень лекарственных средств, медицинских изделий, комплектующих медицинских изделий, а также технических вспомогательных (компенсаторных) средств … устанавливается Правительством Республики Казахстан; 2) к размеру облагаемого оборота по реализации медицинских услуг, в том числе оказываемых в комплексе, в соответствии с законодательством Республики Казахстан субъектом здравоохранения, имеющим лицензию на медицинскую деятельность. Положения настоящего подпункта не применяются по медицинским услугам, предусмотренным подпунктом 28) статьи 474 настоящего Кодекса.»
- п. 3: «Ставка налога на добавленную стоимость составляет 10 процентов и применяется к размеру оборота по реализации отечественных периодических печатных изданий.»
- п. 4: «Обороты по реализации товаров, работ, услуг, указанные в главе 47 настоящего Кодекса, облагаются налогом на добавленную стоимость по нулевой ставке. В случае неподтверждения … указанный оборот … подлежит обложению налогом на добавленную стоимость по ставке, указанной в пункте 1 настоящей статьи.»
- п. 5 (deregistration): stocks at the rate «действовавшая на дату снятия лица с регистрационного учета»; fixed assets at the rate «действовавшая на дату их приобретения».
- Scope note: art. 474 пп. 28) keeps an EXEMPTION: «лекарственных средств и медицинских услуг, в том числе оказываемых в комплексе, … субъектом здравоохранения, имеющим лицензию на медицинскую деятельность: в рамках гарантированного объема бесплатной медицинской помощи и обязательного медицинского страхования; для лечения орфанных и социально значимых заболеваний. Перечень … устанавливается Правительством Республики Казахстан». The 5 % → 10 % rate covers the rest.

---

## What could not be read

1. **KGD's official monthly table of the average crude price** (the legal basis of every month's duty since 2016-03): old kgd.gov.kz URLs redirect to the new portal, regional mirrors and web.archive.org are unreachable. Only search-engine fragments were seen (not usable). Hence no actual duty rates for 2016-03 … 2023-10, and gaps in 2024 (Feb–May, Aug) and 2025 (Aug–Nov).
2. **PP of 20.02.2023 N 146** (restricted, «для служебного пользования»): changed the fuel excise table for 2023 (until 01.01.2024); text not in the register.
3. Monthly values of **Цср / Цсрв** (the wholesale price that drives the fuel excise since May 2025): supplied between ministries, no published series looked for — so the actual monthly excise above the base cannot be computed from the acts alone.
4. The **"выравнивающий коэффициент"** for domestic oil sales from 2027 and the Government's rates for low-margin fields (art. 778 п. 2): delegated acts, not searched.
5. How the 2027 matrix treats prices **between** the column heads (20, 30, … 200): the law is silent.
6. 2008 Tax Code editions between the sampled dates (160 stored editions; 7 read): art. 336 and art. 303 footnotes list no other amending law, so no intermediate change is expected, but the intermediate editions were not opened.
7. The Government lists under art. 503 п. 2 and art. 474 пп. 28) (which medicines, devices and services fall under the reduced rate and which stay exempt); art. 479 п. 1 пп. 17) (exempt import) was not opened.
