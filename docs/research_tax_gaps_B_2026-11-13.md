# Kazakhstan statutory tax rates — gap-filling pass B

Date of research: 2026-11-13. Every value below was read on a fetched page. Raw pages are saved in
`/tmp/claude-0/-home-user-kazakhstan-economic-data/75b92fb2-b6fa-5dc2-bf44-15a6ab5a8c77/scratchpad/gapsB/`.

Status key
- **CONFIRMED** — text of the law / resolution / order. Either on zakon.uchet.kz (mirror of adilet, latest edition or amending act), or a dated historical edition on prg.kz ("Параграф", commercial database; edition date given), or the redline copy on alta.ru (shows "См. пред. ред." blocks with the superseded text).
- **SECOND-HAND** — news or adviser page; URL and quote given.
- **COMPUTED** — a date derived by me from a confirmed publication date and the act's "N days after publication" clause. The month is safe, the day can be off by one.

Sources that turned out to work for old editions
- `https://prg.kz/m/amp/document/<edition id>/<page>/` — each historical edition has its own id; header says «Данная редакция действовала до …». Codes and laws are served in full; Government resolutions are cut off behind a login.
- `https://www.alta.ru/tamdoc/<yy>kz<nnnn>/` — Kazakhstan customs and excise acts with inline previous editions and "Опубликован / Дата вступления в силу" fields. Rate-limited (connection resets; wait a few seconds between requests).
- zakon.uchet.kz "Информация о документе" block gives the official publication date of each act.
- Not usable: zakon.uchet.kz `/rus/history/...` and `/kaz/history/...` (empty shell), adilet `/download`, `/history` (empty shell), online.zakon.kz (redirects to a JS app).

---

## Gap 1. MET on solid minerals 2018–2022 (Tax Code 2017, art. 746)

| Item | Period (from / to) | Value, % | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| Copper | 2018-01 / 2022-12 | 5.7 | Tax Code 2017 art. 746, editions of 19.04.2019, 07.01.2020, 16.12.2020, 21.12.2022 | https://prg.kz/m/amp/document/33805627/74/ ; https://prg.kz/m/amp/document/36689633/75/ ; https://prg.kz/m/amp/document/36839345/78/ ; https://prg.kz/m/amp/document/37225647/87/ | «Медь \| 5,7%» | CONFIRMED |
| Zinc | 2018-01 / 2022-12 | 7.0 | same | same | «Цинк \| 7,0%» | CONFIRMED |
| Gold | 2018-01 / 2022-12 | 5.0 | same | same | «Золото, серебро, платина, палладий \| 5,0%» | CONFIRMED |
| Iron ore | 2018-01 / 2022-12 | 2.8 | same | same | «Железная руда (концентрат) \| 2,8%» | CONFIRMED |
| Uranium | 2018-01 / 2022-12 | 18.5 | same | same | «Уран (продуктивный раствор, шахтный метод) \| 18,5%» | CONFIRMED |
| Coal | 2018-01 / 2020-12 | 0 | Tax Code 2017 art. 746, editions of 19.04.2019, 07.01.2020 and 16.12.2020 («Данная редакция действовала до 1 января 2021 года») | https://prg.kz/m/amp/document/33805627/74/ ; https://prg.kz/m/amp/document/36689633/75/ ; https://prg.kz/m/amp/document/36839345/78/ | «Уголь каменный, бурый уголь, горючие сланцы \| 0%» | CONFIRMED |
| Coal | 2021-01 / 2022-12 | 2.7 | Law of 10.12.2020 N 382-VI; edition of 21.12.2022 («Данная редакция действовала до 1 января 2023 года») | https://prg.kz/m/amp/document/37225647/87/ ; footnote also in https://prg.kz/m/amp/document/36148637/91/ | «Уголь каменный, бурый уголь, горючие сланцы \| 2,7%»; «В статью 746 внесены изменения в соответствии с Законом РК от 10.12.20 г. № 382-VI (введены в действие с 1 января 2021 г.)» | CONFIRMED |

