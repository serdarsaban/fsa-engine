import os
import datetime
import pandas as pd

try:
    from IPython.display import HTML, display
except ImportError:
    HTML = None
    display = None


# ============================================================
# PENMAN & POPE — HTML REPORT MODULE (v2)
# All tooltips, commentaries, summary, expanded scorecard
# ============================================================

TOOLTIPS = {
    "g_star": (
        "Implied Growth Rate (g*)",
        "The perpetual growth rate in residual operating income that the current market price implies. "
        "If g* is close to your required return, the market prices in very high growth. "
        "If g* is well below your required return, the market is being conservative. "
        "Always compare g* to the company historical ReOI growth rate."
    ),
    "hist_cagr": (
        "Historical ReOI CAGR",
        "The compound annual growth rate of Residual Operating Income over the last 2-4 years. "
        "If g* exceeds this, the market bets on acceleration beyond history. "
        "If g* is below this, the market is conservative relative to history."
    ),
    "RNOA": (
        "Return on Net Operating Assets (RNOA)",
        "RNOA = Operating Income after tax / Net Operating Assets. "
        "The core profitability metric in Penman and Pope. Unlike ROE, RNOA isolates "
        "the return from operations. A high and rising RNOA signals genuine competitive advantage."
    ),
    "PM": (
        "Profit Margin (PM)",
        "PM = Operating Income after tax / Revenue. "
        "The margin component of RNOA. RNOA = PM x ATO. "
        "Rising PM means more profit per dollar of revenue."
    ),
    "ATO": (
        "Asset Turnover (ATO)",
        "ATO = Revenue / Average Net Operating Assets. "
        "The efficiency component of RNOA. RNOA = PM x ATO. "
        "High ATO means the company generates lots of revenue per dollar of assets."
    ),
    "ReOI": (
        "Residual Operating Income (ReOI)",
        "ReOI = (RNOA - r) x NOA_start. "
        "Value created above the required return on capital. "
        "Positive ReOI means the company earns more than its cost of capital."
    ),
    "LEV": (
        "Book Leverage (LEV)",
        "LEV = Net Debt / Common Equity. "
        "Measures how much equity is financed by net debt. "
        "Leverage amplifies gains when RNOA exceeds NBC, and amplifies losses when it does not."
    ),
    "ML": (
        "Market Leverage (ML)",
        "ML = Net Debt / Market Capitalisation. "
        "A market-based measure of financial risk. "
        "Negative ML means net cash position."
    ),
    "NBC": (
        "Net Borrowing Cost (NBC)",
        "NBC = Net Financing Expense after tax / Average Net Debt. "
        "The after-tax cost of net debt. "
        "If NBC is less than RNOA, leverage adds value to shareholders."
    ),
    "spread": (
        "Leverage Spread",
        "Spread = RNOA - NBC. "
        "Positive spread means leverage adds to ROE. "
        "Negative spread means leverage destroys ROE."
    ),
    "ROE": (
        "Return on Equity (ROE)",
        "ROE = RNOA + LEV x (RNOA - NBC). "
        "The Penman and Pope decomposition separates ROE into operating performance "
        "and the amplification from leverage."
    ),
    "accruals_bs": (
        "Balance Sheet Accruals Ratio",
        "Accruals_BS = Change in NOA / Average NOA. "
        "High accruals mean earnings are partly driven by accounting estimates rather than cash. "
        "Low or negative accruals are a strong quality signal."
    ),
    "cfo_to_oi": (
        "Cash Conversion (CFO / OI)",
        "CFO divided by Operating Income. "
        "Above 1.0x means cash earnings exceed accounting earnings. "
        "Below 0.75x means significant accruals drag."
    ),
    "NOA": (
        "Net Operating Assets (NOA)",
        "NOA = Operating Assets - Operating Liabilities. "
        "The net investment in the operating business. "
        "Rapid NOA growth dilutes RNOA if not matched by proportional OI growth."
    ),
    "ND": (
        "Net Debt (ND)",
        "ND = Financing Liabilities - Financing Assets. "
        "Negative ND means net cash position. "
        "Includes operating lease liabilities per Penman and Pope."
    ),
    "B": (
        "Book Value of Equity (B)",
        "B = NOA - ND = Common Equity on the balance sheet. "
        "The anchor of the residual earnings model: Value = B + PV(future ReOI). "
        "When market price exceeds B, the market prices in future value creation."
    ),
    "OI": (
        "Operating Income after tax (OI)",
        "OI = Operating Income before tax x (1 - effective tax rate). "
        "The after-tax profit generated purely from operations, stripping out "
        "financing costs. Used as the numerator in RNOA and as OI1 in the "
        "valuation model. Penman and Pope use trailing OI as a proxy for "
        "forward OI when analyst estimates are unavailable."
    ),
    "gap": (
        "Market Challenge Gap",
        "Gap = g* minus Historical ReOI CAGR. "
        "Negative gap: market prices in less growth than history delivered — favourable. "
        "Positive gap: market needs more growth than history delivered — demanding. "
        "This is the core of the market challenge test in Penman and Pope Chapter 7."
    ),
    "accruals_cf": (
        "Cash Flow Accruals Ratio",
        "Accruals_CF = (Net Income - CFO - CFI) / Average NOA. "
        "An alternative accruals measure using cash flow statement data. "
        "Should directionally agree with the balance sheet method. "
        "If CF accruals are much lower than BS accruals, the difference is "
        "often explained by investing cash outflows such as acquisitions."
    ),
    "fcf_to_oi": (
        "Free Cash Flow Conversion (FCF / OI)",
        "FCF = CFO minus Capex. FCF/OI shows how much operating income "
        "remains as free cash after maintaining and growing the asset base. "
        "High FCF/OI means the company does not need heavy reinvestment "
        "to sustain its earnings — a capital-light quality signal."
    ),
    "ROE_actual": (
        "Actual Return on Equity",
        "ROE actual = Net Income / Book Equity. "
        "Compared to ROE decomposed (RNOA + LEV x Spread) to verify "
        "the reformulation is consistent with reported financials. "
        "Differences arise from other comprehensive income items and "
        "minority interests not captured in the operating/financing split."
    ),
}

# Counter for unique IDs per button instance
_tip_counter = [0]

