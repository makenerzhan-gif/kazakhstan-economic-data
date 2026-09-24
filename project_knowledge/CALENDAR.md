# Календарь обновлений модели ВВП

Сформировано 2026-09-24 скриптом `scripts/build_calendar.py`.
«Следующее обновление» для таблиц БНС — «Дата следующей актуализации» из листа Метаданные самой таблицы; для остальных источников — расписание из `config/calendar.yaml`. Дата в прошлом означает: источник обещал выпуск, которого пайплайн ещё не видел.

## Ряды пайплайна, которые читает модель

73 наборов; с объявленной датой следующего обновления — 32, просрочено — 0.

| Следующее обновление | Набор | Агентство | Последнее обновление (публикация) | Где в модели |
|---|---|---|---|---|
| 2026-09-30 | `GVA_DEFLATOR_BY_SECTION` | bns | 2026-09-24 (2026-08-14) | «Факт_БНС» (fact_bns_gva_deflator); «Дефляторы_производ_регионы» (gva_deflator_sections) |
| 2026-09-30 | `GVA_NOMINAL_BY_SECTION` | bns | 2026-09-24 (2026-08-14) | «Факт_БНС» (fact_bns_gva_nominal); «ВДС_производ_регионы» (gva_sections_control) |
| 2026-09-30 | `GVA_VOLUME_INDEX_BY_SECTION` | bns | 2026-09-24 (2026-08-14) | «Факт_БНС» (fact_bns_gva_volume_index); «ИФО_производ_регионы» (gva_volume_index_control) |
| 2026-10-01 | `INCOME_CFC_BY_SECTION` | bns | 2026-09-24 (2026-08-03) | «ВВП_доходы» (income_cfc) |
| 2026-10-01 | `INCOME_COMPENSATION_BY_SECTION` | bns | 2026-09-24 (2026-08-03) | «ВВП_доходы» (income_compensation) |
| 2026-10-01 | `INCOME_OTHER_TAXES_BY_SECTION` | bns | 2026-09-24 (2026-08-03) | «ВВП_доходы» (income_other_taxes) |
| 2026-10-01 | `INCOME_PROFIT_BY_SECTION` | bns | 2026-09-24 (2026-08-03) | «ВВП_доходы» (income_profit) |
| 2026-10-12 | `GDP_EXPENDITURE_DEFLATOR` | bns | 2026-09-24 (2026-07-13) | «ВВП_расходы_МКИ» (expenditure_deflator) |
| 2026-10-12 | `GDP_EXPENDITURE_NOMINAL` | bns | 2026-09-24 (2026-07-13) | «ВВП_расходы_МКИ» (expenditure_nominal) |
| 2026-10-12 | `GDP_EXPENDITURE_VOLUME_INDEX` | bns | 2026-09-24 (2026-07-13) | «ВВП_расходы_МКИ» (expenditure_volume_index) |
| 2026-10-12 | `GRP_VOLUME_INDEX_BY_REGION` | bns | 2026-09-24 (2026-08-24) | «ИФО_производ_регионы» (grp_ifo_regions) |
| 2026-10-12 | `GVA_NOMINAL_BY_REGION_SECTION` | bns | 2026-09-24 (2026-08-24) | «ВДС_производ_регионы» (vrp_regions_sections) |
| 2026-10-28 | `QNA_GDP_EXPENDITURE` | bns | 2026-09-24 (2026-07-28) | «Факт_КНС» (fact_qna_gdp_expenditure) |
| 2026-10-28 | `QNA_GDP_EXPENDITURE_VOLUME_INDEX_YTD` | bns | 2026-09-24 (2026-07-28) | «Факт_КНС» (fact_qna_gdp_expenditure_volume_index_ytd) |
| 2026-11-12 | `EMPLOYED_BY_SECTION` | bns | 2026-09-24 (2026-08-13) | «Занятое население» (employed_sections, employed_sections_control) |
| 2027-03-31 | `EMPLOYED_AGRICULTURE_BY_REGION` | bns | 2026-09-24 (2026-03-30) | «Факт_БНС» (fact_bns_employed_agriculture) |
| 2027-03-31 | `EMPLOYED_BY_REGION` | bns | 2026-09-24 (2026-03-30) | «Внешние и внутренние факторы» (employed_regions); «Факт_БНС» (fact_bns_employed_total) |
| 2027-03-31 | `EMPLOYED_INDUSTRY_CONSTRUCTION_BY_REGION` | bns | 2026-09-24 (2026-03-30) | «Факт_БНС» (fact_bns_employed_industry_construction) |
| 2027-03-31 | `EMPLOYED_SERVICES_BY_REGION` | bns | 2026-09-24 (2026-03-30) | «Факт_БНС» (fact_bns_employed_services) |
| 2027-03-31 | `EMPLOYED_TOTAL` | bns | 2026-09-24 (2026-03-30) | «Внешние и внутренние факторы» (employed); «Прогнозы ЦГО 2024-29» (employed) |
| 2027-03-31 | `EMPLOYEES_BY_REGION` | bns | 2026-09-24 (2026-03-30) | «Прогнозы ЦГО 2024-29» (cgo_employees) |
| 2027-03-31 | `LABOUR_FORCE_BY_REGION` | bns | 2026-09-24 (2026-03-30) | «Внешние и внутренние факторы» (labour_force_regions, labour_force_national); «Прогнозы ЦГО 2024-29» (cgo_labour_force) |
| 2027-03-31 | `SELF_EMPLOYED_BY_REGION` | bns | 2026-09-24 (2026-03-30) | «Внешние и внутренние факторы» (self_employed_regions, self_employed_national); «Прогнозы ЦГО 2024-29» (cgo_self_employed) |
| 2027-03-31 | `UNEMPLOYED_BY_REGION` | bns | 2026-09-24 (2026-03-30) | «Внешние и внутренние факторы» (unemployed_regions, unemployed_national); «Прогнозы ЦГО 2024-29» (cgo_unemployed) |
| 2027-03-31 | `UNEMPLOYMENT_RATE_BY_REGION` | bns | 2026-09-24 (2026-03-30) | «Внешние и внутренние факторы» (unemployment_rate_regions, unemployment_rate_national); «Прогнозы ЦГО 2024-29» (cgo_unemployment_rate) |
| 2027-04-30 | `POPULATION_AVG_BY_REGION` | bns | 2026-09-24 (2026-04-30) | «Внешние и внутренние факторы» (population_regions, population_urban_rural_national) |
| 2027-04-30 | `POPULATION_BNS` | bns | 2026-09-24 (2026-04-30) | «Внешние и внутренние факторы» (population) |
| 2027-07-03 | `PRODUCTION_NATURAL_BY_REGION` | bns | 2026-09-24 (2026-07-03) | «ВДС_производ_регионы» (natural_output_rows); «Прогнозы ЦГО 2024-29» (cgo_oil_fact, cgo_gas_fact) |
| 2027-07-31 | `NOE_ILLEGAL_SHARE_BY_SECTION` | bns | 2026-09-24 (2026-07-31) | «Ненаблюд_незакон_экономика» (noe_illegal_share) |
| 2027-07-31 | `NOE_SHARE_BY_SECTION` | bns | 2026-09-24 (2026-07-31) | «Ненаблюд_незакон_экономика» (noe_share) |
| 2027-08-23 | `GVA_NOMINAL_INDUSTRY_DIVISIONS` | bns | 2026-09-24 (2026-08-24) | «Факт_БНС» (fact_bns_industry_divisions) |
| 2027-08-23 | `GVA_VOLUME_INDEX_BY_REGION_SECTION` | bns | 2026-09-24 (2026-08-24) | «ИФО_производ_регионы» (ifo_regions_sections) |
| — | `AGRICULTURE_VOLUME_INDEX_BY_ACTIVITY` | bns | 2026-09-24 (—) | «Факт_БНС» (fact_bns_agriculture_indices) |
| — | `AVG_WAGE` | bns | 2026-09-24 (—) | «Прогнозы ЦГО 2024-29» (average_wage) |
| — | `CAPITAL_CONSUMPTION` | bns | 2026-09-24 (—) | «ВВП_доходы» (consumption_of_fixed_capital) |
| — | `COMPENSATION_EMPLOYEES` | bns | 2026-09-24 (—) | «ВВП_доходы» (compensation_of_employees) |
| — | `CPI_YTD` | bns | 2026-09-24 (—) | «Внешние и внутренние факторы» (cpi_december) |
| — | `EXPORTS` | bns | 2026-09-24 (—) | «Экспорт» (exports_total) |
| — | `EXPORTS_VALUE_BY_COMMODITY_GROUP` | bns | 2026-09-24 (—) | «Экспорт» (exports_value_groups) |
| — | `EXPORTS_VOLUME_BY_COMMODITY_GROUP` | bns | 2026-09-24 (—) | «Экспорт» (exports_volume_tonnes, exports_volume_thousand_tonnes) |
| — | `EXPORT_VOLUME_INDEX` | bns | 2026-09-24 (—) | «ВВП_расходы_МКИ» (export_volume_index) |
| — | `GDP_DEFLATOR` | bns | 2026-09-24 (—) | «Дефляторы_производ_регионы» (gdp_deflator) |
| — | `GDP_INCOME_METHOD` | bns | 2026-09-24 (—) | «ВДС_производ_регионы» (gdp_nominal); «ВВП_доходы» (gdp_nominal) |
| — | `GDP_REAL` | bns | 2026-09-24 (—) | «ИФО_производ_регионы» (gdp_real); «ВВП_расходы_МКИ» (gdp_real) |
| — | `GFCF` | bns | 2026-09-24 (—) | «ВВП_расходы_МКИ» (gfcf) |
| — | `GFCF_VOLUME_INDEX` | bns | 2026-09-24 (—) | «ВВП_расходы_МКИ» (gfcf_volume_index) |
| — | `GRAIN_HARVEST_BY_REGION` | bns | 2026-09-24 (—) | «ВДС_производ_регионы» (grain_harvest_national, grain_harvest_regions); «Прогнозы ЦГО 2024-29» (cgo_grain_harvest) |
| — | `GROSS_ACCUMULATION` | bns | 2026-09-24 (—) | «ВВП_расходы_МКИ» (gross_accumulation) |
| — | `GVA_FOREIGN_BY_SECTION` | bns | 2026-09-24 (—) | «ВДС_формы_собственности» (ownership_foreign) |
| — | `GVA_PRIVATE_BY_SECTION` | bns | 2026-09-24 (—) | «ВДС_формы_собственности» (ownership_private) |
| — | `GVA_STATE_BY_SECTION` | bns | 2026-09-24 (—) | «ВДС_формы_собственности» (ownership_state) |
| — | `HOUSEHOLD_CONSUMPTION` | bns | 2026-09-24 (—) | «ВВП_расходы_МКИ» (household_consumption) |
| — | `IMPORT_VOLUME_INDEX` | bns | 2026-09-24 (—) | «ВВП_расходы_МКИ» (import_volume_index) |
| — | `INDUSTRIAL_PRODUCTION_INDEX_BY_ACTIVITY` | bns | 2026-09-24 (—) | «Факт_БНС» (fact_bns_industry_indices) |
| — | `INVESTMENT_BY_REGION` | bns | 2026-09-24 (—) | «ИОК» (investment_regions_iok); «ВВП_расходы_МКИ» (investment_regions_mki) |
| — | `INVESTMENT_BY_SECTION` | bns | 2026-09-24 (—) | «ИОК» (investment_sections_iok); «ВВП_расходы_МКИ» (investment_sections_mki) |
| — | `INVESTMENT_VOLUME_INDEX_BY_REGION` | bns | 2026-09-24 (—) | «ИОК» (investment_volume_regions_iok, investment_volume_national); «ВВП_расходы_МКИ» (investment_volume_regions_mki) |
| — | `INVESTMENT_VOLUME_INDEX_BY_SECTION` | bns | 2026-09-24 (—) | «ВВП_расходы_МКИ» (investment_volume_sections_mki) |
| — | `NET_EXPORTS` | bns | 2026-09-24 (—) | «ВВП_расходы_МКИ» (net_exports) |
| — | `NET_TAXES_ON_PRODUCTS` | bns | 2026-09-24 (—) | «ВДС_производ_регионы» (net_taxes_on_products); «ВВП_доходы» (net_taxes_on_products) |
| — | `QNA_GVA_BY_SECTION` | bns | 2026-09-24 (—) | «Факт_КНС» (fact_qna_gva_by_section) |
| — | `QNA_GVA_DEFLATOR_BY_SECTION_YTD` | bns | 2026-09-24 (—) | «Факт_КНС» (fact_qna_gva_deflator_by_section_ytd) |
| — | `QNA_GVA_VOLUME_INDEX_BY_SECTION_YTD` | bns | 2026-09-24 (—) | «Факт_КНС» (fact_qna_gva_volume_index_by_section_ytd) |
| — | `REAL_WAGE_INDEX` | bns | 2026-09-24 (—) | «Прогнозы ЦГО 2024-29» (cgo_real_wage_index) |
| — | `TAXES_ON_PRODUCTS` | bns | 2026-09-24 (—) | «ВДС_производ_регионы» (taxes_on_products) |
| — | `TOTAL_CONSUMPTION_EXPENDITURE` | bns | 2026-09-24 (—) | «ВВП_расходы_МКИ» (final_consumption) |
| — | `EIA_STEO_PRICES` | eia | 2026-09-24 (September 2026) | «Внешние и внутренние факторы» (brent_eia_forecast) |
| — | `IMF_PPP_EXCHANGE_RATE` | imf | 2026-09-24 (—) | «Внешние и внутренние факторы» (ppp_exchange_rate) |
| — | `EXCHANGE_RATE` | nbk | 2026-09-24 (—) | «Внешние и внутренние факторы» (exchange_rate) |
| — | `WB_COMMODITY_INDEX_FORECASTS` | wb | 2026-09-24 (April 28, 2026) | «Внешние и внутренние факторы» (wb_index_forecasts) |
| — | `WB_COMMODITY_INDICES_ANNUAL` | wb | 2026-09-24 (September 02, 2026) | «Внешние и внутренние факторы» (wb_indices_history) |
| — | `WB_COMMODITY_PRICES_ANNUAL` | wb | 2026-09-24 (September 02, 2026) | «Внешние и внутренние факторы» (wb_prices_history, brent_reference_control) |
| — | `WB_COMMODITY_PRICE_FORECASTS` | wb | 2026-09-24 (April 28, 2026) | «Внешние и внутренние факторы» (wb_price_forecasts, brent_wb_forecast) |

