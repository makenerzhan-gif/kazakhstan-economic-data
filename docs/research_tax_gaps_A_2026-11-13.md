# Kazakhstan statutory tax rates — gap-filling pass A

Compiled 2026-11-13. Read-only; nothing in the repository was changed.

## Sources and status labels

- `CONFIRMED` — value read in the text of the legal act on a page fetched in this session.
- Two kinds of law-text pages were used:
  - **zakon.uchet.kz/rus/docs/<id>** — mirror of the official consolidated text (latest edition only) and of amending laws.
  - **prg.kz/m/amp/document/<id>[/<page>/]** — commercial legal database ("Параграф") that keeps **dated historical editions** of each act, headed "(СТАРАЯ РЕДАКЦИЯ)" / "Данная редакция действовала до внесения изменений от …". Long acts are split into pages (`/<id>/<n>/`). This is what filled the gaps the first pass could not. It is law text, but from a commercial database rather than the official registry; every prg.kz value below is cross-checked against an amending law or footnote on zakon.uchet.kz where one exists.
- All pages were fetched with curl; raw HTML and stripped text are in `/tmp/claude-0/-home-user-kazakhstan-economic-data/75b92fb2-b6fa-5dc2-bf44-15a6ab5a8c77/scratchpad/gapsA_dl/`.
- No value below comes from memory or from a search snippet.

---

## Gap 1. Corporate income tax 2009–2010

| Item | Period | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| CIT rate applied | 2009-01 → 2009-12 | 20 | Law of 10.12.2008 N 100-IV (intro law of the 2008 Code), **art. 4**, original edition | https://prg.kz/m/amp/document/30443433 (edition "действовала до внесения изменений от 4 июля 2009 года") ; https://prg.kz/m/amp/document/30519993 (edition as of 17.07.2009) | «Статья 4. Приостановить до 1 января 2011 года действие пункта 1 статьи 147 Кодекса … в части размера ставки корпоративного подоходного налога, установив, что в период приостановления действуют следующие размеры ставки … 1) с 1 января 2009 года до 1 января 2010 года в размере 20 процентов; 2) с 1 января 2010 года до 1 января 2011 года в размере 17,5 процента.» | CONFIRMED |
| CIT rate applied | 2010-01 → 2010-12 | 20 (the 17.5 planned for 2010 never applied) | Law of 16.11.2009 N 200-IV, art. 1 п. 8 пп. 2) (amends art. 4 of Law 100-IV; РЦПИ note: this subparagraph in force from 01.01.2009) | https://zakon.uchet.kz/rus/docs/Z090000200_ | «2) в статье 4: в абзаце первом цифры "2011" заменить цифрами "2014"; в подпункте 1) цифры "2010" заменить цифрами "2013"; в подпункте 2) цифры "2010", "2011" заменить соответственно цифрами "2013", "2014"» | CONFIRMED |
| same, resulting text | 2009-01 → 2010-12 | 20 | Law 100-IV art. 4, edition as of 30.12.2009 | https://prg.kz/m/amp/document/30606018/ | «Статья 4. Приостановить до 1 января 2014 года действие пункта 1 статьи 147 … 1) с 1 января 2009 года до 1 января 2013 года в размере 20 процентов; 2) с 1 января 2013 года до 1 января 2014 года в размере 17,5 процента.» | CONFIRMED |
| End of the transitional article | 2011-01 | 20 written into the Code | Law of 26.11.2010 N 356-IV, art. 1 п. 3 пп. 2) (and the earlier-confirmed «в пункте 1 [ст. 147] цифры "15" заменить цифрами "20"») | https://zakon.uchet.kz/rus/docs/Z1000000356 | «2) статьи 4, 5, 6, 7 и 16 исключить» | CONFIRMED |

