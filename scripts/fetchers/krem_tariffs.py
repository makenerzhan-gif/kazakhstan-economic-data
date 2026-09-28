"""Utility-tariff and administered-price decisions: an item-level EVENT dataset (TARIFF_DECISIONS)
for inflation modelling -- one record per decision, dated by the month it takes effect.

Sources (all verified live 2026-09-27):

1. КРЕМ documents -- gov.kz content-manager API, project «krem»:
       https://www.gov.kz/api/v1/public/content-manager/documents?projects=krem&page=N&size=100
                                                                 &sort-by=created_date:DESC
   The Committee for Regulation of Natural Monopolies (КРЕМ МНЭ РК) and all its territorial
   departments (ДКРЕМ по <области>) publish into this ONE project -- the departments have no
   project slugs of their own (they are sub-pages «Территориальные департаменты» of «krem»);
   the publishing department is the entry's `gosorgan` (e.g. «Департамент Комитета по
   регулированию естественных монополий по Жамбылской области»), and the region is also in
   `activities` («Жамбылская область», «ВКО», «г. Шымкент» …). 33 602 entries on 2026-09-27,
   published 2017-2026 (a few older); 11 993 are «Приказ». 2 770 of them are kept as dated utility
   tariff decisions (3 413 records, one per service); skipped: 23 792 not decisions (protocols,
   reports, procurement lists …), 1 463 Kazakh duplicates, 1 099 without a recognisable service,
   1 017 outside utilities (rail access, ports, oil), 181 estimate-only, 3 245 undated, 35 without
   a region. Filter `created_date=gt:<ISO datetime>` works (incremental
   runs); `created_date=gte:` answers HTTP 500.
   PITFALL: the attached order files are SCANS (PDF and even .docx hold page images; pypdf
   extracts nothing), so everything is read from the TITLE: the decision type, the company, the
   service, the order date («Приказ №54-ОД от 24.09.2026 года …») and -- in ~5% of the kept titles -- the
   effective date («… с вводом в действие с 1 июля 2025 года», «на период с 1 марта 2023
   года …»). The tariff level and the size of the change are not in the title, so these records
   carry value = NaN.
   Effective date: stated in the title -> used as is; otherwise the FIRST DAY OF THE MONTH AFTER
   THE ORDER DATE (an estimate: of the 17 titles that carry both dates, 8 take effect on the 1st
   of the next month, 5 a month later, 4 otherwise). Titles with neither date are dropped
   (publication lags the order by a median 5 days but by more than 69 days for a quarter of the
   titles), except from the two departments that publish within days (PROMPT_PUBLISHERS); the
   skips are counted in the manifest. Resulting basis on 2026-09-27: 178 records stated, 2 689
   order + 1 month, 546 publication + 1 month.
   The listing also carries protocols of hearings, reports on tariff-estimate execution,
   procurement lists, refusals and cancellations; they are excluded by title.

2. КРЕМ news -- same API, /news?projects=eq:krem (1 036 items, 2019-06 to date). The news
   endpoint answers HTTP 400 «notAllowed» unless the session first POSTs to
   /api/v1/public/_/c/k6 (a cookie ticket), unlike /documents. Press releases of the regional
   departments state old->new tariffs and % changes («… тариф снижен с 85,3 тенге до 76,78
   тенге за 1 м3 с НДС или на 10%»; «… с вводом в действие с 1 июня 2020 года»). Parsed per
   clause: a clause is kept only when it names a service, a decision verb and an effective date
   («с 1 <месяц> [<год>]», in the sentence or the one next to it), and a region is known (clause,
   sentence, title, the one department the release names, or -- a central-committee release
   naming no region at all -- national); plans and applications («планируется», «заявка»,
   «предстоящ…») are skipped. value = the stated % (sign from the old->new pair or the verb),
   else computed from «с A до B тенге»; NaN when the two disagree. 90 records (53 with a value),
   mostly 2019-2020 and 2024.

3. Ministry of Energy price caps -- normative orders on old.adilet.zan.kz (the new
   adilet.zan.kz is a SPA whose /api/documents* needs an API key; old.adilet serves full HTML):
   * ELEC_GEN_CAP: «Об утверждении предельных тарифов на электрическую энергию» -- order № 514
     of 14.12.2018 (V1800017956, 2019-2025) and its amendments, found on its /links page, and
     order № 508-н/қ of 24.12.2025 (G25JVM00508, 2026-2032) with its amendments. Each amending
     act restates the whole table «N-группа v2019 … v2025» (or single rows) and says «вводится
     в действие с <дата>». value = the unweighted mean % change of the caps across the groups
     present before and after, for the year in which the act takes effect. Verified:
     V2300032595 (order 192 of 26.05.2023, in force 01.06.2023) raised group 1 from 5.90 to 7.32
     KZT/kWh for 2023 -- a mean +16.34% over 47 groups (27 changed); order 42-н/қ in force
     01.02.2025: +26.33% (36 of 59 groups). 20 acts 2019-2026, 16 with a value. PITFALL: adilet shows a base order in its CURRENT redaction, so the
     original 2019 table of order 514 and the original 2026 table of order 508 are lost -- the
     first act of each chain gets NaN.
   * GAS_WHOLESALE_CAP: «Об утверждении предельных цен оптовой реализации товарного газа на
     внутреннем рынке» -- yearly orders 2014-2022 (one July-June period each; 2015 H1 is
     January-June) and order № 210 of 06.06.2023 (V2300032715) with periods 2023/24 … 2027/28,
     prices by region in KZT per 1000 m3 without VAT. value = % change of the region's cap
     against the previous period; periods that start after today are kept as
     transformation «forecast» (approved schedule). PITFALL: the consolidated text of the 2018
     order is its redaction of 10.12.2018 (in force 01.01.2019), so the July-2018 prices are not
     visible; the event is dated 2019-01 and says so. 202 region-period events 2015-2027 (184
     with a value; 17 «forecast» for 2027-07). Verified: Almaty city 29 873 -> 39 044 KZT from
     01.07.2025 (+30.7%), Aktobe region 8 478 -> 11 445 from 01.07.2024 (+35.0%).

Record layout (config/dims.yaml TARIFF_DECISIONS):
    date       first day of the effective month
    region     dictionaries/regions.csv code, or "national"
    item_code  <REGION>.<SERVICE>.<KIND>.<SOURCE ID>, e.g. ZHM.HEAT.AMEND.D1072256
               (REGION = KZ for national; SOURCE ID: D<gov.kz document id>, N<news id>_<clause>,
               or the adilet document id V…/G…, with _YYYYMM for a gas-cap period) -- one per
               decision and service, so the
               (date, region, item_code) key is unique
    item_name  «service | decision | company | order | effective date and its basis | change | URL»
    value      % change of the tariff when stated or computable, else NaN

The three sources overlap (a news item often reports an order that is also in the documents);
records are not merged across sources -- aggregate by (date, region, service) when counting.
"""
from __future__ import annotations

import gzip
import html
import io
import json
import math
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf_dims  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

