"""NBK monetary surveys from the "records" JSON behind the monetary-statistics pages (added
2026-09-27 for the quasi-fiscal block: history before 2023, where open-data form 50 stops).

Source. Each NBK statistics page «Монетарный обзор …» draws its table from
    https://nationalbank.kz/ru/<page>/records?beginMount=1&beginYear=1990&endMount=12&endYear=YYYY
which returns a JSON list with one dict per period: short field keys (n_d_a_r_non_banking,
r_f_s_n_f_o, …), values in million KZT, plus reporting_date, published_at and note_ru/kz/en.
The same page's HTML carries the Russian label of every key in its JS `trans` dictionary
("n_d_a_r_non_banking": "Требования к небанковским финансовым организациям"); labels are read
from there, with FALLBACK_NAMES used when the page cannot be read or a label is still an
untranslated "monetaryreview::…" placeholder. Five surveys, one dataset each:
    CB   monetaryreview                 NBK survey (Монетарный обзор НБК)         monthly, 1997-12 on
    ODC  monetaryreviewbank             banks' survey (Монетарный обзор по банкам) monthly, 1998-01 on
    BS   monetaryreviewbankingsystem    banking-system survey                      monthly, 1997-12 on
    OFC  otherfinancialinstitutions     other financial organisations' survey      quarterly, 2015-Q1 on
    FS   overviewfinancialsector        financial-sector survey                    quarterly, 2015-Q1 on
item_code = SURVEY.key (the Cyrillic «с» in the NBK key r_m_с_a_s_n_s_o is written as Latin c).
The endpoint returns the latest revised history, not vintages.

Dating. The YEAR-MONTH of reporting_date is the month whose END the stock refers to; the day is
noise (records dated 03, 07, 14 … 31 of the month), and before about 2021 published_at is often
EARLIER than reporting_date, so neither the day nor published_at is a date of anything. Evidence:
  - the NBK-survey record '2023-01-31' equals open-data form 50 at report_date 2023-02-01 (line
    2.4 = 5 089 785), and on all 44 common dates 2023-01..2026-08 lines 1, 2.1, 2.3-2.6, 3, 3.1,
    3.1.1 equal the records of the month before within 0.9 mln (rounding);
  - the banks' claims on non-state nonfinancial organisations jump in the '2014-02' record
    (8.77 -> 9.47 trn; tenge devalued on 11 Feb 2014) and in '2015-08' (7.42 -> 8.12 trn; float
    from 20 Aug 2015) -- the stock at the end of that month, not at its start;
  - the OFC record '2026-06' equals form 26 (OFC_NET_FOREIGN_ASSETS) at 2026-07-01, 8 720 303.
So every record is dated the FIRST DAY OF THE NEXT MONTH (stock "as at"), like form 50 and the
money aggregates (nbk.money_as_at); quarterly surveys likewise land on 04-01, 07-01, 10-01, 01-01.

Verified numbers (mln KZT, month-end, from the records of 2026-09-27):
  CB.n_d_a_r_non_banking (NBK claims on non-bank financial organisations -- KSF, Problem Loans
    Fund, mostly equity): 2011-12 146 208 (IMF MFS_CBS S121_A_ACO_S12R_CBS 146 208.2), 2017-12
    1 230 126, 2019-12 3 044 011, 2021-12 5 317 553, 2026-08 5 137 668.
  CB.n_d_a_r_rest_economy: 2015-05 59 711 -> 2015-06 821 820 (read as a ~750 bn NBK equity claim on public
    nonfinancial corporations; the corporation is not named), 2021-12 848 440.
  ODC.r_f_s_n_f_o (banks' claims on public nonfinancial organisations): 2011-12 897 205, 2015-12
    318 120, 2021-12 605 536, 2024-12 690 279 (IMF ODCORP_A_ACO_S11001_ODCS 690 279.1).
  ODC.l_o (loans RECEIVED by banks, incl. from the NBK): 2011-12 728 538 (= IMF ODC loans 297 603
    + liabilities to the central bank 430 937), 2021-12 2 152 007.
  OFC.r_o_s_r_s_nf_o (OFC claims on public nonfinancial organisations): 2015-Q1 438 758, 2021-Q4
    966 553, 2026-Q2 1 968 351 (= IMF MFS_OFC S12R_A_ACO_S11001_OFCS).

Checks, enforced (StructuralChangeError):
  - every field of a record is a known key of its survey and every period appears once (after
    KNOWN_MISDATED, below);
  - the component sums in IDENTITIES, within rounding (0.5 mln per part), on every date except the
    source errors listed with each identity;
  - cross-survey (monthly surveys, from 2002-11-01): BS claims on NBFIs = CB + ODC claims on NBFIs,
    and BS claims on the rest of the economy = CB «остальная экономика» + ODC claims on local
    government, public and non-state nonfinancial organisations, NPISH and households. Both fail
    only 2001-12..2002-09, when ~2 977 mln sat in NBFIs in the NBK survey and in the rest of the
    economy in the banking-system survey (their sum agrees), so they are checked from 2002-10;
  - CB lines equal form 50 (data/processed/dims/nbk_monetary_survey.csv, FORM50_LINES) and OFC
    lines equal form 26 scalars (data/processed/nbk/ofc_*.csv, FORM26_SCALARS) on common dates,
    within 1 mln, when those files exist.

Pitfalls:
  - The banks' survey has no record for 2003-04 and two for 2005-04; the one with reporting_date
    2005-04-14 holds 2003 values (domestic assets 836 719 against 816 245 in 2003-03 and 882 504 in
    2003-05, and it closes the BS = CB + ODC identity for 2003-04 exactly) -- KNOWN_MISDATED
    moves it to 2003-04.
  - CB net domestic assets (n_d_a) and BS domestic assets (i_a) equal the sum of their published
    lines only through the end of January 2009; from 2009-02 an unpublished line opens (600 006 in
    2009-02, 6.7 trn in 2026-08), the same gap as form 50 line 2 against 2.1..2.6.
  - "NBFI" is not "development institution": it also holds UAPF, insurers, KASE (a central
    counterparty from ~2019, so repo inflates banks' claims on / loans from NBFIs) and BTA Bank
    after it lost its banking licence (ODC.r_f_n_b_f_i 3.3 trn at 2015-12).
  - CB claims on NBFIs are equity stakes, not loans (5.09 of 5.32 trn at 2021-12 in the Statistical
    Bulletin xlsx).
  - OFC coverage: DBK, mortgage companies, insurers and pension funds (NBK methodology
    /file/download/87908), so OFC claims mix DBK lending with UAPF and insurers' bond holdings.
    There is no OFC survey, from the NBK or the IMF, before 2015.
  - Items labelled «Минус: …» are positive numbers that the survey subtracts.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf_dims, nbk  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

SOURCE = "nbk"
BASE_URL = "https://nationalbank.kz/ru/"
REPO_ROOT = Path(__file__).resolve().parents[2]
FORM50_PATH = REPO_ROOT / "data" / "processed" / "dims" / "nbk_monetary_survey.csv"
FORM26_ROOT = REPO_ROOT / "data" / "processed" / "nbk"
META_FIELDS = {"note_kz", "note_ru", "note_en", "published_at", "reporting_date", "updated_at"}
LIABILITIES = "=Пассивы"  # a PARENTS value starting with "=" is a literal label, not a key
_LATIN = str.maketrans("асеорх", "aceopx")  # Cyrillic look-alikes in NBK keys


@dataclass(frozen=True)
class Identity:
    """total = Σ sign·part, e.g. Identity("n_i_r", "+n_i_r_scv -n_i_r_scv_minus"). `until` is the
    last as-at date on which it holds; `exempt` the as-at dates of known source errors."""
    total: str
    parts: str
    until: str | None = None
    exempt: tuple[str, ...] = ()
    name: str = ""

    def terms(self) -> list[tuple[int, str]]:
        return [(1 if t[0] == "+" else -1, t[1:]) for t in self.parts.split()]


@dataclass(frozen=True)
class Survey:
    code: str
    page: str
    frequency: str
    fields: tuple[str, ...]
    parents: dict = field(default_factory=dict)
    identities: tuple[Identity, ...] = ()

    @property
    def page_url(self) -> str:
        return BASE_URL + self.page

    @property
    def records_url(self) -> str:
        return BASE_URL + self.page + "/records"


# ---------------------------------------------------------------- survey definitions

CB = Survey(
    "CB", "monetaryreview/monetarnyy-obzor-nacionalnogo-banka-respubliki-kazahstan-", "monthly",
    ("n_e_a", "n_i_r", "n_i_r_scv", "n_i_r_scv_minus", "n_i_r_national_fund", "n_i_r_other_asset",
     "n_d_a", "n_d_a_central_goverment", "n_d_a_requirement", "n_d_a_minus_obligation",
     "n_d_a_fund_national_fund", "n_d_a_b_r_not_nbk", "n_d_a_r_non_banking", "n_d_a_r_rest_economy",
     "n_d_a_r_other_domestic", "l", "l_monetary_base_narrow", "r_m", "r_m_cash_outside_nbk",
     "r_m_bank_deposit", "r_m_t_d_n_b_f_i", "r_m_c_a_s_n_s_o", "o_d", "s_e_s", "c", "f_d"),
    {"n_i_r": "n_e_a", "n_i_r_scv": "n_i_r", "n_i_r_scv_minus": "n_i_r", "n_i_r_national_fund": "n_e_a",
     "n_i_r_other_asset": "n_e_a", "n_d_a_central_goverment": "n_d_a", "n_d_a_requirement": "n_d_a_central_goverment",
     "n_d_a_minus_obligation": "n_d_a_central_goverment", "n_d_a_fund_national_fund": "n_d_a",
     "n_d_a_b_r_not_nbk": "n_d_a", "n_d_a_r_non_banking": "n_d_a", "n_d_a_r_rest_economy": "n_d_a",
     "n_d_a_r_other_domestic": "n_d_a", "l_monetary_base_narrow": "l", "r_m": "l", "r_m_cash_outside_nbk": "r_m",
     "r_m_bank_deposit": "r_m", "r_m_t_d_n_b_f_i": "r_m", "r_m_c_a_s_n_s_o": "r_m", "o_d": "l", "s_e_s": "l",
     "c": "l", "f_d": "l"},
    (Identity("n_i_r", "+n_i_r_scv -n_i_r_scv_minus", exempt=("2004-08-01",)),  # 2004-07: -522
     Identity("n_e_a", "+n_i_r +n_i_r_national_fund +n_i_r_other_asset"),
     Identity("n_d_a_central_goverment", "+n_d_a_requirement -n_d_a_minus_obligation"),
     Identity("n_d_a", "+n_d_a_central_goverment -n_d_a_fund_national_fund +n_d_a_b_r_not_nbk "
                       "+n_d_a_r_non_banking +n_d_a_r_rest_economy +n_d_a_r_other_domestic", until="2009-02-01"),
     Identity("l", "+n_e_a +n_d_a", name="l=assets"),
     Identity("l", "+r_m +o_d +s_e_s +c +f_d", exempt=("2011-04-01",), name="l=liabilities"),  # 2011-03: 1 603
     Identity("r_m", "+r_m_cash_outside_nbk +r_m_bank_deposit +r_m_t_d_n_b_f_i +r_m_c_a_s_n_s_o")))

ODC = Survey(
    "ODC", "monetaryreviewbank/monetarnyy-obzor-po-bankam-", "monthly",
    ("n_e_a", "n_e_a_h_c", "r_f_n_r_h_c", "l_o_t_n_r_h_c", "o_n_e_a", "d_a", "r", "t_a_o_d_w_t_n", "c_n_c",
     "o_n_r", "n_r_f_t_c_g", "g_r", "l_l", "r_a_l_g_r", "r_f_n_b_f_i", "r_f_s_n_f_o", "r_f_n_g_n_f_o",
     "r_f_n_o", "h_r", "o_n_a", "l", "t_d", "o_d", "c", "f_d", "l_o", "o_a_p"),
    {"n_e_a_h_c": "n_e_a", "r_f_n_r_h_c": "n_e_a_h_c", "l_o_t_n_r_h_c": "n_e_a_h_c", "o_n_e_a": "n_e_a",
     "r": "d_a", "t_a_o_d_w_t_n": "r", "c_n_c": "r", "o_n_r": "d_a", "n_r_f_t_c_g": "d_a", "g_r": "n_r_f_t_c_g",
     "l_l": "n_r_f_t_c_g", "r_a_l_g_r": "d_a", "r_f_n_b_f_i": "d_a", "r_f_s_n_f_o": "d_a", "r_f_n_g_n_f_o": "d_a",
     "r_f_n_o": "d_a", "h_r": "d_a", "o_n_a": "d_a", "t_d": "l", "o_d": "l", "c": "l", "f_d": "l", "l_o": "l",
     "o_a_p": "l"},
    (Identity("n_e_a_h_c", "+r_f_n_r_h_c -l_o_t_n_r_h_c"),
     Identity("n_e_a", "+n_e_a_h_c +o_n_e_a"),
     Identity("r", "+t_a_o_d_w_t_n +c_n_c"),
     Identity("n_r_f_t_c_g", "+g_r -l_l"),
     Identity("d_a", "+r +o_n_r +n_r_f_t_c_g +r_a_l_g_r +r_f_n_b_f_i +r_f_s_n_f_o +r_f_n_g_n_f_o +r_f_n_o +h_r +o_n_a"),
     Identity("l", "+n_e_a +d_a", name="l=assets"),
     Identity("l", "+t_d +o_d +c +f_d +l_o +o_a_p", exempt=("2001-02-01",), name="l=liabilities")))  # 2001-01: 1 114

BS = Survey(
    "BS", "monetaryreviewbankingsystem/monetarnyy-obzor-po-bankovskoy-sisteme-", "monthly",
    ("n_e_a", "n_e_a_r_n_r", "n_e_a_o_n_r", "n_e_a_a_n_f", "n_e_a_o_e_a", "i_a", "i_a_n_r_c_g",
     "i_a_n_r_c_g_r", "i_a_n_r_c_g_c", "i_a_r_r_l_g", "i_a_f_n_f", "i_a_r_nb_f_o", "i_a_r_s_nf_o",
     "i_a_r_ng_nf_o", "i_a_r_nkoth", "i_a_r_h", "i_a_o_d_a", "l", "l_c_c", "l_t_o_d"),
    {"n_e_a_r_n_r": "n_e_a", "n_e_a_o_n_r": "n_e_a", "n_e_a_a_n_f": "n_e_a", "n_e_a_o_e_a": "n_e_a",
     "i_a_n_r_c_g": "i_a", "i_a_n_r_c_g_r": "i_a_n_r_c_g", "i_a_n_r_c_g_c": "i_a_n_r_c_g", "i_a_r_r_l_g": "i_a",
     "i_a_f_n_f": "i_a", "i_a_r_nb_f_o": "i_a", "i_a_r_s_nf_o": "i_a", "i_a_r_ng_nf_o": "i_a", "i_a_r_nkoth": "i_a",
     "i_a_r_h": "i_a", "i_a_o_d_a": "i_a", "l_c_c": "l", "l_t_o_d": "l"},
    (Identity("n_e_a", "+n_e_a_r_n_r -n_e_a_o_n_r +n_e_a_a_n_f +n_e_a_o_e_a", exempt=("2005-12-01",)),  # 2005-11: -515 699
     Identity("i_a_n_r_c_g", "+i_a_n_r_c_g_r -i_a_n_r_c_g_c"),
     Identity("i_a", "+i_a_n_r_c_g +i_a_r_r_l_g -i_a_f_n_f +i_a_r_nb_f_o +i_a_r_s_nf_o +i_a_r_ng_nf_o "
                     "+i_a_r_nkoth +i_a_r_h +i_a_o_d_a", until="2009-02-01"),
     Identity("l", "+n_e_a +i_a", name="l=assets"),
     Identity("l", "+l_c_c +l_t_o_d", name="l=liabilities")))

OFC = Survey(
    "OFC", "otherfinancialinstitutions/obzor-drugih-finansovyh-organizaciy-", "quarterly",
    ("n_e_a", "n_e_a_r_nr", "n_e_a_f_c", "n_e_a_d", "n_e_a_s_o_t_s_i_n", "n_e_a_c", "n_e_a_d_f_i", "n_e_a_etc",
     "o_tr", "o_tr_d", "o_tr_s_o_s", "o_tr_c", "o_tr_d_f_i", "o_tr_etc", "r_b_s", "r_b_s_c_c", "r_b_s_o_r",
     "n_r_c_g", "r_g", "r_g_s_o_s", "r_g_o_r", "m_o_g", "m_o_g_d", "m_o_g_o_o", "r_o_s", "r_o_s_r_r_l_a",
     "r_o_s_r_s_nf_o", "r_o_s_r_ng_nf_o", "r_o_s_r_o_r_s", "d", "d_i_d_c", "s_o_s", "s_o_s_i_d_c", "c",
     "c_i_d_c", "d_f_i", "d_f_i_i_d_c", "i_t_r", "i_t_r_n_v_h_f_i_r", "i_t_r_n_v_h_f_p_f",
     "i_t_r_a_p_i_p_p_u_l", "i_t_r_i_d_c", "s_o_e_p", "other_items"),
    {"n_e_a_r_nr": "n_e_a", "n_e_a_f_c": "n_e_a_r_nr", "n_e_a_d": "n_e_a_r_nr", "n_e_a_s_o_t_s_i_n": "n_e_a_r_nr",
     "n_e_a_c": "n_e_a_r_nr", "n_e_a_d_f_i": "n_e_a_r_nr", "n_e_a_etc": "n_e_a_r_nr", "o_tr": "n_e_a",
     "o_tr_d": "o_tr", "o_tr_s_o_s": "o_tr", "o_tr_c": "o_tr", "o_tr_d_f_i": "o_tr", "o_tr_etc": "o_tr",
     "r_b_s_c_c": "r_b_s", "r_b_s_o_r": "r_b_s", "r_g": "n_r_c_g", "r_g_s_o_s": "r_g", "r_g_o_r": "r_g",
     "m_o_g": "n_r_c_g", "m_o_g_d": "m_o_g", "m_o_g_o_o": "m_o_g", "r_o_s_r_r_l_a": "r_o_s",
     "r_o_s_r_s_nf_o": "r_o_s", "r_o_s_r_ng_nf_o": "r_o_s", "r_o_s_r_o_r_s": "r_o_s",
     "d": LIABILITIES, "d_i_d_c": "d", "s_o_s": LIABILITIES, "s_o_s_i_d_c": "s_o_s", "c": LIABILITIES,
     "c_i_d_c": "c", "d_f_i": LIABILITIES, "d_f_i_i_d_c": "d_f_i", "i_t_r": LIABILITIES,
     "i_t_r_n_v_h_f_i_r": "i_t_r", "i_t_r_n_v_h_f_p_f": "i_t_r", "i_t_r_a_p_i_p_p_u_l": "i_t_r",
     "i_t_r_i_d_c": "i_t_r", "s_o_e_p": LIABILITIES},
    (Identity("n_e_a", "+n_e_a_r_nr -o_tr", name="n_e_a=gross"),
     Identity("n_e_a_r_nr", "+n_e_a_f_c +n_e_a_d +n_e_a_s_o_t_s_i_n +n_e_a_c +n_e_a_d_f_i +n_e_a_etc"),
     Identity("o_tr", "+o_tr_d +o_tr_s_o_s +o_tr_c +o_tr_d_f_i +o_tr_etc", exempt=("2017-04-01",)),  # 2017-Q1: -4
     Identity("r_b_s", "+r_b_s_c_c +r_b_s_o_r"),
     Identity("n_r_c_g", "+r_g -m_o_g"),
     Identity("r_g", "+r_g_s_o_s +r_g_o_r"),
     Identity("m_o_g", "+m_o_g_d +m_o_g_o_o", exempt=("2017-04-01",)),  # 2017-Q1: -22 879
     Identity("r_o_s", "+r_o_s_r_r_l_a +r_o_s_r_s_nf_o +r_o_s_r_ng_nf_o +r_o_s_r_o_r_s"),
     Identity("i_t_r", "+i_t_r_n_v_h_f_i_r +i_t_r_n_v_h_f_p_f +i_t_r_a_p_i_p_p_u_l"),
     Identity("n_e_a", "+d +s_o_s +c +d_f_i +i_t_r +s_o_e_p +other_items -r_b_s -n_r_c_g -r_o_s",
              name="balance")))

FS = Survey(
    "FS", "overviewfinancialsector/obzor-finansovogo-sektora-", "quarterly",
    ("n_e_a", "r_f_n_r", "l_t_n_r", "i_r", "n_r_f_t_c_g", "g_r", "l_o_t_t_g", "r_f_o_s", "r_f_r_a_l_a",
     "r_f_s_n_f_o", "r_f_o_r_s", "f_c_c", "d", "s_o_t_s", "l", "d_f_i", "i_t_r", "s_a_o_f_e_p", "o_a_n"),
    {"r_f_n_r": "n_e_a", "l_t_n_r": "n_e_a", "n_r_f_t_c_g": "i_r", "g_r": "n_r_f_t_c_g", "l_o_t_t_g": "n_r_f_t_c_g",
     "r_f_o_s": "i_r", "r_f_r_a_l_a": "r_f_o_s", "r_f_s_n_f_o": "r_f_o_s", "r_f_o_r_s": "r_f_o_s",
     "f_c_c": LIABILITIES, "d": LIABILITIES, "s_o_t_s": LIABILITIES, "l": LIABILITIES, "d_f_i": LIABILITIES,
     "i_t_r": LIABILITIES, "s_a_o_f_e_p": LIABILITIES},
    (Identity("n_e_a", "+r_f_n_r -l_t_n_r", name="n_e_a=gross"),
     Identity("n_r_f_t_c_g", "+g_r -l_o_t_t_g"),
     Identity("r_f_o_s", "+r_f_r_a_l_a +r_f_s_n_f_o +r_f_o_r_s"),
     Identity("i_r", "+n_r_f_t_c_g +r_f_o_s"),
     Identity("n_e_a", "+f_c_c +d +s_o_t_s +l +d_f_i +i_t_r +s_a_o_f_e_p +o_a_n -i_r", name="balance")))

SURVEYS = {s.code: s for s in (CB, ODC, BS, OFC, FS)}
MONTHLY = ("CB", "ODC", "BS")

# Russian labels as the pages printed them on 2026-09-27 (trailing '*' dropped).
FALLBACK_NAMES = {
    "CB": {"n_e_a": "Чистые внешние активы", "n_i_r": "Чистые международные резервы",
           "n_i_r_scv": "Валовые международные активы, СКВ", "n_i_r_scv_minus": "Минус: Внешние обязательства, СКВ",
           "n_i_r_national_fund": "Активы Национального Фонда", "n_i_r_other_asset": "Прочие чистые внешние активы, ПВВ",
           "n_d_a": "Чистые внутренние активы", "n_d_a_central_goverment": "Чистые требования к Центральному Правительству",
           "n_d_a_requirement": "Требования", "n_d_a_minus_obligation": "Минус: Обязательства",
           "n_d_a_fund_national_fund": "Средства Национального Фонда",
           "n_d_a_b_r_not_nbk": "Требования к банкам (за вычетом обязательств НБК по краткосрочным нотам)",
           "n_d_a_r_non_banking": "Требования к небанковским финансовым организациям",
           "n_d_a_r_rest_economy": "Требования к остальной экономике",
           "n_d_a_r_other_domestic": "Прочие чистые внутренние активы", "l": "Пассивы",
           "l_monetary_base_narrow": "Денежная база ( в узком выражении)", "r_m": "Резервные деньги",
           "r_m_cash_outside_nbk": "Наличные деньги вне НБК", "r_m_bank_deposit": "Депозиты банков",
           "r_m_t_d_n_b_f_i": "Переводимые депозиты небанковских финансовых организаций",
           "r_m_c_a_s_n_s_o": "Текущие счета государственных и негосударственных нефинансовых организаций",
           "o_d": "Другие депозиты", "s_e_s": "Ценные бумаги (кроме акций)", "c": "Кредиты (включая операции РЕПО)",
           "f_d": "Финансовые деривативы"},
    "ODC": {"n_e_a": "Чистые внешние активы", "n_e_a_h_c": "Чистые внешние активы, СКВ",
            "r_f_n_r_h_c": "Требования к нерезидентам, СКВ", "l_o_t_n_r_h_c": "Минус: Обязательства перед нерезидентами, СКВ",
            "o_n_e_a": "Прочие чистые внешние активы, ПВВ", "d_a": "Внутренние активы", "r": "Резервы",
            "t_a_o_d_w_t_n": "Переводимые и другие депозиты в НБК", "c_n_c": "Наличная национальная валюта",
            "o_n_r": "Другие требования к НБК", "n_r_f_t_c_g": "Чистые требования к Центральному Правительству",
            "g_r": "Валовые требования", "l_l": "Минус: обязательства",
            "r_a_l_g_r": "Требования к региональным и местным органам управления",
            "r_f_n_b_f_i": "Требования к небанковским финансовым организациям",
            "r_f_s_n_f_o": "Требования к государственным нефинансовым организациям",
            "r_f_n_g_n_f_o": "Требования к негосударственным нефинансовым организациям",
            "r_f_n_o": "Требования к НКУ ОДХ", "h_r": "Требования к домашним хозяйствам", "o_n_a": "Прочие чистые активы",
            "l": "Пассивы", "t_d": "Переводимые депозиты", "o_d": "Другие депозиты", "c": "Ценные бумаги",
            "f_d": "Финансовые деривативы", "l_o": "Кредиты", "o_a_p": "Другие счета к оплате"},
    "BS": {"n_e_a": "Чистые внешние активы", "n_e_a_r_n_r": "Требования к нерезидентам, СКВ",
           "n_e_a_o_n_r": "Обязательства перед нерезидентами, СКВ", "n_e_a_a_n_f": "Активы Национального фонда",
           "n_e_a_o_e_a": "Прочие чистые внешние активы, ПВВ", "i_a": "Внутренние активы",
           "i_a_n_r_c_g": "Чистые требования к Центральному Правительству", "i_a_n_r_c_g_r": "Требования",
           "i_a_n_r_c_g_c": "Обязательства", "i_a_r_r_l_g": "Требования к региональным и местным органам управления",
           "i_a_f_n_f": "Средства Национального фонда", "i_a_r_nb_f_o": "Требования к небанковским финансовым организациям",
           "i_a_r_s_nf_o": "Требования к государственным нефинансовым организациям",
           "i_a_r_ng_nf_o": "Требования к негосударственным нефинансовым организациям",
           "i_a_r_nkoth": "Требования к НКУ ОДХ", "i_a_r_h": "Требования к домашним хозяйствам",
           "i_a_o_d_a": "Прочие чистые внутренние активы", "l": "Пассивы", "l_c_c": "Наличные деньги в обращении",
           "l_t_o_d": "Переводимые и другие депозиты"},
    "OFC": {"n_e_a": "Чистые внешние активы", "n_e_a_r_nr": "Требования к нерезидентам", "n_e_a_f_c": "Иностранная валюта",
            "n_e_a_d": "Депозиты", "n_e_a_s_o_t_s_i_n": "Ценные бумаги кроме акций, вып. нерез.", "n_e_a_c": "Кредиты",
            "n_e_a_d_f_i": "Производные финансовые инструменты", "n_e_a_etc": "Прочее",
            "o_tr": "Обязательства перед нерезидентами", "o_tr_d": "Депозиты", "o_tr_s_o_s": "Ценные бумаги кроме акций",
            "o_tr_c": "Кредиты", "o_tr_d_f_i": "Производные финансовые инструменты", "o_tr_etc": "Прочее",
            "r_b_s": "Требования к банковской системе", "r_b_s_c_c": "Наличная валюта", "r_b_s_o_r": "Другие требования",
            "n_r_c_g": "Чистые требования к Центральному Правительству", "r_g": "Требования к Правительству",
            "r_g_s_o_s": "Ценные бумаги кроме акций, вып. Прав.", "r_g_o_r": "Другие требования",
            "m_o_g": "Минус: Обязательства перед Правительством", "m_o_g_d": "Депозиты",
            "m_o_g_o_o": "Другие обязательства", "r_o_s": "Требования к другим секторам",
            "r_o_s_r_r_l_a": "Требования к региональным и местным органам власти",
            "r_o_s_r_s_nf_o": "Требования к государственным нефинансовым организациям",
            "r_o_s_r_ng_nf_o": "Требования к негосударственным нефинансовым организациям",
            "r_o_s_r_o_r_s": "Требования к другим секторам-резидентам", "d": "Депозиты",
            "d_i_d_c": "в том числе: депозитные корпорации", "s_o_s": "Ценные бумаги кроме акций",
            "s_o_s_i_d_c": "в том числе: депозитные корпорации", "c": "Кредиты",
            "c_i_d_c": "в том числе: депозитные корпорации", "d_f_i": "Производные финансовые инструменты",
            "d_f_i_i_d_c": "в том числе: депозитные корпорации", "i_t_r": "Страховые технические резервы",
            "i_t_r_n_v_h_f_i_r": "Чистая стоимость средств домашних хозяйств в резервах по страхованию жизни",
            "i_t_r_n_v_h_f_p_f": "Чистая стоимость средств домашних хозяйств в пенсионных фондах",
            "i_t_r_a_p_i_p_p_u_l": "Предварительные взносы страховых премий и резервы на покрытие неурегулированных убытков",
            "i_t_r_i_d_c": "в том числе: депозитные корпорации", "s_o_e_p": "Акции и другие формы участия в капитале",
            "other_items": "Прочие статьи (нетто)"},
    "FS": {"n_e_a": "Чистые внешние активы", "r_f_n_r": "Требования к нерезидентам",
           "l_t_n_r": "Обязательства перед нерезидентами", "i_r": "Внутренние требования",
           "n_r_f_t_c_g": "Чистые требования к Центральному Правительству", "g_r": "Требования к Правительству",
           "l_o_t_t_g": "Минус: Обязательства перед Правительством", "r_f_o_s": "Требования к другим секторам",
           "r_f_r_a_l_a": "Требования к региональным и местным органам власти",
           "r_f_s_n_f_o": "Требования к государственным нефинансовым организациям",
           "r_f_o_r_s": "Требования к другим секторам-резидентам", "f_c_c": "Наличная валюта вне финансового сектора",
           "d": "Депозиты", "s_o_t_s": "Ценные бумаги кроме акций", "l": "Кредиты",
           "d_f_i": "Производные финансовые инструменты", "i_t_r": "Страховые технические резервы",
           "s_a_o_f_e_p": "Акции и другие формы участия в капитале", "o_a_n": "Прочие статьи (нетто)"},
}

# A record whose reporting_date carries the wrong year: (survey, reporting_date[:10]) -> the
# YYYY-MM it belongs to. See the module docstring (banks' survey 2003-04).
KNOWN_MISDATED = {("ODC", "2005-04-14"): "2003-04"}

# Cross-survey identities on the monthly surveys: BS key = Σ (survey, key), from this as-at date.
CROSS_FROM = "2002-11-01"
CROSS_IDENTITIES = {
    "i_a_r_nb_f_o": (("CB", "n_d_a_r_non_banking"), ("ODC", "r_f_n_b_f_i")),
    "rest_of_economy": (("CB", "n_d_a_r_rest_economy"), ("ODC", "r_a_l_g_r"), ("ODC", "r_f_s_n_f_o"),
                        ("ODC", "r_f_n_g_n_f_o"), ("ODC", "r_f_n_o"), ("ODC", "h_r")),
}
BS_REST_OF_ECONOMY = ("i_a_r_r_l_g", "i_a_r_s_nf_o", "i_a_r_ng_nf_o", "i_a_r_nkoth", "i_a_r_h")

# Lines that must equal the open-data forms already in the pipeline, on common dates.
FORM50_LINES = {"n_e_a": "1", "n_d_a_central_goverment": "2.1", "n_d_a_b_r_not_nbk": "2.3",
                "n_d_a_r_non_banking": "2.4", "n_d_a_r_rest_economy": "2.5", "n_d_a_r_other_domestic": "2.6",
                "l": "3", "r_m": "3.1", "r_m_cash_outside_nbk": "3.1.1"}
FORM26_SCALARS = {"n_e_a": "ofc_net_foreign_assets", "n_e_a_r_nr": "ofc_claims_on_nonresidents",
                  "r_b_s": "ofc_claims_on_banking_system"}
FORM_TOLERANCE = 1.0

_RECORDS: dict[str, list[dict]] = {}
_LABELS: dict[str, dict[str, str]] = {}


def _error(what: str, lines: list[str], action: str = "inspect the NBK page and update scripts/fetchers/nbk_records.py"):
    return validation.StructuralChangeError("\n".join(
        [f"STRUCTURAL CHANGE DETECTED in nbk/{what}", *lines, f"ACTION REQUIRED: {action}"]))


# ---------------------------------------------------------------- download

def item_key(raw_key: str) -> str:
    """NBK key -> item key: the Cyrillic «с» in r_m_с_a_s_n_s_o becomes Latin."""
    return raw_key.translate(_LATIN)


def download_records(code: str) -> list[dict]:
    """The survey's records JSON, once per process (archived raw)."""
    if code not in _RECORDS:
        survey = SURVEYS[code]
        params = {"beginMount": 1, "beginYear": 1990, "endMount": 12, "endYear": date.today().year}
        resp = nbk._download(survey.records_url, params)
        today = date.today()
        raw_id = f"SURVEY_RECORDS_{code}"
        raw_store.save_raw_bytes(SOURCE, raw_id, today, "json", resp.content)
        raw_store.write_download_manifest(SOURCE, raw_id, today, {
            "downloaded_at": datetime.now().isoformat(), "source_url": survey.records_url, "params": params,
            "read_by": "fetchers/nbk_records.py"})
        try:
            data = resp.json()
        except ValueError as exc:
            raise _error(raw_id, ["WHAT CHANGED: the records endpoint no longer returns JSON",
                                  f"ACTUAL: {resp.text[:300]!r} ({exc})"]) from exc
        _RECORDS[code] = check_structure(code, data)
    return _RECORDS[code]