def tip(key):
    """
    Generate button + panel together as a matched pair.
    Each call produces a unique ID so duplicate keys work correctly.
    Usage: place {tip("RNOA")} wherever you want button + panel.
    """
    if key not in TOOLTIPS:
        return ""
    _tip_counter[0] += 1
    tip_id = "t{}_{}".format(_tip_counter[0], key)
    title, text = TOOLTIPS[key]
    btn   = '<button class="info-btn" onclick="toggleTip(\'{}\')" title="{}">i</button>'.format(tip_id, title)
    panel = '<div class="tip-panel" id="{}"><strong>{}</strong><br>{}</div>'.format(tip_id, title, text)
    return btn + panel

def tip_panel(key):
    return ""  # panels now embedded in tip()


def fmt_m(val):
    if val is None: return "N/A"
    if abs(val) >= 1000000: return "${:.1f}tn".format(val/1000000)
    if abs(val) >= 1000:    return "${:.1f}bn".format(val/1000)
    return "${:.0f}m".format(val)

def fmt_pct(val):
    if val is None: return "N/A"
    return "{:.1%}".format(val)

def fmt_x(val):
    if val is None: return "N/A"
    return "{:.2f}x".format(val)

def rag_color(signal):
    if any(x in signal for x in ["HIGH","ATTRACTIVE","POSITIVE"]):
        return "#27ae60"
    if any(x in signal for x in ["LOW","EXPENSIVE","NEGATIVE"]):
        return "#e74c3c"
    if "NET CASH" in signal:
        return "#2980b9"
    return "#f39c12"


def valuation_commentary(val):
    g      = val["g_star"]
    r      = val["r"]
    hist   = val["hist_cagr"]
    P0     = val["P0"]
    v_base = val["v_base"]
    v_bull = val["v_bull"]
    B0     = val["B0"]
    ticker = val["ticker"]
    lines  = []

    if g is None:
        return "Insufficient data to generate valuation commentary."

    if g < 0:
        lines.append(
            "{} is priced at an implied growth rate of {:.1%} — negative, "
            "meaning the market expects residual earnings to shrink. "
            "At {} market cap versus {} book value, the stock prices in value destruction.".format(
                ticker, g, fmt_m(P0), fmt_m(B0))
        )
    elif g < r * 0.5:
        lines.append(
            "The implied growth rate of {:.1%} is well below the required return of {:.0%}, "
            "suggesting the market prices {} conservatively. "
            "The company only needs {:.1%} perpetual growth to justify today's price of {}.".format(
                g, r, ticker, g, fmt_m(P0))
        )
    elif g < r:
        lines.append(
            "At a market cap of {}, {} implies a perpetual growth rate of {:.1%} — "
            "below the required return of {:.0%} but requiring sustained above-GDP growth. "
            "The base case value of {} represents {:.0%} premium to a 3% growth scenario.".format(
                fmt_m(P0), ticker, g, r, fmt_m(v_base), (P0/v_base - 1) if v_base else 0)
        )
    else:
        lines.append(
            "At {}, {} is priced for a perpetual growth rate of {:.1%} — "
            "above the required return of {:.0%}. "
            "Even the bull case value of {} is below today's market price.".format(
                fmt_m(P0), ticker, g, r, fmt_m(v_bull))
        )

    if hist is not None:
        gap = g - hist
        if gap < -0.05:
            lines.append(
                "The market challenge gap is {:.1%} — the market needs {:.1%} less growth "
                "than the {:.1%} historical ReOI CAGR. "
                "This is favourable: the market prices in significant deceleration from history.".format(
                    gap, abs(gap), hist)
            )
        elif gap > 0.05:
            lines.append(
                "The market challenge gap is +{:.1%} — the market requires {:.1%} more growth "
                "than the {:.1%} historical CAGR. "
                "The stock embeds an acceleration beyond demonstrated performance.".format(
                    gap, gap, hist)
            )
        else:
            lines.append(
                "The implied growth rate is broadly in line with the historical ReOI CAGR of {:.1%}, "
                "suggesting the market prices in a continuation of recent performance.".format(hist)
            )

    return " ".join(lines)


def profitability_commentary(rnoa_df, ticker):
    if rnoa_df.empty:
        return "Insufficient data."
    latest     = rnoa_df.iloc[-1]
    first      = rnoa_df.iloc[0]
    RNOA       = latest["RNOA"]
    PM         = latest["PM"]
    ATO        = latest["ATO"]
    ReOI       = latest["ReOI"]
    fy         = latest["fiscal_year_end"]
    rnoa_trend = RNOA - first["RNOA"]
    pm_trend   = PM   - first["PM"]
    ato_trend  = ATO  - first["ATO"]
    lines      = []

    if RNOA > 0.50:
        lines.append(
            "{} delivers an exceptional RNOA of {:.1%} in {} — "
            "consistent with a strong and durable competitive advantage.".format(ticker, RNOA, fy)
        )
    elif RNOA > 0.20:
        lines.append(
            "{} generates a strong RNOA of {:.1%} in {}, "
            "comfortably above a typical cost of capital.".format(ticker, RNOA, fy)
        )
    elif RNOA > 0.09:
        lines.append(
            "{} earns an RNOA of {:.1%} in {} — above the cost of capital "
            "but not by a wide margin.".format(ticker, RNOA, fy)
        )
    else:
        lines.append(
            "{} reports an RNOA of {:.1%} in {} — at or below a typical cost of capital, "
            "suggesting limited competitive advantage.".format(ticker, RNOA, fy)
        )

    if pm_trend > 0.02 and ato_trend > 0:
        lines.append(
            "Both DuPont components are improving: margin +{:.1%} and ATO +{:.2f}x — "
            "a rare combination signalling both pricing power and capital efficiency.".format(
                pm_trend, ato_trend)
        )
    elif pm_trend > 0.02:
        lines.append(
            "Profit margin has expanded {:.1%}, driving RNOA improvement. "
            "Asset turnover has declined {:.2f}x — typical when investing "
            "heavily in assets ahead of revenue.".format(pm_trend, abs(ato_trend))
        )
    elif ato_trend > 0.10:
        lines.append(
            "Asset turnover improved {:.2f}x — the company extracts more revenue "
            "per dollar of assets. The primary RNOA driver.".format(ato_trend)
        )
    elif rnoa_trend < -0.05:
        lines.append(
            "RNOA has declined {:.1%} since {}, with both margin and ATO contributing. "
            "Investigate whether this is cyclical or structural.".format(
                abs(rnoa_trend), first["fiscal_year_end"])
        )

    if ReOI and ReOI > 0:
        lines.append(
            "Residual operating income of {} confirms the business creates "
            "substantial value above its cost of capital.".format(fmt_m(ReOI))
        )

    return " ".join(lines)