SOURCE = "krem"
GOV_KZ = "https://www.gov.kz"
DOCS_URL = GOV_KZ + "/api/v1/public/content-manager/documents"
NEWS_URL = GOV_KZ + "/api/v1/public/content-manager/news"
TICKET_URL = GOV_KZ + "/api/v1/public/_/c/k6"
DOC_PAGE = GOV_KZ + "/memleket/entities/krem/documents/details/{id}?lang=ru"
NEWS_PAGE = GOV_KZ + "/memleket/entities/krem/press/news/details/{id}?lang=ru"
ADILET = "https://old.adilet.zan.kz/rus/docs/"
PROJECT = "krem"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)",
           "Accept-Language": "ru"}
PAGE_SIZE = 100
LOOKBACK_DAYS = 120          # an incremental run re-reads documents published in the last 120 days
ENV_FULL = "KREM_TARIFFS_FULL"   # =1 forces a full re-read of the 33k-entry document listing
# sanity floors (2026-09-27: 33 602 documents, 1 036 news, 13 electricity-cap changes with a value, 202 gas events)
MIN_FULL_DOCS, MIN_NEWS, MIN_ELEC, MIN_GAS = 20000, 500, 10, 100

# Minenergo acts. Seeds are verified ids; the /links pages of the base orders add later amendments.
ELEC_BASE_ORDERS = ("V1800017956", "G25JVM00508")
ELEC_SEED = ("V1900019404", "V2000020905", "V2000020967", "V2100022433", "V2100023204", "V2100024974",
             "V2200026644", "V2200028658", "V2300032595", "G23JVM00384", "G23JVM00479", "G24JVM00304",
             "G24JVM00378", "G25JVM00042", "G25JVM00295", "G25JVM00368", "G25JVM00458", "G26JVM00336")
GAS_SEED = ("V1400010051", "V1500011068", "V1600013752", "V1700015295", "V1800017017", "V1900018684",
            "V2000020677", "V2100022968", "V2200028050", "V2300032715")
GAS_SEARCH = "предельных цен оптовой реализации товарного газа"
GAS_TITLE = re.compile(r"^Об утверждении предельных цен оптовой реализации товарного газа на внутреннем рынке"
                       r"(?: Республики Казахстан)?$")

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
          "октября", "ноября", "декабря"]
_MON = "|".join(MONTHS)
DATE_RE = rf"(\d{{1,2}})(?:\s*|-?го\s+)({_MON})\s*(\d{{4}})|(\d{{1,2}})\.(\d{{1,2}})\.(\d{{4}}|\d{{2}})(?!\d)"
REGION_SWITCH = date(2022, 6, 8)      # Абай, Жетісу and Ұлытау split off (Указ of 16.03.2022, in force 08.06.2022)

# ---------------------------------------------------------------------------------- regions
# (code, pattern) on lower-cased text; «алматы» (the city) and «алматинск» (the oblast) are
# different stems. Cities that changed oblast in 2022 are resolved by date in region_of().
REGION_PATTERNS = [
    ("ALA", r"\bалматы\b"), ("ALM", r"алматинск"), ("AST", r"\bастан[аеыу]?\b|нур-?\s?султан"),
    ("SHM", r"шымкент"), ("AKM", r"акмолинск|кокшетау|степногорск"), ("AKT", r"актюбинск|\bактобе"),
    ("ATY", r"атырау"), ("ZKO", r"западно-?\s?казахстанск|\bзко\b|\bуральск"),
    ("ZHM", r"жамбылск|\bтараз"), ("ZHT", r"жет[іиы]су"), ("KRG", r"карагандинск|\bкараганд|темиртау|балхаш"),
    ("KST", r"костанайск|\bкостана|рудн(?:ый|енск|ого)|лисаковск|аркалык"),
    ("KZL", r"кызылорд"), ("MNG", r"мангистау|мангыстау|\bактау\b|жанаозен"),
    ("PVL", r"павлодар|экибастуз"), ("SKO", r"северо-?\s?казахстанск|\bско\b|петропавловск"),
    ("TRK", r"туркестан"), ("ULT", r"[ұу]лытау"), ("VKO", r"восточно-?\s?казахстанск|\bвко\b|усть-?каменогорск|риддер"),
    ("ABY", r"област\w*\s+абай|абайск\w*\s+област|\bабай\s+облыс"), ("YKO", r"южно-?\s?казахстанск|\bюко\b"),
]
_REGION_RES = [(c, re.compile(p)) for c, p in REGION_PATTERNS]
# cities whose oblast changed on REGION_SWITCH: (before, after)
CITY_ERA = [(re.compile(r"\bсеме[йя]"), ("VKO", "ABY")), (re.compile(r"жезказган|сатпаев"), ("KRG", "ULT")),
            (re.compile(r"талдыкорган"), ("ALM", "ZHT"))]


def regions_in(text: str, when: date | None = None) -> set[str]:
    s = (text or "").lower().replace("ё", "е")
    found = {c for c, rx in _REGION_RES if rx.search(s)}
    for rx, (before, after) in CITY_ERA:
        if rx.search(s):
            found.add(after if (when is None or when >= REGION_SWITCH) else before)
    if "ALA" in found and "ALM" in found and re.search(r"алматинск\w* област", s) and not re.search(r"(?:г\.|город\w*)\s*алматы", s):
        found.discard("ALA")      # «Алматинская область ... (Алматы)»-style mentions
    return found


def region_of(text: str, when: date | None = None) -> str | None:
    """The single region a text names, else None (none or several)."""
    found = regions_in(text, when)
    return found.pop() if len(found) == 1 else None


# ---------------------------------------------------------------------------------- services
# (code, Russian name, pattern on lower-cased text). A title may name several services
# («водоснабжения и водоотведения») -> one record each.
SERVICES = [
    ("ELEC_TRANS", "передача и распределение электроэнергии",
     r"передач\w*\s+(?:и\s+(?:\(или\)\s+)?)?(?:распределени\w*\s+)?электрическ|распределени\w*\s+электрическ|электросетев"),
    ("ELEC_SUPPLY", "электроснабжение (розничная реализация электроэнергии)",
     r"реализаци\w*\s+электрическ|снабжени\w*\s+электрическ|электроснабж|энергоснабжающ|"
     r"(?:тариф|цен)\w*\s+на\s+(?:электроэнерги|электрическ\w*\s+энерги)|электроэнерги\w*\s+для"),
    ("HEAT", "теплоснабжение", r"теплов\w*\s+энерги|теплоснабж|отоплени|теплоэнерги"),
    ("HOT_WATER", "горячее водоснабжение", r"горяч\w*\s+вод"),
    ("WATER_BULK", "подача воды по магистральным трубопроводам и каналам",
     r"(?:подач\w*|транспортировк\w*)\s+(?:\w+\s+){0,2}вод\w*\s+по\s+(?:магистральн|канал)|орошени|поверхностн\w*\s+сток"),
    ("WATER", "водоснабжение",
     r"подач\w*\s+(?:питьев\w*\s+|пожарно-питьев\w*\s+)?вод\w*\s+по\s+(?:магистральн\w*\s+трубопровод\w*\s+и\s+)?распределительн|водоснабжени|питьев\w*\s+вод|холодн\w*\s+вод|услуг\w*\s+по\s+подаче\s+воды(?!\s+по\s+(?:магистр|канал))"),
    ("SEWER", "водоотведение", r"отвод\w*\s+сточн|сточн\w*\s+вод|водоотведени|канализац"),
    ("GAS_TRANS", "транспортировка газа по магистральным газопроводам", r"магистральн\w*\s+газопровод"),
    ("GAS_DISTR", "транспортировка газа по газораспределительным сетям",
     r"газораспределительн|транспортировк\w*\s+(?:товарного\s+)?газа\s+по\s+распределительн"),
    ("GAS_STORAGE", "хранение газа", r"хранени\w*\s+(?:товарного\s+)?газа"),
    ("GAS_RETAIL", "розничная реализация газа (газоснабжение)",
     r"розничн\w*\s+реализаци\w*\s+(?:товарного\s+|сжиженного\s+(?:нефтяного\s+)?)?газа|газоснабж|тариф\w*\s+на\s+газ\b|газ\w*\s+для\s+населени"),
]
_SERVICE_RES = [(c, n, re.compile(p)) for c, n, p in SERVICES]
SERVICE_NAMES = {c: n for c, n, _ in SERVICES} | {
    "ELEC_GEN_CAP": "предельный тариф на электроэнергию (энергопроизводящие организации)",
    "GAS_WHOLESALE_CAP": "предельная цена оптовой реализации товарного газа"}