def check_structure(code: str, data) -> list[dict]:
    survey = SURVEYS[code]
    if not isinstance(data, list) or not data or not all(isinstance(r, dict) and r.get("reporting_date") for r in data):
        raise _error(f"SURVEY_RECORDS_{code}", [
            "WHAT CHANGED: expected a list of {reporting_date, <field keys>} dicts", f"ACTUAL: {str(data)[:300]}"])
    seen = {item_key(k) for r in data for k in r} - META_FIELDS
    unknown, missing = seen - set(survey.fields), set(survey.fields) - seen
    if unknown or missing:
        raise _error(f"SURVEY_RECORDS_{code}", [
            "WHAT CHANGED: the survey's field keys differ from nbk_records.SURVEYS",
            f"EXPECTED: {len(survey.fields)} keys", f"ACTUAL: new {sorted(unknown)}, gone {sorted(missing)}"],
            "map the new keys (label from the page's `trans` dictionary) into SURVEYS/FALLBACK_NAMES")
    return data


_LABEL_RE = re.compile(r'"([A-Za-z_Ѐ-ӿ]+)"\s*:\s*"([^"\n]*)"')


def parse_labels(html: str, fields) -> dict[str, str]:
    """{item key: Russian label} from the page's JS `trans` dictionary; the first Cyrillic label of
    each key wins, and untranslated "monetaryreview::…" placeholders are ignored."""
    wanted, out = set(fields), {}
    for key, label in _LABEL_RE.findall(html):
        key = item_key(key)
        label = re.sub(r"\s+", " ", label).strip().rstrip("*").strip()
        if key in wanted and key not in out and "::" not in label and re.search("[А-Яа-яЁё]", label):
            out[key] = label
    return out