def leverage_commentary(lev, ticker):
    ND     = lev["ND"]
    LEV    = lev["LEV"]
    NBC    = lev["NBC"]
    RNOA   = lev["RNOA"]
    spread = lev["spread"]
    ROE_d  = lev["ROE_decomp"]
    ROE_a  = lev["ROE_actual"]
    lines  = []

    if ND < 0:
        lines.append(
            "{} is in a net cash position (ND = {}), "
            "meaning financial assets exceed debt. "
            "Book leverage of {:.2f}x is negative — cash is a mild drag on ROE "
            "because it earns less than operating assets return.".format(
                ticker, fmt_m(ND), LEV)
        )
    elif LEV < 0.5:
        lines.append(
            "{} carries modest leverage of {:.2f}x book equity. "
            "Net debt of {} leaves the balance sheet conservatively structured.".format(
                ticker, LEV, fmt_m(ND))
        )
    elif LEV < 2.0:
        lines.append(
            "{} has book leverage of {:.2f}x — moderate. "
            "Net debt of {} is manageable relative to the equity base.".format(
                ticker, LEV, fmt_m(ND))
        )
    else:
        lines.append(
            "{} carries significant leverage of {:.2f}x book equity "
            "with net debt of {}. This amplifies both upside and downside.".format(
                ticker, LEV, fmt_m(ND))
        )

    if spread and spread > 0.10:
        lines.append(
            "The leverage spread of {:.1%} (RNOA {:.1%} minus NBC {:.1%}) is strongly positive — "
            "each unit of leverage meaningfully boosts shareholder returns.".format(
                spread, RNOA, NBC)
        )
    elif spread and spread > 0:
        lines.append(
            "The spread of {:.1%} is positive but thin. "
            "Any compression in RNOA or rise in borrowing costs could quickly "
            "turn leverage from accretive to destructive.".format(spread)
        )
    elif spread:
        lines.append(
            "The spread is negative ({:.1%}): NBC ({:.1%}) exceeds RNOA ({:.1%}). "
            "Leverage is destroying shareholder value.".format(spread, NBC, RNOA)
        )

    if ROE_d and ROE_a and abs(ROE_d - ROE_a) < 0.05:
        lines.append(
            "The decomposed ROE of {:.1%} closely matches actual ROE of {:.1%}, "
            "confirming the reformulation is consistent with reported earnings.".format(
                ROE_d, ROE_a)
        )

    return " ".join(lines)


