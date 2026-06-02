import pandas as pd
import numpy as np
import requests
import sys
import os


# ============================================================
# PENMAN & POPE — RNOA MODULE
#
# Calculates RNOA, PM, ATO, ReOI for any US-listed ticker
# using live data from SEC EDGAR.
#
# Primary function: calculate_rnoa_series(ticker, r)
# ============================================================


def get_fiscal_year_dates(facts: dict, years: int = 4) -> list:
    """Get last N unique fiscal year end dates from 10-K filings."""
    entries = facts["Assets"]["units"]["USD"]
    tenk    = [e for e in entries if e.get("form") == "10-K"]
    tenk.sort(key=lambda x: x.get("end", ""), reverse=True)
    seen = []
    for e in tenk:
        end = e["end"]
        if end not in seen:
            seen.append(end)
        if len(seen) == years:
            break
    return seen


def get_income_statement(facts: dict, years: int = 4) -> pd.DataFrame:
    """
    Fetch income statement for last N fiscal years.

    Returns DataFrame with:
        fiscal_year_end, revenue, operating_income_pretax,
        operating_income_aftertax, net_income,
        tax_expense, effective_tax_rate
    """
    from data_fetch import get_concept_value

    fy_dates = get_fiscal_year_dates(facts, years)
    rows = []

    for fy in fy_dates:
        def get(concept):
            return get_concept_value(facts, concept, fy) or 0

        revenue = (
            get("RevenueFromContractWithCustomerExcludingAssessedTax") or
            get("Revenues") or
            get("SalesRevenueNet")
        )
        op_income         = get("OperatingIncomeLoss")
        net_income        = get("NetIncomeLoss")
        tax_expense       = get("IncomeTaxExpenseBenefit")
        income_before_tax = get(
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
        )

        eff_tax_rate = (
            tax_expense / income_before_tax
            if income_before_tax and income_before_tax != 0
            else 0.21
        )

        rows.append({
            "fiscal_year_end":           fy,
            "revenue":                   revenue,
            "operating_income_pretax":   op_income,
            "operating_income_aftertax": round(op_income * (1 - eff_tax_rate), 1),
            "net_income":                net_income,
            "tax_expense":               tax_expense,
            "income_before_tax":         income_before_tax,
            "effective_tax_rate":        round(eff_tax_rate, 4),
        })

    df = pd.DataFrame(rows)
    return df.sort_values("fiscal_year_end").reset_index(drop=True)


def get_noa_series(facts: dict, years: int = 4) -> pd.DataFrame:
    """
    Fetch NOA for last N fiscal years using reformulate_from_financing().
    """
    from data_fetch    import get_concept_value
    from reformulation import reformulate_from_financing

    fy_dates = get_fiscal_year_dates(facts, years)
    rows = []

    for fy in fy_dates:
        def get(concept):
            return get_concept_value(facts, concept, fy) or 0

        total_assets      = get("Assets")
        total_liabilities = get("Liabilities")

        if total_liabilities == 0:
            for eq in [
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ]:
                equity = get_concept_value(facts, eq, fy)
                if equity:
                    total_liabilities = total_assets - equity
                    break

        cash      = get("CashAndCashEquivalentsAtCarryingValue")
        st_invest = get("ShortTermInvestments")
        fin_assets = cash + st_invest

        ltd_c  = get("LongTermDebtCurrent") or get("LongTermDebtAndCapitalLeaseObligationsCurrent")
        ltd_nc = get("LongTermDebtNoncurrent") or get("LongTermDebtAndCapitalLeaseObligations")
        ol_nc  = get("OperatingLeaseLiabilityNoncurrent")
        ol_c   = get("OperatingLeaseLiabilityCurrent")

        if ol_c == 0:
            ol_total = get("OperatingLeaseLiability")
            if ol_total > 0 and ol_nc > 0:
                ol_c = ol_total - ol_nc

        st_debt = get("ShortTermBorrowings") or get("CommercialPaper") or 0
        fin_liabilities = ltd_c + ltd_nc + ol_c + ol_nc + st_debt

        result = reformulate_from_financing(
            total_assets          = total_assets,
            total_liabilities     = total_liabilities,
            financing_assets      = fin_assets,
            financing_liabilities = fin_liabilities,
        )

        rows.append({
            "fiscal_year_end": fy,
            "NOA":             result["NOA"],
            "ND":              result["ND"],
            "B":               result["B"],
            "anchor_check":    result["anchor_check"],
        })

    df = pd.DataFrame(rows)
    return df.sort_values("fiscal_year_end").reset_index(drop=True)


