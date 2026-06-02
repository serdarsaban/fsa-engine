import pandas as pd
import numpy as np
import yfinance as yf


# ============================================================
# PENMAN & POPE — CH 8 RISK MODULE
#
# Implements Chapter 8 risk-to-value diagnostic:
#   No-growth value    = B0 + ReOI1 / r
#   Speculative value  = Market Price - No-growth value
#   Value-at-risk table (g = -4% to +8%)
#   Expected return    = B/P × ROE + (1 - B/P) × g
#   Safe equity scorecard (5 criteria)
#
# Primary function: run_risk_diagnostic(ticker, r)
# ============================================================


def run_risk_diagnostic(ticker: str, r: float = 0.09) -> dict:
    """
    Run Chapter 8 risk diagnostic for any ticker.

    Returns dict with all metrics and html key.
    """
    from data_fetch   import get_cik, get_xbrl_facts
    from rnoa         import (get_noa_series, get_income_statement,
                               get_fiscal_year_dates)
    from valuation    import implied_growth_rate, intrinsic_value

    cik      = get_cik(ticker)
    facts    = get_xbrl_facts(cik)
    fy_dates = get_fiscal_year_dates(facts, years=2)
    fy_end   = fy_dates[-1]

    noa_df     = get_noa_series(facts, years=2)
    is_df      = get_income_statement(facts, years=2)
    latest_noa = noa_df.iloc[-1]
    latest_is  = is_df.iloc[-1]

    B0   = latest_noa["B"]
    NOA0 = latest_noa["NOA"]
    ND0  = latest_noa["ND"]
    OI1  = latest_is["operating_income_aftertax"]

    import time
    P0 = 0
    price = None
    for attempt in range(3):
        try:
            stock = yf.Ticker(ticker)
            fast  = stock.fast_info
            P0    = (getattr(fast, "market_cap", None) or 0) / 1e6
            price = getattr(fast, "last_price", None)
            if not P0:
                info  = stock.info
                P0    = (info.get("marketCap") or 0) / 1e6
                price = info.get("currentPrice") or info.get("regularMarketPrice")
            break
        except Exception:
            if attempt < 2:
                time.sleep(2 + attempt * 3)

    ReOI1           = OI1 - r * NOA0
    no_growth_value = B0 + ReOI1 / r if r != 0 else None
    spec_value      = P0 - no_growth_value if no_growth_value else None
    spec_pct        = spec_value / P0      if (spec_value and P0) else None
    ngv_pct         = no_growth_value / P0 if (no_growth_value and P0) else None
    g_star          = implied_growth_rate(
        B0=B0, NOA0=NOA0, OI1=OI1, P0=P0, r=r
    )
    pb_ratio = P0 / B0 if B0 != 0 else None
    lev      = ND0 / B0 if B0 != 0 else None
    ROE      = (latest_is["net_income"] / B0
                if (latest_is["net_income"] and B0) else None)
    bp       = B0 / P0 if P0 != 0 else None

    # Value-at-risk table
    growth_scenarios = [-0.04,-0.03,-0.02,-0.01, 0.00,
                         0.01, 0.02, 0.03, 0.04, 0.05,
                         0.06, 0.07, 0.08]
    var_table = []
    for g in growth_scenarios:
        if g >= r:
            continue
        V = intrinsic_value(B0=B0, NOA0=NOA0, OI1=OI1, r=r, g=g)
        var_table.append({
            "growth_rate":    g,
            "value":          V,
            "value_vs_price": V / P0 if (V and P0) else None,
        })

    # Expected return
    expected_returns = []
    for g in [0.00, 0.02, 0.03, 0.04, 0.05, 0.06]:
        if bp and ROE:
            er = bp * ROE + (1 - bp) * g
            expected_returns.append({
                "growth_assumed":  g,
                "expected_return": round(er, 4),
            })

    # Safe equity scorecard
    safe_criteria = [
        {
            "criterion": "P/B < 3x — anchored in book value",
            "value":     f"{pb_ratio:.1f}x" if pb_ratio else "N/A",
            "pass":      pb_ratio is not None and pb_ratio < 3.0,
            "explain":   "Low P/B means most of the price is book value, not speculative growth.",
        },
        {
            "criterion": "g* < 4% — modest growth required",
            "value":     f"{g_star:.1%}" if g_star is not None else "N/A",
            "pass":      g_star is not None and g_star < 0.04,
            "explain":   "Low g* means the company needs little growth to justify its price.",
        },
        {
            "criterion": "No-growth value ≥ 60% of price",
            "value":     f"{ngv_pct:.0%}" if ngv_pct else "N/A",
            "pass":      ngv_pct is not None and ngv_pct >= 0.60,
            "explain":   "High ratio means existing earnings power justifies most of the price.",
        },
        {
            "criterion": "Speculative value < 40% of price",
            "value":     f"{spec_pct:.0%}" if spec_pct is not None else "N/A",
            "pass":      spec_pct is not None and spec_pct < 0.40,
            "explain":   "Low speculative value means less reliance on uncertain future growth.",
        },
        {
            "criterion": "LEV < 2x — moderate leverage",
            "value":     f"{lev:.2f}x" if lev is not None else "N/A",
            "pass":      lev is not None and lev < 2.0,
            "explain":   "Low leverage reduces tail risk and bankruptcy probability.",
        },
    ]

    safe_score = sum(1 for c in safe_criteria if c["pass"])
    if safe_score >= 4:
        safe_signal = "🟢 SAFE EQUITY"
        safe_color  = "#27ae60"
    elif safe_score >= 2:
        safe_signal = "🟡 MODERATE RISK"
        safe_color  = "#f39c12"
    else:
        safe_signal = "🔴 RISKY EQUITY"
        safe_color  = "#e74c3c"

    result = {
        "ticker":           ticker.upper(),
        "fy_end":           fy_end,
        "B0":               B0,
        "NOA0":             NOA0,
        "OI1":              OI1,
        "ReOI1":            ReOI1,
        "P0":               P0,
        "price":            price,
        "r":                r,
        "g_star":           g_star,
        "pb_ratio":         pb_ratio,
        "no_growth_value":  no_growth_value,
        "spec_value":       spec_value,
        "spec_pct":         spec_pct,
        "ngv_pct":          ngv_pct,
        "var_table":        var_table,
        "expected_returns": expected_returns,
        "safe_criteria":    safe_criteria,
        "safe_score":       safe_score,
        "safe_signal":      safe_signal,
        "safe_color":       safe_color,
        "lev":              lev,
        "ROE":              ROE,
        "bp":               bp,
    }

    result["html"] = _render_html(result)
    return result