# services a title can name that are outside this dataset (rail, ports, oil …): logged, not kept
OUT_OF_SCOPE = re.compile(r"подъездн|железнодорож|локомотив|магистральн\w*\s+железн|аэропорт|аэронавигац|морск\w*\s+порт|"
                          r"портов|нефт|телекоммуникац|почтов|перевозк|зерн")


def services_in(text: str) -> list[str]:
    s = (text or "").lower().replace("ё", "е")
    found = [c for c, _, rx in _SERVICE_RES if rx.search(s)]
    if "WATER_BULK" in found and "WATER" in found and not re.search(r"распределительн", s):
        found.remove("WATER")           # «подача воды по магистральным трубопроводам» alone
    if "HOT_WATER" in found and "WATER" in found and not re.search(r"холодн|питьев|распределительн", s):
        found.remove("WATER")
    return found


# ---------------------------------------------------------------------------------- dates

def parse_date(m: re.Match) -> date | None:
    """A match of DATE_RE -> date (None when impossible)."""
    try:
        if m.group(2):
            return date(int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1)))
        year = int(m.group(6))
        return date(year + 2000 if year < 100 else year, int(m.group(5)), int(m.group(4)))
    except (ValueError, TypeError):
        return None


def month_start(d: date) -> date:
    return d.replace(day=1)


def next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


# ---------------------------------------------------------------------------------- 1. documents
DOC_EXCLUDE = re.compile(
    r"^\W*(?:проект|протокол|публичн|объявлен|извещени\w*\s+о\s+проведени|уведомлени\w*\s+о\s+проведени|об\s+отказе|"
    r"об\s+отмене|отчет|информаци|перечень|сведени|реестр|график|план\b|пресс|заключени\w*\s+по\s+результат)"
    r"|отказ\w*\s+в\s+|перечень\s+закупаем|о\s+проведении\s+публичн|признании\s+утратившим", re.I)
DOC_DECISION = re.compile(
    r"утвержд\w*.{0,200}тариф|временн\w*\s+компенсирующ|внесени\w*\s+изменени.{0,400}тариф|об\s+изменении.{0,80}тариф|"
    r"предельн\w*\s+цен|снижени\w*\s+(?:проектируемой\s+|действующей\s+)?(?:\w+\s+)?цен", re.I)
KINDS = [  # (code, Russian label, pattern) -- first match wins
    ("TEMP_COMP", "временный компенсирующий тариф (снижение)", r"компенсирующ"),
    ("EMERGENCY", "чрезвычайная регулирующая мера", r"чрезвычайн\w*\s+регулирующ"),
    ("CAP_CUT", "снижение предельной цены (мотивированное заключение)", r"снижени\w*\s+(?:\w+\s+){0,3}цен"),
    ("AMEND", "изменение утвержденного тарифа", r"внесени\w*\s+изменени|об\s+изменении"),
    ("PRICE_CAP", "предельная цена (общественно значимый рынок)", r"предельн\w*\s+цен"),
    ("APPROVE", "утверждение тарифа", r"утвержд"),
]
_KIND_RES = [(c, n, re.compile(p, re.I)) for c, n, p in KINDS]
# Departments that publish an order within days of signing it (publication minus order date over
# the titles that carry both, 2017-2026: Карагандинская n=476, 90th percentile 5 days;
# г. Шымкент n=78, 90th percentile 11 days). Only for these is the publication date a usable
# stand-in for an order date the title does not give; elsewhere the lag runs to months
# (Акмолинская p75 70 days, Костанайская 106, Туркестанская 321).
PROMPT_PUBLISHERS = {"KRG": 5, "SHM": 11}
KIND_NAMES = {c: n for c, n, _ in KINDS} | {"ORDER": "приказ Министра энергетики", "NEWS": "сообщение КРЕМ/ДКРЕМ",
                                           "PERIOD": "новый период предельных цен"}
ORG_RE = re.compile(
    r"(ТОО|АО|ГКП|КГП|ГККП|РГП|ПК|МГП|ОАО|ЗАО|ИП|СПК|товариществ\w*\s+с\s+ограниченной\s+ответственностью|"
    r"акционерн\w*\s+обществ\w*|(?:государственн\w*\s+коммунальн|коммунальн\w*\s+государственн)\w*\s+предприяти\w*"
    r"(?:\s+на\s+праве\s+хозяйственного\s+ведения)?)\s*[«\"“„']+\s*([^»\"”“]{2,80}?)\s*[»\"”“]", re.I)
ORG_ABBR = [(r"^товариществ", "ТОО"), (r"^акционерн", "АО"), (r"^государственн", "ГКП"), (r"^коммунальн", "КГП")]


def company_of(text: str) -> str:
    m = ORG_RE.search(text or "")
    if not m:
        return ""
    form = m.group(1)
    for pat, abbr in ORG_ABBR:
        if re.match(pat, form, re.I):
            form = abbr
    return f"{form} «{m.group(2).strip()}»"


def _order_date(title: str) -> tuple[date | None, str]:
    """The date and number of THIS order: the first «от <дата>» not inside the quoted title of
    an amended order («О внесении изменений в приказ … от 18 ноября 2022 года №86-ОД …»)."""
    cut = re.search(r"в\s+приказ", title, re.I)
    own = title[:cut.start()] if cut else title
    for m in re.finditer(r"\bот\s*(?:" + DATE_RE + r")", own):
        d = parse_date(m)
        if d:
            num = re.search(r"№\s*(\d+(?:\s*-\s*[А-ЯЁҚӨ0]{1,3})?)", own)
            return d, (re.sub(r"\s+", "", num.group(1)) if num else "")
    return None, ""