Notes
- The four edition dates bracket the whole period: no change to these six rows between 2018 and 2022 other than coal on 1 Jan 2021. The edition of 21.12.2022 is the last one before Law 135-VII (1 Jan 2023).
- The first edition read is 19.04.2019, not the text as signed on 25.12.2017. The footnote of the final edition lists only three amending laws for art. 746 (382-VI from 2021, 135-VII from 2023, 165-VII from 2024), so nothing changed between 2018-01 and 2019-04.
- Oil in the same editions (art. 743): scale 5 / 7 / 8 / 9 / 10 / 11 / 12 / 13 / 15 / 18 %, and «к установленным ставкам применяется понижающий коэффициент 0,5» for domestic sales — CONFIRMED for 2019 (https://prg.kz/m/amp/document/33805627/73/).

---

## Gap 2. MET on metals 2009–2010 and uranium 2009–2012 (Tax Code 2008, art. 339)

How the law was built: the table in art. 339 of the Code as adopted (higher rates) was suspended, and the rates actually applied came from art. 7 of the introductory Law of 10.12.2008 N 100-IV.

| Item | Period (from / to) | Value, % | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| Copper | 2009-01 / 2010-12 | 5.7 | Law N 100-IV art. 7 пп. 2), column «с 1 января 2009 года» (editions of 17.07.2009 and 30.12.2009) | https://prg.kz/m/amp/document/30519993/1/ ; https://prg.kz/m/amp/document/30606018/1/ | «медь \| 5,7 \| 7,0» | CONFIRMED |
| Zinc | 2009-01 / 2010-12 | 7.0 | same | same | «цинк \| 7,0 \| 8,0» | CONFIRMED |
| Gold | 2009-01 / 2010-12 | 5.0 | same | same | «золото, серебро, платина, палладий \| 5,0 \| 5,5» | CONFIRMED |
| Iron ore | 2009-01 / 2010-12 | 2.8 | same | same | «Железная руда (концентрат, окатыши) \| 2,8 \| 3,2» | CONFIRMED |
| Coal | 2009-01 / 2010-12 | 0 | same | same | «Уголь каменный, бурый уголь, горючие сланцы \| 0 \| 0» | CONFIRMED |
| Uranium, as in force at the time | 2009-01 / 2012-12 | 22.0 | Law N 100-IV art. 7 пп. 2) (2009–2010); Law of 26.11.2010 N 356-IV, art. 339 table (2011–2012) | same two prg.kz URLs; https://zakon.uchet.kz/rus/docs/Z1000000356 | «Уран (продуктивный раствор, шахтный метод) \| 22,0 \| 23,0» | CONFIRMED |
| Uranium, retroactive wording | 2009-01 / 2012-12 | 17.5 | Law of 26.12.2012 N 61-V, art. 6 | https://zakon.uchet.kz/rus/docs/Z1200000061 | «Статья 6. Установить, что в период с 1 января 2009 года до 1 января 2013 года строка 1 таблицы статьи 339 … действует в следующей редакции: … Хромовая руда (концентрат) 16,2; Марганцевая, железо-марганцевая руда (концентрат) 2,5; Железная руда (концентрат, окатыши) 2,8; Уран (продуктивный раствор, шахтный метод) 17,5» | CONFIRMED |

Notes
- The second column of the transitional table (copper 7.0, zinc 8.0, gold 5.5, iron ore 3.2, uranium 23.0) was scheduled for 1 Jan 2010 in the edition of 17.07.2009 («с 1 января 2010 года»; suspension «до 1 января 2011 года»). Law of 16.11.2009 N 200-IV relabelled it «с 1 января 2013 года» and extended the suspension to 2014 (edition of 30.12.2009: «В статью 7 внесены изменения в соответствии с Законом РК от 16.11.09 г. № 200-IV (введены в действие с 1 января 2009 г.)»). So the 2010 step never applied.
- Code table as adopted (suspended, never applied) — edition of 10.07.2009, https://prg.kz/m/amp/document/30449190/23/ : «Железная руда (концентрат, окатыши) 3,5; Уран 24,0; Медь 8,0; Цинк 9,0; золото, серебро, платина, палладий 6,0; Уголь … 0», with the note «Действие части первой статьи 339 приостановлено до 1 января 2011 года в соответствии со статьей 7 Закона РК от 10 декабря 2008 года № 100-IV».
- Uranium: two defensible values for 2009–2012. 22.0 is what the law said during those years; 17.5 is what Law 61-V (signed 26.12.2012) says applied in that period. Law 61-V art. 6 rewrites row 1 only (chrome, manganese, iron ore, uranium); only the uranium figure differs from the earlier text.