def page_labels(code: str) -> tuple[dict[str, str], list[str]]:
    """Labels read from the page, completed from FALLBACK_NAMES; the warnings say which keys fell back."""
    survey, warnings = SURVEYS[code], []
    if code not in _LABELS:
        try:
            resp = requests.get(survey.page_url, headers=nbk.HEADERS, timeout=60)
            resp.raise_for_status()
            _LABELS[code] = parse_labels(resp.text, survey.fields)
        except requests.RequestException as exc:
            _LABELS[code] = {}
            warnings.append(f"{code}: page {survey.page_url} not read ({exc}); fallback labels used")
    labels = dict(FALLBACK_NAMES[code])
    labels.update(_LABELS[code])
    fell_back = [k for k in survey.fields if k not in _LABELS[code]]
    if fell_back and _LABELS[code]:
        warnings.append(f"{code}: no label on the page for {fell_back}; fallback labels used")
    return labels, warnings


def item_names(code: str, labels: dict[str, str]) -> dict[str, str]:
    """Qualified names: a line whose label is short (< 30 characters) or repeated within the survey
    is prefixed with its parent's name («Пассивы: Кредиты», «Чистые требования к Центральному
    Правительству: Требования»)."""
    survey = SURVEYS[code]
    counts: dict[str, int] = {}
    for k in survey.fields:
        counts[labels[k]] = counts.get(labels[k], 0) + 1
    names: dict[str, str] = {}

    def name(k: str) -> str:
        if k not in names:
            label, parent = labels[k], survey.parents.get(k)
            if parent and (len(label) < 30 or counts[label] > 1):
                prefix = parent[1:] if parent.startswith("=") else name(parent)
                label = f"{prefix}: {label}"
            names[k] = label
        return names[k]

    return {k: name(k) for k in survey.fields}


