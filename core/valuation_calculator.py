import warnings
import requests
import pandas as pd
import numpy as np
import yfinance as yf
warnings.filterwarnings("ignore")


# ============================================================
# BOOK VALUATION CALCULATOR — EPS-BASED FAIR VALUE
#
# Based on the study guide valuation calculator.
# Uses EPS CAGR triangulation and P/E exit multiple method.
#
# This complements the Penman & Pope residual earnings model
# in report.py — two independent valuation methodologies.
#
# Primary function: run_eps_valuation(ticker)
# Returns: dict with all metrics + HTML string
# ============================================================

EDGAR_HEADERS = {"User-Agent": "FSA Engine research@example.com"}

CONCEPT_MAP = {
    "eps":        ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "total_assets":["Assets"],
    "equity":     ["StockholdersEquity",
                   "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash":       ["CashAndCashEquivalentsAtCarryingValue",
                   "CashCashEquivalentsAndShortTermInvestments"],
    "ebit":       ["OperatingIncomeLoss"],
    "tax":        ["IncomeTaxExpenseBenefit"],
    "dna":        ["DepreciationDepletionAndAmortization",
                   "DepreciationAndAmortization"],
}

DEBT_CONCEPTS = [
    "LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtCurrent",
    "DebtCurrent", "ShortTermBorrowings", "CommercialPaper",
    "NotesPayableCurrent", "LongTermNotesPayable",
]


# ── DATA FETCH ───────────────────────────────────────────────

def _get_cik(ticker):
    r = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=EDGAR_HEADERS, timeout=15
    )
    for e in r.json().values():
        if e.get("ticker", "").upper() == ticker.upper():
            return str(e["cik_str"]).zfill(10)
    raise ValueError(f"Ticker {ticker!r} not found in SEC EDGAR.")


def _get_facts(cik):
    return requests.get(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
        headers=EDGAR_HEADERS, timeout=30
    ).json()


def _annual_series(facts, concept, n=9):
    try:
        recs = list(
            facts["facts"]["us-gaap"][concept]["units"].values()
        )[0]
        annual = [r for r in recs
                  if r.get("form") in ("10-K", "10-K/A")
                  and r.get("fp") == "FY"]
        if not annual:
            annual = [r for r in recs
                      if r.get("form") in ("10-K", "10-K/A")]
        by_yr = {}
        for r in sorted(annual, key=lambda x: x.get("filed", "")):
            yr = r.get("end", "")[:4]
            if yr and r.get("val") is not None:
                by_yr[yr] = float(r["val"])
        s = pd.Series(by_yr).sort_index()
        return s.iloc[-n:] if len(s) >= n else s
    except Exception:
        return pd.Series(dtype=float)


def _try_concepts(facts, concepts):
    for c in concepts:
        s = _annual_series(facts, c)
        if not s.empty:
            return s
    return pd.Series(dtype=float)


def _total_debt_series(facts):
    by_yr = {}
    for concept in DEBT_CONCEPTS:
        s = _annual_series(facts, concept)
        for yr, v in s.items():
            by_yr[yr] = by_yr.get(yr, 0.0) + v
    return pd.Series(by_yr).sort_index() if by_yr else pd.Series(dtype=float)


def _yf_get(df, *names):
    if df is None or df.empty:
        return None
    idx = [str(i).lower().replace(" ", "").replace("_", "")
           for i in df.index]
    for n in names:
        t = n.lower().replace(" ", "").replace("_", "")
        for i, x in enumerate(idx):
            if t in x or x in t:
                try:
                    v = df.iloc[i, 0]
                    if pd.notna(v):
                        return float(v)
                except Exception:
                    continue
    return None


def _latest(s, fb=None):
    if s is None or (isinstance(s, pd.Series) and s.empty):
        return fb
    for v in reversed(
        list(s.values if isinstance(s, pd.Series) else [s])
    ):
        if v is not None and not pd.isna(v):
            return float(v)
    return fb


def _resolve(edgar_s, yf_df, *names):
    v = _latest(edgar_s)
    if v is not None:
        return v
    return _yf_get(yf_df, *names)