---

## Gap 3. MET on crude oil 2009–2010 (Tax Code 2008, art. 336)

| Annual output | Applied 2009-01 / 2010-12 (and unchanged from 2011) | Scheduled «с 1 января 2010 года», never applied | Code art. 336 as adopted, suspended, never applied |
|---|---|---|---|
| ≤ 250 000 t | 5 | 6 | 7 |
| ≤ 500 000 t | 7 | 8 | 9 |
| ≤ 1 000 000 t | 8 | 9 | 10 |
| ≤ 2 000 000 t | 9 | 10 | 11 |
| ≤ 3 000 000 t | 10 | 11 | 12 |
| ≤ 4 000 000 t | 11 | 12 | 13 |
| ≤ 5 000 000 t | 12 | 13 | 14 |
| ≤ 7 000 000 t | 13 | 14 | 15 |
| ≤ 10 000 000 t | 15 | 16 | 17 |
| > 10 000 000 t | **18** | 19 | 20 |

| Item | Period (from / to) | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| Oil scale, top rate | 2009-01 / 2009-12 | 5–18 %, top 18 | Law N 100-IV art. 7 пп. 1), column «с 1 января 2009 года» (edition of 17.07.2009) | https://prg.kz/m/amp/document/30519993/1/ | «Приостановить до 1 января 2011 года действие частей первой и второй статьи 336 и части первой статьи 339 … 1. до 250 000 тонн включительно \| 5 \| 6 … 10. Свыше 10 000 000 тонн \| 18 \| 19» | CONFIRMED |
| Oil scale, top rate | 2010-01 / 2010-12 | 5–18 %, top 18 | Law N 100-IV art. 7 as amended by Law of 16.11.2009 N 200-IV: second column relabelled «с 1 января 2013 года» (edition of 30.12.2009) | https://prg.kz/m/amp/document/30606018/1/ | «Приостановить до 1 января 2014 года … Ставки, в % \| с 1 января 2009 года \| с 1 января 2013 года … Свыше 10 000 000 тонн \| 18 \| 19» | CONFIRMED |
| Oil scale, top rate | 2011-01 onward | 5–18 %, top 18 | Law of 26.11.2010 N 356-IV (table moved into art. 336; art. 7 of Law 100-IV deleted) | https://zakon.uchet.kz/rus/docs/Z1000000356 | «статьи 4, 5, 6, 7 и 16 исключить» | CONFIRMED (previous pass + this pass) |
| Code table as adopted | never applied | 7–20 %, top 20 | Tax Code 2008 art. 336, edition of 10.07.2009 | https://prg.kz/m/amp/document/30449190/23/ | «Действие частей первой и второй статьи 336 приостановлено до 1 января 2011 года … до 250 000 тонн включительно \| 7 … свыше 10 000 000 тонн \| 20» | CONFIRMED |
| Domestic-sales coefficient | 2009-01 onward | 0.5 | Law N 100-IV art. 7 пп. 1) (2009–2010); Tax Code 2008 art. 336 (from 2011); Tax Code 2017 art. 743(1) | https://prg.kz/m/amp/document/30519993/1/ ; https://prg.kz/m/amp/document/30449190/23/ ; https://prg.kz/m/amp/document/33805627/73/ | «В случае реализации сырой нефти и газового конденсата на внутреннем рынке Республики Казахстан в порядке, предусмотренном подпунктами 1)-3) пункта 2 статьи 332 … к установленным ставкам применяется понижающий коэффициент 0,5» | CONFIRMED |