Notes
- The article is **art. 4** of the intro law (not an article numbered near 16). It is absent from the current consolidated text because Law 356-IV deleted it.
- Schedule as originally enacted (Dec 2008): 2009 = 20, 2010 = 17.5, from 2011 = 15 (the Code's art. 147(1)). After Law 200-IV (Nov 2009): 2009–2012 = 20, 2013 = 17.5, from 2014 = 15. After Law 356-IV: 20 permanently. So neither 17.5 nor 15 ever applied.
- Same intro law, art. 5 (same pages): withholding CIT rate 15 % during the suspension.

---

## Gap 2. Personal income tax 2002–2003; dividends

### 2a. PIT scale 2002–2003 (Tax Code of 12.06.2001 N 209-II, art. 145(1))

| Item | Period | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| PIT scale | 2002-01 → 2003-12 | progressive **5 / 10 / 20 / 30**; bands in annual calculation indices (годовой расчетный показатель): ≤15; 15–40; 40–600; >600 | Tax Code 2001, art. 145(1), original edition | https://prg.kz/m/amp/document/3023502/6/ (edition "действовала до внесения изменений от 21 марта 2002 г.") | «1. Доходы налогоплательщика, облагаемые за налоговый год, за исключением доходов, указанных в пунктах 2 и 3 настоящей статьи, подлежат обложению по следующим ставкам: До 15-кратного годового расчетного показателя 5 процентов с суммы облагаемого дохода; От 15-кратного до 40-кратного … + 10 процентов с суммы, превышающей его; От 40-кратного до 600-кратного … + 20 процентов …; От 600-кратного и свыше … + 30 процентов с суммы, превышающей его» | CONFIRMED |
| same scale still in 2003 | 2003 | same | Tax Code 2001, art. 145(1), edition "действовала до внесения изменений от 13 марта 2003 г." | https://prg.kz/m/amp/document/3323502/6/ | identical table; п. 1 now reads «…указанных в пунктах 1-1, 2 и 3…» | CONFIRMED |
| 2003 change (not a rate change) | 2003-01 | zero rate for low-paid employees added | Law of 23.11.2002 N 358, art. 1 п. 41) | https://zakon.uchet.kz/rus/docs/Z020000358_ | «дополнить пунктом 1-1 … "1-1. Доходы работников, облагаемые у источника выплаты, не превышающие за год 12-кратного минимального размера заработной платы … подлежат обложению по ставке "0"…» | CONFIRMED |
| 2004 scale (cross-check of first pass) | 2004-01 → 2006-12 | 5 / 8 / 13 / 15 / 20 (≤15; 15–40; 40–200; 200–600; >600) | Tax Code 2001 art. 145(1), editions of 2004 and of 1 Jan 2005 | https://prg.kz/m/amp/document/4023502/9/ ; https://prg.kz/m/amp/document/30009114/8/ | table as in Law 475 | CONFIRMED |

**Correction to the expectation:** the 2002–2003 bands are 15 / 40 / 600 annual indices, not the 15 / 30 / 65 of the final 1995-law edition. Rates 5/10/20/30 as expected.

### 2b. Dividends received by individuals

| Item | Period | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| Dividends (withholding, final) | 1995-07 → 2001-12 | 15 | Law of 24.04.1995 N 2235, art. 31(1) | https://prg.kz/m/amp/document/5107159/ (edition valid until 21.12.1995) ; https://zakon.uchet.kz/rus/docs/Z950002235_ (final edition) | «Дивиденды, выплачиваемые юридическим и физическим лицам, подлежат обложению налогом у источника выплаты по ставке 15 процентов и дальнейшему налогообложению не подлежат» | CONFIRMED |
| Dividends, individuals | 2002-01 → 2006-12 | 15 | Tax Code 2001, art. 145(**2**) | original: https://prg.kz/m/amp/document/3023502/6/ ; 2003: https://prg.kz/m/amp/document/3323502/6/ ; 2004: https://prg.kz/m/amp/document/4023502/9/ ; as of 1 Jan 2005 (valid until 15.04.2005): https://prg.kz/m/amp/document/30009114/8/ | «2. Доходы в виде дивидендов, вознаграждений (за исключением вознаграждений по договорам накопительного страхования), выигрышей облагаются по ставке 15 процентов.» (identical in all four editions) | CONFIRMED |
| no amendment in 2005–2006 | — | — | footnote to art. 145, final edition of the 2001 Code | https://zakon.uchet.kz/rus/docs/K010000209_ | «Сноска. В статью 145 внесены изменения - Законом РК от 23 ноября 2002 г. N 358 …; от 4 июля 2003 года N 475 …; от 7 июля 2006 года N 177 (вводится в действие с 1 января 2007 года…)»; Law 475 touches only п. 1 («21) пункт 1 статьи 145 изложить в следующей редакции») | CONFIRMED (15 % held through 2006) |
| Dividends, individuals | 2007-01 → 2008-12 | 5 | Tax Code 2001, art. 145(3), edition as of 06.07.2007 | https://prg.kz/m/amp/document/30118540/10/ | «3. Доходы в виде дивидендов облагаются по ставке 5 процентов.» | CONFIRMED |
| Dividends, individuals | 2018-01 → 2022-12 | 5 | Tax Code of 25.12.2017 N 120-VI, art. 320(2) | editions as of 15.07.2018: https://prg.kz/m/amp/document/39968612/35/ ; 10.01.2020: https://prg.kz/m/amp/document/36153323/37/ ; 30.05.2020: https://prg.kz/m/amp/document/32036893/37/ ; 11.07.2022: https://prg.kz/m/amp/document/33885664/43/ | «1. Доходы налогоплательщика, за исключением доходов, указанных в пункте 2 настоящей статьи, облагаются налогом по ставке 10 процентов. 2. Доходы в виде дивидендов, полученные из источников в Республике Казахстан, облагаются по ставке 5 процентов.» | CONFIRMED |
| only amendment to art. 320 | 2023-01 | п. 2 removed → 10 | Tax Code 2017 art. 320 footnote | https://zakon.uchet.kz/rus/docs/K1700000120 | «Сноска. Статья 320 с изменением, внесенным Законом РК от 11.07.2022 № 135-VII (вводится в действие с 01.01.2023).» | CONFIRMED |