def _effective_date(title: str, kind: str) -> date | None:
    """An effective date stated in the title («с вводом в действие с 1 июля 2025 года», «на период
    с 1 марта 2023 года», «… с 1 сентября 2025 года»). In an amendment only the text before «в
    приказ» counts -- the quoted title of the amended order carries its own, older, dates."""
    scope = title
    if kind == "AMEND":
        cut = re.search(r"в\s+приказ", title, re.I)
        scope = title[:cut.start()] if cut else title
    for pat in (r"(?:в\s+действие|вводом|введением)\s+(?:в\s+действие\s+)?(?:с|со)\s+(?:" + DATE_RE + ")",
                r"период\w*\s+с\s+(?:" + DATE_RE + ")",
                r"(?<!\bот)\s(?:с|С)\s+(?:" + DATE_RE + ")"):
        m = re.search(pat, scope)
        if m:
            sub = re.search(DATE_RE, m.group(0))
            d = parse_date(sub) if sub else None
            if d:
                return d
    return None


def parse_document(doc: dict) -> tuple[list[dict], str | None]:
    """One documents-listing entry -> records (one per service), or ([], reason it was skipped)."""
    title = re.sub(r"\s+", " ", html.unescape(doc.get("title") or "")).strip()
    tl = title.lower().replace("ё", "е")
    if not title or re.search(r"[әіңғүұқөһ]", tl) and not re.search(r"утвержд|тариф", tl):
        return [], "kazakh"
    if DOC_EXCLUDE.search(title) or not DOC_DECISION.search(title):
        return [], "not_a_decision"
    if not re.search(r"тариф(?!н)|цен[аыуе]?\b", tl):
        return [], "estimate_only"          # a change of the tariff estimate (смета) alone
    services = services_in(title)
    if not services:
        return [], "out_of_scope" if OUT_OF_SCOPE.search(tl) else "no_service"
    kind = next(c for c, _, rx in _KIND_RES if rx.search(title))
    published = (doc.get("created_date") or "")[:10]
    order_d, order_no = _order_date(title)
    eff = _effective_date(title, kind)
    if eff and order_d and not (order_d - timedelta(days=400) <= eff <= order_d + timedelta(days=400)):
        eff = None                          # a date of something else (the amended order's period)
    pub_d = date.fromisoformat(published) if published else None
    organs = " ".join(g.get("project_name") or "" for g in (doc.get("gosorgan") or {}).get("items", []))
    acts = " ".join(a.get("title") or "" for a in (doc.get("activities") or {}).get("items", []))
    ref = eff or order_d or pub_d
    region = None
    if re.search(r"департамент", organs, re.I):
        region = region_of(organs, ref)
    region = region or region_of(acts, ref)
    if region is None:
        in_title = regions_in(title, ref)
        if len(in_title) == 1:
            region = in_title.pop()
        elif not in_title and (re.search(r"^комитет|управлени", organs.strip(), re.I) or "Центральный аппарат" in acts):
            region = dims.NATIONAL      # the central committee: republican monopolies (KEGOC, QazaqGaz …)
    if eff:
        when, basis = month_start(eff), f"вступает в силу {eff.isoformat()} (указано)"
    elif order_d:
        when, basis = next_month(order_d), "дата вступления не указана: оценка -- месяц после приказа"
    elif pub_d and region in PROMPT_PUBLISHERS and "T00:00:00" not in (doc.get("created_date") or ""):
        # (a midnight timestamp marks the 2019-2021 migration of old documents: not a publication date)
        when, basis = next_month(pub_d), ("дата приказа не указана: оценка -- месяц после публикации "
                                          f"(ДКРЕМ публикует приказы в течение {PROMPT_PUBLISHERS[region]} дней)")
    else:
        return [], "no_date"
    if when.year < 2010:
        return [], "no_date"
    if region is None:
        return [], "no_region"
    company = company_of(title)
    down = kind in ("TEMP_COMP", "CAP_CUT") or re.search(r"со\s+снижением", tl)
    direction = "снижение, размер не указан" if down else "размер изменения не указан"
    order = f"приказ {('№' + order_no + ' ') if order_no else ''}от {order_d.isoformat()}" if order_d else "приказ (дата не указана)"
    url = DOC_PAGE.format(id=doc["id"])
    rc = "KZ" if region == dims.NATIONAL else region
    out = []
    for svc in services:
        out.append({"date": when.isoformat(), "region": region,
                    "item_code": f"{rc}.{svc}.{kind}.D{doc['id']}",
                    "item_name": " | ".join(x for x in (SERVICE_NAMES[svc], KIND_NAMES[kind], company, order,
                                                         basis, direction, f"опубл. {published}", url) if x),
                    "value": math.nan})
    return out, None


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers["Referer"] = GOV_KZ + "/memleket/entities/krem/press/news?lang=ru"
    return s


def _get_json(session: requests.Session, url: str, params: dict, ticket: bool = False):
    for attempt in range(4):
        try:
            if ticket:
                session.post(TICKET_URL, headers={"Content-Type": "application/json", "Origin": GOV_KZ}, timeout=40)
            r = session.get(url, params=params, timeout=90)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 403) and not ticket:
                raise validation.StructuralChangeError(
                    f"STRUCTURAL CHANGE DETECTED in krem_tariffs: {url} answered {r.status_code}: {r.text[:200]}")
        except requests.RequestException:
            pass
        time.sleep(3 * (attempt + 1))
    raise validation.StructuralChangeError(
        f"STRUCTURAL CHANGE DETECTED in krem_tariffs: {url} {params} failed four times\n"
        f"ACTION REQUIRED: check the gov.kz content-manager API (see scripts/fetchers/krem_tariffs.py)")


def list_documents(session: requests.Session, since: datetime | None = None) -> list[dict]:
    """Every document of project «krem», newest first (since: only those published later)."""
    out, page = [], 1
    params = {"projects": PROJECT, "size": PAGE_SIZE, "sort-by": "created_date:DESC"}
    if since:
        params["created_date"] = "gt:" + since.strftime("%Y-%m-%dT%H:%M:%S")
    while True:
        batch = _get_json(session, DOCS_URL, {**params, "page": page})
        if not isinstance(batch, list):
            raise validation.StructuralChangeError(f"krem_tariffs: documents listing is not a list: {str(batch)[:200]}")
        if not batch:
            return out
        out.extend(batch)
        page += 1


def list_news(session: requests.Session) -> list[dict]:
    out, page = [], 1
    while True:
        batch = _get_json(session, NEWS_URL, {"projects": "eq:" + PROJECT, "page": page, "size": PAGE_SIZE,
                                              "sort-by": "created_date:DESC"}, ticket=True)
        if not batch:
            return out
        out.extend(batch)
        page += 1