Note: the expectation "scheduled increases for 2009, 2010, 2011" is right as legislated in December 2008 (5–18 → 6–19 → 7–20), but neither increase took effect. The top rate was 18 % throughout.
Natural gas in the same article: 10 %; domestic sales 0.5 / 1.0 / 1.5 % by output.

---

## Gap 4. Excise on petrol and diesel, tenge per tonne (wholesale by producers of own production)

| Period (from / to) | Petrol | Diesel | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| 2009-01 / 2014-12 | 4 500 | 540 | Tax Code 2008 art. 280 п. 4 пп. 2) — rates were in the Code itself, not in a Government resolution. Editions of 10.07.2009, 01.01.2013 and 28.11.2014 («Данная редакция действовала до 1 января 2015 года») | https://prg.kz/m/amp/document/30449190/21/ ; https://prg.kz/m/amp/document/31313173/33/ ; https://prg.kz/m/amp/document/31637067/40/ | «1. Оптовая реализация производителями бензина (за исключением авиационного) и дизельного топлива собственного производства \| 4500 \| 540»; retail by producers «5000 \| 600»; «Импорт \| 4500 \| 540» | CONFIRMED |
| 2015-01 / 2015-11-24 | 4 500 | 540 | PP of 13.03.2015 N 133, original edition, in force 1 Jan 2015. Legal basis: art. 280 п. 4 пп. 2) restated by Law of 29.12.2014 N 269-V (in force 1 Jan 2015): rates «утверждаются Правительством» | https://www.alta.ru/tamdoc/15kz0133/ (block «См. пред. ред. Постановление 133 от 13.03.2015»); footnote on https://prg.kz/m/amp/document/30366217/48/ | «1. Оптовая реализация производителями … собственного производства 4500 540»; «изложен в редакции Закона РК от 29.12.14 г. № 269-V (введен в действие с 1 января 2015 г.)» | CONFIRMED |
| 2015-11-25 / 2016-10-14 | 10 500 | 540 | PP of 06.11.2015 N 887; in force 10 calendar days after first publication; published "Казахстанская правда" 14.11.2015 | https://zakon.uchet.kz/rus/docs/P1500000887 | «строку, порядковый номер 1, изложить в следующей редакции: "1. Оптовая реализация производителями … собственного производства 10 500 540"»; «вводится в действие по истечении десяти календарных дней после дня его первого официального опубликования»; «"Казахстанская правда" от 14.11.2015 г. № 219» | CONFIRMED (rates, publication date); start day 25 Nov 2015 COMPUTED |
| 2016-10-15 / 2017-03-31 | 10 500 | 9 300 (April–October); 540 (November–March) | PP of 30.09.2016 N 557, in force 15 Oct 2016 | https://zakon.uchet.kz/rus/docs/P1600000557 | «(апрель – октябрь) 10500 9300 … (ноябрь – март) 10500 540»; «вводится в действие с 15 октября 2016 года» | CONFIRMED |
| 2017-04-01 / 2017-12 | 10 500 | 9 300 (June–October); 540 (November–May) | PP of 31.03.2017 N 144, in force 1 Apr 2017 | https://zakon.uchet.kz/rus/docs/P1700000144 ; https://zakon.uchet.kz/rus/docs/P1500000133 | «(июнь – октябрь) 10500 9300 … (ноябрь – май) 10500 540» | CONFIRMED |
| 2018-01 / 2019-05 | 10 500 | 9 300 (June–October); 540 (November–May) | PP of 06.04.2018 N 173 (in force 1 Jan 2018), table as it stood before PP of 29.05.2019 N 331 | https://www.alta.ru/tamdoc/18kz0173/ (block «См. пред. ред. Постановление 793 от 29.11.2018») | «1. Оптовая реализация производителями … (июнь - октябрь) 10500 9300; 2. … (ноябрь - май) 10500 540 … 7. Импорт 10500 540 (п. 7 в ред. Постановления … от 29.11.2018 N 793)» | CONFIRMED for the producer rows. Caveat: the block read is the edition after PP 793 of 29.11.2018; alta marks only row 7 (import) as changed by PP 793, so rows 1–2 are the original 2018 text |
| 2019-06 onward | see previous pass | | | | | |

