import pandas as pd
import numpy as np
import yfinance as yf


# ============================================================
# PENMAN & POPE — VALUATION MODULE
#
# Implements residual earnings valuation model.
#
# Key insight: implied g* must always be compared against
# historical ReOI growth to assess whether the market is
# pricing in acceleration or deceleration.
#
# Primary function: run_valuation(ticker, r)
# ============================================================


def get_market_data(ticker: str) -> dict:
    """Fetch current market cap and price from yfinance with retry."""
    import time
    last_err = None
    for attempt in range(3):
        try:
            stock = yf.Ticker(ticker)
            info  = stock.fast_info
            price      = getattr(info, "last_price", None)
            market_cap = getattr(info, "market_cap", None)
            shares     = getattr(info, "shares", None)
            if price is None:
                full_info  = stock.info
                price      = full_info.get("currentPrice") or full_info.get("regularMarketPrice")
                market_cap = full_info.get("marketCap")
                shares     = full_info.get("sharesOutstanding")
            return {
                "ticker":       ticker.upper(),
                "price":        price,
                "market_cap_m": market_cap / 1e6 if market_cap else None,
                "shares_m":     shares     / 1e6 if shares     else None,
            }
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 + attempt * 3)
    raise last_err


def implied_growth_rate(
    B0: float, NOA0: float, OI1: float,
    P0: float, r: float,
) -> float:
    """
    Reverse-engineer market-implied perpetual growth rate g*.

    Formula (Penman & Pope):
        g* = r - (OI1 - r x NOA0) / (P0 - B0)
    """
    if P0 == B0:
        return None
    ReOI1  = OI1 - r * NOA0
    g_star = r - ReOI1 / (P0 - B0)
    return round(g_star, 4)


def intrinsic_value(
    B0: float, NOA0: float, OI1: float,
    r: float, g: float,
) -> float:
    """
    Residual earnings valuation model.

    Formula (Penman & Pope):
        V0 = B0 + (OI1 - r x NOA0) / (r - g)
    """
    if r == g:
        return None
    ReOI1 = OI1 - r * NOA0
    V0    = B0 + ReOI1 / (r - g)
    return round(V0, 1)


def valuation_scenarios(
    B0: float, NOA0: float, OI1: float, r: float,
    g_bear: float = 0.00,
    g_base: float = 0.03,
    g_bull: float = 0.06,
) -> dict:
    """Run bear / base / bull valuation scenarios."""
    return {
        "bear":   intrinsic_value(B0, NOA0, OI1, r, g_bear),
        "base":   intrinsic_value(B0, NOA0, OI1, r, g_base),
        "bull":   intrinsic_value(B0, NOA0, OI1, r, g_bull),
        "g_bear": g_bear,
        "g_base": g_base,
        "g_bull": g_bull,
    }


def calculate_historical_reoi_growth(
    ticker: str,
    r:      float = 0.09,
    years:  int   = 4,
) -> dict:
    """
    Calculate historical ReOI growth rate over last N years.

    This is the critical benchmark for evaluating implied g*.

    Key comparison:
        g* > historical growth → market betting on acceleration
        g* < historical growth → market being conservative
        Gap = g* - historical CAGR → magnitude of market bet
    """
    from data_fetch import get_cik, get_xbrl_facts
    from rnoa import get_noa_series, get_income_statement

    cik   = get_cik(ticker)
    facts = get_xbrl_facts(cik)

    noa_df = get_noa_series(facts, years=years)
    is_df  = get_income_statement(facts, years=years)

    df = pd.merge(is_df, noa_df, on="fiscal_year_end", how="inner")
    df = df.sort_values("fiscal_year_end").reset_index(drop=True)
    df["NOA_start"] = df["NOA"].shift(1)

    reoi_series = []
    for _, row in df.iterrows():
        if pd.isna(row["NOA_start"]) or row["NOA_start"] == 0:
            continue
        OI   = row["operating_income_aftertax"]
        ReOI = OI - r * row["NOA_start"]
        reoi_series.append({
            "fiscal_year_end": row["fiscal_year_end"],
            "OI":              OI,
            "NOA_start":       row["NOA_start"],
            "ReOI":            round(ReOI, 1),
        })

    if len(reoi_series) < 2:
        return None

    reoi_values = [x["ReOI"] for x in reoi_series]
    first_reoi  = reoi_values[0]
    latest_reoi = reoi_values[-1]
    n_years     = len(reoi_values) - 1

    cagr = (
        (latest_reoi / first_reoi) ** (1 / n_years) - 1
        if first_reoi > 0 and latest_reoi > 0
        else None
    )

    yoy_rates = [
        (reoi_values[i] - reoi_values[i-1]) / reoi_values[i-1]
        for i in range(1, len(reoi_values))
        if reoi_values[i-1] > 0
    ]
    avg_growth = np.mean(yoy_rates) if yoy_rates else None

    return {
        "reoi_series": reoi_series,
        "cagr":        round(cagr,       4) if cagr       else None,
        "avg_growth":  round(avg_growth, 4) if avg_growth else None,
        "latest_reoi": latest_reoi,
        "first_reoi":  first_reoi,
        "n_years":     n_years,
    }


