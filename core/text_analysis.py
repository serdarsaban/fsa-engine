import re
import json
import requests


HEADERS = {"User-Agent": "FSA Engine research@example.com"}

ANNUAL_PROMPT = """You are a professional equity analyst. Analyse this 10-K annual report.
Return valid JSON only — no markdown, no backticks, no preamble.
{
  "filing_type": "10-K", "period": "",
  "company_overview": {"business_description": "", "headquarters": "", "employees": ""},
  "business_segments": [{"name": "", "description": "", "revenue": "", "revenue_pct": ""}],
  "products_services": [{"name": "", "description": "", "revenue_contribution": ""}],
  "customers": {"description": "", "key_segments": [], "concentration_risk": ""},
  "financials": {"revenue": "", "revenue_growth": "", "gross_margin": "",
    "operating_margin": "", "net_income": "", "eps": "", "fcf": "",
    "cash_and_equivalents": "", "total_debt": "", "expense_highlights": ""},
  "risk_factors": {"business_risks": [], "sector_risks": [],
    "regulatory_risks": [], "legal_risks": [], "macro_risks": []},
  "management_guidance": {"next_quarter": "", "full_year": "", "key_assumptions": []},
  "ma_activity": {"recent_acquisitions": [], "divestitures": [], "pending_deals": []},
  "capital_allocation": {"share_repurchase_program": "", "shares_repurchased": "",
    "dividends": "", "capex": ""},
  "legal_disputes": [],
  "accounting_policies": {"revenue_recognition": "", "notable_changes": []},
  "stock_commentary": "", "key_themes": [], "analyst_flags": []
}
Use actual numbers from the filing. analyst_flags = 5 items to investigate."""

QUARTERLY_PROMPT = """You are a professional equity analyst. Analyse this 10-Q quarterly report.
Focus on CHANGES since the last annual report.
Return valid JSON only — no markdown, no backticks, no preamble.
{
  "filing_type": "10-Q", "period": "", "quarter_summary": "",
  "financials": {"revenue": "", "revenue_growth_yoy": "", "revenue_growth_qoq": "",
    "gross_margin": "", "operating_margin": "", "net_income": "",
    "eps": "", "eps_vs_estimate": "", "fcf": "", "cash_and_equivalents": ""},
  "segment_performance": [{"name": "", "revenue": "", "growth_yoy": "", "commentary": ""}],
  "vs_last_quarter": {"revenue_change": "", "margin_change": "",
    "notable_improvements": [], "notable_deteriorations": []},
  "management_guidance": {"next_quarter": "", "full_year_update": "",
    "key_changes_from_prior_guidance": []},
  "new_risks": [], "legal_updates": [],
  "capital_allocation": {"shares_repurchased_this_quarter": "",
    "dividends_paid": "", "capex": ""},
  "ma_updates": [], "key_themes": [], "analyst_flags": []
}
Use actual numbers. analyst_flags = 5 items that changed materially."""


def get_recent_filings(ticker: str, n: int = 8) -> list:
    from data_fetch import get_cik
    cik  = get_cik(ticker)
    sub  = requests.get(
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        headers=HEADERS
    ).json()
    f        = sub["filings"]["recent"]
    periods  = f.get("reportDate", [""] * len(f["form"]))
    results  = []
    for i, form in enumerate(f["form"]):
        if form not in ("10-K", "10-Q") or len(results) >= n:
            continue
        acc   = f["accessionNumber"][i].replace("-", "")
        c_int = int(cik)
        results.append({
            "form":    form,
            "filed":   f["filingDate"][i],
            "period":  periods[i] if i < len(periods) else "",
            "acc":     acc,
            "cik":     cik,
            "cik_int": c_int,
            "doc":     f["primaryDocument"][i],
            "doc_url": f"https://www.sec.gov/Archives/edgar/data/{c_int}/{acc}/{f['primaryDocument'][i]}",
            "company": sub["name"],
            "label":   f"{form}  {periods[i] if i < len(periods) else ''}  (filed {f['filingDate'][i]})",
        })
    return results


def fetch_and_clean(filing: dict) -> tuple:
    resp = requests.get(filing["doc_url"], headers=HEADERS, timeout=60)
    resp.raise_for_status()
    ct = resp.headers.get("content-type", "")
    if "html" in ct.lower() or filing["doc"].endswith((".htm", ".html")):
        t = resp.content.decode("utf-8", errors="ignore")
        t = re.sub(r"<style[^>]*>.*?</style>", "", t, flags=re.DOTALL)
        t = re.sub(r"<script[^>]*>.*?</script>", "", t, flags=re.DOTALL)
        t = re.sub(r"<[^>]+>", " ", t)
        t = re.sub(r"&nbsp;", " ", t)
        t = re.sub(r"&amp;", "&", t)
        t = re.sub(r"\s+", " ", t).strip()[:400000]
        return t.encode("utf-8"), "text/plain"
    return resp.content, "application/pdf"


