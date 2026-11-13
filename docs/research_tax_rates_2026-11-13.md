# Kazakhstan statutory tax and contribution rates — history by effective date

Compiled 2026-11-13. Read-only research; nothing in the repo was changed.

## How to read this file

- **Status** values
  - `CONFIRMED` — the value and the effective date were read in the text of the legal act on a page fetched in this session.
  - `SECOND-HAND` — read on a fetched non-law page (PwC, news, legal-news site).
  - `UNCONFIRMED` — not seen on any fetched page. Where a number is shown in an UNCONFIRMED row it is an *expectation to be checked*, never a finding; do not load it.
- **Source of law texts.** `adilet.zan.kz` is now a JavaScript-only application: every document URL returns an empty shell (title "НЦПС «Әділет»", no text) to both WebFetch and curl, and its `/api/` returns 401. All law texts below were therefore read on **`zakon.uchet.kz/rus/docs/<ID>`**, a mirror that uses the same document IDs as adilet and reproduces the ИЗПИ/РЦПИ consolidated text with its amendment footnotes ("Сноска …"). Quotes are verbatim from that mirror. The mirror serves only the **latest consolidated edition** of each act (its `/rus/history/...` pages are empty shells), so earlier levels were recovered from the *amending laws* themselves, each fetched separately.
- Effective month = month the level started to apply. Where an act enters into force "N days after first official publication" and the publication date was not on the page, the month is marked `~` and the exact day is unconfirmed.
- Editions seen: Tax Code 2025 (K2500000214) "с изменениями на: 01.07.2026"; Tax Code 2017 (K1700000120) final edition; Tax Code 2008 (K080000099_) final edition; Tax Code 2001 (K010000209_) final edition; Law of 24.04.1995 N 2235 final edition.

---

## 1. VAT — standard rate (%)

| Effective | Value | Legal act | URL fetched | Wording seen | Status |
|---|---|---|---|---|---|
| before 2001-07 | 20 | Law of 24.04.1995 N 2235 "О налогах и других обязательных платежах в бюджет", art. 62(1), as it stood before Law of 03.05.2001 N 183 | https://zakon.uchet.kz/rus/docs/Z010000183_ | «В пункте 1 статьи 62 цифру "20" заменить цифрой "16"» | CONFIRMED (level); start date of 20 % (expected 1995-07) UNCONFIRMED |
| 2001-07 | 16 | Law of 03.05.2001 N 183, art. 1 п. 3, art. 2 | https://zakon.uchet.kz/rus/docs/Z010000183_ ; https://zakon.uchet.kz/rus/docs/Z950002235_ | «Статья 2. Настоящий Закон вводится в действие с 1 июля 2001 года»; 1995 law art. 62: «равняется 16 процентам» | CONFIRMED |
| 2002-01 | 16 | Tax Code of 12.06.2001 N 209, art. 245 (Code in force from 1 Jan 2002 per Law N 210 art. 1) | https://zakon.uchet.kz/rus/docs/Z010000210_ ; https://zakon.uchet.kz/rus/docs/Z030000475_ | «Ввести в действие Кодекс … с 1 января 2002 года»; Law 475: «в пункте 1 цифры "16" заменить цифрами "15"» | CONFIRMED (16 inferred from the replaced figure) |
| 2004-01 | 15 | Law of 04.07.2003 N 475, art. 1 п. 33), art. 2 | https://zakon.uchet.kz/rus/docs/Z030000475_ | «в статье 245: в пункте 1 цифры "16" заменить цифрами "15"»; «вводится в действие с 1 января 2004 года» | CONFIRMED |
| 2007-01 | 14 | Law of 07.07.2006 N 177, art. 1 п. 2 пп. 20), art. 2 | https://zakon.uchet.kz/rus/docs/Z060000177_ | «в пунктах 1 и 3 статьи 245: цифры "15" заменить цифрами "14"»; «вводится в действие с 1 января 2007 года» | CONFIRMED |
| 2008-01 | 13 | same law, абзац третий пп. 20) | https://zakon.uchet.kz/rus/docs/Z060000177_ | «цифры "14" заменить цифрами "13"» … «абзаца третьего подпункта 20) … вводятся в действие с 1 января 2008 года» | CONFIRMED |
| 2009-01 | 12 | same law, абзац четвертый пп. 20); then Tax Code of 10.12.2008 N 99-IV, art. 268(1) | https://zakon.uchet.kz/rus/docs/Z060000177_ ; https://zakon.uchet.kz/rus/docs/K080000099_ | «цифры "13" заменить цифрами "12"» … «вводится в действие с 1 января 2009 года»; art. 268: «ставка … составляет 12 процентов» | CONFIRMED |
| 2018-01 | 12 | Tax Code of 25.12.2017 N 120-VI, art. 422(1) | https://zakon.uchet.kz/rus/docs/K1700000120 | «Ставка налога на добавленную стоимость составляет 12 процентов» | CONFIRMED |
| 2026-01 | **16** | Tax Code of 18.07.2025 N 214-VIII, art. 503(1); art. 848(1) | https://zakon.uchet.kz/rus/docs/K2500000214 | «ставка налога на добавленную стоимость составляет 16 процентов»; «Настоящий Кодекс вводится в действие с 1 января 2026 года» | CONFIRMED |