# ---------------------------------------------------------------------------------- 2. news
NEWS_VERB = re.compile(r"сниж|повыш|утвержд|введ|ввод|установлен|изменен|увелич|пересмотр|вырос|сократ|составит|составля", re.I)
NEWS_PLAN = re.compile(r"планир|ожида|предлага|намерен|заявк|проект|предстоящ|может\s+быть|возможн|прогноз|"
                       r"повысит\b|снизит\b|будет\s+продолжать|"
                       r"не\s+планиру|рассмотр|слушани|не\s+будет|остан\w*\s+(?:на\s+)?(?:прежнем|неизменн)", re.I)
DOWN = re.compile(r"сниж|уменьш|понижен|сократ|\bниже\b")
UP = re.compile(r"повыш|увелич|\bрост|вырос|подорож|\bвыше\b")
NUM = r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
PCT_RE = re.compile(rf"(?:тариф|цен|сниж|повыш|рост|увелич|уменьш|ниже|выше)[^%]{{0,60}}?(?<![\d,.])({NUM})\s*%", re.I)
FROM_TO_RE = re.compile(rf"\bс\s+({NUM})\s*(?:тенге|тг\.?)?(?:[^;%]{{0,40}}?)\s+до\s+({NUM})\s*(?:тенге|тг)")
NEWS_DATE_RE = re.compile(rf"\b(?:с|со)\s+(\d{{1,2}})(?:-?го)?\s+({_MON})(?:\s+(\d{{4}}))?|\b(?:с|со)\s+(\d{{1,2}})\.(\d{{2}})\.(\d{{4}})")
CONSUMERS = [("население", r"населени|физическ\w*\s+лиц|бытов"), ("юрлица", r"бизнес|юридическ|прочих\s+потребител|предприяти\w*\s+малого"),
             ("бюджет", r"бюджетн")]


def _num(s: str) -> float:
    return float(re.sub(r"[  ]", "", s).replace(",", "."))


def _text(body: str) -> str:
    body = re.sub(r"<(?:br|/p|/li|/div|/h\d)[^>]*>", "\n", body or "", flags=re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"[ \t ]+", " ", html.unescape(body))


def _news_date(sentence: str, published: date) -> date | None:
    m = NEWS_DATE_RE.search(sentence)
    if not m:
        return None
    try:
        if m.group(2):
            month, day = MONTHS.index(m.group(2)) + 1, int(m.group(1))
            year = int(m.group(3)) if m.group(3) else published.year
            if not m.group(3) and month - published.month > 6:
                year -= 1                   # «с 1 декабря» in a January release
            return date(year, month, day)
        return date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
    except ValueError:
        return None


def _sentences(text: str) -> list[str]:
    out = []
    for para in re.split(r"\n+", text):
        out.extend(x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[А-ЯA-Z«\"])", para) if x.strip())
    return out


def _clause_value(clause: str) -> tuple[float, str]:
    """(% change, how it was read) of one clause: the stated % signed by the old->new pair or,
    without one, by the verb; else the % computed from «с A до B тенге»; else NaN."""
    cl = clause.lower()
    ft = FROM_TO_RE.search(clause)
    pct = PCT_RE.search(clause)
    computed = None
    if ft:
        old, new = _num(ft.group(1)), _num(ft.group(2))
        if old > 0 and new > 0:
            computed = round((new / old - 1) * 100, 2)
    down, up = bool(DOWN.search(cl)), bool(UP.search(cl))
    sign = (1 if computed > 0 else -1) if computed else (-1 if down and not up else 1 if up and not down else 0)
    fromto = f"с {ft.group(1)} до {ft.group(2)} тенге" if computed is not None else ""
    if pct and sign:
        stated = _num(pct.group(1))
        if computed is not None and abs(abs(computed) - stated) > 1.5:
            return math.nan, f"неоднозначно: указано {pct.group(1)}%, {fromto} (расчёт {computed:+.2f}%)"
        if 0 < stated < 100:
            word = "снижение" if sign < 0 else "повышение"
            return sign * stated, f"{word} на {pct.group(1)}% (указано)" + (f"; {fromto}" if fromto else "")
    if computed is not None:
        return computed, f"{fromto} (расчёт)"
    return math.nan, "размер изменения не указан"


def parse_news(item: dict) -> tuple[list[dict], dict]:
    """One news item -> records, plus counts of the clauses it skipped by reason.

    A sentence counts when it names a service, a tariff or price, and a decision verb; its
    effective date is the «с <дата>» in the sentence itself or, failing that, in the sentence
    just before or after it («… с вводом в действие с 1 апреля 2026 года. Размер тарифа на
    услуги по подаче воды … снижен на 11,78% — с 198,90 тенге за м³ до 175,48 тенге»)."""
    skipped: dict[str, int] = {}
    published = date.fromisoformat(item["created_date"][:10])
    title = re.sub(r"\s+", " ", html.unescape(item.get("title") or ""))
    text = _text(item.get("body") or "")
    depts = {region_of(m.group(1), published) for m in re.finditer(
        r"(?:[Дд]епартамент\w*|ДКРЕМ)[^.]{0,160}?\bпо\s+((?:городу\s+|области\s+)?[^.,;()]{3,40})", title + ". " + text)} - {None}
    sentences = _sentences(text)
    dates = [_news_date(s, published) for s in sentences]
    out, seen = [], set()
    k = 0
    prev_eff: tuple[int, date] | None = None
    for i, s in enumerate(sentences):
        if not re.search(r"тариф|цен", s, re.I) or not services_in(s):
            continue
        eff = dates[i]
        if eff is None:
            near = [j for j in (i - 1, i + 1) if 0 <= j < len(sentences) and dates[j]
                    and re.search(r"действ|ввод|период|тариф", sentences[j], re.I) and not NEWS_PLAN.search(sentences[j])]
            eff = dates[near[0]] if near else None
        if eff is None and prev_eff and prev_eff[0] == i - 1:
            eff = prev_eff[1]           # a run of sentences about the same decision
        if eff is None:
            continue
        if not (published - timedelta(days=5 * 366) <= eff <= published + timedelta(days=400)):
            continue
        prev_eff = (i, eff)
        sent_region = region_of(s, eff)
        head_company = company_of(s)
        for clause in re.split(r";|\s[-–—]\s(?=на\s|по\s|для\s)|,\s+(?=(?:а\s+)?тариф\w*\s+на\s)|\s+а\s+также\s+", s):
            svcs = services_in(clause)
            if not svcs:
                continue
            cl = clause.lower()
            if OUT_OF_SCOPE.search(cl):
                skipped["out_of_scope"] = skipped.get("out_of_scope", 0) + 1
                continue
            if NEWS_PLAN.search(clause) or re.search(r"остал\w*|не\s+изменил|прежнем\s+уровне|без\s+изменени", cl):
                skipped["plan_or_unchanged"] = skipped.get("plan_or_unchanged", 0) + 1
                continue
            if not (NEWS_VERB.search(clause) or (NEWS_VERB.search(s) and len(svcs) == len(services_in(s)))):
                skipped["no_verb"] = skipped.get("no_verb", 0) + 1
                continue
            region = region_of(clause, eff) or sent_region or region_of(title, eff) or \
                (next(iter(depts)) if len(depts) == 1 else None)   # the one department the release names
            if region is None and not depts and not regions_in(title + " " + text, eff):
                region = dims.NATIONAL      # a release of the central committee about a republican monopoly
            if region is None:
                skipped["no_region"] = skipped.get("no_region", 0) + 1
                continue
            value, how = _clause_value(clause)
            consumer = next((n for n, p in CONSUMERS if re.search(p, cl)), "")
            company = company_of(clause) or head_company
            for svc in svcs:
                key = (region, svc, eff, None if math.isnan(value) else round(value, 1), company)
                if key in seen:
                    continue
                seen.add(key)
                k += 1
                rc = "KZ" if region == dims.NATIONAL else region
                out.append({"date": month_start(eff).isoformat(), "region": region,
                            "item_code": f"{rc}.{svc}.NEWS.N{item['id']}_{k}",
                            "item_name": " | ".join(x for x in (
                                SERVICE_NAMES[svc], KIND_NAMES["NEWS"], company, consumer,
                                f"вступает в силу {eff.isoformat()} (указано)", how, f"опубл. {published.isoformat()}",
                                NEWS_PAGE.format(id=item["id"])) if x),
                            "value": value, "_key": key})
    return out, skipped