def analyse_filing(filing: dict, gemini_client, model: str) -> dict:
    from google.genai import types
    content, mime = fetch_and_clean(filing)
    prompt = ANNUAL_PROMPT if filing["form"] == "10-K" else QUARTERLY_PROMPT
    resp   = gemini_client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=content, mime_type=mime),
            types.Part.from_text(text=prompt),
        ]
    )
    raw = resp.text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*",     "", raw)
    raw = re.sub(r"\s*```$",     "", raw)
    try:
        result = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        result = json.loads(m.group()) if m else {"error": raw[:300]}
    result["_filing"] = filing
    return result


def _card(title, body):
    return (
        '<div style="background:white;border-radius:10px;padding:20px;'
        'margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)">'
        '<h3 style="font-size:15px;font-weight:600;color:#1a1a2e;'
        'margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid #eee">'
        + title + '</h3>' + body + '</div>'
    )

def _kv(label, value, color="#2c3e50"):
    if not value or str(value) in ("N/A", "", "None", "null"):
        return ""
    return (
        '<div style="display:flex;justify-content:space-between;'
        'padding:7px 0;border-bottom:1px solid #f5f5f5;font-size:13px">'
        '<span style="color:#666">' + label + '</span>'
        '<span style="font-weight:600;color:' + color + '">' + str(value) + '</span></div>'
    )

def _bullets(items, color="#444"):
    if not items:
        return '<p style="color:#888;font-size:13px">None identified</p>'
    rows = '<ul style="margin:0;padding-left:18px">'
    for item in items:
        if item:
            rows += '<li style="font-size:13px;color:' + color + ';margin-bottom:5px">' + str(item) + '</li>'
    return rows + '</ul>'

def _amber(content):
    return (
        '<div style="background:#fffbf0;border-left:3px solid #f39c12;'
        'padding:12px 14px;border-radius:0 6px 6px 0;'
        'font-size:13px;color:#444;line-height:1.6">'
        + content + '</div>'
    )

def _seg_table(segs, is_q):
    if not segs:
        return ""
    cols = ["Segment","Revenue","Growth YoY","Commentary"] if is_q else ["Segment","Revenue","% of Total","Description"]
    t  = '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px">'
    t += '<thead><tr>'
    for c in cols:
        t += '<th style="background:#f0f2f5;padding:8px 10px;text-align:left;font-weight:500;color:#555">' + c + '</th>'
    t += '</tr></thead><tbody>'
    for seg in segs:
        t += '<tr>'
        if is_q:
            vals = [seg.get("name",""), seg.get("revenue",""),
                    seg.get("growth_yoy",""), seg.get("commentary","")]
        else:
            vals = [seg.get("name",""), seg.get("revenue",""),
                    seg.get("revenue_pct",""), seg.get("description","")]
        for j, v in enumerate(vals):
            bold = "font-weight:600;" if j == 0 else ""
            small = "font-size:12px;color:#666;" if j == 3 else ""
            t += '<td style="padding:8px 10px;border-bottom:1px solid #f5f5f5;' + bold + small + '">' + str(v) + '</td>'
        t += '</tr>'
    return t + '</tbody></table></div>'