**2026 reduced rates (art. 503, same URL) — CONFIRMED**
- Medicines, medical devices, medical services: «с 1 января 2026 года – 5 процентов, с 1 января 2027 года – 10 процентов» (art. 503(2)).
- Domestic periodical print publications: 10 % (art. 503(3)).
- Zero rate: exports etc. (art. 503(4)).
- PwC cross-check (SECOND-HAND, https://taxsummaries.pwc.com/kazakhstan/corporate/other-taxes, last reviewed 23 July 2026): "The current VAT rate is 16%"; "5% (10% from 2027) for sale and import of medicines"; "10% for sale of domestic periodicals".

---

## 2. Corporate income tax (%)

| Effective | Value | Legal act | URL fetched | Wording seen | Status |
|---|---|---|---|---|---|
| ≤2001 | 30 (10 for land users) | Law of 24.04.1995 N 2235, art. 30 | https://zakon.uchet.kz/rus/docs/Z950002235_ | «Налогооблагаемый доход юридического лица подлежит обложению налогом по ставке 30 процентов» | CONFIRMED (level; start month of the 1995 law not checked) |
| 2002-01 | 30 | Tax Code 2001, art. 135(1) | https://zakon.uchet.kz/rus/docs/K010000209_ | «подлежит обложению налогом по ставке 30 процентов» (land as main means of production: 10 %) | CONFIRMED |
| 2009-01 | 20 | Tax Code 2008, art. 147(1) | https://zakon.uchet.kz/rus/docs/K080000099_ | «подлежит обложению налогом по ставке 20 процентов» | CONFIRMED (final edition). See note below |
| 2018-01 | 20 | Tax Code 2017, art. 313(1) | https://zakon.uchet.kz/rus/docs/K1700000120 | «подлежит обложению налогом по ставке 20 процентов»; agricultural producers 10 % (art. 313(2)) | CONFIRMED |
| 2026-01 | 20 standard | Tax Code 2025, art. 357(2) пп. 5) | https://zakon.uchet.kz/rus/docs/K2500000214 | «от иной деятельности … – 20 процентов» | CONFIRMED |

**Note on 2009–2010.** The 2008 Code as enacted wrote the *target* rate 15 % into art. 147(1), with higher transitional rates for the first years; the scheduled cuts never applied. Evidence fetched: Law of 26.11.2010 N 356-IV, art. 1 п. 3): «в статье 147: в пункте 1 цифры "15" заменить цифрами "20"», in force 1 Jan 2011 (https://zakon.uchet.kz/rus/docs/Z1000000356). The transitional text that set 20 % for 2009 and 2010 (and the planned 17.5 %) was **not** seen — it has been removed from the consolidated intro law (Z080000100_). So: 20 % from 2011-01 is CONFIRMED by the amending law; 20 % for 2009–2010 is consistent with every source read but the transitional article itself is UNCONFIRMED.

**2026 differentiated rates — Tax Code 2025, art. 357(2), CONFIRMED** (https://zakon.uchet.kz/rus/docs/K2500000214)

| Activity | Rate | Wording |
|---|---|---|
| Agricultural / aquaculture producers (incl. processing of own produce) | 3 | «– 3 процента» (пп. 1) |
| Agricultural cooperatives (other) | 6 | «– 6 процентов» (пп. 2) |
| Social-sphere organisations | 5 in 2026; 10 from 2027-01 | «5 процентов за налоговый период с 1 января 2026 года по 31 декабря 2026 года, с 1 января 2027 года – 10 процентов» (пп. 3) |
| Banks (second-tier), **excluding** income from lending to businesses; casinos, slot-machine halls, totalisators, bookmakers | 25 | «от следующих видов деятельности – 25 процентов: банковской деятельности … за исключением налогооблагаемого дохода, полученного от деятельности по кредитованию субъектов предпринимательства … казино, зала игровых автоматов, тотализатора и букмекерской конторы» (пп. 4) |
| Other | 20 | пп. 5) |
| Withholding at source (residents) / branch profit tax | 15 / 15 | art. 357(1) пп. 2), 4) |

PwC cross-check (SECOND-HAND, https://taxsummaries.pwc.com/kazakhstan/corporate/taxes-on-corporate-income, reviewed 23 July 2026): "general tax rate … is 20%"; "25% for banks and entities providing services of casinos…"; "5% in 2026 and 10% from 2027 for entities operating in a social sphere"; "3% for … agricultural products or aquaculture".

---

## 3. Personal income tax (%)

| Effective | Value | Legal act | URL fetched | Wording seen | Status |
|---|---|---|---|---|---|
| ≤2001 (final edition of 1995 law) | progressive 5 / 10 / 20 / 30 (bands: ≤15, 15–30, 30–65, >65 annual calculation indices) | Law of 24.04.1995 N 2235, art. 29 (edition of Law 08.12.1997 N 200, amended 1999) | https://zakon.uchet.kz/rus/docs/Z950002235_ | «до 15-кратного годового расчетного показателя 5 процентов … + 10 процентов … + 20 процентов … от 65-кратного … + 30 процентов» | CONFIRMED (final edition only; earlier scales incl. the expected 40 % top rate UNCONFIRMED) |
| 2002-01 – 2003-12 | progressive (expected 5–30) | Tax Code 2001, art. 145, original edition | — | original edition not obtainable | UNCONFIRMED |
| 2004-01 | progressive 5 / 8 / 13 / 15 / 20 (bands: ≤15, 15–40, 40–200, 200–600, >600 annual calculation indices) | Law of 04.07.2003 N 475, art. 1 п. 21), art. 2 | https://zakon.uchet.kz/rus/docs/Z030000475_ | «до 15-кратного … 5 процентов … + 8 процентов … + 13 процентов … + 15 процентов … от 600-кратного … + 20 процентов»; «вводится в действие с 1 января 2004 года» | CONFIRMED |
| 2007-01 | flat 10 | Law of 07.07.2006 N 177, art. 1 п. 2 пп. 10), art. 2 | https://zakon.uchet.kz/rus/docs/Z060000177_ | «Доходы налогоплательщика … подлежат обложению налогом по ставке 10 процентов» | CONFIRMED |
| 2009-01 | flat 10 | Tax Code 2008, art. 158(1) | https://zakon.uchet.kz/rus/docs/K080000099_ | «облагаются налогом по ставке 10 процентов» | CONFIRMED |
| 2018-01 | flat 10 | Tax Code 2017, art. 320(1) | https://zakon.uchet.kz/rus/docs/K1700000120 | «Доходы налогоплательщика облагаются налогом по ставке 10 процентов» | CONFIRMED |
| 2026-01 | progressive 10 / 15; threshold 8 500 MRP of annual taxable income | Tax Code 2025, art. 363 пп. 1) | https://zakon.uchet.kz/rus/docs/K2500000214 | «до 8500-кратного месячного расчетного показателя* (включительно) 10 процентов; свыше … + 15 процентов с суммы, превышающей его»; «*… месячный расчетный показатель, действующий на 1 января соответствующего финансового года» | CONFIRMED |

Other 2026 PIT rates (same article, CONFIRMED): private practice 9 %; individual entrepreneurs / farms on the general regime 10 % up to 230 000 MRP and 15 % above.

**Dividends (individuals)**