# ---------------------------------------------------------------- dating and frames

def survey_frame(code: str, rows: list[dict]) -> dict[str, dict[str, float]]:
    """{as-at date: {item key: value}}. The YYYY-MM of reporting_date is the month whose end the
    stock refers to; dated the first day of the next month (module docstring)."""
    survey = SURVEYS[code]
    months: dict[str, str] = {}
    frame: dict[str, dict[str, float]] = {}
    step = 1 if survey.frequency == "monthly" else 3
    for r in rows:
        rd = str(r["reporting_date"])
        ym = KNOWN_MISDATED.get((code, rd[:10]), rd[:7])
        if not re.fullmatch(r"\d{4}-\d{2}", ym) or (int(ym[5:7]) % step != 0):
            raise _error(f"SURVEY_RECORDS_{code}", [f"WHAT CHANGED: reporting_date {rd!r} is not a "
                                                    f"{survey.frequency} period end"])
        if ym in months:
            raise _error(f"SURVEY_RECORDS_{code}", [
                f"WHAT CHANGED: two records for {ym}: reporting_date {months[ym]!r} and {rd!r}",
                "EXPECTED: one record per period (known misdated records are in KNOWN_MISDATED)"],
                "find the period the extra record belongs to and add it to KNOWN_MISDATED")
        months[ym] = rd
        frame[nbk.money_as_at(ym)] = {item_key(k): float(v) for k, v in r.items()
                                      if k not in META_FIELDS and v is not None}
    return dict(sorted(frame.items()))