def _fmt_m(v):
    if v is None: return "—"
    if abs(v) >= 1000000: return f"${v/1000000:.1f}tn"
    if abs(v) >= 1000:    return f"${v/1000:.1f}bn"
    return f"${v:.0f}m"

def _fmt_pct(v):
    return f"{v:.1%}" if v is not None else "—"


def generate_risk_commentary(R: dict) -> str:
    """
    Generate plain English commentary on the risk profile.
    Reads the key metrics and writes a 3-4 sentence analysis.
    """
    ticker    = R["ticker"]
    ngv_pct   = R["ngv_pct"]
    spec_pct  = R["spec_pct"]
    g_star    = R["g_star"]
    r         = R["r"]
    pb        = R["pb_ratio"]
    safe_score= R["safe_score"]
    lev       = R["lev"]

    lines = []

    # Sentence 1: Overall risk characterisation
    if ngv_pct and ngv_pct >= 0.60:
        lines.append(
            "{} is well anchored in existing earnings power — {:.0%} of the "
            "market cap is justified by no-growth fundamentals alone. "
            "This provides meaningful downside protection even if growth "
            "disappoints.".format(ticker, ngv_pct)
        )
    elif ngv_pct and ngv_pct >= 0.30:
        lines.append(
            "{:.0%} of {}'s market cap is anchored in no-growth value, "
            "with {:.0%} depending on future growth. "
            "The stock has moderate risk — not purely speculative but "
            "requiring above-average growth to justify the full price.".format(
                ngv_pct, ticker, spec_pct or 0)
        )
    else:
        lines.append(
            "Only {:.0%} of {}'s market cap is anchored in existing earnings "
            "power — {:.0%} is speculative value depending on future growth. "
            "This is a high-duration asset: small changes in long-term growth "
            "expectations translate into large price swings.".format(
                ngv_pct or 0, ticker, spec_pct or 0)
        )

    # Sentence 2: g* assessment
    if g_star is not None:
        if g_star < 0.03:
            lines.append(
                "The implied growth rate of {:.1%} is very modest — "
                "the market expects little more than inflation-level growth "
                "in residual earnings, making this a low-hurdle investment "
                "from a valuation standpoint.".format(g_star)
            )
        elif g_star < r:
            lines.append(
                "The implied growth rate of {:.1%} is below the required "
                "return of {:.0%}, meaning the stock does not need "
                "supernormal growth to justify its price — but does require "
                "sustained above-GDP growth.".format(g_star, r)
            )
        else:
            lines.append(
                "The implied growth rate of {:.1%} equals or exceeds the "
                "required return of {:.0%}. This is a demanding hurdle — "
                "the market is pricing in perpetual supernormal growth, "
                "which very few companies sustain long-term.".format(
                    g_star, r)
            )

    # Sentence 3: Leverage risk
    if lev is not None:
        if lev < 0:
            lines.append(
                "With a net cash position (LEV = {:.2f}x), {} faces "
                "minimal financial distress risk. "
                "The balance sheet provides an additional margin of "
                "safety beyond the operating business.".format(lev, ticker)
            )
        elif lev < 1.0:
            lines.append(
                "Leverage of {:.2f}x book equity is conservative, "
                "limiting financial distress risk even in a severe "
                "earnings downturn.".format(lev)
            )
        elif lev < 2.0:
            lines.append(
                "Leverage of {:.2f}x is moderate. "
                "The debt load is manageable under base case earnings "
                "but bears monitoring in a stress scenario.".format(lev)
            )
        else:
            lines.append(
                "Leverage of {:.2f}x is elevated, adding meaningful "
                "tail risk. A significant earnings shortfall could "
                "impair debt service capacity and amplify downside "
                "scenarios materially.".format(lev)
            )

    # Sentence 4: Safe equity verdict
    if safe_score >= 4:
        lines.append(
            "On balance, {} meets most safe equity criteria — "
            "it is conservatively priced relative to fundamentals "
            "with low growth dependence and manageable leverage.".format(ticker)
        )
    elif safe_score >= 2:
        lines.append(
            "The stock meets some but not all safe equity criteria. "
            "It sits in a middle ground — not highly speculative but "
            "not a defensive anchor either. "
            "Suitable for investors comfortable with moderate growth risk."
        )
    else:
        lines.append(
            "Few safe equity criteria are met. "
            "The stock is priced for significant future growth and "
            "carries meaningful fundamental risk. "
            "Investors should be confident in the long-term growth "
            "thesis before paying today's price."
        )

    return " ".join(lines)