| Effective | Value | Legal act | URL fetched | Wording seen | Status |
|---|---|---|---|---|---|
| 2004–2006 | (expected 15) | Tax Code 2001, art. 145(3), pre-2007 edition | — | not seen | UNCONFIRMED |
| 2007-01 | 5 | Law of 07.07.2006 N 177, art. 1 п. 2 пп. 10) | https://zakon.uchet.kz/rus/docs/Z060000177_ | «Доходы в виде дивидендов облагаются по ставке 5 процентов» | CONFIRMED |
| 2009-01 | 5 | Tax Code 2008, art. 158(2) | https://zakon.uchet.kz/rus/docs/K080000099_ | «Доходы в виде дивидендов … облагаются по ставке 5 процентов» | CONFIRMED |
| 2018-01 | 5 | Tax Code 2017, art. 320(2) (text of п. 2 no longer displayed) | https://zakon.uchet.kz/rus/docs/K1700000120 | only «2. Исключен Законом РК от 11.07.2022 № 135-VII (вводится в действие с 01.01.2023)» | UNCONFIRMED value (5 % is inferred from the identical 2008 article) |
| 2023-01 | 10 (special dividend rate abolished → general rate) | Law of 11.07.2022 N 135-VII, art. 1 п. 12) | https://zakon.uchet.kz/rus/docs/Z2200000135 | «в статье 320: в пункте 1 слова ", за исключением доходов, указанных в пункте 2 настоящей статьи," исключить; пункт 2 исключить» | CONFIRMED |
| 2026-01 | 5 up to 230 000 MRP per year; 15 above | Tax Code 2025, art. 363 пп. 3) | https://zakon.uchet.kz/rus/docs/K2500000214 | «до 230 000-кратного месячного расчетного показателя* (включительно) 5 процентов … + 15 процентов с суммы, превышающей его» | CONFIRMED |

---

## 4. Social tax (%)

| Effective | Value | Legal act | URL fetched | Wording seen | Status |
|---|---|---|---|---|---|
| before 2001-07 | 26 | Law of 24.04.1995 N 2235, art. 104-9(1) before Law N 183 | https://zakon.uchet.kz/rus/docs/Z010000183_ | «В статье 104-9: в пункте 1 цифру "26" заменить цифрой "21"» | CONFIRMED (level); start date (expected 1999-01) UNCONFIRMED |
| 2001-07 | 21 | Law of 03.05.2001 N 183, art. 1 п. 11, art. 2 | https://zakon.uchet.kz/rus/docs/Z010000183_ ; https://zakon.uchet.kz/rus/docs/Z950002235_ | «вводится в действие с 1 июля 2001 года»; art. 104-9: «по ставке 21 процентов от фонда оплаты труда» | CONFIRMED |
| 2002-01 – 2003-12 | (expected 21) | Tax Code 2001, art. 317, original edition | — | not seen | UNCONFIRMED |
| 2004-01 | regressive 20 / 15 / 12 / 9 / 7 (bands of employee income: ≤15, 15–40, 40–200, 200–600, >600 annual calculation indices) | Law of 04.07.2003 N 475, art. 1 п. 43), art. 2 | https://zakon.uchet.kz/rus/docs/Z030000475_ | «до 15-кратного … 20 процентов … + 15 процентов … + 12 процентов … + 9 процентов … + 7 процентов» | CONFIRMED |
| 2008-01 | regressive 13 / 11 / 9 / 7 / 5 (same bands) | Law of 07.07.2006 N 177, art. 1 п. 2 пп. 22), art. 2 п. 1) | https://zakon.uchet.kz/rus/docs/Z060000177_ ; https://zakon.uchet.kz/rus/docs/K010000209_ | «статью 317 изложить в следующей редакции … 13 процентов … + 11 процентов … + 5 процентов»; «подпунктов 22) и 23) … вводятся в действие с 1 января 2008 года» | CONFIRMED |
| 2009-01 | flat 11 | Tax Code 2008, art. 358(1) | https://zakon.uchet.kz/rus/docs/K080000099_ | «социальный налог исчисляется по ставке 11 процентов» | CONFIRMED |
| 2018-01 | 9.5 | Tax Code 2017, art. 485(1) | https://zakon.uchet.kz/rus/docs/K1700000120 | «с 1 января 2018 года – 9,5 процента» | CONFIRMED |
| 2025-01 | 11 | same | same | «с 1 января 2025 года – 11 процентов» | CONFIRMED |
| 2026-01 | 6 (1.8 for agricultural production) | Tax Code 2025, art. 557(1)–(2) | https://zakon.uchet.kz/rus/docs/K2500000214 | «Социальный налог исчисляется по ставке 6 процентов»; «по ставке 1,8 процента» | CONFIRMED |

**Two points that differ from the expected path in the brief**
1. **Flat 11 % starts 2009-01, not 2008-01.** 2008 was a separate regressive scale 13–5 %; the 2004 scale 20–7 % ran through 2007 (Law 177 changed art. 317 only from 1 Jan 2008; a further amendment by Law of 11.12.2006 N 201 "с 1 января 2007 г." is listed in the footnote of art. 317 but its content was not checked).
2. **The headline rate is gross of social contributions until 2025.** Tax Code 2017 art. 486(3): «Сумма социального налога, подлежащая уплате в бюджет, определяется как разница между исчисленным социальным налогом и суммой социальных отчислений». So the *net* social tax was 9.5 − 3.5 = 6 % (2018–2024) and 11 − 5 = 6 % (2025). No such offset wording was found in the 2025 Code (art. 558), i.e. 6 % in 2026 is payable on top of the 5 % social contributions. The equivalent offset rule for 2005–2017 was not located in the 2008/2001 Code texts (UNCONFIRMED for those years).

---

## 5. Social contributions to the State Social Insurance Fund (СО), % of the contribution base, paid by the employer