def dedupe_news(records: list[dict]) -> list[dict]:
    """The same change is often repeated by later releases: keep the first report of each
    (region, service, effective date, value, company)."""
    out, seen = [], set()
    for r in sorted(records, key=lambda r: int(re.search(r"N(\d+)_", r["item_code"]).group(1))):
        key = r.pop("_key", None)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# ---------------------------------------------------------------------------------- 3. adilet
def adilet_text(session: requests.Session, doc_id: str) -> str:
    """The act's text as one normalised line (from «Печать» -- the end of the page chrome -- to
    the site footer)."""
    for attempt in range(3):
        try:
            r = session.get(ADILET + doc_id, timeout=60)
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(3)
    return clean_adilet_html(r.text)


def clean_adilet_html(page: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    head = t.find("Печать")
    end = t.find("Если Вы обнаружили на странице ошибку")
    body = t[head + len("Печать"):end if end > 0 else None] if head >= 0 else t
    top = t[:t.find("Текст Официальная публикация")] if "Текст Официальная публикация" in t else t[:4000]
    heading = re.search(r"(?:Совместный приказ|Приказ|Постановление)(?: и\.о\.)?[^.]{0,160}?от \d{1,2} [а-я]+ \d{4} года "
                        r"№ [^\s.]+(?:\.\s*Зарегистрирован[^.]{0,120}?№ \d+)?", top)
    name = html.unescape(re.sub(r"\s+", " ", title.group(1))).split(" - ИПС")[0].strip() if title else ""
    return f"TITLE: {name} HEADING: {heading.group(0) if heading else ''} BODY: {body.strip()}"


def adilet_links(session: requests.Session, doc_id: str) -> list[tuple[str, str]]:
    r = session.get(ADILET + doc_id + "/links", timeout=60)
    r.raise_for_status()
    out = []
    for m in re.finditer(r'href="/rus/docs/([VG][^"#/?]+)"[^>]*>(.*?)</a>', r.text, re.S):
        name = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        if (m.group(1), name) not in out:
            out.append((m.group(1), name))
    return out


def _act_header(text: str) -> tuple[date | None, str]:
    head = text.split("HEADING:", 1)[-1].split("BODY:", 1)[0]
    m = re.search(r"от (\d{1,2}) (" + _MON + r") (\d{4}) года № ([^\s.]+)", head)
    if not m:
        return None, ""
    return date(int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1))), m.group(4)


def _act_registered(text: str) -> date | None:
    head = text.split("HEADING:", 1)[-1].split("BODY:", 1)[0]
    m = re.search(r"Зарегистрирован[^.]{0,60}?(\d{1,2}) (" + _MON + r") (\d{4}) года", head)
    return date(int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1))) if m else None


def _act_effective(text: str) -> tuple[date | None, str]:
    """(date, basis) of «вводится в действие с <дата>»; «со дня/после дня первого официального
    опубликования» -> the order date's month, flagged."""
    body = text.split("BODY:", 1)[-1]
    m = re.search(r"[Вв]водится в действие (?:с|со) (?:" + DATE_RE + r")", body)
    if m:
        d = parse_date(re.search(DATE_RE, m.group(0)))
        if d:
            return d, "указано"
    if re.search(r"[Вв]водится в действие (?:со дня|после дня|по истечении)", body):
        return None, "со дня официального опубликования"
    return None, ""


def parse_elec_caps_table(text: str, years: list[int] | None = None) -> tuple[list[int], dict[int, dict[int, float]], bool]:
    """(years, {group: {year: KZT/kWh}}, partial) of a price-cap act. Rows read «1 1-группа 5,76
    5,80 …» or «1-группа 5,76 …» (both layouts occur); the years are the «2019 год 2020 год …»
    header in front of the first row. `partial` when the act restates or adds single rows
    («строку, порядковый номер 47, изложить …», «дополнить строками …») instead of the whole
    table; a row without its own header takes `years` (the table it amends)."""
    body = text.split("BODY:", 1)[-1]
    partial = bool(re.search(r"дополнить\s+строк|строк[уи],?\s+порядков", body)) and \
        not re.search(r"изложить в новой редакции согласно приложению", body)
    first = re.search(r"\d+-групп[аы]\s", body)
    if first:
        head = re.findall(r"((?:\d{4}\s+год\s*){2,})", body[:first.start()])
        if head:
            years = [int(y) for y in re.findall(r"(\d{4})\s+год", head[-1])]
    if not years or not first:
        return years or [], {}, partial
    n = len(years)
    tok = r"(?:\d+(?:,\d+)?|-)"
    rows: dict[int, dict[int, float]] = {}
    for m in re.finditer(rf"(?:\d+\s+)?(\d+)-групп[аы]\s+((?:{tok}\s+){{{n - 1}}}{tok})(?![\d,])", body):
        rows[int(m.group(1))] = {y: float(v.replace(",", ".")) for y, v in zip(years, m.group(2).split()) if v != "-"}
    return years, rows, partial