## Источники с фиксированным ритмом и ручные документы

| Ближайшая дата | Источник | Ритм | Где в модели | Действие |
|---|---|---|---|---|
| 2026-10-02 | Commodity Markets Outlook — таблица прогнозов (WB_COMMODITY_PRICE_FORECASTS, WB_COMMODITY_INDEX_FORECASTS) | два раза в год, конец апреля и конец октября | «Внешние и внутренние факторы» строки 65–124 и 146–161 за 2026–2027, строка 5 (Brent ВБ) | update_all → model_sync --apply; 2028–2030 модель дотягивает сама (уровень 2027 г.) |
| — | Экспресс-информация «Об инвестициях в основной капитал» по источникам финансирования | ежемесячно (оперативные данные); уточнённые годовые — февраль–март | «ИОК» строки 48–49, «ВВП_расходы_МКИ» 54–55 (manual_inputs: iok_budget_private_split) | вручную: динамической таблицы у БНС нет |
| — | Таблицы «Затраты–Выпуск» (справочные листы Лист2, Лист3) | ежегодно, с лагом около двух лет (за 2023 г. — в 2025 г.) | Лист2, Лист3 (manual_inputs: io_tables_2023_*) | вручную; на расчёт не влияет |
| — | Прогнозы Brent агентств (строки 6–24) | по решению автора; ВБ и EIA обновляются пайплайном | «Внешние и внутренние факторы» строки 3–24 (manual_inputs: brent_agency_forecasts) | вручную |
| — | Short-Term Energy Outlook, таблица 2 (EIA_STEO_PRICES) | ежемесячно, первая декада месяца (выпуск сентября 2026 — 9 сентября) | «Внешние и внутренние факторы» строка 4 (Brent EIA, 2026–2027) | update_all → model_sync; консенсус (строка 3) пересчитается формулой |
| — | World Economic Outlook — IMF_* ряды, курс по ППС (IMF_PPP_EXCHANGE_RATE) | два раза в год, апрель и октябрь | «Внешние и внутренние факторы» строка 51 (курс к международному доллару) | update_all → model_sync --apply (все годы, включая прогноз) |
| — | Прогноз социально-экономического развития на 2027–2029 гг. — прогнозы ЦГО и министерств, курс, инфляция | ежегодно, август–сентябрь (одобрение Правительством); документ ПСЭР 2027–2029 в модель ещё не поступал | «Прогнозы ЦГО 2024-29» (manual_inputs: cgo_forecasts, cgo_fact_columns), «Внешние и внутренние факторы» 51, 55–57 | вручную, по решению автора; после загрузки — model_sync для строк, у которых есть ряд БНС |
| — | Pink Sheet — месячные и годовые цены и индексы (WB_COMMODITY_PRICES_ANNUAL, WB_COMMODITY_INDICES_ANNUAL, OIL_PRICE_BRENT) | ежемесячно, первые рабочие дни месяца; годовой файл дополняется новым годом в январе | «Внешние и внутренние факторы» строки 65–124, 146–161 (факт), строки 2 и 66 (Brent) | факт прошлого года появляется в январском выпуске — тогда сверка 2026 г. |