def tolerance(n_terms: int) -> float:
    """Rounding band of an identity between integer-rounded lines: 0.5 mln per term, at least 3 --
    the NBK rounds totals from unrounded detail, so two-term identities miss by 2-3 mln (ODC
    l = n_e_a + d_a in 2006-07, 2006-09, 2006-10, 2007-03; OFC n_e_a in 2017-Q1)."""
    return max(3.0, 0.5 * n_terms)


def check_identities(code: str, frame: dict[str, dict[str, float]]) -> list[str]:
    """Breaches of the survey's IDENTITIES, beyond rounding (tolerance())."""
    errors = []
    for ident in SURVEYS[code].identities:
        terms = ident.terms()
        tol = tolerance(len(terms) + 1)
        for d, row in frame.items():
            if ident.total not in row or d in ident.exempt or (ident.until and d > ident.until):
                continue
            s = sum(sign * row.get(k, 0.0) for sign, k in terms)
            if abs(row[ident.total] - s) > tol:
                errors.append(f"{code} {d}: {ident.name or ident.total} = {row[ident.total]:,.0f}, "
                              f"{ident.parts} = {s:,.0f}")
    return errors


def check_cross(frames: dict[str, dict[str, dict[str, float]]]) -> list[str]:
    """BS claims on NBFIs and on the rest of the economy = CB + ODC, from CROSS_FROM."""
    errors = []
    bs = frames["BS"]
    for d, row in bs.items():
        if d < CROSS_FROM or d not in frames["CB"] or d not in frames["ODC"]:
            continue
        for name, parts in CROSS_IDENTITIES.items():
            lhs = row.get(name) if name != "rest_of_economy" else sum(row.get(k, 0.0) for k in BS_REST_OF_ECONOMY)
            if lhs is None:
                continue
            rhs = sum(frames[s][d].get(k, 0.0) for s, k in parts)
            n_terms = len(parts) + (len(BS_REST_OF_ECONOMY) if name == "rest_of_economy" else 1)
            if abs(lhs - rhs) > tolerance(n_terms):
                errors.append(f"{d}: BS {name} = {lhs:,.0f}, CB + ODC = {rhs:,.0f}")
    return errors