| Effective | Value | Legal act | URL fetched | Wording seen | Status |
|---|---|---|---|---|---|
| 2005-01 | 1.5 | Law of 25.04.2003 N 405 "Об обязательном социальном страховании", art. 14(1) | https://zakon.uchet.kz/rus/docs/Z030000405_ | «с 1 января 2005 года – 1,5 процента от объекта исчисления социальных отчислений» | CONFIRMED |
| 2006-01 | 2 | same | same | «с 1 января 2006 года – 2 процента» | CONFIRMED |
| 2007-01 | 3 | same | same | «с 1 января 2007 года – 3 процента» | CONFIRMED |
| 2009-01 | 4 | same | same | «с 1 января 2009 года – 4 процента» | CONFIRMED |
| 2010-01 | 5 | same | same | «с 1 января 2010 года – 5 процентов» | CONFIRMED |
| 2018-01 | 3.5 | same; then Law of 26.12.2019 N 286-VI, art. 14(1) | same; https://zakon.uchet.kz/rus/docs/Z1900000286 | «с 1 января 2018 года – 3,5 процента» | CONFIRMED |
| 2025-01 | 5 | Social Code of 20.04.2023 N 224-VII, art. 244(1) | https://zakon.uchet.kz/rus/docs/K2300000224 | «в размере 3,5 процента …, с 1 января 2025 года – 5 процентов» | CONFIRMED |
| 2026-01 | 5 (unchanged) | same (edition amended by Law 18.07.2025 N 215-VIII) | same | same wording | CONFIRMED |

There is no 2008 step: the schedule goes 3 (2007) → 4 (2009). PwC cross-check (SECOND-HAND): "Obligatory social insurance contributions are payable by employers at the rate of 5%".

---

## 6. Mandatory pension contributions

**Employee (ОПВ), % of monthly income**

| Effective | Value | Legal act | URL fetched | Wording seen | Status |
|---|---|---|---|---|---|
| 1998-01 (law of 1997) | 10 | Law of 20.06.1997 N 136 "О пенсионном обеспечении", art. 22-1(1) | https://zakon.uchet.kz/rus/docs/Z970000136_ | «устанавливаются в размере десяти процентов от ежемесячного дохода работника» | CONFIRMED (level); the 1 Jan 1998 start is the system start date referred to throughout the law, the commencement clause itself was not read |
| 2013-06 | 10 | Law of 21.06.2013 N 105-V, art. 25(1) | https://zakon.uchet.kz/rus/docs/Z1300000105 | «в размере 10 процентов от ежемесячного дохода» | CONFIRMED |
| 2023-07 → 2026 | 10 | Social Code, art. 249(1) | https://zakon.uchet.kz/rus/docs/K2300000224 | «в размере 10 процентов от ежемесячного дохода»; cap 50 minimum wages | CONFIRMED |

**Employer (ОПВР), % of the employee's monthly income** — Social Code art. 251(1), https://zakon.uchet.kz/rus/docs/K2300000224 — all CONFIRMED

| Effective | Value | Wording |
|---|---|---|
| 2024-01 | 1.5 | «с 1 января 2024 года – в размере 1,5 процента» |
| 2025-01 | 2.5 | «с 1 января 2025 года – в размере 2,5 процента» |
| 2026-01 | 3.5 | «с 1 января 2026 года – в размере 3,5 процента» |
| 2027-01 | 4.5 (legislated) | «с 1 января 2027 года – в размере 4,5 процента» |
| 2028-01 | 5 (legislated) | «с 1 января 2028 года – в размере 5 процентов» |

Not covered: mandatory *professional* pension contributions (5 %, hazardous jobs only, Law 105-V art. 26 / Social Code art. 250).

---

## 7. Mandatory social medical insurance — Law of 16.11.2015 N 405-V "Об обязательном социальном медицинском страховании"

URL fetched: https://zakon.uchet.kz/rus/docs/Z1500000405 — all CONFIRMED

**Employer deductions (ООСМС), art. 27(1)**

| Effective | Value | Wording |
|---|---|---|
| 2017-07 | 1 | «с 1 июля 2017 года – 1 процента от объекта исчисления отчислений» |
| 2018-01 | 1.5 | «с 1 января 2018 года – 1,5 процентов» |
| 2020-01 | 2 | «с 1 января 2020 года – 2 процентов» |
| 2022-01 | 3 | «с 1 января 2022 года – 3 процентов» |
| 2026 | 3 (no later step in the current edition) | — |

**Employee contributions (ВОСМС), art. 28(1)**

| Effective | Value | Wording |
|---|---|---|
| 2020-01 | 1 | «с 1 января 2020 года – 1 процента от объекта исчисления взносов» |
| 2021-01 | 2 | «с 1 января 2021 года – 2 процентов» |
| 2026 | 2 (no later step in the current edition) | — |

Base cap seen in the current edition (art. 27(2-2)): employer base «не должен превышать 40-кратный минимальный размер заработной платы». Self-employed / individual entrepreneurs: 5 % from 2020-01 (art. 28(3)–(4)).

---

## 8. Export customs duty on crude oil (USD per tonne; HS 2709 00 900)

**How it is set.** Until 2015 by Government resolution (first inside PP N 1036 of 15.10.2005 on duties on oil products, later PP N 520 of 07.06.2010); from mid-2015 by order of the Minister of National Economy, later the Minister of Trade and Integration. 2008: computed from the monitored world price; 2010–Feb 2016: fixed USD/tonne; from 1 March 2016: tied to the average world price.

