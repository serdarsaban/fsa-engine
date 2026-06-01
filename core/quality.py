import pandas as pd
import numpy as np


# ============================================================
# PENMAN & POPE — EARNINGS QUALITY MODULE
#
# Calculates accruals ratios, cash conversion metrics,
# and generates plain English interpretation of results.
#
# Primary function: print_quality_report(ticker)
# ============================================================


def get_cash_flows(facts: dict, fy_end: str) -> dict:
    """Fetch operating and investing cash flows."""
    from data_fetch import get_concept_value

    def get(concept):
        return get_concept_value(facts, concept, fy_end) or 0

    CFO   = get("NetCashProvidedByUsedInOperatingActivities")
    CFI   = get("NetCashProvidedByUsedInInvestingActivities")
    capex = get("PaymentsToAcquirePropertyPlantAndEquipment")
    FCF   = CFO - capex

    return {"CFO": CFO, "CFI": CFI, "capex": capex, "FCF": FCF}


def calculate_accruals(ticker: str, years: int = 4) -> pd.DataFrame:
    """
    Calculate accruals ratios for last N fiscal years.

    Method 1 — Balance sheet:
        Accruals_BS = ΔNOA / Average NOA

    Method 2 — Cash flow:
        Accruals_CF = (Net Income - CFO - CFI) / Average NOA

    Cash conversion:
        CFO / OI = fraction of operating income that became cash
    """
    from data_fetch import get_cik, get_xbrl_facts
    from rnoa import get_noa_series, get_income_statement

    cik   = get_cik(ticker)
    facts = get_xbrl_facts(cik)

    noa_df = get_noa_series(facts, years)
    is_df  = get_income_statement(facts, years)

    df = pd.merge(is_df, noa_df, on="fiscal_year_end", how="inner")
    df = df.sort_values("fiscal_year_end").reset_index(drop=True)
    df["NOA_start"] = df["NOA"].shift(1)
    df["NOA_avg"]   = (df["NOA"] + df["NOA_start"]) / 2

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row["NOA_start"]):
            continue

        fy      = row["fiscal_year_end"]
        NOA_avg = row["NOA_avg"]
        NI      = row["net_income"]
        OI      = row["operating_income_aftertax"]

        delta_NOA   = row["NOA"] - row["NOA_start"]
        accruals_bs = delta_NOA / NOA_avg if NOA_avg != 0 else None

        cf          = get_cash_flows(facts, fy)
        CFO, CFI    = cf["CFO"], cf["CFI"]
        capex, FCF  = cf["capex"], cf["FCF"]
        accruals_cf = (NI - CFO - CFI) / NOA_avg if NOA_avg != 0 else None
        cfo_to_oi   = CFO / OI if OI != 0 else None
        fcf_to_oi   = FCF / OI if OI != 0 else None

        rows.append({
            "fiscal_year_end": fy,
            "NOA_start":       row["NOA_start"],
            "NOA_end":         row["NOA"],
            "delta_NOA":       delta_NOA,
            "NOA_avg":         NOA_avg,
            "net_income":      NI,
            "OI_aftertax":     OI,
            "CFO":             CFO,
            "CFI":             CFI,
            "capex":           capex,
            "FCF":             FCF,
            "accruals_bs":     round(accruals_bs, 4) if accruals_bs is not None else None,
            "accruals_cf":     round(accruals_cf, 4) if accruals_cf is not None else None,
            "cfo_to_oi":       round(cfo_to_oi,  4) if cfo_to_oi  is not None else None,
            "fcf_to_oi":       round(fcf_to_oi,  4) if fcf_to_oi  is not None else None,
        })

    return pd.DataFrame(rows)