def elec_cap_events(acts: list[dict]) -> list[dict]:
    """Chain the acts (dicts: id, text, base) by effective date; each act's event value is the
    mean % change of the caps for its effective year over the groups present before and after."""
    parsed = []
    for a in acts:
        order_d, order_no = _act_header(a["text"])
        eff, basis = _act_effective(a["text"])
        if eff is None:
            reg = _act_registered(a["text"])
            eff = reg or order_d
            if eff is None:
                continue
            basis = f"{basis or 'дата вступления не указана'}: оценка -- " + ("дата регистрации в Минюсте" if reg else "дата приказа")
        parsed.append({**a, "order_d": order_d, "order_no": order_no, "eff": eff, "basis": basis})
    parsed.sort(key=lambda a: (a["eff"], a["order_d"] or a["eff"]))
    out, current, years = [], None, None
    for a in parsed:
        yrs, rows, partial = parse_elec_caps_table(a["text"], years)
        consolidated = a.get("base") and re.search(r"Сноска\. Предельные тарифы\s*[–-]\s*в редакции", a["text"])
        value, note = math.nan, ""
        if consolidated or not rows:
            # a base order read in its current redaction: its original table is not visible
            new = None
            note = "исходная таблица не видна (adilet показывает текущую редакцию)" if consolidated else "таблица не распознана"
        elif partial and current is not None:
            new = {g: dict(v) for g, v in current.items()}
            for g, v in rows.items():
                new.setdefault(g, {}).update(v)
        else:
            new = rows
            years = yrs or years
        if new is not None and current is not None:
            y = a["eff"].year
            changes = []
            for g in sorted(set(new) & set(current)):
                nv = new[g].get(y)
                prior = [yy for yy in current[g] if yy <= y]
                ov = current[g][max(prior)] if prior else None
                if nv is not None and ov:
                    changes.append((nv / ov - 1) * 100)
            if changes:
                value = round(sum(changes) / len(changes), 2)
                moved = sum(1 for c in changes if abs(c) > 1e-9)
                note = f"среднее по {len(changes)} группам, изменились {moved}"
        elif new is not None and current is None and not note:
            note = "первый акт цепочки: предыдущие тарифы не видны"
        if new is not None:
            current = new
        elif consolidated:
            current = None
        out.append({"date": month_start(a["eff"]).isoformat(), "region": dims.NATIONAL,
                    "item_code": f"KZ.ELEC_GEN_CAP.ORDER.{a['id']}",
                    "item_name": " | ".join(x for x in (
                        SERVICE_NAMES["ELEC_GEN_CAP"], KIND_NAMES["ORDER"],
                        f"приказ № {a['order_no']} от {a['order_d'].isoformat()}" if a["order_d"] else "",
                        f"вступает в силу {a['eff'].isoformat()} ({a['basis']})", note, ADILET + a["id"]) if x),
                    "value": value})
    return out


GAS_PERIOD = re.compile(rf"на период с (\d{{1,2}}) ({_MON})(?: (\d{{4}}))?(?: года)? по (\d{{1,2}}) ({_MON}) (\d{{4}})")
GAS_ROW = re.compile(r"(\d{1,2})\.?\s+((?:[Гг]ород|г\.)\s+[А-ЯЁ][\w\-]+|[А-ЯЁ][а-яё]+(?:-[А-ЯЁа-яё]+)?\s+область|"
                     r"[Оо]бласть\s+[А-ЯЁӘІҢҒҮҰҚӨҺ][\w]+)\s+((?:\d{1,3}(?: \d{3})*\s+\([^)]*\)\s*)+)")


def parse_gas_caps(text: str) -> tuple[list[date], dict[str, list[float]], str]:
    """(period starts, {region: [KZT per 1000 m3 per period]}, restatement note) of a
    wholesale gas price-cap order, from its appendix 1 (appendix 2, for industrial
    consumer-investors, is cut off)."""
    body = text.split("BODY:", 1)[-1]
    start = max(body.find("Предельные цены оптовой реализации товарного газа на внутреннем рынке", 200), 0)
    app = body[start:]
    for stop in ("Приложение 2", "Предельные цены оптовой реализации товарного газа для промышленных"):
        cut = app.find(stop, 50)
        if cut > 0:
            app = app[:cut]
    periods = []
    for m in GAS_PERIOD.finditer(app):
        end_year = int(m.group(6))
        start_year = int(m.group(3)) if m.group(3) else end_year
        d = date(start_year, MONTHS.index(m.group(2)) + 1, int(m.group(1)))
        if d not in periods:
            periods.append(d)
    if not periods:                        # the period is only in the order's body
        for m in GAS_PERIOD.finditer(body):
            d = date(int(m.group(3)) if m.group(3) else int(m.group(6)), MONTHS.index(m.group(2)) + 1, int(m.group(1)))
            periods = [d]
            break
    note = ""
    foot = re.search(r"Сноска\.[^.]*в редакции приказа[^()]*\(вводится в действие ([^)]*)\)", app)
    if foot:
        note = "таблица в редакции " + re.sub(r"\s+", " ", foot.group(0)[8:])[:160]
    prices: dict[str, list[float]] = {}
    for m in GAS_ROW.finditer(app):
        vals = [_num(v) for v in re.findall(r"(\d{1,3}(?: \d{3})*)\s+\(", m.group(3))]
        name = m.group(2)
        code = region_of(name, periods[0] if periods else None) or \
            (region_of(name.replace("область", "области"), periods[0] if periods else None))
        if code and vals:
            prices[code] = vals
    return periods, prices, note


def gas_cap_events(acts: list[dict], today: date) -> list[dict]:
    """Per region: the cap of every period start from every order, the later order winning a
    shared period; value = % change against the region's previous period."""
    timeline: dict[str, dict[date, tuple]] = {}
    for a in acts:
        order_d, order_no = _act_header(a["text"])
        periods, prices, note = parse_gas_caps(a["text"])
        restated = re.search(r"вводится в действие с (\d{2})\.(\d{2})\.(\d{4})", note)
        for region, vals in prices.items():
            for i, p in enumerate(periods[:len(vals)]):
                start, how = p, ""
                if restated and len(periods) == 1:
                    rd = date(int(restated.group(3)), int(restated.group(2)), int(restated.group(1)))
                    if rd > p:
                        start, how = rd, f"цены периода с {p.isoformat()} пересмотрены с {rd.isoformat()}; исходные не видны"
                prev = timeline.setdefault(region, {}).get(start)
                if prev is None or (order_d or date.min) >= (prev[2] or date.min):
                    timeline[region][start] = (vals[i], a["id"], order_d, order_no, note, how)
    out = []
    for region, series in timeline.items():
        last = None
        for start in sorted(series):
            price, act, order_d, order_no, note, how = series[start]
            value = round((price / last - 1) * 100, 2) if last else math.nan
            last = price
            rc = "KZ" if region == dims.NATIONAL else region
            out.append({"date": month_start(start).isoformat(), "region": region,
                        "item_code": f"{rc}.GAS_WHOLESALE_CAP.PERIOD.{act}_{start:%Y%m}",
                        "item_name": " | ".join(x for x in (
                            SERVICE_NAMES["GAS_WHOLESALE_CAP"], KIND_NAMES["PERIOD"],
                            f"приказ № {order_no} от {order_d.isoformat()}" if order_d else "",
                            f"вступает в силу {start.isoformat()} (период цен)", f"{price:,.0f} тенге/1000 м3 без НДС".replace(",", " "),
                            how, note, ADILET + act) if x),
                        "value": value,
                        **({"transformation": "forecast"} if start > today else {})})
    return out


def _gas_acts(session: requests.Session) -> list[str]:
    ids = list(GAS_SEED)
    try:
        r = session.get("https://old.adilet.zan.kz/rus/search/docs/fulltext=" + requests.utils.quote(GAS_SEARCH), timeout=60)
        for m in re.finditer(r'href="/rus/docs/([VG][^"#/?]+)"[^>]*>(.*?)</a>', r.text, re.S):
            name = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
            if GAS_TITLE.match(name) and m.group(1) not in ids:
                ids.append(m.group(1))
    except requests.RequestException:
        pass
    return ids