| Effective | Value | Legal act | URL fetched | Wording seen | Status |
|---|---|---|---|---|---|
| ~2008-05 | 109.91 | PP of 08.04.2008 N 328 (amending PP N 1036); "30 calendar days after first official publication" | https://zakon.uchet.kz/rus/docs/P080000328_ | «"2709 00 900 0 Сырая нефть 109,91»; formula rule for prices «свыше 138,6 долларов за 1 тонну» | CONFIRMED (rate); exact start day UNCONFIRMED |
| 2008-Q4 | (expected ≈203.8) | — | — | no act found | UNCONFIRMED |
| ~2009-01 | 139.79 | PP of 05.12.2008 N 1162; 30 days after publication | https://zakon.uchet.kz/rus/docs/P080001162_ | «"Ставка пошлины (в долларах за 1000 кг)" "139,79", …» | CONFIRMED (rate); start day UNCONFIRMED; superseded within weeks |
| ~2009-01 | 0 | PP of 24.12.2008 N 1253; 30 days after publication | https://zakon.uchet.kz/rus/docs/P080001253_ | «"Ставка пошлины (в долларах за 1000 кг)" "0", "0", "61,86", …»; «слова "сырую нефть и" исключить» | CONFIRMED (rate); start day UNCONFIRMED |
| 2009-01 | not applied to oil subject to the new rent tax on export | PP of 24.12.2008 N 1234 | https://zakon.uchet.kz/rus/docs/P080001234_ | «не применяются в отношении … вывоза сырой нефти, подлежащей обложению рентным налогом на экспортируемую сырую нефть с 1 января 2009 года» | CONFIRMED |
| ~2010-08 | 20 | PP of 13.07.2010 N 709; 30 days after publication | https://zakon.uchet.kz/rus/docs/P100000709_ | «"Ставка пошлины (в долларах за 1000 кг)" "20", "99,71", …» | CONFIRMED (rate); start day UNCONFIRMED |
| 2011-01 (expected) | 40 | amending act of late 2010 not found | — | — | UNCONFIRMED date. Level confirmed from 2012-01 at the latest ↓ |
| 2012-01 | 40 | PP of 31.12.2011 N 1739 (new annex to PP N 1036), in force 1 Jan 2012 | https://zakon.uchet.kz/rus/docs/P1100001739 | «2709 00 900 6 Сырая нефть 40»; «вводится в действие с 1 января 2012 года» | CONFIRMED |
| ~2013-04 | 60 | PP of 02.04.2013 N 321; 10 days after publication | https://zakon.uchet.kz/rus/docs/P1300000321 | «строку «2709 00 900 9 Сырая нефть 40» изложить в новой редакции: «2709 00 900 9 Сырая нефть 60»» | CONFIRMED (rate); start day UNCONFIRMED |
| ~2014-03 | 80 | PP of 11.03.2014 N 211 (amending PP N 520); from first official publication | https://zakon.uchet.kz/rus/docs/P1400000211 | ««Нефть сырая – 60 долларов 60 долларов» изложить в следующей редакции: «… Нефть сырая – 80 долларов 80 долларов»» | CONFIRMED (rate); start day UNCONFIRMED |
| ~2015-03 | 60 | PP of 17.03.2015 N 145 (amending PP N 520); from first official publication | https://zakon.uchet.kz/rus/docs/P1500000145 | ««… НеФть сырая - 80 долларов 80 долларов» изложить в следующей редакции: «… Нефть сырая - 60 долларов 60 долларов»» | CONFIRMED (rate); start day UNCONFIRMED |
| 2015-07 | 60, "постоянно" | Order of the Minister of National Economy of 27.05.2015 N 405 (reg. N 11473); PP N 520 repealed by PP 15.10.2015 N 829 | https://zakon.uchet.kz/rus/docs/V1500011473 ; https://zakon.uchet.kz/rus/docs/V1600012895 | Order N 18 replaces the row «Нефть сырая – 60 долларов 60 долларов постоянно» | CONFIRMED |
| 2016-01 | 40 | Order of 20.01.2016 N 18 (reg. N 12895), applies to relations from 1 Jan 2016 | https://zakon.uchet.kz/rus/docs/V1600012895 | «Нефть сырая – 40 долларов 40 долларов До 31 декабря 2016 года включительно»; «распространяется на отношения, возникшие с 1 января 2016 года» | CONFIRMED |
| 2016-03 | progressive scale tied to the world price | Order of 17.02.2016 N 81 (reg. N 13217), applies to relations from 1 Feb 2016; 40 USD kept until 1 March 2016 | https://zakon.uchet.kz/rus/docs/V1600013217 ; https://cdb.kz/sistema/novosti/vyvoznye-tamozhennye-poshliny-utverzhden-perechen-tovarov-i-pravila-rascheta-razmera-stavok/ | order: «вводится в действие со дня его первого официального опубликования и распространяется на отношения, возникшие с 1 февраля 2016 года»; cdb.kz news of 29.02.2016: «До 1 марта 2016 года ЭТП на сырую нефть действует в размере 40 долларов США за 1 тонну нефти» | Regime change CONFIRMED (order) + SECOND-HAND (1 March date). **The original 2016 scale table was not obtainable** (only the later edition is served) → UNCONFIRMED |
| by 2023-08 at the latest | formula (below) | Order N 81 in the edition of Order of 14.08.2023 N 311-НҚ | https://zakon.uchet.kz/rus/docs/V1600013217 | see below | CONFIRMED for the 2023 edition; whether the formula dates from 2016 or from a later amendment is UNCONFIRMED |
| 2026-05 / 2026-08 | same formula, new act | Order of the Minister of Trade and Integration of 17.04.2026 N 169-НҚ; Order N 81 repealed by Order of 29.07.2026 N 228-НҚ | https://cdb.kz/sistema/pravovaya-baza/ob-utverzhdenii-perechnya-tovarov-v-otnoshenii-kotorykh-primenyayutsya-vyvoznye-tamozhennye-poshliny/ ; https://zakon.uchet.kz/rus/docs/V2600039445 | 169-НҚ: «вводится в действие по истечении десяти календарных дней»; N 81: «Утратил силу приказом … от 29.07.2026 № 228-НҚ» | SECOND-HAND for 169-НҚ (cdb.kz copy, no registration number shown); repeal CONFIRMED. Start dates 4 May 2026 / 15 Aug 2026 came from search snippets and alta.ru only |

**Rule in force (Order N 81, edition of 14.08.2023, Rules п. 3; identical in the cdb.kz copy of Order 169-НҚ)**
- Average market price below 25 USD/bbl: «размер ставки вывозной таможенной пошлины равен 0».
- 25–105 USD/bbl: «ВТП=Ср*К», where «ВТП – размер ставки … в долларах США за тонну; Ср – средняя рыночная цена сырой нефти за предшествующий период; К – поправочный коэффициент 1» — i.e. the duty in USD/tonne equals the price in USD/bbl.
- Above 105 USD/bbl — table (Annex 2 to the Rules):

| Average price, USD/bbl | Duty, USD/t |
|---|---|
| 105–115 | 115 |
| 115–125 | 130 |
| 125–135 | 145 |
| 135–145 | 160 |
| 145–155 | 176 |
| 155–165 | 191 |
| 165–175 | 206 |
| 175–185 | 221 |
| 185 and above | 236 |

Exemptions seen: PSAs and subsoil contracts with a duty exemption (PP N 709); in 2009 oil subject to rent tax.