def get_quality_score(accruals_bs: float,
                       cfo_to_oi: float) -> tuple:
    """Score earnings quality on RAG basis. Returns (score, signal, flags)."""
    score = 0
    flags = []

    if accruals_bs is not None:
        if accruals_bs < 0.05:
            score += 2
            flags.append("✅ Very low accruals — earnings well backed by cash")
        elif accruals_bs < 0.10:
            score += 1
            flags.append("🟡 Moderate accruals — monitor trend")
        elif accruals_bs < 0.20:
            score += 0
            flags.append("🟡 Elevated accruals — some earnings quality risk")
        else:
            score -= 1
            flags.append("🔴 High accruals — earnings quality concern")

    if cfo_to_oi is not None:
        if cfo_to_oi > 1.0:
            score += 2
            flags.append("✅ CFO exceeds OI — strong cash conversion")
        elif cfo_to_oi > 0.75:
            score += 1
            flags.append("🟡 Good cash conversion")
        elif cfo_to_oi > 0.50:
            score += 0
            flags.append("🟡 Moderate cash conversion — watch trend")
        else:
            score -= 1
            flags.append("🔴 Weak cash conversion — accruals drag")

    if score >= 3:
        signal = "🟢 HIGH QUALITY"
    elif score >= 1:
        signal = "🟡 MODERATE QUALITY"
    else:
        signal = "🔴 LOW QUALITY"

    return score, signal, flags