## Ручные входы модели (config/manual_inputs.yaml)

| Блок | Лист | Строки | Вид | Версия | Когда обновлять |
|---|---|---|---|---|---|
| `factors_history` | Внешние и внутренние факторы | 2–331 (1991–2022) | history | до 2025-01; версия источников не зафиксирована | не сверяется; при желании — расширить years в model_map (пайплайн отдаёт ВБ с 1960 г., БНС с 2000/2010 г.) |
| `brent_agency_forecasts` | Внешние и внутренние факторы | 3–24 (2023–2030) | external | 2025-01 (ВБ строка 5 и EIA строка 4 за 2026–2027 — из пайплайна, CMO апрель 2026 / STEO сентябрь 2026) | при пересборе консенсуса; 2023–2025 в строках 4–5 — прогнозы старых выпусков, не факт |
| `factors_oil_parameters` | Внешние и внутренние факторы | 26–41 (2023–2030) | assumption | unknown | по решению автора |
| `inflation_corridor` | Внешние и внутренние факторы | 55–56 (2023–2030) | external | 2025-01 | при изменении цели по инфляции НБ РК (ряд INFLATION_TARGET в пайплайне — для сверки) |
| `deflator_inflation_value` | Внешние и внутренние факторы | 57 (2023–2030) | assumption | 2025-01 | решение автора (см. отчёт, «Не заменено и почему») |
| `grains_price_constant` | Внешние и внутренние факторы | 85 (2025–2030) | review | unknown | уточнить у автора, используется ли строка |
| `wb_price_changes_history` | Внешние и внутренние факторы | 128–143 (2023–2025) | history | 2025-01 | не требуется: прогнозные годы считаются формулами |
| `cgo_history` | Прогнозы ЦГО 2024-29 | 2–135 (2020–2022) | history | 2025-01 | не сверяется |
| `cgo_fact_columns` | Прогнозы ЦГО 2024-29 | 2–135 (2023–2025) | external | 2025-01 | при выходе ПСЭР 2027–2029 (документ ещё не получен — публично есть только сообщение Правительства) |
| `cgo_forecasts` | Прогнозы ЦГО 2024-29 | 2–135 (2026–2030) | external | 2025-01 | при выходе ПСЭР 2027–2029; до этого 2026–2029 — прежний вариант, 2030 — правило модели |
| `iok_history` | ИОК | 1–140 (1991–2022) | history | до 2025-01 | не сверяется (пайплайн отдаёт 5546/5547/5549 с 2001 г. — можно расширить years в model_map) |
| `iok_budget_private_split` | ИОК | 48, 49, 74 (2023–2025) | external | 2026-09-14 | при выходе годовой публикации ИОК по источникам финансирования; динамической таблицы у БНС нет |
| `mki_history` | ВВП_расходы_МКИ | 1–170 (1991–2022) | history | до 2025-01 | не сверяется |
| `mki_budget_split_and_constants` | ВВП_расходы_МКИ | 54, 55, 123, 125 (2023–2025) | external | 2026-09-14 | вместе с iok_budget_private_split |
| `gva_history` | ВДС_производ_регионы | 1–1460 (1991–2022) | history | до 2025-01 | не сверяется; секции, регионы и натуральные строки за 2023–2025 сверяются пайплайном |
| `gva_base_2023_lower_rows` | ВДС_производ_регионы | 1–1460 (2023–2023) | history | 2025-01 (пересмотры БНС 2023 г. по регионам и секциям внесены 14.09.2026) | при пересмотре БНС 2023 г. — вручную, по секциям через пайплайн |
| `ifo_history` | ИФО_производ_регионы | 1–1460 (1991–2022) | history | до 2025-01 | не сверяется |
| `ifo_base_2023_lower_rows` | ИФО_производ_регионы | 1–1460 (2023–2023) | history | 2025-01 | не сверяется |
| `ifo_coal_2024_override` | ИФО_производ_регионы | 102 (2024–2024) | review | unknown | решение автора: вернуть формулу или задокументировать число |
| `deflators_history` | Дефляторы_производ_регионы | 1–1460 (1991–2022) | history | до 2025-01 | не сверяется |
| `deflators_base_2023_lower_rows` | Дефляторы_производ_регионы | 1–1460 (2023–2023) | history | 2025-01 | не сверяется |
| `satellites_history` | Занятое население | 1–80 (1991–2022) | history | до 2025-01 | не сверяется |
| `ownership_history` | ВДС_формы_собственности | 1–80 (1991–2022) | history | до 2025-01 | не сверяется |
| `noe_history` | Ненаблюд_незакон_экономика | 1–80 (1991–2022) | history | до 2025-01 | не сверяется |
| `income_history` | ВВП_доходы | 1–60 (1991–2022) | history | до 2025-01 | не сверяется |
| `exports_history` | Экспорт | 1–109 (1998–2022) | history | до 2025-01 | не сверяется (пайплайн отдаёт группы с 2015 г. — можно расширить years в model_map) |
| `exports_ten_digit_rows` | Экспорт | 10, 11, 91, 92, 93, 94 (2023–2025) | external | 2025-01 | вручную по публикации основных товаров экспорта, либо подключить 10-значный источник |
| `exports_price_constants` | Экспорт | 52–53 (2023–2030) | assumption | unknown | по решению автора |
| `productivity_satellite` | Производ-ть труда | 1–60 | satellite | до 2025-01 | не требуется |
| `io_tables_2023_resources` | Лист3 | 1–131 | satellite | 2025 (таблицы ЗВ за 2023 г.) | при выходе таблиц ЗВ за 2024 г. |
| `io_tables_2023_summary` | Лист2 | 1–74 | satellite | 2025 (таблицы ЗВ за 2023 г.) | при выходе таблиц ЗВ за 2024 г. |
| `fact_bns_calibration` | Факт_БНС | 1–130 | assumption | 2026-09-14 | пересчитываются при загрузке новых индексов |
| `real_gva_zero_row` | Реал_ВДС_производ_регионы | 1435 | assumption | unknown | не требуется |
| `ifo_zero_row` | ИФО_производ_регионы | 1435 | assumption | unknown | не требуется |
| `deflators_zero_row` | Дефляторы_производ_регионы | 1435 | assumption | unknown | не требуется |
| `ifo_electricity_subsections_2024` | ИФО_производ_регионы | 975, 998, 1000 (2024–2024) | review | unknown | решение автора: источник или удалить |
| `derived_sheets_literal_numbers` | Вклад_в_ВВП_производ_регионы | 301 (2022–2023) | review | unknown | решение автора: вернуть формулы |
| `derived_sheets_literal_numbers_share` | Доля_в_ВВП_производ_регионы | 301 (2022–2023) | review | unknown | решение автора |
| `derived_sheets_literal_numbers_structure` | Структура_ВДС_производ_регионы | 301 (2022–2023) | review | unknown | решение автора |
| `derived_sheets_history` | Вклад_в_ВВП_производ_регионы | 1–1460 (1991–2022) | history | до 2025-01 | не сверяется |
| `derived_sheets_history_share` | Доля_в_ВВП_производ_регионы | 1–1460 (1991–2022) | history | до 2025-01 | не сверяется |
| `derived_sheets_history_share_industry` | Доля_по_отрасл_производ_регионы | 1–1460 (1991–2023) | history | до 2025-01 | не сверяется |
| `derived_sheets_history_structure` | Структура_ВДС_производ_регионы | 1–1460 (1991–2022) | history | до 2025-01 | не сверяется |
| `derived_sheets_history_real` | Реал_ВДС_производ_регионы | 1–1460 (1991–2022) | history | до 2025-01 | не сверяется |

## Порядок обновления модели

1. `python scripts/update_all.py                       # источники → сырьё → проверки → processed → unified (в CI ежедневно)`
2. `python scripts/model_sync.py                       # сверка модели с пайплайном: ok / diff / control / missing`
3. `python scripts/model_sync.py --apply --out <копия>  # запись расхождений во входные ячейки (примечание + журнал), оригинал не трогается`
4. `python scripts/model_coverage.py --strict           # ни одного числа без источника: model_map или manual_inputs`
5. `python scripts/build_calendar.py                    # календарь: что и когда обновится следующим`