Other rates in art. 145 of the 2001 Code (original): interest and winnings 15 % (same п. 2); advocates and private notaries 10 % (п. 3).

---

## Gap 3. Social tax 2002–2008 (Tax Code 2001, art. 317)

| Item | Period | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| Social tax, legal entities | 2002-01 → 2003-12 | flat **21** | Tax Code 2001, art. 317(1), original edition | https://prg.kz/m/amp/document/3023502/11/ | «1. Юридические лица - резиденты Республики Казахстан, а также нерезиденты, осуществляющие деятельность в Республике Казахстан через постоянное учреждение, уплачивают социальный налог по ставке 21 процент, если иное не установлено настоящей статьей.» | CONFIRMED |
| same in 2003 | 2003 | 21 | art. 317(1), edition valid until 13.03.2003 | https://prg.kz/m/amp/document/3323502/13/ | same sentence | CONFIRMED |
| Law 358 (2003-01) did not touch the rate | 2003-01 | — | Law of 23.11.2002 N 358, art. 1 п. 94) | https://zakon.uchet.kz/rus/docs/Z020000358_ | «94) в статье 317: пункт 3 после слов "налоговые режимы" дополнить словами…; в пункте 4 слова "за инвалидов" исключить» | CONFIRMED |
| Regressive scale | 2004-01 → 2007-12 | 20 / 15 / 12 / 9 / 7 (≤15; 15–40; 40–200; 200–600; >600 annual indices of employee income) | Tax Code 2001 art. 317(1), editions of 2004, of 1 Jan 2005 and **as of 06.07.2007** | https://prg.kz/m/amp/document/4023502/17/ ; https://prg.kz/m/amp/document/30009114/17/ ; https://prg.kz/m/amp/document/30118540/21/ | 06.07.2007 edition: «до 15-кратного годового расчетного показателя 20 процентов с суммы облагаемого дохода; от 15 до 40-кратного … + 15 процентов …; от 40 до 200-кратного … + 12 процентов …; от 200 до 600-кратного … + 9 процентов…», with the note «См. изменения от 07.07.06 г. № 177-III (вводятся в действие с 01.01.2008 г.)» | CONFIRMED |
| Law 201 (2007-01) did not touch the rates | 2007-01 | — | Law of 11.12.2006 N 201, art. 1 п. 122) | https://zakon.uchet.kz/rus/docs/Z060000201_ | «122) пункт 3 статьи 317 дополнить частью второй следующего содержания: "Настоящий пункт не распространяется на налогоплательщиков в период временного приостановления ими деятельности…"» (the only change to art. 317 in that law) | CONFIRMED |
| Regressive scale | 2008-01 → 2008-12 | 13 / 11 / 9 / 7 / 5 | first pass (Law 177) | — | — | CONFIRMED (first pass) |

**Top marginal (first-bracket) social tax rate by year**

| Year | 2002 | 2003 | 2004 | 2005 | 2006 | 2007 | 2008 |
|---|---|---|---|---|---|---|---|
| Rate, % | 21 | 21 | 20 | 20 | 20 | 20 | 13 |
| Structure | flat | flat | regressive to 7 | regressive to 7 | regressive to 7 | regressive to 7 | regressive to 5 |

Other 2002–2003 rates in the original art. 317: foreign specialists (administrative / engineering staff) 11 %; individual entrepreneurs 3 MCI for self + 2 MCI per employee; specialised organisations employing disabled people 6.5 %.