**Related: rent tax on export of crude oil, 2026** (Tax Code 2025 art. 749, CONFIRMED): 0 % up to 40 USD/bbl; 7 % up to 50; 11 % up to 60; 14 % up to 70; 16 % up to 80; 17 % up to 90; 19 % up to 100; 21 / 22 / 23 / 25 / 26 / 27 / 29 / 30 % for each further 10 USD; 32 % from 180–190 upward.

---

## 9. Mineral extraction tax (%)

### 9a. Crude oil incl. gas condensate — scale by annual output

| Annual output | Rate |
|---|---|
| ≤ 250 000 t | 5 |
| ≤ 500 000 t | 7 |
| ≤ 1 000 000 t | 8 |
| ≤ 2 000 000 t | 9 |
| ≤ 3 000 000 t | 10 |
| ≤ 4 000 000 t | 11 |
| ≤ 5 000 000 t | 12 |
| ≤ 7 000 000 t | 13 |
| ≤ 10 000 000 t | 15 |
| > 10 000 000 t | 18 |

| Effective | Legal act | URL fetched | Status |
|---|---|---|---|
| 2009-01 – 2010-12 | Tax Code 2008, art. 336, original edition (expected: a scale with scheduled increases) | — | UNCONFIRMED |
| 2011-01 | Law of 26.11.2010 N 356-IV, art. 1 п. 11) («в части первой статьи 336 таблицу изложить в следующей редакции» — table above); law in force 1 Jan 2011 | https://zakon.uchet.kz/rus/docs/Z1000000356 | CONFIRMED |
| 2011–2017 | Tax Code 2008, art. 336 (final edition, same table) | https://zakon.uchet.kz/rus/docs/K080000099_ | CONFIRMED |
| 2018-01 – 2025-12 | Tax Code 2017, art. 743(1) (final edition, same table) | https://zakon.uchet.kz/rus/docs/K1700000120 | CONFIRMED (final edition; no amendment footnote changing the table was seen) |
| 2026-01 – 2026-12 | Tax Code 2025, art. 778(1) пп. 1) «с 1 января 2026 года по 31 декабря 2026 года включительно» — same table | https://zakon.uchet.kz/rus/docs/K2500000214 | CONFIRMED |
| 2027-01 | Tax Code 2025, art. 778(1) пп. 2): a matrix by annual output **and** oil price (20–150 USD/bbl) | same | CONFIRMED that the regime changes; matrix values not transcribed |

Domestic-market sales get a reduction coefficient (text truncated in my read; 0.5 expected — UNCONFIRMED). Natural gas: 10 % (2008 Code art. 336; PwC 2026).

### 9b. Main solid minerals

| Mineral | 2011-01 (Law 356-IV, art. 339 table) | 2013-01 (Law 61-V) → 2017 (2008 Code final) | 2018–2022 (2017 Code, original) | 2023-01 (Law 135-VII) | 2025-01 | 2026-01 (Tax Code 2025 art. 781) |
|---|---|---|---|---|---|---|
| Copper | 5.7 | 5.7 | UNCONFIRMED (expected 5.7) | 8.55 | 8.55 | 8.55 |
| Zinc | 7.0 | 7.0 | UNCONFIRMED (expected 7.0) | 10.5 | 10.5 | 10.5 |
| Gold | 5.0 | 5.0 | UNCONFIRMED (expected 5.0) | 7.5 | 7.5 | price scale 7.5–11 (below) |
| Iron ore (concentrate) | 2.8 | 2.8 | UNCONFIRMED (expected 2.8) | 3.64 | 3.64 | 3.64 |
| Uranium | 22.0 | 18.5 | UNCONFIRMED (expected 18.5) | 6 | 9 | output scale 4–18 + price add-on (below) |
| Coal (hard, brown) | 0 (2008 Code final: «Уголь каменный, бурый уголь, горючие сланцы 0») | 0 | UNCONFIRMED | 2.7 (coking coal, anthracite 4.05) | 2.7 / 4.05 | 2.7 / 4.05 |

Sources and wording (all CONFIRMED unless a cell above says otherwise)
- 2011: Law of 26.11.2010 N 356-IV, art. 1 п. 12), in force 1 Jan 2011 — https://zakon.uchet.kz/rus/docs/Z1000000356 — «Железная руда (концентрат, окатыши) 2,8; Уран (продуктивный раствор, шахтный метод) 22,0; Медь 5,7; Цинк 7,0; Свинец 8,0; Золото, серебро, платина, палладий 5,0».
- 2013: Law of 26.12.2012 N 61-V, art. 1 п. 149) — https://zakon.uchet.kz/rus/docs/Z1200000061 — row 1 restated with «Уран (продуктивный раствор, шахтный метод) 18,5». Its art. 6 also sets a retroactive wording of row 1 "с 1 января 2009 года до 1 января 2013 года"; the uranium figure in that retroactive row was cut off in my read → 2009–2012 uranium is ambiguous (22.0 per Law 356-IV vs. a retroactive value not read).
- 2008 Code final edition art. 339 — https://zakon.uchet.kz/rus/docs/K080000099_ — «Железная руда (концентрат) 2,8; Уран … 18,5; Медь 5,7; Цинк 7,0; Золото, серебро, платина, палладий 5,0; Уголь каменный, бурый уголь, горючие сланцы 0».
- 2009–2010 levels (original 2008 Code table): UNCONFIRMED.
- 2018–2022: the original edition of art. 746 of the 2017 Code was not obtainable. The expected values are the 2008 Code figures; this is arithmetically consistent with the 2023 figures (5.7 × 1.5 = 8.55; 7.0 × 1.5 = 10.5; 5.0 × 1.5 = 7.5; 2.8 × 1.3 = 3.64) but that is inference, not a reading. The only fetched trace for coal is Law of 10.12.2020 N 382-VI, art. 1 п. 297) (footnote: in force 01.01.2021), which restates row 9 with «Уголь каменный, бурый уголь, горючие сланцы 2,7%» — https://zakon.uchet.kz/rus/docs/Z2000000382 — so coal was 2.7 % from 2021-01 at the latest; whether 2.7 % dates from 2018 is UNCONFIRMED.
- 2023: Law of 11.07.2022 N 135-VII, art. 1 п. 35); footnote to art. 746: «от 11.07.2022 № 135-VII (вводится в действие с 01.01.2023)» — https://zakon.uchet.kz/rus/docs/Z2200000135 — «Железная руда (концентрат) 3,64 %; Уран (извлеченный из продуктивных растворов, шахтный метод) 6 %; Медь 8,55 %; Цинк 10,5 %; Свинец 10,4 %; Золото, серебро 7,5 %; … Уголь каменный коксующийся, антрацит 4,05 %; Уголь каменный (кроме коксующегося и антрацита), бурый уголь, горючие сланцы 2,7 %». Note the uranium *base* also changed in 2023 (rate fell from 18.5 to 6 on a different base), so the uranium series is not comparable across 2022/2023.
- 2025 uranium: Law of 01.07.2024 N 105-VIII, new art. 57-19 of the 2017 intro law: «с 1 января 2025 года до 1 января 2026 года … Уран (извлеченный из продуктивных растворов, шахтный метод) 9 %» — https://zakon.uchet.kz/rus/docs/Z2400000105.
- 2026: Tax Code 2025, art. 781 — https://zakon.uchet.kz/rus/docs/K2500000214 — «Железная руда (концентрат) 3,64; Медь 8,55; Цинк 10,5; Свинец 10,4; … Уголь каменный коксующийся, антрацит 4,05; Уголь каменный (кроме коксующегося и антрацита), бурый уголь, горючие сланцы 2,7».
  - Uranium by annual output: ≤500 t 4 %; ≤1 000 t 6 %; ≤2 000 t 9 %; ≤3 000 t 12 %; ≤4 000 t 15 %; >4 000 t 18 %; plus an add-on when the U3O8 price exceeds 70 / 80 / 90 / 100 / 110 USD/lb: +0.5 / 1.0 / 1.5 / 2.0 / 2.5 points.
  - Gold by exchange price (USD/oz): ≤2 800 → 7.5; ≤3 000 → 8; ≤3 200 → 8.5; ≤3 400 → 9; ≤3 600 → 9.5; ≤3 800 → 10; >3 800 → 11. Silver: the same 7.5–11 ladder on 28–38 USD/oz.