Notes
- Practical effect of the seasonal split in 2016: the 9 300 diesel rate first applied 15–31 October 2016, then from 1 June 2017.
- Retail sale by producers: +500 petrol / +60 diesel in every table (5 000 / 600 until Nov 2015; 11 000 / 600 or 9 360 afterwards).
- Import row stayed 4 500 / 540 until PP 793 of 29.11.2018 raised petrol to 10 500.

---

## Gap 5. Excise on filter cigarettes, tenge per 1 000 (domestically produced)

| Period (from / to) | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|
| 2009-01 / 2009-12 | 600 (imported: 750) | Law of 10.12.2008 N 100-IV art. 21 пп. 1), edition of 30.12.2009 (no amendment note on art. 21, i.e. original text) | https://prg.kz/m/amp/document/30606018/2/ | «1) с 1 января 2009 года до 1 января 2010 года действуют следующие ставки акцизов: … 14. \| из 2402 \| Сигареты с фильтром \| 600 тенге/ 1 000 штук \| 750 тенге/ 1 000 штук» (columns «на производимые товары \| на импортируемые товары») | CONFIRMED |
| 2010-01 / 2010-06 | 800 (imported: 950) | same, пп. 2) | same | «2) с 1 января 2010 года до 1 января 2011 года … Сигареты с фильтром \| 800 тенге/ 1 000 штук \| 950 тенге/ 1 000 штук» | CONFIRMED |
| 2010-07 / 2010-12 | 800 (single rate) | Law of 30.06.2010 N 297-IV: пп. 2) cut to «июля 2010», new пп. 2-1) | https://zakon.uchet.kz/rus/docs/Z100000297_ | «в подпункте 2) слова "января 2011" заменить словами "июля 2010"; … "2-1) с 1 июля 2010 года до 1 января 2011 года действуют следующие ставки акцизов» → «Сигареты с фильтром 800 тенге/1000 штук» | CONFIRMED |
| 2011-01 / 2011-12 | 1 000 | Law of 26.11.2010 N 356-IV, art. 1 п. 3 пп. 3): new пп. 3-1) of art. 21 of Law 100-IV | https://zakon.uchet.kz/rus/docs/Z1000000356 | «"3-1) с 1 января 2011 года до 1 января 2012 года действуют следующие ставки акцизов: … Сигареты с фильтром \| 1000 тенге/ 1000 штук» | CONFIRMED |
| 2012-01 / 2012-12 | 1 250 | same, пп. 3-2) | same | «3-2) с 1 января 2012 года до 1 января 2013 года … Сигареты с фильтром \| 1250 тенге/ 1000 штук» | CONFIRMED |
| 2013-01 / 2013-12 | 1 550 | same, пп. 3-3) | same | «3-3) с 1 января 2013 года до 1 января 2014 года … Сигареты с фильтром \| 1550 тенге/ 1000 штук» | CONFIRMED |

