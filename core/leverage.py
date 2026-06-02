import pandas as pd
import numpy as np
import yfinance as yf


# ============================================================
# PENMAN & POPE — LEVERAGE MODULE
#
# Implements ROE leverage decomposition:
#   ROE = RNOA + LEV x (RNOA - NBC)
#
# Primary function: print_leverage_report(ticker, r)
# ============================================================


def get_net_financing_expense(facts: dict, fy_end: str,
                               tax_rate: float) -> dict:
    """
    Calculate Net Financing Expense (after tax).

    NE = (Interest Expense - Interest Income) x (1 - tax_rate)
    """
    from data_fetch import get_concept_value

    def get(concept):
        return get_concept_value(facts, concept, fy_end) or 0

    interest_expense = (
        get("InterestExpense") or
        get("InterestAndDebtExpense") or
        get("FinanceLeaseInterestExpense")
    )

    interest_income = (
        get("InvestmentIncomeNet")               or
        get("InterestIncomeOperating")           or
        get("InvestmentIncomeInterest")          or
        get("InterestAndDividendIncomeOperating")
    )

    net_financing_pretax = interest_expense - interest_income
    NE = net_financing_pretax * (1 - tax_rate)

    return {
        "interest_expense":     interest_expense,
        "interest_income":      interest_income,
        "net_financing_pretax": round(net_financing_pretax, 1),
        "NE":                   round(NE, 1),
        "tax_rate":             tax_rate,
    }


def calculate_leverage(ticker: str, r: float = 0.09) -> dict:
    """
    Calculate full leverage analysis for any ticker.

    Penman & Pope leverage decomposition:
        ROE  = RNOA + LEV x (RNOA - NBC)
        LEV  = ND / B          (book leverage)
        NBC  = NE / Avg ND     (net borrowing cost after tax)
        ML   = ND / Mkt Cap    (market leverage)

    Returns dict with all leverage metrics.
    """
    from data_fetch import get_cik, get_xbrl_facts
    from rnoa import get_noa_series, get_income_statement

    cik   = get_cik(ticker)
    facts = get_xbrl_facts(cik)

    noa_df = get_noa_series(facts, years=2)
    is_df  = get_income_statement(facts, years=2)

    latest_noa = noa_df.iloc[-1]
    prior_noa  = noa_df.iloc[-2] if len(noa_df) > 1 else noa_df.iloc[-1]
    latest_is  = is_df.iloc[-1]

    fy_end   = latest_noa["fiscal_year_end"]
    B        = latest_noa["B"]
    NOA      = latest_noa["NOA"]
    ND       = latest_noa["ND"]
    ND_prior = prior_noa["ND"]
    avg_ND   = (ND + ND_prior) / 2

    OI        = latest_is["operating_income_aftertax"]
    NOA_start = prior_noa["NOA"]
    RNOA      = OI / NOA_start if NOA_start != 0 else None
    tax_rate  = latest_is["effective_tax_rate"]
    net_income = latest_is["net_income"]

    nfe = get_net_financing_expense(facts, fy_end, tax_rate)
    NE  = nfe["NE"]

    NBC    = NE / avg_ND if avg_ND != 0 else None
    LEV    = ND / B      if B      != 0 else None
    spread = (RNOA - NBC) if (RNOA is not None and NBC is not None) else None

    ROE_decomp = (
        RNOA + LEV * spread
        if (RNOA is not None and LEV is not None and spread is not None)
        else None
    )
    ROE_actual = net_income / B if B != 0 else None

    import time
    mkt_cap = 0
    for attempt in range(3):
        try:
            stock   = yf.Ticker(ticker)
            fast    = stock.fast_info
            mkt_cap = (getattr(fast, "market_cap", None) or
                       stock.info.get("marketCap", 0)) / 1e6
            break
        except Exception:
            if attempt < 2:
                time.sleep(2 + attempt * 3)
    ML      = ND / mkt_cap if mkt_cap != 0 else None

    return {
        "ticker":           ticker.upper(),
        "fy_end":           fy_end,
        "NOA":              NOA,
        "ND":               ND,
        "B":                B,
        "avg_ND":           avg_ND,
        "OI":               OI,
        "NE":               NE,
        "RNOA":             round(RNOA,       4) if RNOA       is not None else None,
        "NBC":              round(NBC,        4) if NBC        is not None else None,
        "LEV":              round(LEV,        4) if LEV        is not None else None,
        "spread":           round(spread,     4) if spread     is not None else None,
        "ROE_decomp":       round(ROE_decomp, 4) if ROE_decomp is not None else None,
        "ROE_actual":       round(ROE_actual, 4) if ROE_actual is not None else None,
        "ML":               round(ML,         4) if ML         is not None else None,
        "mkt_cap":          mkt_cap,
        "tax_rate":         tax_rate,
        "interest_expense": nfe["interest_expense"],
        "interest_income":  nfe["interest_income"],
    }