# ── CALCULATIONS ─────────────────────────────────────────────

def _sdiv(a, b):
    try:
        if a is None or b is None:
            return None
        a, b = float(a), float(b)
        if np.isnan(a) or np.isnan(b) or b == 0:
            return None
        return a / b
    except Exception:
        return None


def _cagr(s, e, n):
    try:
        if any(v is None or v <= 0 for v in [s, e, n]):
            return None
        return (e / s) ** (1.0 / n) - 1.0
    except Exception:
        return None


def _pe_mult(g):
    g = (g or 0) * 100
    if g >= 20: return 32
    if g >= 15: return 26
    if g >= 12: return 22
    if g >= 9:  return 18
    if g >= 6:  return 15
    return 12


def _signal(mos):
    if mos is None:    return "N/A"
    if mos >= 0.30:    return "STRONG BUY"
    if mos >= 0.20:    return "BUY"
    if mos >= 0.10:    return "WATCH"
    if mos >= 0.00:    return "FAIR VALUE"
    return "EXPENSIVE"


def _build_cagr(eps_s):
    if (eps_s is None or not isinstance(eps_s, pd.Series)
            or eps_s.empty or len(eps_s) < 3):
        return {}, pd.Series(dtype=float)

    yrs  = list(eps_s.index)
    vals = [float(v) for v in eps_s.values]
    pos  = [(y, v) for y, v in zip(yrs, vals) if v > 0]
    if len(pos) < 2:
        return {}, eps_s

    med   = float(np.median([v for _, v in pos]))
    thr   = med * 0.15
    clean = [(y, v) for y, v in pos if v >= thr]
    if len(clean) < 2:
        clean = pos

    periods = {}
    y0, v0 = clean[0]
    yn, vn = clean[-1]
    n = len(clean) - 1

    if n > 0:
        periods["Full Period"] = dict(
            start_year=y0, end_year=yn,
            start_eps=v0, end_eps=vn, years=n,
            rate=_cagr(v0, vn, n),
            formula=f"({vn:.2f}/{v0:.2f})^(1/{n})-1"
        )
    mid = len(clean) // 2
    if mid >= 2:
        ym, vm = clean[mid - 1]
        periods["First Half"] = dict(
            start_year=y0, end_year=ym,
            start_eps=v0, end_eps=vm, years=mid - 1,
            rate=_cagr(v0, vm, mid - 1),
            formula=f"({vm:.2f}/{v0:.2f})^(1/{mid-1})-1"
        )
    if mid < len(clean) - 1:
        ys, vs = clean[mid]
        n2 = len(clean) - 1 - mid
        periods["Second Half"] = dict(
            start_year=ys, end_year=yn,
            start_eps=vs, end_eps=vn, years=n2,
            rate=_cagr(vs, vn, n2),
            formula=f"({vn:.2f}/{vs:.2f})^(1/{n2})-1"
        )
    if len(clean) >= 4:
        y3, v3 = clean[-4]
        periods["Last 3 Yrs"] = dict(
            start_year=y3, end_year=yn,
            start_eps=v3, end_eps=vn, years=3,
            rate=_cagr(v3, vn, 3),
            formula=f"({vn:.2f}/{v3:.2f})^(1/3)-1"
        )

    return periods, pd.Series(dict(clean)).sort_index()


# ── MAIN CALCULATION ─────────────────────────────────────────