def _load_form50(path: Path | None = None) -> dict[tuple[str, str], float]:
    path = path or FORM50_PATH
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {(r["date"], r["item_code"]): float(r["value"]) for r in csv.DictReader(f)
                if (r.get("region") or dims.NATIONAL) == dims.NATIONAL}


def _load_scalar(name: str, root: Path | None = None) -> dict[str, float]:
    path = (root or FORM26_ROOT) / f"{name}.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f) if r.get("value") not in (None, "")}


def check_against_forms(code: str, frame: dict[str, dict[str, float]],
                        form50: dict[tuple[str, str], float] | None = None,
                        form26: dict[str, dict[str, float]] | None = None) -> tuple[list[str], int]:
    """CB vs form 50 (FORM50_LINES), OFC vs the form 26 scalars (FORM26_SCALARS): (errors, points compared)."""
    errors, n = [], 0
    if code == "CB":
        form50 = _load_form50() if form50 is None else form50
        for d, row in frame.items():
            for key, line in FORM50_LINES.items():
                if key in row and (d, line) in form50:
                    n += 1
                    if abs(row[key] - form50[(d, line)]) > FORM_TOLERANCE:
                        errors.append(f"CB {d}: {key} = {row[key]:,.1f}, form 50 line {line} = {form50[(d, line)]:,.1f}")
    elif code == "OFC":
        form26 = {k: _load_scalar(v) for k, v in FORM26_SCALARS.items()} if form26 is None else form26
        for d, row in frame.items():
            for key, series in form26.items():
                if key in row and d in series:
                    n += 1
                    if abs(row[key] - series[d]) > FORM_TOLERANCE:
                        errors.append(f"OFC {d}: {key} = {row[key]:,.1f}, form 26 {FORM26_SCALARS[key]} = {series[d]:,.1f}")
    return errors, n