---

## 10. Excises

### 10a. Petrol (excluding aviation) and diesel, tenge per tonne — set by Government resolution, not by the Code

Row shown: wholesale sale by producers of own production (the row that also equals the import rate from 2022). Retail sale by producers adds 500 (petrol) / 60 (diesel).

| Effective | Petrol | Diesel | Legal act | URL fetched | Status |
|---|---|---|---|---|---|
| 2015-01 – 2017-03 | not seen (expected 4 500) | not seen (expected 540) | PP of 13.03.2015 N 133, original edition (in force 1 Jan 2015) | https://zakon.uchet.kz/rus/docs/P1500000133 (only the 2017 edition is served) | UNCONFIRMED. The import row of the 2017 edition still reads 4500 / 540 |
| 2017-04 | 10 500 | 9 300 (June–October); 540 (November–May) | PP N 133 in the edition of PP of 31.03.2017 N 144, «вводится в действие с 01.04.2017 года» | https://zakon.uchet.kz/rus/docs/P1500000133 | CONFIRMED |
| 2018-01 | not seen (expected unchanged 10 500 / 9 300 / 540) | — | PP of 06.04.2018 N 173, original edition (in force 1 Jan 2018) | https://zakon.uchet.kz/rus/docs/P1800000173 (only the 2025 edition is served) | UNCONFIRMED |
| 2019-06 | 10 500 | 9 300 (July–November); 540 (December–June) | PP of 29.05.2019 N 331, in force 1 June 2019 | https://zakon.uchet.kz/rus/docs/P1900000331 | CONFIRMED |
| 2020-01 | 24 435 | 9 300 (July–November); 540 (December–June) | PP of 13.12.2019 N 928, in force 1 Jan 2020 | https://zakon.uchet.kz/rus/docs/P1900000928 | CONFIRMED |
| ~2022-04 | 38 134 | 35 726 (year-round, seasonal split dropped) | PP of 24.03.2022 N 155, 10 days after publication (KPMG: from 5 April 2022) | https://zakon.uchet.kz/rus/docs/P2200000155 | CONFIRMED (rates); start day SECOND-HAND (search snippet of KPMG newsflash April 2022, page itself not fetched) |
| 2022 (restated) | 38 134 | 35 726 | PP of 05.10.2022 N 786, «вводится в действие с 1 января 2022 года» — same rates, adds gasohol etc. | https://zakon.uchet.kz/rus/docs/P2200000786 | CONFIRMED. Formally retroactive to 2022-01; economically the increase dates from April 2022 |
| 2025-05 | 38 134 | 35 726 | PP of 28.04.2025 N 280 (new edition of the table, rates unchanged) | https://zakon.uchet.kz/rus/docs/P2500000280 | CONFIRMED |
| 2026-01 | 38 134 | 35 726 | PP of 05.12.2025 N 1049 under Tax Code 2025 art. 537(6) пп. 2); edition "с изменениями на 11.09.2026" (amended by PP 14.07.2026 N 615, 27.08.2026 N 773, 11.09.2026 N 816 — the producer-wholesale row is unchanged in that edition; what those three acts changed was not examined) | https://zakon.uchet.kz/rus/docs/P2500001049 | CONFIRMED |

Rates before 2015 (PP of 2009–2014 under 2008 Code art. 280) were not researched: UNCONFIRMED. The series is not differentiated by octane grade in any act read (no separate AI-92 rate).

### 10b. Cigarettes with filter, tenge per 1 000 sticks