**Side finding (offset by social contributions before 2009).** Tax Code 2001 art. 318(1), edition as of 06.07.2007 (https://prg.kz/m/amp/document/30118540/21/): «исчисление социального налога производится посредством применения ставок, установленных в пунктах 1, 2 и 4 статьи 317 … и уменьшения на сумму социальных отчислений в Государственный фонд социального страхования, исчисленных в соответствии с законодательным актом … об обязательном социальном страховании». CONFIRMED for 2007; so the 20 % (and 13 % in 2008) scale was gross of social contributions (the 2005 start of this offset was not separately checked).

---

## Gap 4. VAT 20 % — start date

| Item | Period | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| Entry into force of the 1995 tax law | 1995-07-01 | — | Decree having force of law of 24.04.1995 N 2235, art. 179(1) | https://zakon.uchet.kz/rus/docs/Z950002235_ (final edition; document info block: «Дата вступления в силу 01.07.1995») ; https://prg.kz/m/amp/document/5107159/5/ (edition valid until 21.12.1995) | final edition: «Статья 179. Порядок введения в действие 1. Настоящий Закон вводится в действие с 1 июля 1995 года.»; 1995 edition: «1. Настоящий Указ вводится в действие с 1 июля 1995 года.» | CONFIRMED |
| VAT standard rate | 1995-07 → 2001-06 | 20 | same decree, **art. 66(1)** in the 1995–1999 numbering (became art. 62 after renumbering) | 1995 edition (valid until 21.12.1995): https://prg.kz/m/amp/document/5107159/2/ ; 1996 edition (valid until 31.12.1996): https://prg.kz/m/amp/document/3707159/2/ ; 1999 edition (valid until 16.07.1999): https://prg.kz/m/amp/document/3307159/4/ | «Статья 66. Ставки налога на добавленную стоимость 1. Ставка налога на добавленную стоимость равняется 20 процентам от размера облагаемого оборота, кроме случаев, указанных в пункте 2 настоящей статьи. … 3. Ставка … по облагаемому импорту равняется 20 процентам» | CONFIRMED |

Caveats
- The very first edition (24.04.1995, valid until 20.07.1995) is truncated on prg.kz (https://prg.kz/m/amp/document/4907159 shows only arts 1–3). The earliest full text read is the edition valid from 20.07.1995 to 21.12.1995; the only intervening amendment (Decree N 2370 of 20.07.1995) is listed by prg.kz as a customs-related amendment and its text was not read. The law itself only took effect on 1 July 1995, so the gap is three weeks.
- 1999 edition also shows a reduced 10 % rate for basic foodstuffs (art. 66(4), added by later laws) — not part of the standard rate.
- The pre-1995 VAT rate (28 % under the 1991 law) was not researched: NOT FOUND (optional item).

## Gap 5. CIT 30 % — start date

| Item | Period | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| CIT (income tax on legal entities) | 1995-07 → 2001-12 | 30 (10 where land is the main means of production) | Decree N 2235, art. 30(1); commencement art. 179(1) | https://prg.kz/m/amp/document/5107159/ (1995 edition, art. 30 on page 1, art. 179 on page 5) ; https://prg.kz/m/amp/document/3707159/ (1996) ; https://zakon.uchet.kz/rus/docs/Z950002235_ (final) | «Статья 30. Ставки подоходного налога для юридических лиц 1. Налогооблагаемый доход юридического лица подлежит обложению налогом по ставке 30 процентов. 2. Юридические лица, для которых земля является основным средством производства, уплачивают налог по ставке 10 процентов…» | CONFIRMED |
| CIT | 2002-01 → 2008-12 | 30 | Tax Code 2001 art. 135(1), original edition | https://prg.kz/m/amp/document/3023502/5/ | «подлежит обложению налогом по ставке 30 процентов» | CONFIRMED |

Bonus (not requested, same pages): the 1995 PIT scale, art. 29, edition valid until 21.12.1995 — six brackets 5 / 10 / 15 / 20 / 30 / **40** % at 10 / 20 / 30 / 40 / 50 multiples of the annual minimum wage («от 50-кратной минимальной годовой заработной платы и свыше … + 40 процентов»). CONFIRMED for H2 1995; the date the top rate fell to 30 was not traced (art. 29 was restated by Law of 08.12.1997 N 200-1). Also the 2002 VAT rate in the original 2001 Code, art. 245(1): «равняется 16 процентам» (https://prg.kz/m/amp/document/3023502/9/) — direct confirmation of what the first pass had inferred.

---

## Gap 6. Tax Code 2025 — is social tax still reduced by social contributions?

**No.** Read in full: arts 555–562 of the Tax Code of 18.07.2025 N 214-VIII (edition "с изменениями на: 01.07.2026"), https://zakon.uchet.kz/rus/docs/K2500000214. The phrase «социальных отчислений» does not occur anywhere in arts 554–562.

| Item | Period | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| Calculation rule | 2026-01 → | tax payable = rate × object; no deduction of social contributions | Tax Code 2025, art. 558(1) | https://zakon.uchet.kz/rus/docs/K2500000214 | «Статья 558. Порядок исчисления социального налога 1. Если иное не установлено настоящей статьей, сумма социального налога, подлежащая уплате в бюджет, определяется путем применения ставок, установленных пунктами 1 и 2 статьи 557 настоящего Кодекса, к: 1) объекту налогообложения, предусмотренному пунктом 1 статьи 556 настоящего Кодекса, уменьшенному на сумму исключений из объекта согласно пункту 2 статьи 556 настоящего Кодекса; или 2) объекту налогообложения, предусмотренному пунктом 3 статьи 556 настоящего Кодекса, в случаях, предусмотренных данным пунктом.» | CONFIRMED |
| Rate | 2026-01 → | 6 (1.8 agricultural) | art. 557(1)–(2) | same | «1. Социальный налог исчисляется по ставке 6 процентов, за исключением случаев, установленных пунктами 2, 3 и 4 настоящей статьи. 2. … по ставке 1,8 процента…» | CONFIRMED |
| What is deducted from the **base** (not from the tax) | 2026-01 → | employee pension contributions, employee medical-insurance contributions, exempt incomes | art. 556(2) | same | «2. Объект налогообложения … уменьшается на следующие исключения из объекта: 1) обязательные пенсионные взносы в единый накопительный пенсионный фонд …; 2) взносы на обязательное социальное медицинское страхование …; 3) доходы, установленные статьей 429 …; 4) доходы, установленные подпунктом 12) статьи 681» | CONFIRMED |
| Only reduction of the tax itself | 2026-01 → | state institutions: minus temporary-disability benefit paid | art. 559(2) | same | «Сумма социального налога, исчисленная государственными учреждениями за налоговый период, уменьшается на сумму выплаченного … социального пособия по временной нетрудоспособности.» | CONFIRMED |
| Minimum base | 2026-01 → | 14 MCI per month | art. 556(3) | same | «…от одного теңге до 14-кратного месячного расчетного показателя … объект налогообложения определяется исходя из 14-кратного месячного расчетного показателя» | CONFIRMED |