def _elec_acts(session: requests.Session) -> list[tuple[str, bool]]:
    ids = [(i, True) for i in ELEC_BASE_ORDERS] + [(i, False) for i in ELEC_SEED]
    known = {i for i, _ in ids}
    for base in ELEC_BASE_ORDERS:
        try:
            for doc_id, name in adilet_links(session, base):
                if doc_id not in known and re.search(r"№ (?:514|508-н/қ) .{0,5}Об утверждении предельных тарифов на электрическую", name):
                    ids.append((doc_id, False))
                    known.add(doc_id)
        except requests.RequestException:
            pass
    return ids


# ---------------------------------------------------------------------------------- fetch

DOC_CODE = re.compile(r"\.D(\d+)$")      # item codes of records read from the documents listing


def _stored() -> list[dict]:
    out = []
    for r in dims.load_processed("TARIFF_DECISIONS"):
        v = r.get("value")
        out.append({"date": r["date"], "region": r["region"], "item_code": r["item_code"], "item_name": r["item_name"],
                    "value": float(v) if v not in (None, "") else math.nan,
                    **({"transformation": r["transformation"]} if r.get("transformation") not in (None, "", "level") else {})})
    return out


def _save_json(name: str, obj, today: date) -> Path:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return raw_store.save_raw_bytes(SOURCE, name, today, "json.gz", buf.getvalue())


def build_document_records(docs: list[dict]) -> tuple[list[dict], dict[str, int]]:
    records, skipped = [], {}
    for d in docs:
        if "id" not in d:
            continue
        recs, reason = parse_document(d)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
        records.extend(recs)
    return records, skipped


def fetch(ds: dict) -> tuple[list[dict], dict]:
    today = date.today()
    stored = _stored()
    days = ds.get("refresh_days", 0)
    last = imf_dims.last_download(SOURCE, ds["id"])
    if days and stored and last and (today - last).days < days and os.environ.get(ENV_FULL) != "1":
        return stored, {"frequency": ds["frequency"], "note": ds.get("note", ""),
                        "warnings": [f"not re-downloaded: last download {last.isoformat()}, refreshed every {days} days"]}
    session = _session()
    full = os.environ.get(ENV_FULL) == "1" or ds.get("full_refresh") or not any(DOC_CODE.search(r["item_code"]) for r in stored)
    since = None if full else datetime.combine(today - timedelta(days=LOOKBACK_DAYS), datetime.min.time())
    docs = list_documents(session, since)
    if full and len(docs) < MIN_FULL_DOCS:
        raise validation.StructuralChangeError(
            f"STRUCTURAL CHANGE DETECTED in krem_tariffs: the full «krem» document listing has {len(docs)} entries "
            f"(33 602 on 2026-09-27)\nACTION REQUIRED: check {DOCS_URL}?projects={PROJECT}")
    doc_records, doc_skipped = build_document_records(docs)
    # raw: what the parser reads (title, dates, department, tags) of the entries that mention a
    # tariff or price -- 1.0 MB gzipped for the full listing, ~35 KB for a 120-day window
    _save_json("tariff_documents" + ("" if full else "_recent"), [
        {"id": d["id"], "title": d.get("title"), "created_date": d.get("created_date"),
         "gosorgan": [g.get("project_name") for g in (d.get("gosorgan") or {}).get("items", [])],
         "activities": [x.get("title") for x in (d.get("activities") or {}).get("items", [])],
         "files": [f.get("document") for f in d.get("full_text") or [] if f.get("document")]}
        for d in docs if "id" in d and re.search(r"тариф|цен", d.get("title") or "", re.I)], today)

    news = list_news(session)
    if len(news) < MIN_NEWS:
        raise validation.StructuralChangeError(
            f"STRUCTURAL CHANGE DETECTED in krem_tariffs: the «krem» news listing has {len(news)} items (1 036 on 2026-09-27)")
    recent = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    _save_json("tariff_news" + ("" if full else "_recent"),     # all on a full run, else the last 120 days
               [{k: n.get(k) for k in ("id", "title", "created_date", "body")} for n in news
                if full or (n.get("created_date") or "") >= recent], today)
    news_records, news_skipped = [], {}
    for n in news:
        recs, sk = parse_news(n)
        news_records.extend(recs)
        for k, v in sk.items():
            news_skipped[k] = news_skipped.get(k, 0) + v
    news_records = dedupe_news(news_records)

    adilet = requests.Session()
    adilet.headers.update(HEADERS)
    elec_acts = [{"id": i, "base": base, "text": adilet_text(adilet, i)} for i, base in _elec_acts(adilet)]
    gas_acts = []
    for i in _gas_acts(adilet):
        text = adilet_text(adilet, i)
        if "товарного газа" in text[:400]:
            gas_acts.append({"id": i, "text": text})
    _save_json("tariff_adilet_acts", {a["id"]: a["text"] for a in elec_acts + gas_acts}, today)
    elec_records = elec_cap_events(elec_acts)
    gas_records = gas_cap_events(gas_acts, today)
    if len([r for r in elec_records if not math.isnan(r["value"])]) < MIN_ELEC or len(gas_records) < MIN_GAS:
        raise validation.StructuralChangeError(
            f"STRUCTURAL CHANGE DETECTED in krem_tariffs: adilet price-cap acts parsed into {len(elec_records)} electricity "
            f"and {len(gas_records)} gas events (expected 19+ / 150+)\nACTION REQUIRED: inspect {ADILET}V2300032595 and V2300032715")

    if full:
        kept_docs = doc_records
    else:        # earlier documents are final; the recent window is re-read and replaces its records
        window = {str(d["id"]) for d in docs if "id" in d} | {DOC_CODE.search(r["item_code"]).group(1) for r in doc_records}
        kept_docs = doc_records + [r for r in stored if (m := DOC_CODE.search(r["item_code"])) and m.group(1) not in window]
    records = kept_docs + news_records + elec_records + gas_records
    records.sort(key=lambda r: (r["date"], r["region"], r["item_code"]))
    raw_store.write_download_manifest(SOURCE, ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{DOCS_URL}?projects={PROJECT}",
        "documents_read": len(docs), "full_listing": bool(full), "document_records": len(doc_records),
        "documents_skipped": doc_skipped, "news_read": len(news), "news_records": len(news_records),
        "news_clauses_skipped": news_skipped, "adilet_acts": [a["id"] for a in elec_acts + gas_acts]})
    by_src = {"documents": len(kept_docs), "news": len(news_records), "electricity caps": len(elec_records),
              "gas caps": len(gas_records)}
    return records, {
        "frequency": ds["frequency"], "source_url": f"{DOCS_URL}?projects={PROJECT}",
        "dataset_id": "gov.kz krem documents + news; adilet Minenergo price-cap orders",
        "note": ds.get("note", ""),
        "warnings": [f"records by source: {by_src}",
                     f"documents skipped by reason: {dict(sorted(doc_skipped.items()))}",
                     f"news clauses skipped by reason: {dict(sorted(news_skipped.items()))}"]}