| Effective | Value | Legal act | URL fetched | Wording seen | Status |
|---|---|---|---|---|---|
| 2009-01 – 2010-06 | — | Tax Code 2008 art. 280, original | — | — | UNCONFIRMED |
| 2010-07 | 800 | Law of 30.06.2010 N 297-IV (adds пп. 2-1 «с 1 июля 2010 года до 1 января 2011 года действуют следующие ставки акцизов») | https://zakon.uchet.kz/rus/docs/Z100000297_ | «Сигареты с фильтром 800 тенге/1000 штук» | CONFIRMED |
| 2011 – 2012 | — | — | — | — | UNCONFIRMED |
| 2013 | (1 550 per a search snippet only) | — | — | — | UNCONFIRMED |
| 2014-01 | 3 000 | Law of 05.12.2013 N 152-V («с 1 января 2014 года до 1 января 2015 года действуют следующие ставки акцизов») | https://zakon.uchet.kz/rus/docs/Z1300000152 | «Сигареты с фильтром 3 000 тенге/1 000 штук» | CONFIRMED |
| 2015-01 | 3 900 | same («с 1 января 2015 года до 1 января 2016 года») | same | «Сигареты с фильтром 3 900 тенге/1 000 штук» | CONFIRMED |
| 2016-01 | 5 000 | same — base table of art. 280 (rows 14–18 restated) applying once the two transitional years lapse | same | «Сигареты с фильтром 5 000 тенге/ 1 000 штук» | CONFIRMED as legislated in 2013; no later amendment to this row was found in the 2014–2015 laws checked (257-V, 412-V, 432-V) |
| 2017-01 (from 2 Jan) | 6 200 | Law of 30.11.2016 N 26-VI, art. 2 («со 2 января 2017 года до 1 января 2018 года действуют следующие ставки акцизов») | https://zakon.uchet.kz/rus/docs/Z1600000026 | «Сигареты с фильтром 6200 тенге/ 1 000 штук» | CONFIRMED |
| 2018-01 | 7 500 | Law of 25.12.2017 N 121-VI (intro law of the 2017 Code), art. 43(1) пп. 1) | https://zakon.uchet.kz/rus/docs/Z1700000121 | «Сигареты с фильтром 7 500 тенге/1 000 штук» | CONFIRMED |
| 2019-01 | 8 700 | same, пп. 2) | same | «8 700 тенге/1 000 штук» | CONFIRMED |
| 2020-01 | 9 900 | same, пп. 3) | same | «9 900 тенге/1 000 штук» | CONFIRMED |
| 2021-01 | 11 100 | same, пп. 4) | same | «11100 тенге/1 000 штук» | CONFIRMED |
| 2022-01 | 12 300 | same, пп. 5) (added by Law 10.12.2020 N 382-VI) | same; https://zakon.uchet.kz/rus/docs/Z2000000382 | «с 1 января 2022 года до 1 января 2023 года: … Сигареты с фильтром 12 300 тенге/1 000 штук» | CONFIRMED |
| 2023-01 | 14 100 | same, art. 43(2) (added by Law 11.07.2022 N 135-VII: suspension «до 1 января 2024 года») | https://zakon.uchet.kz/rus/docs/Z2200000135 | «Сигареты с фильтром 14 100 тенге/1 000 штук» | CONFIRMED |
| 2024-01 | 15 900 | Tax Code 2017 art. 463(4) row 14 (edition of Law 135-VII) | https://zakon.uchet.kz/rus/docs/K1700000120 | «Сигареты с фильтром 15 900 тенге/1 000 штук» | CONFIRMED |
| 2025-01 | 15 900 | same (final edition of the 2017 Code; Law 12.12.2023 N 45-VIII changed only row 12, beer) | same | same | CONFIRMED |
| 2026-01 | 18 051 | Tax Code 2025, art. 537(6) row 14 | https://zakon.uchet.kz/rus/docs/K2500000214 | «с 1 января 2026 года по 31 декабря 2026 года включительно … 18 051 теңге / 1 000 штук» | CONFIRMED |
| 2027 / 2028 / 2029 / 2030 | 21 163 / 21 880 / 23 279 / 25 607 (legislated) | same | same | same row | CONFIRMED |

Note: a search snippet (prg.kz, 05.01.2021) quotes 11 000 for 2021; the law text reads 11 100.

---

## What could not be confirmed

1. VAT: the month 20 % first applied (only "20 before July 2001" is confirmed).
2. CIT: the transitional article that set 20 % for 2009–2010 and the planned 17.5 % / 15 % schedule; start month of 30 % under the 1995 law.
3. PIT: the 2002–2003 scale (original 2001 Code); pre-1998 scales of the 1995 law; dividend rate before 2007; the 5 % wording for 2018–2022.
4. Social tax: 2002–2003 rate (original 2001 Code; 21 % expected); start of the 26 % rate; content of the 2007 amendment (Law 11.12.2006 N 201); whether the "minus social contributions" rule applied in 2005–2017.
5. Pension contributions: the commencement clause of the 1997 law.
6. Oil export duty: exact start days of every "N days after publication" step; the Q4-2008 level; the act and month of the 20 → 40 step (2011-01 expected); **the original March-2016 price scale** and the date the duty = price formula replaced it; registration details and exact start of Order 169-НҚ of 2026.
7. MET: oil scale and solid-mineral rates for 2009–2010; all solid-mineral rates for 2018–2022 (original 2017 Code); uranium 2009–2012 (22.0 vs. the retroactive row of Law 61-V); the domestic-market coefficient for oil; the 2027 oil matrix values.
8. Excise: petrol/diesel before April 2017 and the original 2018 table; cigarettes 2009–H1 2010 and 2011–2013.

## Sites: reachable or not

| Site | Result |
|---|---|
| adilet.zan.kz | **Unusable.** Every `/rus/docs/…` and `/rus/archive/docs/…` URL returns an empty JS shell (HTTP 200, 1.5 kB, "Для работы … включите JavaScript"); `/api/…` → 401 |
| zakon.uchet.kz | Works via curl (full consolidated texts, same IDs as adilet). `/rus/history/…`, `/rus/archive/…` → 404 or empty shell, so no historical editions |
| web.archive.org | Blocked (WebFetch refuses; curl connection reset) |
| taxsummaries.pwc.com | Works (three pages, reviewed 23 July 2026) |
| cdb.kz | Works via WebFetch |
| alta.ru | Works via WebFetch (long page, truncated before the annex) |
| yko.kgd.gov.kz (KGD) | 503 / connection reset |
| ey.com tax alert (Jan 2023) | 404 |
| bdo.global (VAT history) | 500 |
| centralbanking.com | page shell only, no article text |
| oecd.org (Tax Policy Review 2020) | 403 |
| kapital.kz, inform.kz | 403 |
| assets.kpmg.com (O&G newsflash July 2016 PDF) | downloaded; contains no duty scale |
| online.zakon.kz | reachable (HTTP 200) but not used; IMF Article IV, kgd.gov.kz main site, uchet.kz and mybuh.kz rate tables were not consulted |