def _render_html(R: dict) -> str:
    """Render Ch 8 risk diagnostic as HTML section."""
    rows = []
    a = rows.append

    r = R["r"]

    a('<div style="font-family:-apple-system,sans-serif;color:#2c3e50;font-size:14px">')
    a('<p style="color:#888;font-size:12px;margin-bottom:12px">')
    a("Chapter 8 - Risk to value: how much of today's price depends on uncertain future growth, ")
    a('and what return can you expect under different growth scenarios.</p>')

    # ── Key metrics ───────────────────────────────────────────
    a('<p style="font-weight:600;margin:0 0 8px">Risk Anchor Metrics</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
    a('No-growth value = B + ReOI/r assumes zero perpetual growth. ')
    a('Speculative value = market price minus no-growth value — this is what you pay for growth. ')
    a('The higher the speculative %, the more the stock depends on uncertain future earnings.</p>')

    a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<tbody>')
    metrics = [
        ("Book value (B₀)",            _fmt_m(R["B0"]),
         "Anchor for valuation"),
        ("NOA₀",                        _fmt_m(R["NOA0"]),
         "Net operating assets"),
        ("ReOI₁ (forward)",             _fmt_m(R["ReOI1"]),
         "OI₁ − r × NOA₀"),
        ("No-growth value",             _fmt_m(R["no_growth_value"]),
         "B₀ + ReOI₁ / r  (g = 0 forever)"),
        ("Market cap",                  _fmt_m(R["P0"]),
         "Current market price"),
        ("No-growth value / Price",     _fmt_pct(R["ngv_pct"]),
         "≥60% = well anchored  ✅  <30% = highly speculative 🔴"),
        ("Speculative value",           _fmt_m(R["spec_value"]),
         "Market cap minus no-growth value"),
        ("Speculative value / Price",   _fmt_pct(R["spec_pct"]),
         "<40% = low risk  ✅  >70% = high growth dependence 🔴"),
        ("Implied g*",                  _fmt_pct(R["g_star"]),
         "Growth rate market is pricing in"),
        ("P/B ratio",                   f"{R['pb_ratio']:.1f}x" if R["pb_ratio"] else "—",
         "<3x = anchored  ✅  >10x = highly speculative 🔴"),
    ]
    for label, value, note in metrics:
        # Colour the value based on the note
        if "✅" in note and "🔴" in note:
            if "≥60%" in note:
                color = "#27ae60" if R["ngv_pct"] and R["ngv_pct"] >= 0.60 else "#e74c3c"
            elif "<40%" in note:
                color = "#27ae60" if R["spec_pct"] is not None and R["spec_pct"] < 0.40 else "#e74c3c"
            elif "<3x" in note:
                color = "#27ae60" if R["pb_ratio"] and R["pb_ratio"] < 3 else "#e74c3c"
            else:
                color = "#2c3e50"
        else:
            color = "#2c3e50"
        a(f'<tr>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#666;width:35%">{label}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;font-weight:600;color:{color};width:20%">{value}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#888;font-size:12px">{note}</td>')
        a('</tr>')
    a('</tbody></table>')

    # ── Value-at-risk table ───────────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 4px">Value-at-Risk Table</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
    a("V(g) = B0 + ReOI1 / (r - g). Each row shows what the company is worth ")
    a("under a different perpetual growth assumption. ")
    a("Value/Price shows how much of today's market cap is justified. ")
    a(f"Required return used: {r:.0%}.</p>")

    a('<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<thead><tr>')
    for h in ["Growth Rate (g)", "Intrinsic Value", "Value / Price", "Signal"]:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;text-align:right;font-weight:500;font-size:12px;color:#555">{h}</th>')
    a('</tr></thead><tbody>')

    for row in R["var_table"]:
        g   = row["growth_rate"]
        V   = row["value"]
        vp  = row["value_vs_price"]

        if vp and vp >= 1.0:
            signal = "✅ Above market"
            color  = "#27ae60"
        elif vp and vp >= 0.70:
            signal = "🟡 Close to market"
            color  = "#f39c12"
        else:
            signal = "🔴 Below market"
            color  = "#e74c3c"

        # Highlight the g=0 row
        bg = "background:#fff8e8;" if g == 0.00 else ""
        a(f'<tr style="{bg}">')
        gstr = f"{g:.0%}"
        if g == 0.00:
            gstr = "0% (no-growth baseline)"
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#666">{gstr}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600">{_fmt_m(V)}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600;color:{color}">{_fmt_pct(vp)}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:{color}">{signal}</td>')
        a('</tr>')
    a('</tbody></table></div>')

    # ── Expected return table ─────────────────────────────────
    if R["expected_returns"]:
        a('<p style="font-weight:600;margin:14px 0 4px">Expected Return Profile</p>')
        a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
        a("E(r) = B/P x ROE + (1 - B/P) x g. ")
        a("Shows what return to expect at each assumed growth rate. ")
        a("Higher assumed growth means higher expected return, but higher risk.</p>")

        a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
        a('<thead><tr>')
        for h in ["Growth Assumed", "Expected Return", "vs Required Return"]:
            a(f'<th style="background:#f0f2f5;padding:8px 10px;text-align:right;font-weight:500;font-size:12px;color:#555">{h}</th>')
        a('</tr></thead><tbody>')
        for er_row in R["expected_returns"]:
            g  = er_row["growth_assumed"]
            er = er_row["expected_return"]
            vs_r = er - r
            color = "#27ae60" if vs_r >= 0.02 else "#f39c12" if vs_r >= 0 else "#e74c3c"
            a('<tr>')
            a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#666">{g:.0%}</td>')
            a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600;color:{color}">{er:.1%}</td>')
            a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:{color}">{vs_r:+.1%}</td>')
            a('</tr>')
        a('</tbody></table>')

    # ── Safe equity scorecard ─────────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 4px">Safe Equity Scorecard</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
    a("Penman and Pope define safe equities as stocks with low fundamental risk - ")
    a("anchored in book value, requiring modest growth, with conservative leverage.</p>")

    a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px">')
    a('<thead><tr>')
    for h in ["Criterion", "Value", "Pass", "Why it matters"]:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;text-align:left;font-weight:500;font-size:12px;color:#555">{h}</th>')
    a('</tr></thead><tbody>')
    for c in R["safe_criteria"]:
        icon  = "✅" if c["pass"] else "❌"
        color = "#27ae60" if c["pass"] else "#e74c3c"
        a('<tr>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5">{c["criterion"]}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;font-weight:600;color:{color}">{c["value"]}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:{color}">{icon}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#888;font-size:12px">{c["explain"]}</td>')
        a('</tr>')
    a('</tbody></table>')

    a(f'<div style="background:#f8f9fa;border-left:3px solid {R["safe_color"]};')
    a('padding:12px 16px;border-radius:0 6px 6px 0">')
    a(f'<strong>Safe Equity Score: {R["safe_score"]}/5 — {R["safe_signal"]}</strong><br>')
    a(f'<span style="color:#666;font-size:13px">')
    if R["safe_score"] >= 4:
        a("Most criteria met. Price is largely anchored in existing earnings power ")
        a("with modest growth requirements and conservative leverage.")
    elif R["safe_score"] >= 2:
        a("Some criteria met. The stock has moderate risk characteristics - ")
        a("not a pure safe equity but not highly speculative.")
    else:
        a("Few criteria met. The stock is priced for significant future growth ")
        a("with meaningful dependence on uncertain future earnings.")
    a('</span></div>')

    # Commentary
    commentary = generate_risk_commentary(R)
    a('<div style="background:#f8f9fa;border-left:3px solid #1a1a2e;'
      'padding:12px 14px;font-size:13px;color:#444;'
      'margin-top:14px;border-radius:0 6px 6px 0;line-height:1.7">')
    a(commentary)
    a('</div>')

    a('</div>')
    return "".join(rows)


print("risk.py loaded.")
print("Primary function: run_risk_diagnostic(ticker, r)")
print("Returns: all metrics + html key")