def run_eps_valuation(ticker: str) -> dict:
    """
    Run EPS-based valuation for any US ticker.

    Returns dict with:
        metrics   — all calculated values
        html      — formatted HTML section for embedding in report
    """
    ticker = ticker.upper()

    # Fetch Yahoo Finance data
    try:
        yft  = yf.Ticker(ticker)
        info = yft.info
        try:    inc = yft.income_stmt
        except: inc = yft.financials
        try:    cf  = yft.cash_flow
        except: cf  = yft.cashflow
        bal  = yft.balance_sheet
        hist = yft.history(period="5y", interval="1mo")
    except Exception:
        info, inc, bal, cf, hist = (
            {}, pd.DataFrame(), pd.DataFrame(),
            pd.DataFrame(), pd.DataFrame()
        )

    # Fetch SEC EDGAR data
    edgar = {k: pd.Series(dtype=float)
             for k in list(CONCEPT_MAP.keys()) + ["total_debt"]}
    company_name = info.get("longName", ticker)

    try:
        cik   = _get_cik(ticker)
        facts = _get_facts(cik)
        company_name = facts.get("entityName", company_name)
        for k, v in CONCEPT_MAP.items():
            edgar[k] = _try_concepts(facts, v)
        edgar["total_debt"] = _total_debt_series(facts)
    except Exception:
        pass

    R = {}
    R["ticker"]       = ticker
    R["company_name"] = company_name
    R["price"]        = (info.get("currentPrice")
                         or info.get("regularMarketPrice"))
    R["mktcap"]       = info.get("marketCap")
    R["52h"]          = info.get("fiftyTwoWeekHigh")
    R["52l"]          = info.get("fiftyTwoWeekLow")
    R["sector"]       = info.get("sector", "N/A")
    R["beta"]         = info.get("beta")
    R["divy"]         = info.get("dividendYield") or 0
    R["eps_ttm"]      = info.get("trailingEps")
    R["eps_fwd"]      = info.get("forwardEps")
    R["pe_ttm"]       = _sdiv(R["price"], R["eps_ttm"])
    R["pe_fwd"]       = _sdiv(R["price"], R["eps_fwd"])

    ni   = _resolve(edgar["net_income"],   inc, "Net Income")
    ta   = _resolve(edgar["total_assets"], bal, "Total Assets")
    eq   = _resolve(edgar["equity"],       bal,
                    "Stockholders Equity", "Total Stockholder Equity")
    ebit = _resolve(edgar["ebit"],         inc,
                    "Operating Income", "Ebit")
    tax  = _resolve(edgar["tax"],          inc,
                    "Tax Provision", "Income Tax Expense")
    cash = _resolve(edgar["cash"],         bal,
                    "Cash And Cash Equivalents")
    dna  = _resolve(edgar["dna"],          cf,
                    "Depreciation And Amortization", "Depreciation")

    # Debt
    td_edgar = _latest(edgar["total_debt"])
    td_yf    = _yf_get(bal, "Total Debt",
                        "Long Term Debt And Capital Lease Obligation",
                        "Long Term Debt")
    if td_edgar and td_yf and td_edgar < td_yf * 0.5:
        td = td_yf
    elif td_edgar:
        td = td_edgar
    elif td_yf:
        td = td_yf
    else:
        td = None

    R.update(net_income=ni, total_assets=ta, equity=eq,
             ebit=ebit, cash=cash, total_debt=td, dna=dna)
    R["roa"]  = _sdiv(ni, ta)
    R["roe"]  = _sdiv(ni, eq)

    pbt   = (ni + tax) if (ni and tax) else ebit
    tr    = max(0.0, min(0.5, _sdiv(tax, pbt) or 0.21))
    nopat = (ebit * (1 - tr)) if ebit is not None else None
    ic    = ((eq + td - (cash or 0))
             if (eq is not None and td is not None) else None)
    R.update(tax_rate=tr, nopat=nopat, invested_capital=ic)
    R["roic"] = _sdiv(nopat, ic)
    R["de"]   = _sdiv(td, eq)

    ebitda = ((ebit + dna) if (ebit is not None and dna is not None)
              else None)
    nd     = ((td - cash) if (td is not None and cash is not None)
              else None)
    R.update(ebitda=ebitda, net_debt=nd)
    R["nde"] = _sdiv(nd, ebitda)

    # P/E history
    eps_s = edgar["eps"]
    peh   = []
    if not eps_s.empty and not hist.empty:
        for yr_str, ev in eps_s.iloc[-5:].items():
            try:
                yr = int(yr_str)
                yp = hist[hist.index.year == yr]["Close"]
                if len(yp) > 0 and ev and float(ev) > 0:
                    peh.append(
                        (yr_str, round(float(yp.mean()) / float(ev), 1))
                    )
            except Exception:
                pass
    R["pe5avg"] = float(np.mean([p for _, p in peh])) if peh else None
    R["peh"]    = peh

    # CAGR
    periods, clean = _build_cagr(eps_s)
    R["periods"]   = periods
    R["eps_full"]  = eps_s
    R["eps_clean"] = clean
    rates = [c["rate"] for c in periods.values()
             if c.get("rate") and c["rate"] > 0]
    R["cagr_c"] = min(rates)            if rates else None
    R["cagr_m"] = float(np.median(rates)) if rates else None
    R["cagr_o"] = max(rates)            if rates else None

    # Implied growth
    R["imp1"] = (
        _sdiv((R["eps_fwd"] or 0) - (R["eps_ttm"] or 0), R["eps_ttm"])
        if (R.get("eps_fwd") and R.get("eps_ttm")
            and R["eps_ttm"] > 0)
        else None
    )

    # Fair value scenarios
    be  = R["eps_ttm"] or R["eps_fwd"]
    pr  = R["price"]
    fvs = {}
    for name, g in [("Conservative", R["cagr_c"]),
                    ("Median",        R["cagr_m"]),
                    ("Optimistic",    R["cagr_o"])]:
        if g and g > 0:
            m   = _pe_mult(g)
            fv  = be * m if be is not None else None
            mos = _sdiv((fv or 0) - (pr or 0), fv) if (fv and pr) else None
            fvs[name] = dict(
                growth=g, multiple=m, base_eps=be,
                fair_value=fv, mos=mos, signal=_signal(mos),
                fv5=(be * ((1 + g) ** 5) * _pe_mult(g * 0.7)
                     if be is not None else None)
            )
    R["fvs"]   = fvs
    R["be"]    = be
    fvl        = [v["fair_value"] for v in fvs.values()
                  if v.get("fair_value")]
    R["fvlo"]  = min(fvl) if fvl else None
    R["fvhi"]  = max(fvl) if fvl else None
    R["moslo"] = (_sdiv((R["fvlo"] or 0) - (pr or 0), R["fvlo"])
                  if R.get("fvlo") and pr else None)
    R["moshi"] = (_sdiv((R["fvhi"] or 0) - (pr or 0), R["fvhi"])
                  if R.get("fvhi") and pr else None)

    # Generate HTML
    R["html"] = _render_html(R)
    return R