def get_valuation_signal(
    g_star: float,
    r:      float,
    hist_cagr: float = None,
) -> str:
    """
    Return signal based on implied g* vs required return
    AND vs historical ReOI growth.

    This is the market challenge from Penman & Pope:
    Is the market pricing in more or less than history delivered?
    """
    if g_star is None:
        return "⚪ INSUFFICIENT DATA"

    # Primary signal: g* vs required return
    if g_star < 0:
        primary = "🔴 EXPENSIVE — pricing value destruction"
    elif g_star < r * 0.5:
        primary = "🟢 ATTRACTIVE — low growth hurdle"
    elif g_star < r:
        primary = "🟡 FAIR — moderate growth required"
    else:
        primary = "🔴 EXPENSIVE — implausible growth required"

    # Secondary signal: g* vs history
    if hist_cagr is not None:
        gap = g_star - hist_cagr
        if gap > 0.03:
            secondary = f"⚠️  Market pricing {gap:.1%} ABOVE historical growth"
        elif gap < -0.03:
            secondary = f"✅  Market pricing {abs(gap):.1%} BELOW historical growth"
        else:
            secondary = f"➡️  Market pricing in line with historical growth"
        return f"{primary}\n  {secondary}"

    return primary


def run_valuation(
    ticker:  str,
    r:       float = 0.09,
    g_bear:  float = 0.00,
    g_base:  float = 0.03,
    g_bull:  float = 0.06,
    years:   int   = 4,
    verbose: bool  = True,
) -> dict:
    """
    Full valuation pipeline for any ticker.

    Inputs:
        ticker  — stock ticker (e.g. "AAPL")
        r       — required return (default 9%)
        g_bear  — bear case growth (default 0%)
        g_base  — base case growth (default 3%)
        g_bull  — bull case growth (default 6%)
        years   — years of history for ReOI growth (default 4)
        verbose — print report (default True)

    Returns dict with all valuation metrics including
    historical ReOI growth for market challenge comparison.
    """
    from data_fetch import get_cik, get_xbrl_facts
    from rnoa import get_noa_series, get_income_statement

    cik   = get_cik(ticker)
    facts = get_xbrl_facts(cik)

    noa_df = get_noa_series(facts, years=2)
    is_df  = get_income_statement(facts, years=2)

    latest_noa = noa_df.iloc[-1]
    latest_is  = is_df.iloc[-1]

    B0   = latest_noa["B"]
    NOA0 = latest_noa["NOA"]
    OI1  = latest_is["operating_income_aftertax"]
    fy   = latest_noa["fiscal_year_end"]

    mkt = get_market_data(ticker)
    P0  = mkt["market_cap_m"]

    g_star    = implied_growth_rate(B0=B0, NOA0=NOA0, OI1=OI1, P0=P0, r=r)
    scenarios = valuation_scenarios(
        B0=B0, NOA0=NOA0, OI1=OI1, r=r,
        g_bear=g_bear, g_base=g_base, g_bull=g_bull,
    )

    # Historical ReOI growth — the market challenge
    hist = calculate_historical_reoi_growth(ticker, r=r, years=5)
    hist_cagr = hist["cagr"] if hist else None

    base_val = scenarios["base"]
    premium  = (P0 / base_val - 1) if base_val else None
    signal   = get_valuation_signal(g_star, r, hist_cagr)

    result = {
        "ticker":       ticker.upper(),
        "fy_end":       fy,
        "B0":           B0,
        "NOA0":         NOA0,
        "OI1":          OI1,
        "P0":           P0,
        "price":        mkt["price"],
        "shares_m":     mkt["shares_m"],
        "r":            r,
        "g_star":       g_star,
        "v_bear":       scenarios["bear"],
        "v_base":       scenarios["base"],
        "v_bull":       scenarios["bull"],
        "g_bear":       g_bear,
        "g_base":       g_base,
        "g_bull":       g_bull,
        "premium":      premium,
        "hist_cagr":    hist_cagr,
        "hist_n_years": hist["n_years"] if hist else None,
        "signal":       signal,
        "reoi_series":  hist["reoi_series"] if hist else None,
    }

    if verbose:
        print(f"  {'='*50}")
        print(f"  VALUATION — {ticker.upper()}")
        print(f"  FY end: {fy}  |  Required return: {r:.0%}")
        print(f"  {'='*50}")
        print(f"  Book value (B0):    ${B0:>10,.0f}m")
        print(f"  NOA0:               ${NOA0:>10,.0f}m")
        print(f"  OI1 (trailing):     ${OI1:>10,.0f}m")
        print(f"  Market cap (P0):    ${P0:>10,.0f}m")
        print()
        print(f"  Implied g*:         {g_star:.1%}")
        if hist_cagr:
            gap = g_star - hist_cagr
            print(f"  Historical CAGR:    {hist_cagr:.1%}"
                  f"  ({hist['n_years']} years)")
            print(f"  Gap (g* - hist):    {gap:+.1%}"
                  f"  ← {"market needs MORE" if gap > 0 else "market needs LESS"}"
                  f" than history")
        print()
        print(f"  Scenario analysis:")
        print(f"  Bear  (g={g_bear:.0%}):  ${scenarios['bear']:>10,.0f}m")
        print(f"  Base  (g={g_base:.0%}):  ${scenarios['base']:>10,.0f}m")
        print(f"  Bull  (g={g_bull:.0%}):  ${scenarios['bull']:>10,.0f}m")
        print()
        print(f"  Market cap:  ${P0:>10,.0f}m")
        print(f"  vs Base:     "
              f"{"PREMIUM" if premium > 0 else "DISCOUNT"} "
              f"{abs(premium):.0%}")
        print()
        for line in signal.split("\n"):
            print(f"  {line}")
        print()

    return result