Notes
- The domestic rate went to 800 on 1 Jan 2010, not on 1 July 2010. What changed in July 2010 was the removal of the separate, higher import column (Customs Union).
- Base table of art. 280 п. 4 пп. 1) row 14 (suspended, never applied): 1 000 in the Code as adopted (https://prg.kz/m/amp/document/30449190/21/), raised to 1 960 by Law 356-IV («в графе 4 строки 14 слова "1000 тенге" заменить словами "1960 тенге"»).
- Path confirmed: 600 (2009) → 800 (2010) → 1 000 (2011) → 1 250 (2012) → 1 550 (2013) → 3 000 (2014, previous pass).

---

## Gap 6. Export customs duty on crude oil, USD per tonne

| Sub-gap | Period (from / to) | Value | Act and article | URL fetched | Exact wording seen | Status |
|---|---|---|---|---|---|---|
| (a) start | 2008-05-17 / 2008-10-10 | 109.91 | PP of 08.04.2008 N 328, 30 days after publication | https://kase.kz/ru/news/show/1047911 (Interfax-Kazakhstan, 17.05.08) | «В Казахстане 17 мая введена в действие таможенная пошлина на экспорт нефти в размере $109,91 за тонну» | Rate CONFIRMED (previous pass); start date SECOND-HAND |
| (a) autumn 2008 | 2008-10-11 / 2009-01-19 | 203.8 | PP of 29.08.2008 N 805, 30 days after first publication (uchet lists only САПП 2008 N 37 as the publication) | https://zakon.uchet.kz/rus/docs/P080000805_ ; http://kz.kursiv.media/2009-04-23/neftyanikam-oblegchili-poshliny/ ; https://www.inbusiness.kz/ru/news/poshlina_na_neft_poplyvet_vmeste_s_cenoy | act: «в графе "Ставка пошлины (в долларах за 1000 кг)" цифры "109,91", "27,43", "123,3", "82,2", "82,2" заменить соответственно цифрами "203,8", "121,32", "168,7", "112,5", …»; Kursiv 23.04.2009: «С 11 октября прошлого года …»; «До октября 2008 года ставка составляла $109,91 доллара за тонну, после чего поднялась до $203,8 доллара и продержалась до 19 января 2009 года»; inbusiness 29.02.2016: «109,91 доллара за тонну (с момента введения и до 11 октября 2008 года)» | Rate and act CONFIRMED; date 11 Oct 2008 SECOND-HAND. (PortNews / RIA of 11.09.2008 announced 13 October — search snippet only, page not fetched) |
| (a) | 2009-01-20 / 2009-01-25 | 139.79 | PP of 05.12.2008 N 1162, 30 days after publication; published "Казахстанская правда" 20.12.2008 | https://zakon.uchet.kz/rus/docs/P080001162_ ; Kursiv as above ; https://kase.kz/en/news/show/1063535 | Kursiv: «В середине января ставку понизили до $139,79»; Reuters 29.12.2008 via KASE: «reduce the current oil export duty to $139.8 per ton from $203.8 per ton since January 21, 2009» | Rate and publication date CONFIRMED; start day 20 Jan COMPUTED (press: after 19 Jan / "January 21") |
| (b) zero | 2009-01-26 / 2010-08-15 | 0 | PP of 24.12.2008 N 1253, 30 days after publication; published "Казахстанская правда" 27.12.2008 | https://zakon.uchet.kz/rus/docs/P080001253_ ; https://kase.kz/en/news/show/1063535 ; Kursiv as above | Reuters 29.12.2008: «Kazakhstan nulls rate on oil export duty since January 26, 2009»; Kursiv: «С 26 января 2009 года в Казахстане ЭТП на сырую нефть … равняется нулю» | Rate and publication date CONFIRMED; date 26 Jan 2009 SECOND-HAND (strict count from 27.12.2008 gives 26–27 Jan) |
| (c) 20 | 2010-08-15 or 16 / 2010-12-31 | 20 | PP of 13.07.2010 N 709, 30 days after publication; published "Казахстанская правда" 16.07.2010 | https://zakon.uchet.kz/rus/docs/P100000709_ ; https://www.alta.ru/tamdoc/10kz0709/ | uchet: «"Казахстанская правда" от 16.07.2010 г., № 184-185»; alta: «Опубликован 16.07.2010; Дата вступления в силу 15.08.2010» | Rate and publication date CONFIRMED; day: alta.ru says 15 Aug 2010 (SECOND-HAND), strict count gives 16 Aug. Month 2010-08 either way |
| (d) 40 | 2011-01-01 / 2013-04-13 | 40 | **PP of 30.12.2010 N 1445**, п. 3: in force 1 Jan 2011 | https://zakon.uchet.kz/rus/docs/P1000001445 ; https://www.alta.ru/tamdoc/10kz1445/ | «в графе "Ставка пошлины (в долларах за 1000 кг)" цифры "20" заменить цифрами "40"»; «Настоящее постановление вводится в действие с 1 января 2011 года и подлежит официальному опубликованию»; published "Казахстанская правда" 06.01.2011 | CONFIRMED |
| (e) 60 | 2013-04-14 / 2014-03-11 | 60 | PP of 02.04.2013 N 321, 10 days after publication; published "Казахстанская правда" 03.04.2013 | https://zakon.uchet.kz/rus/docs/P1300000321 | «"Казахстанская правда" от 03.04.2013 г. № 115-116»; «вводится в действие по истечении десяти календарных дней со дня первого официального опубликования» | Rate and publication date CONFIRMED; start day 14 Apr 2013 COMPUTED (no press date found; alta.ru gives no in-force date for this act) |
| (e) 80 | 2014-03-12 / 2015-03-18 | 80 | PP of 11.03.2014 N 211, from first publication | https://zakon.uchet.kz/rus/docs/P1400000211 ; https://www.alta.ru/tamdoc/14kz0211/ | uchet: «"Казахстанская правда" от 12.03.2014 г. № 48»; alta: «Дата вступления в силу 12.03.2014; Опубликован 12.03.2014» | CONFIRMED |
| (e) 60 | 2015-03-19 / 2015-12-31 | 60 | PP of 17.03.2015 N 145, from first publication; then Order of 27.05.2015 N 405 (published 08.07.2015, in force 19.07.2015 per alta) keeps 60 | https://zakon.uchet.kz/rus/docs/P1500000145 ; https://www.alta.ru/tamdoc/15kz0145/ ; https://www.alta.ru/tamdoc/15kz0405/ | uchet: «"Казахстанская правда" от 19.03.2015 г. № 52»; alta: «Дата вступления в силу 19.03.2015; Опубликован 19.03.2015» | CONFIRMED |
| 40 | 2016-01-01 / 2016-02-29 | 40 | Order of 20.01.2016 N 18 (published 22.01.2016, applies from 1 Jan 2016) | https://www.alta.ru/tamdoc/16kz0018/ ; previous pass | alta: «Опубликован в Интернете 22.01.2016; Дата вступления в силу 23.01.2016» | CONFIRMED (previous pass) |
| (f) step table | 2016-03-01 / 2023-08-25 | table below | Order of the Minister of National Economy of 17.02.2016 N 81, Annex 1 to the Rules, **as originally enacted** (registered 24.02.2016 N 13217, published 25.02.2016) | https://www.alta.ru/tamdoc/16kz0081/ (block «См. пред. ред. Приказ 81 от 17.02.2016 … СТАВКИ ВЫВОЗНЫХ ТАМОЖЕННЫХ ПОШЛИН НА СЫРУЮ НЕФТЬ») | «1. до 25 долларов США за баррель 0; 2. с 25 до 30 долларов США за баррель 10; 3. с 30 до 35 … 20; 4. с 35 до 40 … 35; 5. с 40 до 45 … 40; … 17. со 100 до 105 … 100; 18. со 105 до 115 … 115; … 26. от 185 долларов США за баррель и выше 236»; Rules п. 5: «в течении месяца применяется одна из ставок … предусмотренная приложением 1 … в зависимости от значения средней рыночной цены на сырую нефть за предшествующий период» | CONFIRMED (alta.ru redline copy). 1 March 2016 start: SECOND-HAND (KPMG April 2016: «с 1 марта 2016 г. введена прогрессивная шкала ставок»; cdb.kz, previous pass) |
| (f) formula | 2023-08-26 / 2026-08 | duty (USD/t) = average price (USD/bbl) for 25–105; 0 below 25; table above 105 | Order of 14.08.2023 N 311-НҚ (new edition of the Rules), in force 10 days after publication | https://cdb.kz/sistema/pravovaya-baza/o-vnesenii-izmeneniy-v-prikaz-ministra-natsionalnoy-ekonomiki-respubliki-kazakhstan-ot-17-fevralya-2-2023-08/ ; https://www.alta.ru/tamdoc/23kz0311/ ; https://www.alta.ru/tamdoc/16kz0081/ | «2) при значении средней рыночной цены сырой нефти от 25 до 105 долларов США за баррель – размер ставки вывозной таможенной пошлины рассчитывается …»; alta: «Дата вступления в силу 26.08.2023»; alta marks the Rules «Нов. ред. Приказ 311-НК от 14.08.2023» | Text CONFIRMED; date 26.08.2023 SECOND-HAND (alta.ru field). First month computed by formula: September 2023 |

**Original March-2016 crude scale (Order N 81, Annex 1 to the Rules) — CONFIRMED via alta.ru**

| Average price, USD/bbl | Duty, USD/t | | Average price, USD/bbl | Duty, USD/t |
|---|---|---|---|---|
| below 25 | 0 | | 85–90 | 85 |
| 25–30 | 10 | | 90–95 | 90 |
| 30–35 | 20 | | 95–100 | 95 |
| 35–40 | 35 | | 100–105 | 100 |
| 40–45 | 40 | | 105–115 | 115 |
| 45–50 | 45 | | 115–125 | 130 |
| 50–55 | 50 | | 125–135 | 145 |
| 55–60 | 55 | | 135–145 | 160 |
| 60–65 | 60 | | 145–155 | 176 |
| 65–70 | 65 | | 155–165 | 191 |
| 70–75 | 70 | | 165–175 | 206 |
| 75–80 | 75 | | 175–185 | 221 |
| 80–85 | 80 | | 185 and above | 236 |

Later changes to the scale, as seen in the redline copy and in amending orders
- The crude column is identical in every later version of the table read: edition of Order of 11.06.2019 N 54 (adds a light-products column at 0.9 × crude), Order of 25.12.2020 N 310-НҚ (light products at 0.3 × crude; https://cdb.kz/sistema/pravovaya-baza/o-vnesenii-izmeneniy-v-prikaz-ministra-natsionalnoy-ekonomiki-respubliki-kazakhstan-ot-17-fevralya-2/), Order of 13.02.2023 N 70-НҚ (light products = crude). So for crude the step table ran unchanged from March 2016 to August 2023.
- Order of 06.10.2016 N 441 changed only the rounding/publication rule (п. 4) and added п. 10-1 on oil products. Order of 30.01.2017 N 27 changed only HS codes in the list (https://zakon.uchet.kz/rus/docs/V1700014829).
- Order 311-НҚ (Aug 2023) replaced the 5-dollar steps between 25 and 105 USD/bbl with the continuous formula and kept the old steps above 105. Step table vs. formula differ by up to 5 USD/t inside a band (and by 0–15 in the 25–40 range, where the old table gave 10 / 20 / 35).
- Other amending orders listed by alta.ru for Order N 81 (list of goods, oil products, not the crude scale as far as the redlines show): 19.04.2017 N 167, 02.03.2018 N 87, 28.12.2018 N 106, 24.05.2019 N 42, 10.04.2020 N 76-НҚ, 03.08.2020 N 163-НҚ, 19.03.2021 N 227-НҚ, 09.06.2021 N 400-НҚ, 07.10.2021 N 550-НҚ, 01.03.2022 N 133-НҚ, 31.05.2022 N 244-НҚ, 07.11.2022 N 425-НҚ, 20.01.2023 N 35-НҚ, 24.05.2023 N 184-НҚ, 21.08.2024 N 310-НҚ, 07.02.2025 N 47-НҚ, 11.06.2025 N 183-НҚ. Order N 81 lost force on 15.08.2026 (alta.ru).
- A press description of the 2016 scale is slightly wrong: inbusiness.kz 29.02.2016 says «от 30 до 40 долларов – 20 долларов»; the order has 30–35 → 20 and 35–40 → 35.

---

## What is still open

1. Exact legal start day of PP 805 (203.8): no newspaper publication date on zakon.uchet.kz; 11 Oct 2008 rests on two press sources.
2. Start days marked COMPUTED (20 Jan 2009, 14 Apr 2013, 25 Nov 2015) could be one day off; 15 vs 16 Aug 2010 differs between alta.ru and a strict count.
3. PP N 173 of 2018: the text exactly as signed on 06.04.2018 was not seen; the earliest edition read is the one after PP 793 of 29.11.2018, in which only the import row is marked as changed.
4. Tax Code 2017 art. 746: the earliest edition read is 19.04.2019 (no amending law to art. 746 before 2021 is listed).
5. Law of 29.12.2014 N 269-V (moved fuel excise rates from the Code to the Government) was seen only as a footnote in the prg.kz final edition, not as its own text.