# ── HTML RENDERER ────────────────────────────────────────────

def _fmt(v, prefix="", suffix="", d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{prefix}{v:,.{d}f}{suffix}"

def _usd(v):   return _fmt(v, "$")
def _pct(v):   return f"{v*100:.1f}%" if v is not None else "—"
def _xm(v):    return _fmt(v, suffix="x")
def _bn(v):    return _fmt(v/1e9, "$", "B") if v else "—"

SIG_COLORS = {
    "STRONG BUY": "#27ae60",
    "BUY":        "#2ecc71",
    "WATCH":      "#f39c12",
    "FAIR VALUE": "#3498db",
    "EXPENSIVE":  "#e74c3c",
    "N/A":        "#95a5a6",
}

def _sig_badge(sig):
    color = SIG_COLORS.get(sig, "#95a5a6")
    return (f'<span style="background:{color};color:white;'
            f'padding:3px 10px;border-radius:12px;'
            f'font-size:12px;font-weight:600">{sig}</span>')


def _render_html(R: dict) -> str:
    """Render the EPS valuation as an HTML section."""
    rows = []
    a = rows.append

    a('<div style="font-family:-apple-system,sans-serif;'
      'color:#2c3e50;font-size:14px">')

    # ── Part 1: Snapshot ─────────────────────────────────────
    a('<p style="color:#666;font-size:12px;margin-bottom:12px">')
    a('EPS-based valuation using historical CAGR triangulation ')
    a('and P/E exit multiples. Complements the Penman &amp; Pope ')
    a('residual earnings model above.</p>')

    a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<thead><tr>')
    for h in ["Metric", "Value", "Benchmark"]:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;'
          f'text-align:left;font-weight:500;font-size:12px;'
          f'color:#555;border-bottom:2px solid #ddd">{h}</th>')
    a('</tr></thead><tbody>')

    def qrow(label, val, fmt_fn, benchmark, lo, mid, hi,
             rev=False):
        if val is None:
            color = "#95a5a6"
        elif not rev:
            color = ("#27ae60" if val >= hi
                     else "#f39c12" if val >= mid
                     else "#e74c3c")
        else:
            color = ("#27ae60" if val <= lo
                     else "#f39c12" if val <= mid
                     else "#e74c3c")
        return (
            f'<tr><td style="padding:8px 10px;border-bottom:'
            f'1px solid #f0f2f5">{label}</td>')  + (
            f'<td style="padding:8px 10px;border-bottom:'
            f'1px solid #f0f2f5;font-weight:600;color:{color}">')  + (
            fmt_fn(val) + '</td>')  + (
            f'<td style="padding:8px 10px;border-bottom:'
            f'1px solid #f0f2f5;color:#888;font-size:12px">')  + (
            benchmark + '</td></tr>')

    a(qrow("ROA",  R.get("roa"),  _pct, "Good >8%",    .05,.08,.12))
    a(qrow("ROE",  R.get("roe"),  _pct, "Good >15%",   .10,.15,.20))
    a(qrow("ROIC", R.get("roic"), _pct, "Above WACC",  .08,.10,.15))
    a(qrow("D/E",  R.get("de"),   _xm,  "Strong <0.5x",.5,1.0,2.0, rev=True))
    a(qrow("Net Debt/EBITDA", R.get("nde"), _xm,
           "Healthy <2x", 2.0,3.5,5.0, rev=True))
    a('</tbody></table>')

    # P/E table
    a('<p style="font-weight:600;margin:14px 0 8px">P/E Variants</p>')
    a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<thead><tr>')
    for h in ["Variant", "Value", "Note"]:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;'
          f'text-align:left;font-weight:500;font-size:12px;'
          f'color:#555">{h}</th>')
    a('</tr></thead><tbody>')
    for lbl, val, note in [
        ("TTM",     R.get("pe_ttm"),  "Last 12 months EPS"),
        ("Forward", R.get("pe_fwd"),  "Consensus next 12m estimate"),
        ("5yr Avg", R.get("pe5avg"),  "Historical mean — reversion reference"),
    ]:
        a(f'<tr><td style="padding:8px 10px;border-bottom:1px solid #f0f2f5">{lbl}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;'
          f'font-weight:600;color:#e67e22">{_xm(val)}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;'
          f'color:#888;font-size:12px">{note}</td></tr>')
    for yr, pe in (R.get("peh") or []):
        a(f'<tr><td style="padding:6px 10px;color:#888">  ↳ {yr}</td>')
        a(f'<td style="padding:6px 10px;color:#888">{_xm(pe)}</td>')
        a(f'<td style="padding:6px 10px;color:#888;font-size:12px">Annual avg / EPS</td></tr>')
    a('</tbody></table>')

    # ── Part 2: CAGR ─────────────────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 8px">EPS CAGR Triangulation</p>')
    eps_s = R.get("eps_full", pd.Series())
    if not eps_s.empty:
        a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px">')
        a('<tr>')
        for yr in eps_s.index:
            a(f'<th style="background:#f0f2f5;padding:6px 8px;'
              f'font-size:11px;color:#555;text-align:center">{yr}</th>')
        a('</tr><tr>')
        for v in eps_s.values:
            a(f'<td style="padding:6px 8px;text-align:center;'
              f'font-weight:600;color:#e67e22;font-size:13px">'
              f'{_usd(float(v))}</td>')
        a('</tr></table>')

    a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<thead><tr>')
    for h in ["Period", "Start EPS", "End EPS", "Years", "CAGR", "Formula"]:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;'
          f'text-align:left;font-weight:500;font-size:12px;color:#555">{h}</th>')
    a('</tr></thead><tbody>')
    for pn, c in (R.get("periods") or {}).items():
        g = c.get("rate")
        color = ("#27ae60" if g and g >= 0.15
                 else "#f39c12" if g and g >= 0.08
                 else "#e74c3c" if g else "#95a5a6")
        a(f'<tr>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;font-weight:600">{pn}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#888">{_usd(c["start_eps"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#888">{_usd(c["end_eps"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#888">{c["years"]}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;'
          f'font-weight:600;color:{color}">{_pct(g)}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;'
          f'color:#888;font-size:11px">{c.get("formula","")}</td>')
        a(f'</tr>')

    # Summary CAGR rows
    for label, val, color in [
        ("Conservative (anchor)", R.get("cagr_c"), "#27ae60"),
        ("Median",                R.get("cagr_m"), "#e67e22"),
        ("Optimistic",            R.get("cagr_o"), "#e74c3c"),
    ]:
        a(f'<tr style="background:#f8f9fa">')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;'
          f'font-weight:600">{label}</td>')
        a(f'<td colspan="3" style="padding:8px 10px;border-bottom:1px solid #f0f2f5"></td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;'
          f'font-weight:600;color:{color}">{_pct(val)}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;'
          f'color:#888;font-size:12px">')
        if label == "Conservative (anchor)":
            a("Lowest positive — recommended anchor")
        elif label == "Median":
            a("Median across all periods")
        else:
            a("Highest rate — optimistic scenario")
        a('</td></tr>')
    a('</tbody></table>')

    # ── Part 3: Fair Value ────────────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 8px">Fair Value Scenarios</p>')
    a(f'<p style="color:#888;font-size:12px;margin-bottom:10px">')
    a(f'Base EPS: <strong style="color:#e67e22">{_usd(R.get("be"))}</strong>')
    a(f' &nbsp;|&nbsp; Current Price: <strong>{_usd(R.get("price"))}</strong>')
    a(f' &nbsp;|&nbsp; Formula: Base EPS × Exit Multiple</p>')

    a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<thead><tr>')
    for h in ["Scenario","Growth","Multiple","Fair Value","5yr FV","MOS","Signal"]:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;'
          f'text-align:left;font-weight:500;font-size:12px;color:#555">{h}</th>')
    a('</tr></thead><tbody>')
    for sc, fv in (R.get("fvs") or {}).items():
        sig   = fv["signal"]
        color = SIG_COLORS.get(sig, "#95a5a6")
        mos   = fv.get("mos")
        mc    = ("#27ae60" if mos and mos >= 0.20
                 else "#f39c12" if mos and mos >= 0.10
                 else "#e74c3c" if mos is not None else "#95a5a6")
        a(f'<tr>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;font-weight:600">{sc}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#888">{_pct(fv["growth"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#e67e22">{fv["multiple"]}x</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;font-weight:600">{_usd(fv["fair_value"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#888">{_usd(fv.get("fv5"))}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;'
          f'font-weight:600;color:{mc}">{_pct(mos)}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5">{_sig_badge(sig)}</td>')
        a('</tr>')
    a('</tbody></table>')

    # Summary box
    if R.get("fvlo") and R.get("price"):
        ls = _signal(R.get("moslo"))
        hs = _signal(R.get("moshi"))
        lc = SIG_COLORS.get(ls, "#95a5a6")
        hc = SIG_COLORS.get(hs, "#95a5a6")
        a('<div style="background:#f0f8f0;border-left:3px solid #27ae60;'
          'padding:12px 16px;border-radius:0 6px 6px 0;line-height:2">')
        a(f'<strong>Current Price:</strong> {_usd(R["price"])} &nbsp;|&nbsp; ')
        a(f'<strong>Fair Value Range:</strong> ')
        a(f'<span style="color:#27ae60">{_usd(R["fvlo"])} — {_usd(R["fvhi"])}</span>')
        a(f' &nbsp;|&nbsp; ')
        a(f'<strong>MOS Range:</strong> {_pct(R.get("moslo"))} — {_pct(R.get("moshi"))}')
        a(f' &nbsp;|&nbsp; ')
        a(f'{_sig_badge(ls)} — {_sig_badge(hs)}')
        a('</div>')

    a('</div>')
    return "".join(rows)


print("valuation_calculator.py loaded.")
print("Primary function: run_eps_valuation(ticker)")
print("Returns: dict with metrics + html key")