def render_html(data: dict) -> str:
    parts  = []
    f      = data.get("_filing", {})
    is_q   = data.get("filing_type") == "10-Q"
    period = data.get("period", f.get("period", ""))
    co     = f.get("company", "")

    parts.append('<div style="font-family:-apple-system,sans-serif;color:#2c3e50">')

    # Header
    parts.append(
        '<div style="background:#1a1a2e;color:white;padding:20px;'
        'border-radius:10px;margin-bottom:16px">'
        '<h2 style="margin:0;font-size:20px">' + co + '</h2>'
        '<p style="color:#aaa;margin:4px 0 0;font-size:13px">'
        + f.get("form","") + ' · ' + period + ' · Filed ' + f.get("filed","")
        + '</p></div>'
    )

    # Summary / Overview
    if is_q:
        s = data.get("quarter_summary", "")
        if s:
            parts.append(_card("Quarter Summary",
                '<p style="font-size:14px;line-height:1.7">' + s + '</p>'))
    else:
        ov = data.get("company_overview", {})
        if ov.get("business_description"):
            b  = '<p style="font-size:14px;line-height:1.7">' + ov["business_description"] + '</p>'
            b += _kv("Headquarters", ov.get("headquarters"))
            b += _kv("Employees", ov.get("employees"))
            parts.append(_card("Business Overview", b))

    # Financials
    fin = data.get("financials", {})
    if fin:
        fin_rows = [
            ("Revenue",            "revenue",              "#1a1a2e"),
            ("Revenue Growth",     "revenue_growth",       "#27ae60"),
            ("Revenue Growth YoY", "revenue_growth_yoy",   "#27ae60"),
            ("Gross Margin",       "gross_margin",         "#27ae60"),
            ("Operating Margin",   "operating_margin",     "#27ae60"),
            ("Net Income",         "net_income",           "#1a1a2e"),
            ("EPS",                "eps",                  "#1a1a2e"),
            ("EPS vs Estimate",    "eps_vs_estimate",      "#f39c12"),
            ("FCF",                "fcf",                  "#27ae60"),
            ("Cash",               "cash_and_equivalents", "#27ae60"),
            ("Total Debt",         "total_debt",           "#e74c3c"),
            ("Expense Highlights", "expense_highlights",   "#444"),
        ]
        b = ""
        for label, key, color in fin_rows:
            b += _kv(label, fin.get(key), color)
        parts.append(_card("Financial Highlights", b))

    # Segments
    segs = data.get("business_segments") or data.get("segment_performance", [])
    if segs:
        parts.append(_card("Business Segments", _seg_table(segs, is_q)))

    # Guidance
    g = data.get("management_guidance", {})
    if g:
        b  = _kv("Next Quarter", g.get("next_quarter"))
        b += _kv("Full Year",    g.get("full_year") or g.get("full_year_update"))
        ch = g.get("key_changes_from_prior_guidance") or g.get("key_assumptions", [])
        if ch:
            b += '<p style="font-size:12px;color:#888;margin:8px 0 4px">Key points:</p>'
            b += _bullets(ch)
        if b.strip():
            parts.append(_card("Management Guidance", b))

    # vs Last Quarter
    if is_q:
        vlq = data.get("vs_last_quarter", {})
        if vlq:
            b  = _kv("Revenue Change QoQ", vlq.get("revenue_change"))
            b += _kv("Margin Change",       vlq.get("margin_change"))
            impr  = vlq.get("notable_improvements", [])
            deter = vlq.get("notable_deteriorations", [])
            if impr:
                b += '<p style="font-size:12px;color:#27ae60;margin:8px 0 4px;font-weight:600">Improvements:</p>'
                b += _bullets(impr, "#27ae60")
            if deter:
                b += '<p style="font-size:12px;color:#e74c3c;margin:8px 0 4px;font-weight:600">Deteriorations:</p>'
                b += _bullets(deter, "#e74c3c")
            if b.strip():
                parts.append(_card("vs Previous Quarter", b))

    # Risks
    risks     = data.get("risk_factors", {})
    new_risks = data.get("new_risks", [])
    risk_html = ""
    if new_risks:
        risk_html += '<p style="font-size:12px;color:#e74c3c;font-weight:600;margin-bottom:4px">New/Updated Risks:</p>'
        risk_html += _bullets(new_risks, "#e74c3c")
    if isinstance(risks, dict):
        for rtype, items in risks.items():
            if items:
                risk_html += '<p style="font-size:12px;color:#888;font-weight:600;margin:8px 0 4px">' + rtype.replace("_"," ").title() + ':</p>'
                risk_html += _bullets(items)
    if risk_html.strip():
        parts.append(_card("Risk Factors", risk_html))

    # Capital allocation
    cap = data.get("capital_allocation", {})
    if cap:
        b  = _kv("Share Repurchase Program", cap.get("share_repurchase_program"))
        b += _kv("Shares Repurchased",        cap.get("shares_repurchased") or cap.get("shares_repurchased_this_quarter"))
        b += _kv("Dividends",                 cap.get("dividends") or cap.get("dividends_paid"))
        b += _kv("Capex",                     cap.get("capex"))
        if b.strip():
            parts.append(_card("Capital Allocation", b))

    # M&A
    ma = data.get("ma_activity", {}) or {}
    ma_items = (ma.get("recent_acquisitions",[]) +
                ma.get("pending_deals",[]) +
                data.get("ma_updates",[]))
    if ma_items:
        parts.append(_card("M&A Activity", _bullets(ma_items)))

    # Legal
    legal = data.get("legal_disputes",[]) or data.get("legal_updates",[])
    if legal:
        parts.append(_card("Legal Proceedings", _bullets(legal, "#e74c3c")))

    # Accounting policies (10-K)
    if not is_q:
        ap = data.get("accounting_policies", {})
        if ap.get("revenue_recognition"):
            b  = _kv("Revenue Recognition", ap["revenue_recognition"])
            b += _bullets(ap.get("notable_changes",[]))
            parts.append(_card("Accounting Policies", b))

    # Key themes
    themes = data.get("key_themes", [])
    if themes:
        parts.append(_card("Key Themes", _bullets(themes, "#1a1a2e")))

    # Analyst flags
    flags = data.get("analyst_flags", [])
    if flags:
        b = '<p style="font-weight:600;margin:0 0 8px;color:#b7760a">Items to Investigate</p>'
        b += _bullets(flags)
        parts.append(_card("Analyst Flags", _amber(b)))

    parts.append('</div>')
    return "".join(parts)


def run_text_analysis(ticker: str, filing_index: int,
                      gemini_client, model: str) -> dict:
    filings = get_recent_filings(ticker, n=8)
    if filing_index >= len(filings):
        raise ValueError(f"Filing index {filing_index} out of range")
    filing = filings[filing_index]
    print(f"Analysing {filing['label']}...")
    data = analyse_filing(filing, gemini_client, model)
    data["html"] = render_html(data)
    return data


print("text_analysis.py loaded.")
print("Primary function: run_text_analysis(ticker, filing_index, client, model)")
print("Filing list:      get_recent_filings(ticker)")