def print_valuation_table(
    tickers: list,
    r:       float = 0.09,
) -> None:
    """Print a comparison valuation table for multiple tickers."""
    print(f"  {'='*78}")
    print(f"  VALUATION COMPARISON  |  Required return: {r:.0%}")
    print(f"  {'='*78}")
    print(f"  {'Ticker':<6} {'g*':>6} {'Hist CAGR':>10} "
          f"{'Gap':>7} {'Base Val':>12} {'Mkt Cap':>12}  Signal")
    print(f"  {'-'*76}")

    for ticker in tickers:
        try:
            v = run_valuation(ticker, r=r, verbose=False)
            gap = (v["g_star"] - v["hist_cagr"]
                   if v["hist_cagr"] else None)
            signal_icon = (
                "🔴" if v["g_star"] >= r
                else "🟡" if v["g_star"] >= r * 0.5
                else "🟢"
            )
            hist_str = (f"{v['hist_cagr']:.1%}"
                        if v["hist_cagr"] else "N/A")
            gap_str  = (f"{gap:+.1%}" if gap else "N/A")
            print(f"  {ticker:<6} "
                  f"{v['g_star']:>5.1%} "
                  f"{hist_str:>10} "
                  f"{gap_str:>7} "
                  f"${v['v_base']:>10,.0f}m "
                  f"${v['P0']:>10,.0f}m "
                  f"  {signal_icon}")
        except Exception as e:
            print(f"  {ticker:<6} ERROR: {e}")


print("valuation.py loaded.")
print("Primary functions:")
print("  run_valuation(ticker, r)          — full valuation + market challenge")
print("  print_valuation_table(tickers)    — comparison table")
print("  implied_growth_rate(...)          — g* formula")
print("  intrinsic_value(...)              — V0 formula")
print("  calculate_historical_reoi_growth()— historical benchmark")