Implication: the 2026 rate of 6 % is a **net** rate, payable in addition to the 5 % social contributions. It equals the previous *net* burden (2018–2024: 9.5 − 3.5 = 6; 2025: 11 − 5 = 6), so a series of the headline rate (9.5 → 11 → 6) shows a cut that did not happen on a net basis. The same gross/net issue applies back to at least 2007 (see the side finding in gap 3).

---

## Summary

| Gap | Result | Status |
|---|---|---|
| 1 | CIT 20 % in 2009-01 → 2010-12 under art. 4 of Law 100-IV (original: 2009 = 20, 2010 = 17.5; Law 200-IV extended 20 to end-2012; Law 356-IV deleted art. 4 and wrote 20 into art. 147 from 2011-01) | CONFIRMED |
| 2a | PIT 2002-01 → 2003-12: 5 / 10 / 20 / 30, bands ≤15 / 15–40 / 40–600 / >600 annual calculation indices | CONFIRMED |
| 2b | Dividends to individuals: 15 % 2002-01 → 2006-12 (also 15 % 1995-07 → 2001-12); 5 % 2007-01 → 2008-12; 5 % 2018-01 → 2022-12 | CONFIRMED |
| 3 | Social tax first-bracket rate: 2002 21, 2003 21 (flat); 2004–2007 20 (scale 20/15/12/9/7); 2008 13. Law 201 of 2006 changed only art. 317(3), no rates | CONFIRMED |
| 4 | VAT 20 % from 1995-07-01 (art. 179 commencement; rate in art. 66(1) of the 1995 numbering) to 2001-06 | CONFIRMED (earliest full edition read is 20.07.1995–21.12.1995; the first three weeks' edition is truncated on prg.kz). 28 % pre-1995: NOT FOUND, not researched |
| 5 | CIT 30 % from 1995-07-01 (art. 30(1)) | CONFIRMED |
| 6 | Tax Code 2025 has no offset of social contributions against social tax (art. 558(1)); 6 % in 2026 is net and comes on top of 5 % social contributions | CONFIRMED |
