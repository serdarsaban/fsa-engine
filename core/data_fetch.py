import requests
import pandas as pd
import numpy as np


# ============================================================
# PENMAN & POPE — DATA FETCH MODULE
#
# Fetches balance sheet inputs for reformulation
# directly from SEC EDGAR for any US-listed ticker.
#
# Primary function: run_reformulation(ticker)
# Returns NOA, ND, B plus all inputs.
# ============================================================

HEADERS = {"User-Agent": "FSA Engine research@example.com"}


def get_cik(ticker: str) -> str:
    """Convert ticker to SEC CIK number."""
    url = "https://www.sec.gov/files/company_tickers.json"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry["ticker"] == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker {ticker!r} not found in SEC database.")


def get_latest_10k(cik: str) -> dict:
    """Find the most recent 10-K filing for a company."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    filings = data["filings"]["recent"]
    for i, form in enumerate(filings["form"]):
        if form == "10-K":
            return {
                "company":   data["name"],
                "cik":       cik,
                "filed":     filings["filingDate"][i],
                "accession": filings["accessionNumber"][i],
                "document":  filings["primaryDocument"][i],
            }
    raise ValueError(f"No 10-K found for CIK {cik}")


def get_xbrl_facts(cik: str) -> dict:
    """Fetch all XBRL financial facts from SEC."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)
    return response.json()["facts"].get("us-gaap", {})


def get_fiscal_year_end(facts: dict) -> str:
    """Determine the most recent fiscal year end date."""
    if "Assets" not in facts:
        return None
    entries = facts["Assets"]["units"]["USD"]
    tenk = [e for e in entries if e.get("form") == "10-K"]
    tenk.sort(key=lambda x: x.get("end", ""), reverse=True)
    return tenk[0]["end"] if tenk else None


def get_concept_value(facts: dict, concept: str,
                      fy_end: str) -> float:
    """Extract a single concept value for a fiscal year end."""
    if concept not in facts:
        return None
    units   = facts[concept]["units"]
    key     = list(units.keys())[0]
    matches = [
        e for e in units[key]
        if e.get("form") == "10-K"
        and e.get("end", "") == fy_end
    ]
    if matches:
        return matches[-1]["val"] / 1e6
    return None


def get_total_liabilities(facts: dict, fy_end: str,
                           total_assets: float) -> float:
    """
    Get total liabilities.
    Fallback: Total Assets - Stockholders Equity
    """
    liab = get_concept_value(facts, "Liabilities", fy_end)
    if liab and liab > 0:
        return liab

    for concept in [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ]:
        equity = get_concept_value(facts, concept, fy_end)
        if equity is not None:
            return total_assets - equity

    raise ValueError("Cannot determine total liabilities.")


def get_reformulation_inputs(ticker: str) -> dict:
    """
    Fetch the four inputs needed for reformulate_from_financing().

    Returns dict containing:
        total_assets, total_liabilities,
        financing_assets, financing_liabilities,
        plus all component line items and metadata.
    """
    cik    = get_cik(ticker)
    filing = get_latest_10k(cik)
    facts  = get_xbrl_facts(cik)
    fy_end = get_fiscal_year_end(facts)

    def get(concept):
        return get_concept_value(facts, concept, fy_end) or 0

    # Totals
    total_assets      = get("Assets")
    total_liabilities = get_total_liabilities(
        facts, fy_end, total_assets
    )

    # Financing assets: cash + short-term investments
    cash      = get("CashAndCashEquivalentsAtCarryingValue")
    st_invest = get("ShortTermInvestments")
    fin_assets = cash + st_invest

    # Financing liabilities: debt + operating leases
    ltd_current = (
        get("LongTermDebtCurrent") or
        get("LongTermDebtAndCapitalLeaseObligationsCurrent")
    )
    ltd_noncurrent = (
        get("LongTermDebtNoncurrent") or
        get("LongTermDebtAndCapitalLeaseObligations")
    )
    op_lease_noncurrent = get("OperatingLeaseLiabilityNoncurrent")
    op_lease_current    = get("OperatingLeaseLiabilityCurrent")

    # Fallback for current operating lease
    if op_lease_current == 0:
        op_lease_total = get("OperatingLeaseLiability")
        if op_lease_total > 0 and op_lease_noncurrent > 0:
            op_lease_current = op_lease_total - op_lease_noncurrent

    st_debt = get("ShortTermBorrowings") or get("CommercialPaper") or 0

    fin_liabilities = (
        ltd_current        +
        ltd_noncurrent     +
        op_lease_current   +
        op_lease_noncurrent +
        st_debt
    )

    return {
        "ticker":              ticker.upper(),
        "company":             filing["company"],
        "fiscal_year_end":     fy_end,
        "filed":               filing["filed"],
        "total_assets":        total_assets,
        "total_liabilities":   total_liabilities,
        "cash":                cash,
        "st_investments":      st_invest,
        "financing_assets":    fin_assets,
        "ltd_current":         ltd_current,
        "ltd_noncurrent":      ltd_noncurrent,
        "op_lease_current":    op_lease_current,
        "op_lease_noncurrent": op_lease_noncurrent,
        "st_debt":             st_debt,
        "financing_liabilities": fin_liabilities,
    }


print("data_fetch.py loaded.")
print("Primary function: get_reformulation_inputs(ticker)")