def get_leverage_verdict(result: dict) -> str:
    """Return RAG verdict on leverage quality."""
    ND     = result["ND"]
    spread = result["spread"]

    if ND < 0:
        return "🔵 NET CASH — negative leverage, cash drag on ROE"
    if spread is None:
        return "⚪ INSUFFICIENT DATA"
    if spread > 0.05:
        return "🟢 LEVERAGE ADDS VALUE — spread strongly positive"
    if spread > 0:
        return "🟡 LEVERAGE MARGINALLY POSITIVE — spread thin"
    return "🔴 LEVERAGE DESTROYS VALUE — NBC > RNOA"


def print_leverage_report(ticker: str, r: float = 0.09) -> dict:
    """Print formatted leverage report for any ticker."""
    result  = calculate_leverage(ticker, r)
    verdict = get_leverage_verdict(result)

    print(f"  {'='*52}")
    print(f"  LEVERAGE ANALYSIS — {ticker.upper()}")
    print(f"  FY end: {result['fy_end']}")
    print(f"  {'='*52}")
    print()
    print(f"  Balance sheet:")
    print(f"    NOA:          ${result['NOA']:>10,.0f}m")
    print(f"    Net Debt:     ${result['ND']:>10,.0f}m")
    print(f"    Book Equity:  ${result['B']:>10,.0f}m")
    print()
    print(f"  Profitability vs cost of debt:")
    print(f"    RNOA:         {result['RNOA']:>9.1%}")
    print(f"    NBC:          {result['NBC']:>9.1%}")
    print(f"    Spread:       {result['spread']:>9.1%}"
          f"  ← {'positive ✅' if result['spread'] > 0 else 'negative ⚠️'}")
    print()
    print(f"  Leverage ratios:")
    print(f"    LEV (ND/B):   {result['LEV']:>9.2f}x")
    print(f"    ML  (ND/Mkt): {result['ML']:>9.2f}x")
    print()
    print(f"  ROE decomposition (Penman & Pope):")
    print(f"    RNOA:                    {result['RNOA']:>7.1%}")
    lev_spread = result['LEV'] * result['spread']
    print(f"    + LEV x Spread:          {lev_spread:>7.1%}")
    print(f"    = ROE (decomposed):      {result['ROE_decomp']:>7.1%}")
    print(f"    ROE (actual):            {result['ROE_actual']:>7.1%}")
    print()
    print(f"  Verdict: {verdict}")
    print()

    return result


def print_leverage_table(tickers: list, r: float = 0.09) -> None:
    """Print comparison leverage table for multiple tickers."""
    print(f"  {'='*72}")
    print(f"  LEVERAGE COMPARISON")
    print(f"  {'='*72}")
    print(f"  {'Ticker':<6} {'RNOA':>7} {'NBC':>7} {'Spread':>8} "
          f"{'LEV':>7} {'ML':>7} {'ROE':>7}  Verdict")
    print(f"  {'-'*70}")

    for ticker in tickers:
        try:
            r_val   = calculate_leverage(ticker, r)
            verdict = ("🔵" if r_val["ND"] < 0
                       else "🟢" if r_val["spread"] > 0.05
                       else "🟡" if r_val["spread"] > 0
                       else "🔴")
            print(f"  {ticker:<6} "
                  f"{r_val['RNOA']:>6.1%} "
                  f"{r_val['NBC']:>6.1%} "
                  f"{r_val['spread']:>7.1%} "
                  f"{r_val['LEV']:>6.2f}x "
                  f"{r_val['ML']:>6.2f}x "
                  f"{r_val['ROE_decomp']:>6.1%} "
                  f"  {verdict}")
        except Exception as e:
            print(f"  {ticker:<6} ERROR: {e}")


print("leverage.py loaded.")
print("Primary functions:")
print("  calculate_leverage(ticker, r)    — returns all metrics")
print("  print_leverage_report(ticker, r) — formatted report")
print("  print_leverage_table(tickers)    — comparison table")