def generate_commentary(ticker: str, df: pd.DataFrame) -> str:
    """
    Generate plain English interpretation of earnings quality metrics.

    Reads the pattern of accruals and cash conversion across years
    and writes a 3-4 sentence analyst-style commentary.
    """
    if df.empty:
        return "Insufficient data to generate commentary."

    latest      = df.iloc[-1]
    acc_bs      = latest["accruals_bs"]
    acc_cf      = latest["accruals_cf"]
    cfo_oi      = latest["cfo_to_oi"]
    fcf_oi      = latest["fcf_to_oi"]
    delta_noa   = latest["delta_noa"] if "delta_noa" in latest else latest.get("delta_NOA", 0)
    fy          = latest["fiscal_year_end"]

    # Trend analysis
    if len(df) >= 2:
        acc_trend   = acc_bs - df["accruals_bs"].iloc[0]
        cfo_trend   = cfo_oi - df["cfo_to_oi"].iloc[0]
        peak_acc    = df["accruals_bs"].max()
        peak_fy     = df.loc[df["accruals_bs"].idxmax(), "fiscal_year_end"]
    else:
        acc_trend   = 0
        cfo_trend   = 0
        peak_acc    = acc_bs
        peak_fy     = fy

    lines = []

    # ── SENTENCE 1: Overall accruals assessment ──────────────
    if acc_bs < 0:
        lines.append(
            f"{ticker} shows negative balance sheet accruals of "
            f"{acc_bs:.1%} in {fy}, meaning net operating assets are "
            f"actually contracting. This typically reflects asset-light "
            f"operations, aggressive buybacks reducing equity, or "
            f"working capital improvements — all positive quality signals."
        )
    elif acc_bs < 0.05:
        lines.append(
            f"{ticker} has very low accruals of {acc_bs:.1%} in {fy}, "
            f"indicating that reported earnings are tightly backed by "
            f"tangible changes in net operating assets. "
            f"This is a strong earnings quality signal."
        )
    elif acc_bs < 0.15:
        lines.append(
            f"{ticker} reports moderate accruals of {acc_bs:.1%} in {fy}. "
            f"This level is consistent with normal organic growth — "
            f"receivables, inventory, and fixed assets expanding in line "
            f"with the business. Not a concern unless the trend deteriorates."
        )
    elif peak_acc > 0.30 and peak_fy != fy:
        lines.append(
            f"{ticker} had a spike in accruals of {peak_acc:.1%} in "
            f"{peak_fy}, likely driven by a significant acquisition or "
            f"capital investment that inflated net operating assets. "
            f"Accruals have since moderated to {acc_bs:.1%}, suggesting "
            f"the one-time effect is fading."
        )
    else:
        lines.append(
            f"{ticker} shows elevated accruals of {acc_bs:.1%} in {fy}. "
            f"High accruals mean a significant portion of reported earnings "
            f"reflects accounting estimates rather than cash receipts. "
            f"This warrants closer examination of revenue recognition "
            f"and asset valuation policies."
        )

    # ── SENTENCE 2: Cash conversion ──────────────────────────
    if cfo_oi > 1.20:
        lines.append(
            f"Cash conversion is excellent: operating cash flow of "
            f"{cfo_oi:.2f}x operating income means the company is "
            f"collecting more cash than its accounting income suggests, "
            f"often due to favourable working capital dynamics or "
            f"non-cash charges that don't consume cash."
        )
    elif cfo_oi > 1.0:
        lines.append(
            f"Cash conversion is strong at {cfo_oi:.2f}x — operating cash "
            f"flow exceeds reported operating income, confirming that "
            f"earnings are fully backed by real cash generation."
        )
    elif cfo_oi > 0.75:
        lines.append(
            f"Cash conversion is good at {cfo_oi:.2f}x. The company "
            f"converts the majority of its operating income into cash, "
            f"though the gap between CFO and OI is worth monitoring "
            f"in future periods."
        )
    else:
        lines.append(
            f"Cash conversion is weak at {cfo_oi:.2f}x — operating cash "
            f"flow is significantly below reported operating income. "
            f"This gap often signals aggressive revenue recognition, "
            f"building receivables, or inventory accumulation that "
            f"has not yet converted to cash."
        )

    # ── SENTENCE 3: BS vs CF accruals comparison ─────────────
    gap = abs(acc_bs - acc_cf) if acc_cf is not None else None
    if gap is not None:
        if gap < 0.05:
            lines.append(
                f"Both accruals methods are consistent (BS: {acc_bs:.1%}, "
                f"CF: {acc_cf:.1%}), which increases confidence in the "
                f"quality assessment."
            )
        elif acc_bs > acc_cf:
            lines.append(
                f"The balance sheet method shows higher accruals "
                f"({acc_bs:.1%}) than the cash flow method ({acc_cf:.1%}). "
                f"The gap is often explained by investing cash outflows "
                f"(acquisitions, capex) that inflate BS accruals but "
                f"are captured differently in the CF method."
            )
        else:
            lines.append(
                f"The cash flow accruals ({acc_cf:.1%}) exceed the balance "
                f"sheet measure ({acc_bs:.1%}), which can indicate "
                f"off-balance-sheet activity or timing differences "
                f"between income recognition and asset changes."
            )

    # ── SENTENCE 4: Trend ────────────────────────────────────
    if len(df) >= 2:
        if acc_trend < -0.05 and cfo_trend > 0:
            lines.append(
                f"The trend is positive: accruals have fallen "
                f"{abs(acc_trend):.1%} and cash conversion has improved "
                f"{cfo_trend:.2f}x over the analysis period, suggesting "
                f"earnings quality is strengthening."
            )
        elif acc_trend > 0.05 and cfo_trend < 0:
            lines.append(
                f"The trend is concerning: accruals have risen "
                f"{acc_trend:.1%} and cash conversion has declined "
                f"{abs(cfo_trend):.2f}x, suggesting earnings quality "
                f"is deteriorating and warrants monitoring."
            )
        elif acc_trend < -0.05:
            lines.append(
                f"Accruals have declined {abs(acc_trend):.1%} over the "
                f"period, a positive trend indicating improving "
                f"earnings quality."
            )
        elif cfo_trend < -0.10:
            lines.append(
                f"Cash conversion has declined {abs(cfo_trend):.2f}x over "
                f"the period. While still adequate, this declining trend "
                f"should be monitored in future filings."
            )

    return " ".join(lines)