def calculate_rnoa_series(ticker: str, r: float = 0.09,
                           years: int = 5) -> pd.DataFrame:
    """
    Calculate RNOA, PM, ATO, ReOI for last N fiscal years.

    Inputs:
        ticker  — stock ticker (e.g. "MSFT")
        r       — required return on operations (default 9%)
        years   — number of fiscal years to fetch (default 4)

    Returns DataFrame with columns:
        fiscal_year_end, revenue, OI_aftertax,
        NOA_start, NOA_end, NOA_avg,
        RNOA, PM, ATO, ReOI, effective_tax_rate

    Formulas (Penman & Pope):
        RNOA = OI (after tax) / NOA_start
        PM   = OI (after tax) / Revenue
        ATO  = Revenue / Average NOA
        ReOI = (RNOA - r) x NOA_start
    """
    from data_fetch import get_cik, get_xbrl_facts

    cik   = get_cik(ticker)
    facts = get_xbrl_facts(cik)

    is_df  = get_income_statement(facts, years)
    noa_df = get_noa_series(facts, years)

    df = pd.merge(is_df, noa_df, on="fiscal_year_end", how="inner")
    df = df.sort_values("fiscal_year_end").reset_index(drop=True)

    df["NOA_start"] = df["NOA"].shift(1)
    df["NOA_avg"]   = (df["NOA"] + df["NOA_start"]) / 2

    results = []
    for _, row in df.iterrows():
        if pd.isna(row["NOA_start"]) or row["NOA_start"] == 0:
            continue

        OI      = row["operating_income_aftertax"]
        rev     = row["revenue"]
        noa_s   = row["NOA_start"]
        noa_avg = row["NOA_avg"]

        RNOA = OI / noa_s    if noa_s   != 0 else None
        PM   = OI / rev      if rev     != 0 else None
        ATO  = rev / noa_avg if noa_avg != 0 else None
        ReOI = (RNOA - r) * noa_s if RNOA is not None else None

        results.append({
            "fiscal_year_end":    row["fiscal_year_end"],
            "revenue":            row["revenue"],
            "OI_aftertax":        OI,
            "effective_tax_rate": row["effective_tax_rate"],
            "NOA_start":          noa_s,
            "NOA_end":            row["NOA"],
            "NOA_avg":            noa_avg,
            "RNOA":               round(RNOA, 4) if RNOA else None,
            "PM":                 round(PM,   4) if PM   else None,
            "ATO":                round(ATO,  4) if ATO  else None,
            "ReOI":               round(ReOI, 1) if ReOI else None,
            "required_return":    r,
        })

    return pd.DataFrame(results)


def print_rnoa_report(ticker: str, r: float = 0.09) -> None:
    """Print a formatted RNOA report for a ticker."""
    df = calculate_rnoa_series(ticker, r)

    print(f"{'='*62}")
    print(f"  RNOA ANALYSIS — {ticker.upper()}")
    print(f"  Required return: {r:.0%}")
    print(f"{'='*62}")
    print(f"  {'FY End':<14} {'RNOA':>8} {'PM':>8} "
          f"{'ATO':>8} {'ReOI ($m)':>12} {'OI ($m)':>10}")
    print(f"  {'-'*60}")
    for _, row in df.iterrows():
        print(f"  {row['fiscal_year_end']:<14} "
              f"{row['RNOA']:>7.1%} "
              f"{row['PM']:>7.1%} "
              f"{row['ATO']:>8.2f}x "
              f"${row['ReOI']:>10,.0f}m "
              f"${row['OI_aftertax']:>8,.0f}m")
    print()


print("rnoa.py loaded.")
print("Primary function: calculate_rnoa_series(ticker, r)")
print("Report function:  print_rnoa_report(ticker, r)")