def to_records(code: str, frame: dict[str, dict[str, float]], names: dict[str, str]) -> list[dict]:
    fields = SURVEYS[code].fields
    return [{"date": d, "region": dims.NATIONAL, "item_code": f"{code}.{k}", "item_name": names[k], "value": row[k]}
            for k in fields for d, row in frame.items() if k in row]


# ---------------------------------------------------------------- dims fetcher

def fetch(ds: dict) -> tuple[list[dict], dict]:
    """dims.yaml dataset with `survey: CB|ODC|BS|OFC|FS` (and optionally `refresh_days`)."""
    if ds.get("refresh_days"):  # optional: skip the download while the last one is younger than this
        fresh = imf_dims.stored_if_fresh(ds, SOURCE, ds["id"])
        if fresh:
            return fresh
    code = ds["survey"]
    survey = SURVEYS[code]
    frames = {c: survey_frame(c, download_records(c)) for c in (MONTHLY if code in MONTHLY else (code,))}
    frame = frames[code]
    errors = check_identities(code, frame)
    if code in MONTHLY:
        errors += check_cross(frames)
    form_errors, compared = check_against_forms(code, frame)
    errors += form_errors
    if errors:
        raise _error(ds["id"], ["WHAT CHANGED: a survey identity or a cross-check against the open-data forms fails",
                                f"ACTUAL ({len(errors)}): " + "; ".join(errors[:12])],
                     "compare with the NBK page; a one-off source error goes into the identity's `exempt`")
    labels, warnings = page_labels(code)
    names = item_names(code, labels)
    records = to_records(code, frame, names)
    rows = download_records(code)
    latest = max(rows, key=lambda r: str(r["reporting_date"]))
    if latest.get("note_ru"):
        warnings.append(f"{code} latest record: {latest['note_ru']}")
    published = max(str(r.get("published_at") or "")[:10] for r in rows) or None
    raw_store.write_download_manifest(SOURCE, ds["id"], date.today(), {
        "downloaded_at": datetime.now().isoformat(), "source_url": survey.records_url,
        "raw": f"SURVEY_RECORDS_{code}", "latest_reporting_date": str(latest["reporting_date"])})
    manifest = {
        "frequency": survey.frequency, "source_url": survey.records_url,
        "dataset_id": f"nbk-records/{survey.page.split('/')[0]}",
        "release": published,
        "note": ds.get("note") or (f"NBK page records, million KZT, stock at the end of the period dated as at "
                                   f"the first day of the next {'month' if survey.frequency == 'monthly' else 'quarter'}."),
        "warnings": warnings,
        "checks": {"identities": len(survey.identities), "form_points_compared": compared},
    }
    return records, manifest


if __name__ == "__main__":  # python scripts/fetchers/nbk_records.py CB  -> summary, writes nothing under data/processed
    import argparse
    ap = argparse.ArgumentParser(description="Download and check one NBK survey (no processed write).")
    ap.add_argument("survey", choices=sorted(SURVEYS))
    args = ap.parse_args()
    recs, man = fetch({"id": f"{args.survey}_CHECK", "survey": args.survey})
    items = sorted({r["item_code"] for r in recs})
    print(json.dumps({"records": len(recs), "items": len(items), "first": min(r["date"] for r in recs),
                      "last": max(r["date"] for r in recs), "manifest": man}, ensure_ascii=False, indent=1))