def print_quality_report(ticker: str, years: int = 4) -> dict:
    """Print formatted earnings quality report with commentary."""
    df = calculate_accruals(ticker, years=years)

    print(f"  {'='*58}")
    print(f"  EARNINGS QUALITY — {ticker.upper()}")
    print(f"  {'='*58}")
    print()
    print(f"  {'FY End':<14} {'Accruals BS':>12} "
          f"{'Accruals CF':>12} {'CFO/OI':>8} {'FCF/OI':>8}")
    print(f"  {'-'*58}")

    for _, row in df.iterrows():
        acc_flag = " ⚠️" if row["accruals_bs"] > 0.15 else ""
        cfo_flag = " ⚠️" if row["cfo_to_oi"]  < 0.75 else ""
        print(f"  {row['fiscal_year_end']:<14} "
              f"{row['accruals_bs']:>11.1%}{acc_flag:<3} "
              f"{row['accruals_cf']:>11.1%} "
              f"{row['cfo_to_oi']:>7.2f}x{cfo_flag:<3} "
              f"{row['fcf_to_oi']:>7.2f}x")

    print()

    latest            = df.iloc[-1]
    score, signal, flags = get_quality_score(
        latest["accruals_bs"], latest["cfo_to_oi"]
    )

    print(f"  Signals:")
    for flag in flags:
        print(f"    {flag}")
    print()
    print(f"  Overall: {signal}  (score: {score}/4)")
    print()

    # Trend
    if len(df) >= 2:
        acc_trend = df["accruals_bs"].iloc[-1] - df["accruals_bs"].iloc[0]
        cfo_trend = df["cfo_to_oi"].iloc[-1]   - df["cfo_to_oi"].iloc[0]
        print(f"  Trend ({df['fiscal_year_end'].iloc[0]} → "
              f"{df['fiscal_year_end'].iloc[-1]}):")
        print(f"    Accruals: {acc_trend:+.1%}  "
              f"{'⚠️ deteriorating' if acc_trend > 0.05 else '✅ stable/improving'}")
        print(f"    CFO/OI:   {cfo_trend:+.2f}x  "
              f"{'✅ improving' if cfo_trend > 0 else '⚠️ declining'}")
    print()

    # Plain English commentary
    commentary = generate_commentary(ticker, df)
    print(f"  Commentary:")
    # Word-wrap at 65 chars
    words  = commentary.split()
    line   = "    "
    for word in words:
        if len(line) + len(word) + 1 > 68:
            print(line)
            line = "    " + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)
    print()

    return {
        "ticker":       ticker.upper(),
        "score":        score,
        "signal":       signal,
        "commentary":   commentary,
        "accruals_avg": round(df["accruals_bs"].mean(), 4),
        "cfo_oi_avg":   round(df["cfo_to_oi"].mean(),  4),
        "latest":       latest.to_dict(),
    }


def print_quality_table(tickers: list, years: int = 4) -> None:
    """Print comparison quality table for multiple tickers."""
    print(f"  {'='*65}")
    print(f"  EARNINGS QUALITY COMPARISON")
    print(f"  {'='*65}")
    print(f"  {'Ticker':<6} {'Acc BS':>8} {'Acc CF':>8} "
          f"{'CFO/OI':>8} {'FCF/OI':>8} {'Score':>6}  Signal")
    print(f"  {'-'*63}")

    for ticker in tickers:
        try:
            df     = calculate_accruals(ticker, years=years)
            latest = df.iloc[-1]
            score, signal, _ = get_quality_score(
                latest["accruals_bs"], latest["cfo_to_oi"]
            )
            icon = signal.split()[0]
            print(f"  {ticker:<6} "
                  f"{latest['accruals_bs']:>7.1%} "
                  f"{latest['accruals_cf']:>7.1%} "
                  f"{latest['cfo_to_oi']:>7.2f}x "
                  f"{latest['fcf_to_oi']:>7.2f}x "
                  f"{score:>5}/4 "
                  f"  {icon}")
        except Exception as e:
            print(f"  {ticker:<6} ERROR: {e}")


print("quality.py loaded.")
print("Primary functions:")
print("  calculate_accruals(ticker, years)  — returns DataFrame")
print("  print_quality_report(ticker)       — report + commentary")
print("  print_quality_table(tickers)       — comparison table")
print("  generate_commentary(ticker, df)    — plain English analysis")
