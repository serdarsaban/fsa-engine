import pandas as pd
import numpy as np
import time


# ============================================================
# STANDARD ANALYSIS MODULE
#
# Fetches all practitioner metrics for Tab 2:
# Revenue, EPS, FCF, ROIC, ROIIC, margins, leverage,
# valuation multiples, 52w position, CAGRs.
#
# Primary function: fetch_standard_data(ticker)
# Returns: snapshot, annual DataFrame, html
# ============================================================

HEADERS = {"User-Agent": "FSA Engine research@example.com"}


def _cagr(s, e, n):
    try:
        if s and e and s > 0 and n > 0:
            return (e / s) ** (1/n) - 1
    except Exception:
        pass
    return None


def _fmt_m(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if abs(v) >= 1e6:  return f"${v/1e6:.2f}tn"
    if abs(v) >= 1e3:  return f"${v/1e3:.1f}bn"
    return f"${v:.0f}m"

def _fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.1%}"

def _fmt_x(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.1f}x"

def _fmt_usd(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"${v:,.2f}"

def _yoy_color(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "#95a5a6"
    return "#27ae60" if v > 0 else "#e74c3c"

def _flag(v, good_thresh, warn_thresh, reverse=False):
    """Return RAG color for a metric value."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "#95a5a6"
    if not reverse:
        if v >= good_thresh: return "#27ae60"
        if v >= warn_thresh: return "#f39c12"
        return "#e74c3c"
    else:
        if v <= good_thresh: return "#27ae60"
        if v <= warn_thresh: return "#f39c12"
        return "#e74c3c"


def fetch_standard_data(ticker: str) -> dict:
    """
    Fetch all standard analysis metrics for any US ticker.
    Returns dict with snapshot, annual df, and html.
    """
    import yfinance as yf
    from data_fetch import get_cik, get_xbrl_facts, get_concept_value
    from rnoa import get_fiscal_year_dates

    ticker = ticker.upper()

    # Yahoo Finance
    stock = yf.Ticker(ticker)
    for attempt in range(3):
        try:
            info = stock.info
            fast = stock.fast_info
            break
        except Exception:
            if attempt < 2: time.sleep(3)
            else: info, fast = {}, {}

    # SEC EDGAR
    cik      = get_cik(ticker)
    facts    = get_xbrl_facts(cik)
    ann_dates= get_fiscal_year_dates(facts, years=5)

    def ga(concept, period):
        return get_concept_value(facts, concept, period) or 0

    # Build annual series
    annual = []
    for fy in ann_dates:
        rev   = (ga("RevenueFromContractWithCustomerExcludingAssessedTax", fy) or
                 ga("Revenues", fy) or ga("SalesRevenueNet", fy))
        gp    = ga("GrossProfit", fy)
        ni    = ga("NetIncomeLoss", fy)
        cfo   = ga("NetCashProvidedByUsedInOperatingActivities", fy)
        capex = ga("PaymentsToAcquirePropertyPlantAndEquipment", fy)
        fcf   = cfo - capex if cfo else None
        ebit  = ga("OperatingIncomeLoss", fy)
        dna   = (ga("DepreciationDepletionAndAmortization", fy) or
                 ga("DepreciationAndAmortization", fy) or
                 ga("Depreciation", fy))
        # Fallback: try direct EBITDA concept
        ebitda_direct = ga("EarningsBeforeInterestTaxesDepreciationAndAmortization", fy)
        ebitda= ebitda_direct or ((ebit + dna) if (ebit and dna) else None)
        tax   = ga("IncomeTaxExpenseBenefit", fy)
        ibt   = ga("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", fy)
        tr    = tax/ibt if (ibt and ibt != 0) else 0.21
        nopat = ebit * (1 - tr) if ebit else None
        eq    = (ga("StockholdersEquity", fy) or
                 ga("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", fy))
        ta    = ga("Assets", fy)
        tl    = ga("Liabilities", fy)
        if not tl and eq and ta:
            tl = ta - eq
        cash  = ga("CashAndCashEquivalentsAtCarryingValue", fy)
        sti   = ga("ShortTermInvestments", fy)
        ltd   = ga("LongTermDebtNoncurrent", fy) or ga("LongTermDebt", fy)
        ltd_c = ga("LongTermDebtCurrent", fy)
        std   = ga("ShortTermBorrowings", fy) or ga("CommercialPaper", fy)
        gross_debt = ltd + ltd_c + std
        net_debt   = gross_debt - cash - sti
        ic    = (eq + gross_debt - cash - sti) if eq else None
        roic  = (nopat / ic) if (nopat and ic and ic != 0) else None
        gm    = gp / rev if (gp and rev) else None
        ni_m  = ni / rev if (ni and rev) else None
        eps_v = ga("EarningsPerShareDiluted", fy)
        net_lev = net_debt / ebitda if (ebitda and ebitda != 0) else None
        shares  = ga("CommonStockSharesOutstanding", fy) or ga("CommonStockSharesIssued", fy)
        fcf_ps  = fcf / (shares/1e6) if (fcf and shares) else None

        annual.append({
            "period":       fy,
            "revenue":      rev,
            "gross_profit": gp,
            "gross_margin": gm,
            "ebitda":       ebitda,
            "net_income":   ni,
            "net_margin":   ni_m,
            "cfo":          cfo,
            "capex":        capex,
            "fcf":          fcf,
            "fcf_ps":       fcf_ps,
            "gross_debt":   gross_debt,
            "net_debt":     net_debt,
            "net_leverage": net_lev,
            "equity":       eq,
            "invested_capital": ic,
            "nopat":        nopat,
            "roic":         roic,
            "eps":          eps_v,
        })

    ann_df = pd.DataFrame(annual).sort_values("period").reset_index(drop=True)

    # ROIIC
    ann_df["delta_ic"]    = ann_df["invested_capital"].diff()
    ann_df["delta_nopat"] = ann_df["nopat"].diff()
    ann_df["roiic"] = ann_df.apply(
        lambda r: r["delta_nopat"] / r["delta_ic"]
        if (pd.notna(r["delta_ic"]) and r["delta_ic"] and r["delta_ic"] != 0)
        else None, axis=1
    )

    # YoY % changes
    for col in ["revenue","gross_profit","ebitda","net_income","fcf","eps","roic"]:
        ann_df[f"{col}_yoy"] = ann_df[col].pct_change(fill_method=None)

    # CAGRs
    rv = ann_df["revenue"].dropna().tolist()
    fv = ann_df["fcf"].dropna().tolist()
    ev = [v for v in ann_df["eps"].dropna().tolist() if v > 0]
    nv = ann_df["net_income"].dropna().tolist()

    # Snapshot
    price    = getattr(fast,"last_price",None) or info.get("currentPrice")
    mkt_cap  = getattr(fast,"market_cap",None) or info.get("marketCap")
    w52h     = getattr(fast,"year_high",None)  or info.get("fiftyTwoWeekHigh")
    w52l     = getattr(fast,"year_low",None)   or info.get("fiftyTwoWeekLow")
    mkt_m    = mkt_cap/1e6 if mkt_cap else None
    ev_v     = info.get("enterpriseValue")
    ev_m     = ev_v/1e6 if ev_v else None
    latest_fcf = ann_df["fcf"].iloc[-1] if not ann_df.empty else None

    snapshot = {
        "ticker":    ticker,
        "company":   info.get("longName", ticker),
        "sector":    info.get("sector","N/A"),
        "price":     price,
        "mkt_cap_m": mkt_m,
        "ev_m":      ev_m,
        "w52_high":  w52h,
        "w52_low":   w52l,
        "pct_52h":   (price/w52h - 1) if (price and w52h) else None,
        "pct_52l":   (price/w52l - 1) if (price and w52l) else None,
        "pe_trail":  info.get("trailingPE"),
        "pe_fwd":    info.get("forwardPE"),
        "pb":        info.get("priceToBook"),
        "peg":       info.get("trailingPegRatio") or info.get("pegRatio"),
        "ev_sales":  info.get("enterpriseToRevenue"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "eps_ttm":   info.get("trailingEps"),
        "eps_fwd":   info.get("forwardEps"),
        "div_yield": info.get("dividendYield") or 0,
        "target":    info.get("targetMeanPrice"),
        "beta":      info.get("beta"),
        "shares_m":  (info.get("sharesOutstanding") or 0)/1e6,
        "fcf_yield": (latest_fcf/mkt_m) if (latest_fcf and mkt_m) else None,
        "rev_cagr":  _cagr(rv[0],rv[-1],len(rv)-1) if len(rv)>=2 else None,
        "fcf_cagr":  _cagr(fv[0],fv[-1],len(fv)-1) if len(fv)>=2 else None,
        "eps_cagr":  _cagr(ev[0],ev[-1],len(ev)-1) if len(ev)>=2 else None,
        "ni_cagr":   _cagr(nv[0],nv[-1],len(nv)-1) if len(nv)>=2 else None,
        "latest_fcf":latest_fcf,
        "latest_rev":ann_df["revenue"].iloc[-1] if not ann_df.empty else None,
        "latest_eps":ann_df["eps"].iloc[-1]     if not ann_df.empty else None,
        "latest_roic":ann_df["roic"].iloc[-1]   if not ann_df.empty else None,
        "latest_gm": ann_df["gross_margin"].iloc[-1] if not ann_df.empty else None,
        "latest_netlev":ann_df["net_leverage"].iloc[-1] if not ann_df.empty else None,
    }

    return {
        "ticker":   ticker,
        "company":  snapshot["company"],
        "snapshot": snapshot,
        "annual":   ann_df,
    }


def generate_standard_html(ticker: str) -> str:
    """
    Generate the complete standard analysis HTML.
    Includes snapshot, trend tables, and
    interactive intrinsic value calculator.
    """
    data = fetch_standard_data(ticker)
    snap = data["snapshot"]
    ann  = data["annual"]

    rows = []
    a    = rows.append

    # ── SNAPSHOT GRID ─────────────────────────────────────────
    def snap_item(label, value, color="#2c3e50", note=""):
        return (
            f'<div style="padding:14px;background:white;border-radius:8px;border:1px solid #e8ecf0">'
            f'<div style="font-size:11px;text-transform:uppercase;'
            f'letter-spacing:.05em;color:#888;margin-bottom:4px">{label}</div>'
            f'<div style="font-size:18px;font-weight:600;color:{color}">{value}</div>'
            f'<div style="font-size:11px;color:#888;margin-top:3px">{note}</div>'
            f'</div>'
        )

    p     = snap
    p52h  = f"{p['pct_52h']:.1%} from 52w high" if p.get("pct_52h") else ""
    p52l  = f"{p['pct_52l']:.1%} from 52w low"  if p.get("pct_52l") else ""
    fwd_c = _flag(p.get("pe_fwd") or 99, 15, 25, reverse=True)
    pb_c  = _flag(p.get("pb")     or 99, 2,  5,  reverse=True)
    peg_c = _flag(p.get("peg")    or 99, 1,  2,  reverse=True)

    a('<div style="font-family:-apple-system,sans-serif;color:#2c3e50;font-size:14px">')
    a(f'<p style="color:#666;font-size:12px;margin-bottom:12px">')
    a(f'Sector: <strong>{p["sector"]}</strong> &nbsp;|&nbsp; ')
    a(f'Beta: <strong>{p["beta"]:.2f}</strong>' if p.get("beta") else '')
    a(f' &nbsp;|&nbsp; Analyst target: <strong>{_fmt_usd(p.get("target"))}</strong>')
    a(f' &nbsp;|&nbsp; Div yield: <strong>{_fmt_pct(p.get("div_yield"))}</strong></p>')

    a('<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px">')
    a(snap_item("Stock Price",   _fmt_usd(p.get("price")),  note=p52h))
    a(snap_item("Market Cap",    _fmt_m(p.get("mkt_cap_m"))))
    a(snap_item("EV",            _fmt_m(p.get("ev_m"))))
    a(snap_item("52w High/Low",
                f"{_fmt_usd(p.get('w52_high'))} / {_fmt_usd(p.get('w52_low'))}",
                note=p52l))
    a(snap_item("P/E (Trail)",   _fmt_x(p.get("pe_trail"))))
    a(snap_item("P/E (Fwd)",     _fmt_x(p.get("pe_fwd")),   fwd_c))
    a(snap_item("P/B",           _fmt_x(p.get("pb")),        pb_c))
    a(snap_item("PEG",           _fmt_x(p.get("peg")),       peg_c,
                note="<1x = attractive"))
    a(snap_item("EV/Sales",      _fmt_x(p.get("ev_sales"))))
    a(snap_item("EV/EBITDA",     _fmt_x(p.get("ev_ebitda"))))
    a(snap_item("EPS (TTM)",     _fmt_usd(p.get("eps_ttm"))))
    a(snap_item("EPS (Fwd)",     _fmt_usd(p.get("eps_fwd")),
                note=f"vs TTM: {(p['eps_fwd']/p['eps_ttm']-1):+.1%}" if (p.get("eps_fwd") and p.get("eps_ttm")) else ""))
    a(snap_item("FCF Yield",     _fmt_pct(p.get("fcf_yield")),
                "#27ae60" if (p.get("fcf_yield") or 0) > 0.03 else "#f39c12"))
    a(snap_item("Rev CAGR (5yr)",_fmt_pct(p.get("rev_cagr")),
                "#27ae60" if (p.get("rev_cagr") or 0) > 0.08 else "#f39c12"))
    a(snap_item("EPS CAGR (5yr)",_fmt_pct(p.get("eps_cagr")),
                "#27ae60" if (p.get("eps_cagr") or 0) > 0.08 else "#f39c12"))
    a(snap_item("FCF CAGR (5yr)",_fmt_pct(p.get("fcf_cagr"))))
    a('</div>')

    # ── TREND TABLES ──────────────────────────────────────────
    def trend_table(title, desc, cols, df):
        """Render a trend table with YoY % change."""
        h  = f'<p style="font-weight:600;margin:14px 0 4px">{title}</p>'
        h += f'<p style="color:#888;font-size:12px;margin-bottom:8px">{desc}</p>'
        h += '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">'
        h += '<thead><tr><th style="background:#e8ecf0;padding:10px 10px;text-align:left;font-weight:600;font-size:12px;color:#333">FY End</th>'
        for label, _ in cols:
            h += f'<th style="background:#e8ecf0;padding:10px 10px;text-align:right;font-weight:600;font-size:12px;color:#333;white-space:nowrap">{label}</th>'
        h += '</tr></thead><tbody>'
        for _, row in df.iterrows():
            h += '<tr>'
            h += f'<td style="padding:8px 10px;border-bottom:1px solid #eee;color:#333;font-size:12px">{row["period"]}</td>'
            for label, col in cols:
                val = row.get(col)
                yoy = row.get(f"{col}_yoy")
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    cell = "—"
                    color = "#95a5a6"
                elif col in ["gross_margin","net_margin"]:
                    cell = _fmt_pct(val)
                    # Green if margin > 20%, show YoY trend in parentheses
                    color = "#27ae60" if val > 0.20 else "#f39c12" if val > 0.10 else "#e74c3c"
                elif col in ["roic","roiic"]:
                    cell = _fmt_pct(val)
                    color = "#27ae60" if val > 0.10 else "#f39c12" if val > 0.05 else "#e74c3c"
                elif col in ["net_leverage"]:
                    cell = _fmt_x(val)
                    color = _flag(val, 1.0, 3.0, reverse=True)
                elif col in ["eps", "fcf_ps"]:
                    cell = f"${val:.2f}" if abs(val) < 1000 else _fmt_m(val)
                    color = _yoy_color(yoy)
                else:
                    cell = _fmt_m(val)
                    color = _yoy_color(yoy)
                yoy_str = f' <span style="color:{_yoy_color(yoy)};font-size:11px">({_fmt_pct(yoy)})</span>' if (yoy is not None and not np.isnan(yoy)) else ''
                h += f'<td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;font-weight:600;color:{color}">{cell}{yoy_str}</td>'
            h += '</tr>'
        h += '</tbody></table></div>'
        return h

    a(trend_table(
        "Growth Metrics",
        "Revenue, EPS and FCF with YoY % change. Consistency matters more than any single year.",
        [("Revenue","revenue"),("EPS","eps"),("FCF","fcf"),("Net Income","net_income")],
        ann
    ))

    a(trend_table(
        "Profitability",
        "Gross margin and ROIC show pricing power and capital efficiency. ROIIC measures returns on new investment.",
        [("Gross Margin","gross_margin"),("Net Margin","net_margin"),
         ("EBITDA","ebitda"),("ROIC","roic"),("ROIIC","roiic")],
        ann
    ))

    a(trend_table(
        "Balance Sheet & Leverage",
        "Net leverage = Net Debt / EBITDA. Above 3x is elevated. Negative = net cash.",
        [("Gross Debt","gross_debt"),("Net Debt","net_debt"),
         ("Net Leverage","net_leverage"),("Equity","equity")],
        ann
    ))

    # ── TREND FLAGS ───────────────────────────────────────────
    flags = []

    # Revenue growth deceleration
    rev_yoys = ann["revenue_yoy"].dropna().tolist()
    if len(rev_yoys) >= 2 and rev_yoys[-1] < rev_yoys[-2] - 0.05:
        flags.append(f"Revenue growth decelerated from {rev_yoys[-2]:.1%} to {rev_yoys[-1]:.1%} — investigate whether cyclical or structural.")

    # Margin compression
    gm_vals = ann["gross_margin"].dropna().tolist()
    if len(gm_vals) >= 2 and gm_vals[-1] < gm_vals[-2] - 0.02:
        flags.append(f"Gross margin compressed {(gm_vals[-1]-gm_vals[-2]):.1%} — check pricing power and cost trends.")

    # FCF vs net income divergence
    latest = ann.iloc[-1]
    if latest.get("fcf") and latest.get("net_income"):
        if latest["fcf"] < latest["net_income"] * 0.6:
            flags.append("FCF significantly below net income — high accruals or heavy capex cycle. Verify sustainability.")
        elif latest["fcf"] > latest["net_income"] * 1.4:
            flags.append("FCF significantly above net income — strong cash conversion, non-cash charges boosting cash flow.")

    # ROIC trend
    roic_vals = ann["roic"].dropna().tolist()
    if len(roic_vals) >= 2 and roic_vals[-1] < roic_vals[-2] - 0.03:
        flags.append(f"ROIC declining ({roic_vals[-2]:.1%} → {roic_vals[-1]:.1%}) — capital efficiency deteriorating.")

    if flags:
        a('<p style="font-weight:600;margin:14px 0 6px">Trend Flags</p>')
        a('<div style="background:#fffbf0;border-left:3px solid #f39c12;padding:12px 14px;border-radius:0 6px 6px 0;font-size:13px;color:#444">')
        for f_item in flags:
            a(f'<div style="margin-bottom:4px">🟡 {f_item}</div>')
        a('</div>')

    # ── INTRINSIC VALUE CALCULATOR ────────────────────────────
    # Build historical context for slider defaults
    eps_hist = [(r["period"][:4], r["eps"]) for _, r in ann.iterrows()
                if r.get("eps") and r["eps"] > 0]
    fcf_hist = [(r["period"][:4], r["fcf"]) for _, r in ann.iterrows()
                if r.get("fcf") and r["fcf"] > 0]
    rev_hist = [(r["period"][:4], r["revenue"]) for _, r in ann.iterrows()
                if r.get("revenue")]

    eps_fwd_def   = round(p.get("eps_fwd") or (eps_hist[-1][1]*1.1 if eps_hist else 5), 2)
    fcf_def       = round((fcf_hist[-1][1] if fcf_hist else 1000), 0)
    gr_def        = round((p.get("eps_cagr") or 0.10) * 100, 1)
    pe_def        = round(p.get("pe_fwd") or 20, 1)
    shares_def    = round(p.get("shares_m") or 1000, 0)
    price_now     = round(p.get("price") or 100, 2)
    dr_def        = 9.0

    eps_hist_str  = " | ".join([f"{y}: ${v:.2f}" for y, v in eps_hist[-5:]])
    fcf_hist_str  = " | ".join([f"{y}: {_fmt_m(v)}" for y, v in fcf_hist[-5:]])

    # Interactive calculator via JS
    calc_html = f"""
<div style="margin-top:16px">
<p style="font-weight:600;margin:0 0 4px">Intrinsic Value Calculator</p>
<p style="color:#888;font-size:12px;margin-bottom:12px">
Adjust the sliders to model different scenarios.
All inputs are editable — defaults are based on historical data and consensus estimates.
Both methods should give similar answers if assumptions are consistent.
</p>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">

<!-- METHOD A: DCF -->
<div style="background:#f8f9fa;border-radius:8px;padding:16px">
<p style="font-weight:600;margin:0 0 8px;color:#1a1a2e">Method A — DCF (FCF-based)</p>
<p style="color:#888;font-size:11px;margin-bottom:12px">
Historical FCF: {fcf_hist_str}
</p>

<div class="slider-group">
  <label class="slabel">Base FCF ($m): <span id="fcf_disp">{fcf_def:.0f}</span></label>
  <input type="range" id="fcf_sl" min="{max(100,fcf_def*0.3):.0f}" max="{fcf_def*3:.0f}"
         step="{max(100,fcf_def*0.05):.0f}" value="{fcf_def:.0f}"
         oninput="upd_dcf()">
</div>
<div class="slider-group">
  <label class="slabel">Growth yr 1-5 (%): <span id="g1_disp">{gr_def:.1f}</span></label>
  <input type="range" id="g1_sl" min="0" max="40" step="0.5" value="{gr_def:.1f}"
         oninput="upd_dcf()">
</div>
<div class="slider-group">
  <label class="slabel">Growth yr 6-10 (%): <span id="g2_disp">{max(2,gr_def*0.6):.1f}</span></label>
  <input type="range" id="g2_sl" min="0" max="25" step="0.5" value="{max(2,gr_def*0.6):.1f}"
         oninput="upd_dcf()">
</div>
<div class="slider-group">
  <label class="slabel">Terminal growth (%): <span id="tg_disp">2.5</span></label>
  <input type="range" id="tg_sl" min="0" max="5" step="0.1" value="2.5"
         oninput="upd_dcf()">
</div>
<div class="slider-group">
  <label class="slabel">Discount rate (%): <span id="dr_disp">{dr_def}</span></label>
  <input type="range" id="dr_sl" min="6" max="15" step="0.5" value="{dr_def}"
         oninput="upd_dcf()">
</div>
<div class="slider-group">
  <label class="slabel">Shares out (m): <span id="sh_disp">{shares_def:.0f}</span></label>
  <input type="range" id="sh_sl" min="{max(100,shares_def*0.5):.0f}"
         max="{shares_def*1.5:.0f}" step="{max(10,shares_def*0.02):.0f}"
         value="{shares_def:.0f}" oninput="upd_dcf()">
</div>
<div style="margin-top:14px;padding:12px;background:white;border-radius:6px;text-align:center">
  <div style="font-size:11px;color:#888">DCF Intrinsic Value / Share</div>
  <div id="dcf_val" style="font-size:28px;font-weight:700;color:#1a1a2e">—</div>
  <div id="dcf_mos" style="font-size:13px;margin-top:4px">—</div>
</div>
</div>

<!-- METHOD B: EPS Multiple -->
<div style="background:#f8f9fa;border-radius:8px;padding:16px">
<p style="font-weight:600;margin:0 0 8px;color:#1a1a2e">Method B — EPS × Exit Multiple</p>
<p style="color:#888;font-size:11px;margin-bottom:12px">
Historical EPS: {eps_hist_str}
</p>

<div class="slider-group">
  <label class="slabel">Forward EPS ($): <span id="eps_disp">{eps_fwd_def:.2f}</span></label>
  <input type="range" id="eps_sl" min="{max(0.1,eps_fwd_def*0.3):.2f}"
         max="{eps_fwd_def*3:.2f}" step="0.01" value="{eps_fwd_def:.2f}"
         oninput="upd_eps()">
</div>
<div class="slider-group">
  <label class="slabel">EPS growth 5yr (%): <span id="eg_disp">{gr_def:.1f}</span></label>
  <input type="range" id="eg_sl" min="0" max="40" step="0.5" value="{gr_def:.1f}"
         oninput="upd_eps()">
</div>
<div class="slider-group">
  <label class="slabel">Exit P/E (x): <span id="pe_disp">{pe_def:.1f}</span></label>
  <input type="range" id="pe_sl" min="5" max="60" step="0.5" value="{pe_def:.1f}"
         oninput="upd_eps()">
</div>
<div class="slider-group">
  <label class="slabel">Discount rate (%): <span id="dr2_disp">{dr_def}</span></label>
  <input type="range" id="dr2_sl" min="6" max="15" step="0.5" value="{dr_def}"
         oninput="upd_eps()">
</div>
<div style="margin-top:60px;padding:12px;background:white;border-radius:6px;text-align:center">
  <div style="font-size:11px;color:#888">EPS Intrinsic Value / Share</div>
  <div id="eps_val" style="font-size:28px;font-weight:700;color:#1a1a2e">—</div>
  <div id="eps_mos" style="font-size:13px;margin-top:4px">—</div>
</div>
</div>

</div><!-- end grid -->

<!-- Consensus -->
<div id="consensus" style="margin-top:12px;padding:12px;background:#f0f4ff;
     border-radius:8px;text-align:center;font-size:13px;color:#444">
  Adjust sliders to see consensus
</div>

<!-- Current price reference -->
<p style="text-align:center;color:#888;font-size:12px;margin-top:8px">
  Current price: <strong>${price_now:.2f}</strong>
</p>
</div>

<style>
.slider-group {{ margin-bottom:10px }}
.slabel {{ font-size:12px;color:#555;display:block;margin-bottom:3px }}
input[type=range] {{ width:100%;accent-color:#1a1a2e }}
</style>

<script>
var PRICE = {price_now};

function upd_dcf() {{
  var fcf = parseFloat(document.getElementById("fcf_sl").value);
  var g1  = parseFloat(document.getElementById("g1_sl").value) / 100;
  var g2  = parseFloat(document.getElementById("g2_sl").value) / 100;
  var tg  = parseFloat(document.getElementById("tg_sl").value) / 100;
  var dr  = parseFloat(document.getElementById("dr_sl").value) / 100;
  var sh  = parseFloat(document.getElementById("sh_sl").value);

  document.getElementById("fcf_disp").textContent = Math.round(fcf).toLocaleString();
  document.getElementById("g1_disp").textContent  = (g1*100).toFixed(1);
  document.getElementById("g2_disp").textContent  = (g2*100).toFixed(1);
  document.getElementById("tg_disp").textContent  = (tg*100).toFixed(1);
  document.getElementById("dr_disp").textContent  = (dr*100).toFixed(1);
  document.getElementById("sh_disp").textContent  = Math.round(sh).toLocaleString();

  // 10-year DCF
  var pv = 0;
  var cf = fcf;
  for (var i = 1; i <= 5; i++) {{
    cf *= (1 + g1);
    pv += cf / Math.pow(1 + dr, i);
  }}
  for (var i = 6; i <= 10; i++) {{
    cf *= (1 + g2);
    pv += cf / Math.pow(1 + dr, i);
  }}
  // Terminal value
  var tv = cf * (1 + tg) / (dr - tg);
  pv += tv / Math.pow(1 + dr, 10);

  var per_share = pv / sh;
  var mos = (per_share - PRICE) / per_share;

  document.getElementById("dcf_val").textContent =
    "$" + per_share.toFixed(2);
  var mos_el = document.getElementById("dcf_mos");
  mos_el.textContent = "MOS: " + (mos*100).toFixed(1) + "%";
  mos_el.style.color = mos >= 0.15 ? "#27ae60" : mos >= 0 ? "#f39c12" : "#e74c3c";

  upd_consensus();
}}

function upd_eps() {{
  var eps = parseFloat(document.getElementById("eps_sl").value);
  var eg  = parseFloat(document.getElementById("eg_sl").value) / 100;
  var pe  = parseFloat(document.getElementById("pe_sl").value);
  var dr  = parseFloat(document.getElementById("dr2_sl").value) / 100;

  document.getElementById("eps_disp").textContent = eps.toFixed(2);
  document.getElementById("eg_disp").textContent  = (eg*100).toFixed(1);
  document.getElementById("pe_disp").textContent  = pe.toFixed(1);
  document.getElementById("dr2_disp").textContent = (dr*100).toFixed(1);

  // EPS × exit multiple discounted back 5 years
  var eps5 = eps * Math.pow(1 + eg, 5);
  var price5 = eps5 * pe;
  var iv = price5 / Math.pow(1 + dr, 5);
  var mos = (iv - PRICE) / iv;

  document.getElementById("eps_val").textContent = "$" + iv.toFixed(2);
  var mos_el = document.getElementById("eps_mos");
  mos_el.textContent = "MOS: " + (mos*100).toFixed(1) + "%";
  mos_el.style.color = mos >= 0.15 ? "#27ae60" : mos >= 0 ? "#f39c12" : "#e74c3c";

  upd_consensus();
}}

function upd_consensus() {{
  var dcf_el = document.getElementById("dcf_val");
  var eps_el = document.getElementById("eps_val");
  var con    = document.getElementById("consensus");

  var dcf_v = parseFloat(dcf_el.textContent.replace("$",""));
  var eps_v = parseFloat(eps_el.textContent.replace("$",""));

  if (isNaN(dcf_v) || isNaN(eps_v)) return;

  var diff = Math.abs(dcf_v - eps_v) / Math.max(dcf_v, eps_v);
  var avg  = (dcf_v + eps_v) / 2;
  var mos  = (avg - PRICE) / avg;

  if (diff < 0.15) {{
    con.style.background = "#e8f5e9";
    con.innerHTML = "✅ <strong>Methods agree</strong> — avg value $" +
      avg.toFixed(2) + " | MOS " + (mos*100).toFixed(1) + "%";
  }} else if (dcf_v > eps_v * 1.5) {{
    con.style.background = "#fffbf0";
    con.innerHTML = "🟡 <strong>DCF significantly higher than EPS method</strong> — " +
      "check FCF growth assumptions or exit P/E";
  }} else {{
    con.style.background = "#fffbf0";
    con.innerHTML = "🟡 <strong>Methods diverge by " + (diff*100).toFixed(0) +
      "%</strong> — align growth assumptions for consistency";
  }}
}}

// Store defaults for reset
var DEFAULTS = {{
  fcf_sl: {fcf_def:.0f}, g1_sl: {gr_def:.1f}, g2_sl: {max(2,gr_def*0.6):.1f},
  tg_sl: 2.5, dr_sl: {dr_def}, sh_sl: {shares_def:.0f},
  eps_sl: {eps_fwd_def:.2f}, eg_sl: {gr_def:.1f},
  pe_sl: {pe_def:.1f}, dr2_sl: {dr_def}
}};

function resetSliders() {{
  Object.keys(DEFAULTS).forEach(function(id) {{
    var el = document.getElementById(id);
    if (el) el.value = DEFAULTS[id];
  }});
  upd_dcf();
  upd_eps();
}}

// Initialise on load
upd_dcf();
upd_eps();
</script>
"""

    a(calc_html)
    a('</div>')
    return "".join(rows)


print("standard.py loaded.")
print("Primary function: generate_standard_html(ticker)")
print("Data function:    fetch_standard_data(ticker)")