def generate_overall_summary(val, rnoa_df, lev, qual_df, q_score, ticker):
    strengths   = []
    risks       = []
    investigate = []

    g      = val["g_star"]
    r      = val["r"]
    hist   = val["hist_cagr"]
    rnoa_l = rnoa_df.iloc[-1] if not rnoa_df.empty else None
    qual_l = qual_df.iloc[-1] if not qual_df.empty else None

    if g is not None and hist is not None:
        gap = g - hist
        if gap < -0.05:
            strengths.append(
                "Market pricing {:.1%} below historical ReOI growth — "
                "conservative valuation relative to track record".format(abs(gap))
            )
        elif gap > 0.05:
            risks.append(
                "Market requires {:.1%} more growth than history delivered — "
                "demanding valuation hurdle".format(gap)
            )

    if g is not None:
        if g < r * 0.5:
            strengths.append(
                "Low implied g* ({:.1%}) — modest growth required "
                "to justify current price".format(g)
            )
        elif g >= r:
            risks.append(
                "Implied g* ({:.1%}) at or above required return ({:.0%}) — "
                "implausible perpetual growth priced in".format(g, r)
            )

    if rnoa_l is not None:
        RNOA = rnoa_l["RNOA"]
        ReOI = rnoa_l["ReOI"]
        if RNOA > 0.30:
            strengths.append(
                "Exceptional RNOA of {:.1%} — strong competitive advantage".format(RNOA)
            )
        elif RNOA < r:
            risks.append(
                "RNOA ({:.1%}) below required return — "
                "not earning cost of capital".format(RNOA)
            )
        if ReOI and ReOI > 0:
            strengths.append(
                "Positive ReOI of {} — creating value above cost of capital".format(fmt_m(ReOI))
            )
        elif ReOI and ReOI < 0:
            risks.append("Negative ReOI — destroying value above cost of capital")
        if len(rnoa_df) >= 2:
            rnoa_trend = rnoa_l["RNOA"] - rnoa_df.iloc[0]["RNOA"]
            if rnoa_trend < -0.10:
                investigate.append(
                    "RNOA declining {:.1%} — investigate whether structural or cyclical".format(
                        abs(rnoa_trend))
                )

    if lev["ND"] < 0:
        strengths.append("Net cash position — zero financial distress risk")
    elif lev["LEV"] and lev["LEV"] > 3:
        risks.append(
            "High leverage ({:.1f}x) — vulnerable to earnings or rate shocks".format(lev["LEV"])
        )
    if lev["spread"] and lev["spread"] > 0.10:
        strengths.append(
            "Strong leverage spread ({:.1%}) — debt cheap relative to returns".format(lev["spread"])
        )
    elif lev["spread"] and lev["spread"] < 0:
        risks.append("Negative spread — leverage reducing ROE")

    if qual_l is not None:
        acc = qual_l["accruals_bs"]
        cfo = qual_l["cfo_to_oi"]
        if acc < 0.05 and cfo > 1.0:
            strengths.append(
                "High earnings quality — low accruals and strong cash conversion ({:.2f}x)".format(cfo)
            )
        elif acc > 0.20:
            risks.append(
                "High accruals ({:.1%}) — earnings quality concern".format(acc)
            )
            investigate.append("Examine revenue recognition and working capital trends")
        if cfo > 1.2:
            strengths.append(
                "Exceptional cash conversion ({:.2f}x) — earnings backed by cash".format(cfo)
            )
        elif cfo < 0.5:
            risks.append("Weak cash conversion ({:.2f}x)".format(cfo))
            investigate.append("Investigate receivables and deferred revenue trends")
        if len(qual_df) >= 2:
            acc_trend = qual_l["accruals_bs"] - qual_df.iloc[0]["accruals_bs"]
            if acc_trend > 0.10:
                investigate.append(
                    "Accruals rising {:.1%} — track whether NOA growth is productive".format(acc_trend)
                )

    investigate.append("Verify forward OI estimate — model uses trailing OI as proxy")
    investigate.append("Review latest 10-K MD&A for qualitative risk factors")

    return {"strengths": strengths, "risks": risks, "investigate": investigate}


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:#f5f6fa;color:#2c3e50;font-size:15px;line-height:1.6}
.header{background:#1a1a2e;color:white;padding:28px 24px 20px}
.header h1{font-size:26px;font-weight:600}
.header .sub{color:#aaa;font-size:13px;margin-top:4px}
.container{max-width:820px;margin:0 auto;padding:20px 16px}
.card{background:white;border-radius:10px;padding:20px;
      margin-bottom:18px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.card h2{font-size:16px;font-weight:600;margin-bottom:6px;
         padding-bottom:8px;border-bottom:1px solid #eee;color:#1a1a2e}
.card-desc{font-size:12px;color:#888;margin-bottom:12px;line-height:1.5}
.scorecard{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.score-item{padding:12px;border-radius:8px;background:#f8f9fa}
.score-label{font-size:11px;text-transform:uppercase;
             letter-spacing:.05em;color:#666;margin-bottom:4px}
.score-value{font-size:20px;font-weight:600}
.score-signal{font-size:11px;margin-top:3px;color:#555}
.score-explain{font-size:11px;color:#777;margin-top:6px;
               line-height:1.4;border-top:1px solid #e8e8e8;padding-top:6px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#f0f2f5;padding:8px 10px;text-align:right;
   font-weight:500;font-size:12px;color:#555}
th:first-child{text-align:left}
td{padding:8px 10px;text-align:right;border-bottom:1px solid #f0f2f5}
td:first-child{text-align:left;color:#666}
.badge{display:inline-block;padding:4px 10px;border-radius:20px;
       font-size:12px;font-weight:500;color:white;margin-top:8px}
.metric-row{display:flex;justify-content:space-between;align-items:center;
            padding:8px 0;border-bottom:1px solid #f0f2f5;font-size:14px}
.metric-left{display:flex;align-items:center;gap:6px;color:#666}
.metric-value{font-weight:500}
.commentary{background:#f8f9fa;border-left:3px solid #1a1a2e;
            padding:12px 14px;font-size:13px;color:#444;
            margin-top:14px;border-radius:0 6px 6px 0;line-height:1.7}
.scenario-grid{display:grid;grid-template-columns:1fr 1fr 1fr;
               gap:8px;margin:12px 0}
.scenario-item{text-align:center;padding:12px 8px;
               border-radius:8px;background:#f8f9fa}
.scenario-label{font-size:11px;color:#666;text-transform:uppercase;
                letter-spacing:.05em}
.scenario-value{font-size:16px;font-weight:600;margin-top:4px}
.info-btn{display:inline-flex;align-items:center;justify-content:center;
          width:16px;height:16px;border-radius:50%;background:#d0e8ff;
          color:#1a5276;font-size:9px;font-weight:700;cursor:pointer;
          border:1px solid #a9cce3;flex-shrink:0;padding:0;
          font-style:normal;vertical-align:middle;margin-left:2px}
.info-btn:hover{background:#a9cce3}
.tip-panel{display:none;background:#eaf4fb;border-left:3px solid #2980b9;
           padding:10px 14px;font-size:12px;color:#1a3a5c;
           margin:6px 0 4px;border-radius:0 6px 6px 0;line-height:1.6}
.summary-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
.summary-col{padding:14px;border-radius:8px}
.summary-col h3{font-size:13px;font-weight:600;margin-bottom:10px;
                padding-bottom:6px;border-bottom:1px solid rgba(0,0,0,.1)}
.summary-col ul{list-style:none;padding:0}
.summary-col li{font-size:12px;line-height:1.5;padding:4px 0;
                border-bottom:1px solid rgba(0,0,0,.06)}
.summary-col li:last-child{border-bottom:none}
.col-green{background:#e8f5e9;color:#1b5e20}
.col-green h3{color:#2e7d32}
.col-red{background:#fce4ec;color:#880e4f}
.col-red h3{color:#c62828}
.col-blue{background:#e3f2fd;color:#0d47a1}
.col-blue h3{color:#1565c0}
.footer{text-align:center;color:#999;font-size:12px;padding:20px 0}
@media(max-width:500px){
  .scorecard,.scenario-grid,.summary-grid{grid-template-columns:1fr}
}
"""

JS = """
function toggleTip(id) {
  var el = document.getElementById(id);
  if (el) {
    el.style.display = (el.style.display === "block") ? "none" : "block";
  }
}
"""


def _build_piotroski_notes(bq: dict, prof: dict) -> str:
    """Change 4: Reconcile Piotroski with DuPont."""
    if not bq or not prof:
        return ""
    notes = []
    items = {x["name"]: x["pass"] for x in bq.get("f_items", [])}

    # Gross margin vs PM
    if not items.get("Gross margin improving"):
        pm_df = prof.get("pm_df")
        if pm_df is not None and len(pm_df) >= 2:
            pm_trend = pm_df["pm_pct"].iloc[-1] - pm_df["pm_pct"].iloc[-2]
            if pm_trend > 0.005:
                notes.append(
                    "Gross margin (COGS only) is falling while operating margin is improving. "
                    "This typically indicates rising R&D or SG&A costs offsetting top-line efficiency. "
                    "Investigate the cost structure."
                )

    # ATO: Piotroski vs DuPont
    if not items.get("Asset turnover improving"):
        ato_df = prof.get("ato_df")
        if ato_df is not None and len(ato_df) >= 2:
            ato_trend = ato_df["ato_calc"].iloc[-1] - ato_df["ato_calc"].iloc[-2]
            if ato_trend > 0.05:
                notes.append(
                    "Piotroski uses total assets; DuPont uses Net Operating Assets. "
                    "Rising DuPont ATO with falling Piotroski ATO typically means financial assets "
                    "are growing faster than operating assets. Check whether excess cash distorts the picture."
                )

    # New shares
    if not items.get("No new shares issued"):
        notes.append(
            "Shares outstanding have increased. For tech companies this is almost always SBC. "
            "Verify whether buybacks are offsetting dilution net — SBC is a real cost not fully captured in GAAP EPS."
        )

    if not notes:
        return ""
    html = '<div style="background:#fffbf0;border-left:3px solid #f39c12;padding:10px 14px;border-radius:0 6px 6px 0;margin-top:8px;font-size:13px">'
    html += "<strong>Piotroski reconciliation notes:</strong><ul style='margin:6px 0 0 16px'>"
    for n in notes:
        html += f"<li style='margin-bottom:4px'>{n}</li>"
    html += "</ul></div>"
    return html


def _build_eps_warning(eps_val: dict) -> str:
    """Change 7: EPS exit multiple warning."""
    if not eps_val:
        return ""
    pe_fwd = eps_val.get("pe_fwd")
    fvs    = eps_val.get("fvs", {})
    cons   = fvs.get("Conservative", {})
    mult   = cons.get("multiple")
    cagr_c = eps_val.get("cagr_c", 0) or 0

    if pe_fwd and mult and mult > pe_fwd * 1.5:
        return (
            ('<div style="background:#fffbf0;border-left:3px solid #f39c12;'
            'padding:10px 14px;border-radius:0 6px 6px 0;margin-top:8px;font-size:13px">'
            f'🟡 <strong>Exit multiple ({mult}x) is significantly above current forward P/E ({pe_fwd:.1f}x).</strong> '
            'The market has already re-rated this stock. '
            'Verify whether the historical average P/E is still an appropriate anchor.'
            '</div>')
        )
    return ""


def generate_report(ticker, r=0.09, project_root=None):
    """Generate complete upgraded HTML FSA report."""
    import sys
    if project_root:
        sys.path.insert(0, project_root)
        sys.path.insert(0, os.path.join(project_root, "core"))

    from valuation              import run_valuation
    from rnoa                   import calculate_rnoa_series
    from leverage               import calculate_leverage
    from quality                import (calculate_accruals,
                                        get_quality_score,
                                        generate_commentary)
    from valuation_calculator   import run_eps_valuation
    from profitability          import run_profitability
    from risk                   import run_risk_diagnostic
    from balance_quality        import run_balance_quality

    # Reset tip counter for each report
    _tip_counter[0] = 0

    today = datetime.date.today().strftime("%B %d, %Y")

    print("  Fetching valuation...")
    # Check for foreign filer (20-F) before running
    try:
        val = run_valuation(ticker, r=r, verbose=False)
    except (KeyError, IndexError, ValueError) as e:
        if "fiscal_year_end" in str(e) or "empty" in str(e).lower():
            return """
            <div style="font-family:-apple-system,sans-serif;max-width:700px;
            margin:60px auto;text-align:center;color:#2c3e50">
            <div style="font-size:48px;margin-bottom:16px">🌍</div>
            <h2 style="font-size:24px;font-weight:600">Foreign Private Issuer</h2>
            <p style="color:#666;font-size:15px;line-height:1.7;margin-top:12px">
            <strong>""" + ticker + """</strong> appears to be a foreign private issuer
            that files with the SEC using <strong>Form 20-F</strong> (IFRS accounting)
            rather than Form 10-K (US GAAP).<br><br>
            The Penman &amp; Pope analysis is calibrated for US GAAP filers.
            IFRS filings use different XBRL concept names which are not yet
            supported in this engine.<br><br>
            <strong>What you can do:</strong><br>
            Use <strong>Tab 2 — Standard Analysis</strong> for market metrics,
            or try Tab 3 for the 10-K/Q text analysis if the company files
            annual reports with the SEC.
            </p>
            <div style="margin-top:24px;padding:16px;background:#f8f9fa;
            border-radius:8px;font-size:13px;color:#888">
            Examples of foreign filers: ICLR (ICON), ASML, SAP, NVO (Novo Nordisk)
            </div>
            </div>
            """
        raise
    print("  Fetching RNOA series...")
    rnoa_df = calculate_rnoa_series(ticker, r=r, years=5)
    print("  Fetching leverage...")
    lev     = calculate_leverage(ticker, r=r)
    print("  Fetching quality...")
    qual_df = calculate_accruals(ticker, years=5)
    print("  Fetching EPS valuation...")
    eps_val = None
    try:
        eps_val  = run_eps_valuation(ticker)
        eps_html = eps_val.get("html", "") if eps_val else ""
    except Exception as e:
        eps_html = f"<p style='color:#e74c3c'>EPS valuation unavailable: {e}</p>"

    print("  Fetching balance & credit quality...")
    try:
        bq        = run_balance_quality(ticker)
        bq_html   = bq.get("html", "")
    except Exception as e:
        bq_html = f"<p style='color:#e74c3c'>Balance quality unavailable: {e}</p>"

    print("  Fetching balance & credit quality...")
    try:
        bq        = run_balance_quality(ticker)
        bq_html   = bq.get("html", "")
    except Exception as e:
        bq_html = f"<p style='color:#e74c3c'>Balance quality unavailable: {e}</p>"

    print("  Fetching Ch 8 risk diagnostic...")
    try:
        risk_result = run_risk_diagnostic(ticker, r=r)
        risk_html   = risk_result.get("html", "")
    except Exception as e:
        risk_html = f"<p style='color:#e74c3c'>Risk diagnostic unavailable: {e}</p>"

    print("  Fetching Ch 6 profitability...")
    try:
        prof     = run_profitability(ticker, years=4)
        prof_html = prof.get("html", "")
    except Exception as e:
        prof_html = f"<p style='color:#e74c3c'>Profitability diagnostic unavailable: {e}</p>"

    qual_latest = qual_df.iloc[-1]
    q_score, q_signal, _ = get_quality_score(
        qual_latest["accruals_bs"], qual_latest["cfo_to_oi"]
    )
    q_comment   = generate_commentary(ticker, qual_df)
    val_comment = valuation_commentary(val)
    prof_comment= profitability_commentary(rnoa_df, ticker)
    lev_comment = leverage_commentary(lev, ticker)
    summary     = generate_overall_summary(
        val, rnoa_df, lev, qual_df, q_score, ticker
    )

    val_signal = val["signal"].split("\n")[0]
    lev_signal = ("NET CASH"         if lev["ND"] < 0
                  else "SPREAD POSITIVE" if lev["spread"] and lev["spread"] > 0.05
                  else "THIN SPREAD"     if lev["spread"] and lev["spread"] > 0
                  else "SPREAD NEGATIVE")
    rnoa_latest = rnoa_df.iloc[-1] if not rnoa_df.empty else None

    gap_str  = fmt_pct(val["g_star"] - val["hist_cagr"]) if val["hist_cagr"] else "N/A"
    hist_str = fmt_pct(val["hist_cagr"]) if val["hist_cagr"] else "N/A"
    hist_yrs = str(val["hist_n_years"]) if val["hist_n_years"] else ""

    # Build table rows
    rnoa_rows = ""
    for _, row in rnoa_df.iterrows():
        rnoa_rows += (
            "<tr><td>{}</td><td>{}</td><td>{}</td>"
            "<td>{}</td><td>{}</td><td>{}</td></tr>".format(
                row["fiscal_year_end"],
                fmt_m(row["OI_aftertax"]),
                fmt_pct(row["RNOA"]),
                fmt_pct(row["PM"]),
                fmt_x(row["ATO"]),
                fmt_m(row["ReOI"]),
            )
        )

    qual_rows = ""
    for _, row in qual_df.iterrows():
        acc_c = "#e74c3c" if row["accruals_bs"] > 0.15 else "#27ae60"
        cfo_c = "#e74c3c" if row["cfo_to_oi"]  < 0.75 else "#27ae60"
        qual_rows += (
            '<tr><td>{}</td>'
            '<td style="color:{}">{}</td>'
            '<td>{}</td>'
            '<td style="color:{}">{}</td>'
            '<td>{}</td></tr>'.format(
                row["fiscal_year_end"],
                acc_c, fmt_pct(row["accruals_bs"]),
                fmt_pct(row["accruals_cf"]),
                cfo_c, fmt_x(row["cfo_to_oi"]),
                fmt_x(row["fcf_to_oi"]),
            )
        )

    def li(items):
        return "".join("<li>{}</li>".format(i) for i in items) if items else ""

    # Change 6: Structured minimum risk checklist
    def build_risks(risks_list, val_data, bq_data, lev_data, qual_data, rnoa_data):
        r = list(risks_list)
        # Goodwill concentration
        gw = bq_data.get("goodwill_pct") if bq_data else None
        if gw and gw > 0.20:
            r.append(f"Goodwill {gw:.0%} of assets — acquisition quality unverified")
        # High P/B
        pb = val_data.get("P0", 0) / val_data.get("B0", 1) if val_data.get("B0") else None
        if pb and pb > 5:
            r.append(f"P/B = {pb:.1f}x — significant price depends on future value creation")
        # Piotroski
        if bq_data:
            fscore = bq_data.get("f_score", 9)
            if fscore < 7:
                failed = [x["name"] for x in bq_data.get("f_items", []) if not x["pass"]]
                r.append(f"Piotroski {fscore}/9 — failed: {', '.join(failed)}")
        # ROE gap
        if lev_data:
            rd = lev_data.get("ROE_decomp") or 0
            ra = lev_data.get("ROE_actual") or 0
            if abs(rd - ra) > 0.10:
                r.append(f"ROE gap {abs(rd-ra)*100:.1f}pp — SBC or OCI distortion likely")
        # Always include qualitative reminder
        r.append("Qualitative risks not assessed — review MD&A for competitive, regulatory and macro threats")
        return r if r else ["Review MD&A for qualitative risks before acting"]

    # Generate tooltip panels for each section
    tp = tip_panel

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FSA Report — {ticker}</title>
<style>{css}</style>
</head>
<body>
<script>{js}</script>

<div class="header">
  <h1>{ticker}</h1>
  <div class="sub">FSA Report &middot; FY {fy_end}
  &middot; {today} &middot; Required return: {r_pct}</div>
</div>

<div class="container">

<!-- SCORECARD -->
<div class="card">
  <h2>Summary Scorecard</h2>
  <p class="card-desc">Four key dimensions of investment quality.
  Click any <strong>i</strong> button for the textbook definition.</p>
  <div class="scorecard">
    <div class="score-item">
      <div class="score-label">Valuation {tip_gstar}</div>
      <div class="score-value">{g_star_fmt}</div>
      <div class="score-signal">Implied g* (market-required growth)</div>
      <div class="score-explain">Growth rate in residual earnings the market
      needs to justify today's price. Compare to required return ({r_pct})
      and historical CAGR ({hist_str}).</div>
      <div class="badge" style="background:{val_color}">{val_badge}</div>
    </div>
    <div class="score-item">
      <div class="score-label">Profitability {tip_rnoa}</div>
      <div class="score-value">{rnoa_fmt}</div>
      <div class="score-signal">RNOA = PM x ATO (latest year)</div>
      <div class="score-explain">Return on net operating assets — how efficiently
      the business converts its asset base into profit.
      Above {r_pct} = value creation.</div>
    </div>
    <div class="score-item">
      <div class="score-label">Leverage {tip_lev}</div>
      <div class="score-value">{lev_fmt}</div>
      <div class="score-signal">Book leverage ND/B &middot; Spread: {spread_fmt}</div>
      <div class="score-explain">Leverage amplifies ROE when RNOA exceeds NBC.
      Spread = {spread_fmt} — leverage is
      {lev_adding} shareholder value.</div>
      <div class="badge" style="background:{lev_color}">{lev_signal}</div>
    </div>
    <div class="score-item">
      <div class="score-label">Earnings Quality {tip_acc}</div>
      <div class="score-value">{q_score}/4</div>
      <div class="score-signal">{q_signal}</div>
      <div class="score-explain">Whether reported earnings are backed by cash.
      Latest: Accruals {acc_fmt}, CFO/OI {cfo_fmt}.</div>
      <div class="badge" style="background:{q_color}">{q_badge}</div>
    </div>
  </div>
</div>

<!-- VALUATION -->
<div class="card">
  <h2>Valuation</h2>
  <p class="card-desc">V = B + (OI - r x NOA) / (r - g).
  The implied g* is reverse-engineered from today's market price.</p>
  <div class="metric-row">
    <span class="metric-left">Book value (B) {tip_B}</span>
    <span class="metric-value">{B0_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Net operating assets (NOA) {tip_NOA}</span>
    <span class="metric-value">{NOA0_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Operating income OI (trailing) {tip_OI}</span>
    <span class="metric-value">{OI1_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Market cap</span>
    <span class="metric-value">{P0_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Implied growth rate g* {tip_gstar2}</span>
    <span class="metric-value" style="font-size:18px;color:#1a1a2e">{g_star_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Historical ReOI CAGR ({hist_yrs} yrs) {tip_hist}</span>
    <span class="metric-value">{hist_str}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Market challenge gap (g* minus hist) {tip_gap}</span>
    <span class="metric-value">{gap_str}</span>
  </div>
  <div class="scenario-grid">
    <div class="scenario-item">
      <div class="scenario-label">Bear (g=0%)</div>
      <div class="scenario-value">{v_bear_fmt}</div>
    </div>
    <div class="scenario-item" style="background:#e8f5e9">
      <div class="scenario-label">Base (g=3%)</div>
      <div class="scenario-value">{v_base_fmt}</div>
    </div>
    <div class="scenario-item">
      <div class="scenario-label">Bull (g=6%)</div>
      <div class="scenario-value">{v_bull_fmt}</div>
    </div>
  </div>
  <div class="badge" style="background:{val_color}">{val_signal}</div>
  <div class="commentary">{val_comment}</div>
</div>

<!-- PROFITABILITY -->
<div class="card">
  <h2>Profitability</h2>
  <p class="card-desc">RNOA = PM x ATO. Rising RNOA above cost of capital
  signals competitive advantage.</p>
  <table>
    <thead><tr>
      <th>FY End</th>
      <th>OI after tax</th>
      <th>RNOA {tip_rnoa2}</th>
      <th>PM {tip_pm}</th>
      <th>ATO {tip_ato}</th>
      <th>ReOI {tip_reoi}</th>
    </tr></thead>
    <tbody>{rnoa_rows}</tbody>
  </table>
  <div class="commentary">{prof_comment}</div>
</div>

<!-- LEVERAGE -->
<div class="card">
  <h2>Leverage</h2>
  <p class="card-desc">ROE = RNOA + LEV x (RNOA - NBC).
  Leverage adds value when RNOA exceeds the net borrowing cost.</p>
  <div class="metric-row">
    <span class="metric-left">Net Debt (ND) {tip_nd}</span>
    <span class="metric-value">{ND_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Book Equity (B) {tip_b2}</span>
    <span class="metric-value">{B_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Book leverage LEV = ND/B {tip_lev2}</span>
    <span class="metric-value">{LEV_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Market leverage ML = ND/Mkt {tip_ml}</span>
    <span class="metric-value">{ML_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">RNOA {tip_rnoa3}</span>
    <span class="metric-value">{RNOA_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Net borrowing cost NBC {tip_nbc}</span>
    <span class="metric-value">{NBC_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">Spread = RNOA minus NBC {tip_spread}</span>
    <span class="metric-value">{spread_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">ROE decomposed {tip_roe}</span>
    <span class="metric-value">{ROE_d_fmt}</span>
  </div>
  <div class="metric-row">
    <span class="metric-left">ROE actual {tip_ROE_actual}</span>
    <span class="metric-value">{ROE_a_fmt}</span>
  </div>
  <div class="badge" style="background:{lev_color}">{lev_signal}</div>
  <div class="commentary">{lev_comment}</div>
</div>

<!-- EARNINGS QUALITY -->
<div class="card">
  <h2>Earnings Quality</h2>
  <p class="card-desc">High accruals signal earnings driven by accounting
  estimates. High CFO/OI confirms cash-backed earnings.</p>
  <table>
    <thead><tr>
      <th>FY End</th>
      <th>Accruals BS {tip_acc2}</th>
      <th>Accruals CF {tip_accruals_cf}</th>
      <th>CFO/OI {tip_cfo}</th>
      <th>FCF/OI {tip_fcf_to_oi}</th>
    </tr></thead>
    <tbody>{qual_rows}</tbody>
  </table>
  <div class="badge" style="background:{q_color};margin-top:12px">{q_signal}</div>
  <div class="commentary">{q_comment}</div>
</div>

<!-- CH 8 RISK -->
<div class="card">
  <h2>Risk Diagnostic (Ch 8)</h2>
  <p class="card-desc">No-growth value, speculative value, value-at-risk table,
  expected return profile and safe equity scorecard.</p>
  {risk_html}
</div>

<!-- CH 6 PROFITABILITY -->
<div class="card">
  <h2>Profitability Diagnostic (Ch 6)</h2>
  <p class="card-desc">Full DuPont decomposition: RNOA = PM × ATO.
  Level 2 drivers, operating liability leverage, and cash conversion cycle.</p>
  {prof_html}
</div>

<!-- EPS VALUATION -->
<div class="card">
  <h2>EPS Valuation (Book Calculator)</h2>
  <p class="card-desc">EPS-based fair value using CAGR triangulation and P/E exit multiples.
  Independent methodology — compare with the residual earnings model above.</p>
  {eps_html}
  {eps_pe_warning}
</div>

<!-- BALANCE QUALITY -->
<div class="card">
  <h2>Balance Sheet &amp; Credit Quality (Ch 9 / Ch 13)</h2>
  <p class="card-desc">Balance sheet risk items, Altman Z-score and Piotroski F-score.</p>
  {bq_html}
  {piotroski_notes}
</div>

<!-- SUMMARY -->
<div class="card">
  <h2>Investment Summary</h2>
  <p class="card-desc">Auto-generated from all modules.
  Starting point for deeper research — not a buy/sell recommendation.</p>
  <div class="summary-grid">
    <div class="summary-col col-green">
      <h3>Strengths</h3>
      <ul>{strengths_li}</ul>
    </div>
    <div class="summary-col col-red">
      <h3>Risks</h3>
      <ul>{risks_li}</ul>
    </div>
    <div class="summary-col col-blue">
      <h3>Investigate</h3>
      <ul>{investigate_li}</ul>
    </div>
  </div>
</div>

</div>
<div class="footer">
  FSA Engine &middot; Penman and Pope methodology &middot;
  SEC EDGAR + Yahoo Finance &middot; {today}
</div>
</body>
</html>""".format(
        ticker      = val["ticker"],
        css         = CSS,
        js          = JS,
        fy_end      = val["fy_end"],
        today       = today,
        r_pct       = fmt_pct(r),
        # Scorecard tooltips
        tip_gstar   = tip("g_star"),
        tip_rnoa    = tip("RNOA"),
        tip_lev     = tip("LEV"),
        tip_acc     = tip("accruals_bs"),
        # Scorecard values
        g_star_fmt  = fmt_pct(val["g_star"]),
        rnoa_fmt    = fmt_pct(rnoa_latest["RNOA"]) if rnoa_latest is not None else "N/A",
        lev_fmt     = fmt_x(lev["LEV"]),
        spread_fmt  = fmt_pct(lev["spread"]),
        lev_adding  = "adding to" if lev["spread"] and lev["spread"] > 0 else "reducing",
        acc_fmt     = fmt_pct(qual_latest["accruals_bs"]),
        cfo_fmt     = fmt_x(qual_latest["cfo_to_oi"]),
        q_score     = q_score,
        q_signal    = q_signal,
        q_color     = rag_color(q_signal),
        q_badge     = q_signal.split(" ", 1)[1].strip() if " " in q_signal else q_signal,
        val_color   = rag_color(val_signal),
        val_badge   = val_signal.split("—")[0].strip(),
        val_signal  = val_signal,
        lev_color   = rag_color(lev_signal),
        lev_signal  = lev_signal,
        hist_str    = hist_str,
        # Valuation section
        tip_gstar2  = tip("g_star"),
        tip_hist    = tip("hist_cagr"),
        tip_B       = tip("B"),
        tip_NOA     = tip("NOA"),
        B0_fmt      = fmt_m(val["B0"]),
        NOA0_fmt    = fmt_m(val["NOA0"]),
        OI1_fmt     = fmt_m(val["OI1"]),
        P0_fmt      = fmt_m(val["P0"]),
        hist_yrs    = hist_yrs,
        gap_str     = gap_str,
        v_bear_fmt  = fmt_m(val["v_bear"]),
        v_base_fmt  = fmt_m(val["v_base"]),
        v_bull_fmt  = fmt_m(val["v_bull"]),
        val_comment = val_comment,
        # Profitability section
        tip_rnoa2   = tip("RNOA"),
        tip_pm      = tip("PM"),
        tip_ato     = tip("ATO"),
        tip_reoi    = tip("ReOI"),
        rnoa_rows   = rnoa_rows,
        prof_comment= prof_comment,
        # Leverage section
        tip_nd      = tip("ND"),
        tip_b2      = tip("B"),
        tip_lev2    = tip("LEV"),
        tip_ml      = tip("ML"),
        tip_rnoa3   = tip("RNOA"),
        tip_nbc     = tip("NBC"),
        tip_spread  = tip("spread"),
        tip_roe     = tip("ROE"),
        ND_fmt      = fmt_m(lev["ND"]),
        B_fmt       = fmt_m(lev["B"]),
        LEV_fmt     = fmt_x(lev["LEV"]),
        ML_fmt      = fmt_x(lev["ML"]),
        RNOA_fmt    = fmt_pct(lev["RNOA"]),
        NBC_fmt     = fmt_pct(lev["NBC"]),
        ROE_d_fmt   = fmt_pct(lev["ROE_decomp"]),
        ROE_a_fmt   = fmt_pct(lev["ROE_actual"]),
        lev_comment = lev_comment,
        roe_gap_warning = (
            '<div style="background:#fffbf0;border-left:3px solid #f39c12;'
            'padding:10px 14px;border-radius:0 6px 6px 0;margin-top:8px;font-size:13px">'
            f'🟡 <strong>ROE decomposed and ROE actual differ by {abs((lev.get("ROE_decomp",0) or 0) - (lev.get("ROE_actual",0) or 0))*100:.1f}pp.</strong> '
            'Common causes: (a) stock-based compensation reducing book equity faster than net income builds it; '
            '(b) unrealised gains/losses in OCI; (c) share buybacks above book value. '
            'Investigate which is the dominant driver before relying on either ROE figure.'
            '</div>'
        ) if lev.get("ROE_decomp") and lev.get("ROE_actual") and abs((lev["ROE_decomp"] or 0) - (lev["ROE_actual"] or 0)) > 0.10 else "",
        # Quality section
        tip_acc2    = tip("accruals_bs"),
        tip_cfo     = tip("cfo_to_oi"),
        qual_rows   = qual_rows,
        q_comment   = q_comment,
        # Summary
        strengths_li  = li(summary["strengths"]),
        risks_li      = li(build_risks(
            summary["risks"], val, bq if "bq" in dir() else {},
            lev, qual_df.iloc[-1].to_dict() if not qual_df.empty else {},
            rnoa_df.iloc[-1].to_dict() if not rnoa_df.empty else {}
        )),
        investigate_li= li(summary["investigate"]),
        eps_html        = eps_html,
        eps_pe_warning  = _build_eps_warning(eps_val or {}),
        prof_html       = prof_html,
        risk_html       = risk_html,
        bq_html         = bq_html,
        piotroski_notes = _build_piotroski_notes(bq if bq else {}, prof if prof else {}),
        tip_OI          = tip("OI"),
        tip_gap         = tip("gap"),
        tip_ROE_actual  = tip("ROE_actual"),
        tip_accruals_cf = tip("accruals_cf"),
        tip_fcf_to_oi   = tip("fcf_to_oi"),
    )

    return html


def save_and_display_report(ticker, r=0.09, project_root=None,
                             display_html=True):
    """Generate, save and display upgraded HTML report."""
    if project_root is None:
        project_root = os.environ.get(
            "FSA_PROJECT_ROOT",
            "/content/drive/MyDrive/fsa-engine"
        )

    print("Generating report for {}...".format(ticker.upper()))
    html     = generate_report(ticker, r=r, project_root=project_root)
    today    = datetime.date.today().strftime("%Y-%m-%d")
    filename = "{}_{}.html".format(ticker.upper(), today)
    out_dir  = os.path.join(project_root, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    filepath = os.path.join(out_dir, filename)

    with open(filepath, "w") as f:
        f.write(html)

    print("Saved: {}".format(filepath))

    if display_html and display is not None:
        display(HTML(html))

    return filepath


print("report.py v3 loaded.")
print("Tooltips: expandable panels (click i button)")
print("Sections: valuation, profitability, leverage, quality commentaries")
print("Summary:  strengths / risks / investigate")
