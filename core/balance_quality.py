import pandas as pd
import numpy as np


# ============================================================
# PENMAN & POPE — BALANCE SHEET & CREDIT QUALITY MODULE
#
# Combines Ch 9 (balance sheet quality),
# Ch 10 (income statement quality flags),
# Ch 13 (credit risk: Altman Z, Piotroski F)
#
# Primary function: run_balance_quality(ticker)
# ============================================================


def run_balance_quality(ticker: str, r: float = 0.09) -> dict:
    """
    Run combined Ch 9 / Ch 10 / Ch 13 diagnostic.
    Returns dict with all metrics and html key.
    """
    from data_fetch import (get_cik, get_xbrl_facts,
                             get_concept_value, get_fiscal_year_end)
    from rnoa import (get_noa_series, get_income_statement,
                      get_fiscal_year_dates)

    cik      = get_cik(ticker)
    facts    = get_xbrl_facts(cik)
    fy_dates = get_fiscal_year_dates(facts, years=3)
    fy       = fy_dates[-1]
    fy_prev  = fy_dates[-2] if len(fy_dates) > 1 else fy

    def get(concept, period=None):
        return get_concept_value(facts, concept, period or fy) or 0

    # ── BALANCE SHEET ITEMS ───────────────────────────────────
    total_assets   = get("Assets")
    total_liab     = get("Liabilities")
    if total_liab == 0:
        for eq_c in ["StockholdersEquity",
                     "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]:
            eq_v = get_concept_value(facts, eq_c, fy)
            if eq_v:
                total_liab = total_assets - eq_v
                break

    equity         = total_assets - total_liab
    goodwill       = get("Goodwill")
    intangibles    = get("FiniteLivedIntangibleAssetsNet") or get("IntangibleAssetsNetExcludingGoodwill")
    dta_gross      = get("DeferredTaxAssetsGross") or get("DeferredIncomeTaxAssetsNet")
    dta_valallow   = get("DeferredTaxAssetsValuationAllowance")
    dta_net        = get("DeferredTaxAssetsLiabilitiesNet") or (dta_gross - dta_valallow)
    ppe_gross      = get("PropertyPlantAndEquipmentGross")
    ppe_net        = get("PropertyPlantAndEquipmentNet")
    accum_depr     = ppe_gross - ppe_net if ppe_gross and ppe_net else 0
    depr_rate      = accum_depr / ppe_gross if ppe_gross else None

    # ── INCOME STATEMENT ITEMS ────────────────────────────────
    revenue        = (get("RevenueFromContractWithCustomerExcludingAssessedTax") or
                      get("Revenues") or get("SalesRevenueNet"))
    op_income      = get("OperatingIncomeLoss")
    net_income     = get("NetIncomeLoss")
    interest_exp   = get("InterestExpense") or get("InterestAndDebtExpense")
    tax_expense    = get("IncomeTaxExpenseBenefit")
    inc_before_tax = get("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest")
    dna            = (get("DepreciationDepletionAndAmortization") or
                      get("DepreciationAndAmortization"))
    cfo            = get("NetCashProvidedByUsedInOperatingActivities")

    # ── PENSION ───────────────────────────────────────────────
    pension_obligation = (get("DefinedBenefitPlanBenefitObligation") or
                          get("PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent"))
    pension_assets     = (get("DefinedBenefitPlanFairValueOfPlanAssets") or
                          get("DefinedBenefitPlanAssetsForPlanBenefitsNoncurrent"))
    pension_deficit    = max(0, pension_obligation - pension_assets) if (pension_obligation and pension_assets) else 0

    # ── CURRENT ITEMS (for liquidity) ─────────────────────────
    current_assets = get("AssetsCurrent")
    current_liab   = get("LiabilitiesCurrent")
    cash           = get("CashAndCashEquivalentsAtCarryingValue")
    receivables    = get("AccountsReceivableNetCurrent") or get("ReceivablesNetCurrent")
    inventory      = get("InventoryNet")

    # Prior year for Piotroski
    total_assets_prev = get("Assets", fy_prev)
    net_income_prev   = get("NetIncomeLoss", fy_prev)
    revenue_prev      = (get("RevenueFromContractWithCustomerExcludingAssessedTax", fy_prev) or
                         get("Revenues", fy_prev))
    cfo_prev          = get("NetCashProvidedByUsedInOperatingActivities", fy_prev)
    current_assets_p  = get("AssetsCurrent", fy_prev)
    current_liab_p    = get("LiabilitiesCurrent", fy_prev)
    total_liab_prev   = get("Liabilities", fy_prev)
    shares_curr       = (get("CommonStockSharesOutstanding") or
                         get("CommonStockSharesIssued"))
    shares_prev       = (get_concept_value(facts, "CommonStockSharesOutstanding", fy_prev) or
                         get_concept_value(facts, "CommonStockSharesIssued", fy_prev) or 0)
    gross_profit      = get("GrossProfit")
    gross_profit_prev = get("GrossProfit", fy_prev)

    # ── CH 9: BALANCE SHEET QUALITY METRICS ──────────────────
    goodwill_pct      = goodwill / total_assets if total_assets else None
    intangibles_pct   = intangibles / total_assets if total_assets else None
    combined_intang   = (goodwill + intangibles) / total_assets if total_assets else None
    dta_pct           = dta_net / total_assets if total_assets else None
    pension_deficit_pct = pension_deficit / equity if equity else None

    # ── CH 13: ALTMAN Z-SCORE (public company version) ───────
    # Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
    working_capital   = current_assets - current_liab
    retained_earnings = (get("RetainedEarningsAccumulatedDeficit") or
                         get("RetainedEarnings"))
    ebit_val          = op_income

    X1 = working_capital  / total_assets if total_assets else None
    X2 = retained_earnings/ total_assets if (retained_earnings and total_assets) else None
    X3 = ebit_val         / total_assets if total_assets else None
    X4 = equity           / total_liab   if total_liab   else None
    X5 = revenue          / total_assets if total_assets else None

    if all(v is not None for v in [X1, X2, X3, X4, X5]):
        altman_z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
    else:
        altman_z = None

    if altman_z is None:
        z_signal = "⚪ N/A"
        z_color  = "#95a5a6"
    elif altman_z > 2.99:
        z_signal = "✅ SAFE ZONE"
        z_color  = "#27ae60"
    elif altman_z > 1.81:
        z_signal = "🟡 GREY ZONE"
        z_color  = "#f39c12"
    else:
        z_signal = "🔴 DISTRESS ZONE"
        z_color  = "#e74c3c"

    # ── CH 13: PIOTROSKI F-SCORE ──────────────────────────────
    f_score = 0
    f_items = []

    def f_check(name, condition, explanation):
        nonlocal f_score
        passed = bool(condition)
        if passed:
            f_score += 1
        f_items.append({"name": name, "pass": passed,
                        "explanation": explanation})

    # Profitability
    roa = net_income / total_assets if total_assets else None
    roa_prev = net_income_prev / total_assets_prev if total_assets_prev else None
    f_check("ROA > 0", roa and roa > 0, "Positive return on assets")
    f_check("CFO > 0", cfo > 0, "Positive operating cash flow")
    f_check("ROA improving", roa and roa_prev and roa > roa_prev, "ROA rising YoY")
    f_check("CFO > Net Income (accruals)", cfo > net_income if net_income else False,
            "Cash earnings exceed accounting earnings")

    # Leverage / Liquidity
    current_ratio      = current_assets / current_liab      if current_liab   else None
    current_ratio_prev = current_assets_p / current_liab_p  if current_liab_p else None
    leverage_curr = total_liab / total_assets if total_assets else None
    leverage_prev = total_liab_prev / total_assets_prev if total_assets_prev else None

    f_check("Leverage falling", leverage_curr and leverage_prev and leverage_curr < leverage_prev,
            "Debt ratio declining")
    f_check("Current ratio improving", current_ratio and current_ratio_prev and current_ratio > current_ratio_prev,
            "Liquidity improving")
    f_check("No new shares issued", shares_curr and shares_prev and shares_curr <= shares_prev * 1.02,
            "No meaningful dilution")

    # Operating efficiency
    gm_curr = gross_profit / revenue if (gross_profit and revenue) else None
    gm_prev = gross_profit_prev / revenue_prev if (gross_profit_prev and revenue_prev) else None
    asset_turn_curr = revenue / total_assets if total_assets else None
    asset_turn_prev = revenue_prev / total_assets_prev if total_assets_prev else None

    f_check("Gross margin improving", gm_curr and gm_prev and gm_curr > gm_prev,
            "Gross margin rising YoY")
    f_check("Asset turnover improving", asset_turn_curr and asset_turn_prev and asset_turn_curr > asset_turn_prev,
            "Revenue per asset rising")

    if f_score >= 7:
        f_signal = "🟢 STRONG (7-9)"
        f_color  = "#27ae60"
    elif f_score >= 4:
        f_signal = "🟡 MODERATE (4-6)"
        f_color  = "#f39c12"
    else:
        f_signal = "🔴 WEAK (0-3)"
        f_color  = "#e74c3c"

    # ── OTHER CREDIT METRICS ──────────────────────────────────
    current_ratio_val  = current_assets / current_liab if current_liab else None
    interest_coverage  = op_income / interest_exp if interest_exp else None
    debt_to_equity     = total_liab / equity if equity else None

    # Get latest NOA and OI for tangible RNOA calculation (Change 1)
    try:
        from rnoa import get_noa_series, get_income_statement
        _noa_df = get_noa_series(facts, years=2)
        _is_df  = get_income_statement(facts, years=2)
        NOA_latest      = _noa_df.iloc[-1]["NOA"] if not _noa_df.empty else None
        OI_latest       = _is_df.iloc[-1]["operating_income_aftertax"] if not _is_df.empty else None
        reported_rnoa   = f"{OI_latest/_noa_df.iloc[-2]['NOA']:.1%}" if (OI_latest and len(_noa_df)>1 and _noa_df.iloc[-2]["NOA"]!=0) else "N/A"
    except Exception:
        NOA_latest, OI_latest, reported_rnoa = None, None, "N/A"

    result = {
        "ticker":             ticker.upper(),
        "NOA_latest":         NOA_latest,
        "OI_latest":          OI_latest,
        "reported_rnoa":      reported_rnoa,
        "fy_end":             fy,
        "total_assets":       total_assets,
        "equity":             equity,
        "goodwill":           goodwill,
        "intangibles":        intangibles,
        "goodwill_pct":       goodwill_pct,
        "intangibles_pct":    intangibles_pct,
        "combined_intang":    combined_intang,
        "dta_net":            dta_net,
        "dta_pct":            dta_pct,
        "pension_deficit":    pension_deficit,
        "pension_deficit_pct":pension_deficit_pct,
        "ppe_gross":          ppe_gross,
        "ppe_net":            ppe_net,
        "depr_rate":          depr_rate,
        "altman_z":           round(altman_z, 2) if altman_z else None,
        "z_signal":           z_signal,
        "z_color":            z_color,
        "f_score":            f_score,
        "f_items":            f_items,
        "f_signal":           f_signal,
        "f_color":            f_color,
        "current_ratio":      round(current_ratio_val, 2) if current_ratio_val else None,
        "interest_coverage":  round(interest_coverage, 1) if interest_coverage else None,
        "debt_to_equity":     round(debt_to_equity, 2)    if debt_to_equity    else None,
        "cfo":                cfo,
        "net_income":         net_income,
        "revenue":            revenue,
    }

    result["html"] = _render_html(result)
    return result


def _fmt_m(v):
    if v is None: return "N/A"
    if abs(v) >= 1e6: return f"${v/1e6:.1f}tn"
    if abs(v) >= 1e3: return f"${v/1e3:.1f}bn"
    return f"${v:.0f}m"

def _fmt_pct(v):
    return f"{v:.1%}" if v is not None else "N/A"

def _fmt_x(v):
    return f"{v:.1f}x" if v is not None else "N/A"


AMBER_STYLE = 'style="background:#fffbf0;border-left:3px solid #f39c12;border-radius:0 6px 6px 0;padding:10px 14px;font-size:13px;color:#444;line-height:1.6;margin-top:8px"'

def _render_html(R: dict) -> str:
    rows = []
    a = rows.append

    a('<div style="font-family:-apple-system,sans-serif;color:#2c3e50;font-size:14px">')

    # ── CH 9: Balance sheet quality ───────────────────────────
    a('<p style="font-weight:600;margin:0 0 4px">Balance Sheet Quality (Ch 9)</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
    a('Key items that may overstate book value or hide risk. ')
    a('High goodwill = acquisition premium at risk of impairment. ')
    a('Pension deficit = hidden debt not in net debt. ')
    a('High DTA = deferred tax asset that requires future profits to realise.</p>')

    a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<thead><tr>')
    for h in ["Item", "Value", "% of Assets", "Signal"]:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;text-align:right;')
        a(f'font-weight:500;font-size:12px;color:#555">{h}</th>')
    a('</tr></thead><tbody>')

    def bs_row(label, value, pct, lo, hi, note):
        if pct is None:
            color, signal = "#95a5a6", "N/A"
        elif pct < lo:
            color, signal = "#27ae60", "✅ Low"
        elif pct < hi:
            color, signal = "#f39c12", f"🟡 Moderate — {note}"
        else:
            color, signal = "#e74c3c", f"🔴 High — {note}"
        return (f'<tr><td style="padding:8px 10px;border-bottom:1px solid #f0f2f5">{label}</td>')  + (
            f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right">{_fmt_m(value)}</td>') + (
            f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600;color:{color}">{_fmt_pct(pct)}</td>') + (
            f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:{color}">{signal}</td></tr>')

    gw_pct = R["goodwill_pct"] or 0
    if gw_pct > 0.30:
        gw_color  = "#e74c3c"
        gw_signal = "🔴 High goodwill — investigate before proceeding. Has there been a major acquisition in the last 3-5 years? Check SEC EDGAR 10-K for recent business combinations and impairment tests."
    elif gw_pct > 0.10:
        gw_color  = "#f39c12"
        gw_signal = "🟡 Moderate — impairment risk if acquisitions underperform"
    else:
        gw_color  = "#27ae60"
        gw_signal = "✅ Low"

    # Tangible RNOA (Change 1 addition)
    tang_noa = R.get("NOA_latest", 0) - (R["goodwill"] or 0) - (R["intangibles"] or 0)
    tang_rnoa_str = ""
    if R.get("OI_latest") and tang_noa > 0:
        tang_rnoa = R["OI_latest"] / tang_noa
        tang_rnoa_str = f'<tr><td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#888;font-size:12px" colspan="2">Tangible RNOA (OI / NOA ex-goodwill): <strong>{tang_rnoa:.1%}</strong> vs reported RNOA {R.get("reported_rnoa","N/A")}</td><td colspan="2" style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#888;font-size:12px">Lower tangible RNOA = more goodwill-dependent profitability</td></tr>'
    elif R.get("OI_latest") and tang_noa <= 0:
        _as = AMBER_STYLE
        tang_rnoa_str = (
            '<tr><td colspan="4" style="padding:8px 10px;border-bottom:1px solid #f0f2f5">'
            f'<div {_as}>⚠️ Tangible NOA is near zero or negative — '
            'reported RNOA is entirely goodwill-dependent. '
            'Verify acquired businesses generate returns above purchase price.'
            '</div></td></tr>'
        )

    a(f'<tr><td style="padding:8px 10px;border-bottom:1px solid #f0f2f5">Goodwill</td>')
    a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right">{_fmt_m(R["goodwill"])}</td>')
    a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600;color:{gw_color}">{_fmt_pct(R["goodwill_pct"])}</td>')
    a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:{gw_color}">{gw_signal}</td></tr>')
    if tang_rnoa_str:
        a(tang_rnoa_str)
    a(bs_row("Intangibles (ex goodwill)",
             R["intangibles"], R["intangibles_pct"],
             0.05, 0.20, "amortisation drag on future earnings"))
    a(bs_row("Combined goodwill + intangibles",
             R["goodwill"] + (R["intangibles"] or 0), R["combined_intang"],
             0.15, 0.40, "book value heavily acquisition-driven"))
    a(bs_row("Net deferred tax assets",
             R["dta_net"], R["dta_pct"],
             0.05, 0.15, "requires future profitability to realise"))
    a(bs_row("Pension deficit",
             R["pension_deficit"], R["pension_deficit_pct"],
             0.05, 0.15, "adds to effective net debt — hidden leverage"))
    a('</tbody></table>')

    # ── CH 13: Altman Z-Score ─────────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 4px">Altman Z-Score (Credit Risk)</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
    a('Z = 1.2×WC/TA + 1.4×RE/TA + 3.3×EBIT/TA + 0.6×Equity/Liab + 1.0×Sales/TA. ')
    a('Z > 2.99 = safe zone. Z 1.81-2.99 = grey zone. Z < 1.81 = distress zone.</p>')

    z = R["altman_z"]
    a(f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">')
    a(f'<div style="font-size:36px;font-weight:700;color:{R["z_color"]}">')
    a(f'{z:.2f}' if z else "N/A")
    a('</div>')
    a(f'<div>')
    a(f'<div style="font-weight:600;color:{R["z_color"]}">{R["z_signal"]}</div>')
    a(f'<div style="color:#888;font-size:12px">Altman Z-Score</div>')
    a('</div></div>')

    # ── CH 13: Piotroski F-Score ──────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 4px">Piotroski F-Score (Financial Strength)</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
    a('9 binary tests across profitability, leverage and efficiency. ')
    a('7-9 = strong. 4-6 = moderate. 0-3 = weak.</p>')

    a(f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">')
    a(f'<div style="font-size:36px;font-weight:700;color:{R["f_color"]}">{R["f_score"]}/9</div>')
    a(f'<div><div style="font-weight:600;color:{R["f_color"]}">{R["f_signal"]}</div>')
    a(f'<div style="color:#888;font-size:12px">Piotroski F-Score</div></div></div>')

    a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    for item in R["f_items"]:
        icon  = "✅" if item["pass"] else "❌"
        color = "#27ae60" if item["pass"] else "#e74c3c"
        a(f'<tr>')
        a(f'<td style="padding:6px 10px;border-bottom:1px solid #f0f2f5;width:28px;color:{color}">{icon}</td>')
        a(f'<td style="padding:6px 10px;border-bottom:1px solid #f0f2f5;font-weight:500">{item["name"]}</td>')
        a(f'<td style="padding:6px 10px;border-bottom:1px solid #f0f2f5;color:#888;font-size:12px">{item["explanation"]}</td>')
        a('</tr>')
    a('</table>')

    # ── Liquidity ratios ──────────────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 4px">Key Credit Ratios</p>')
    a('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<tbody>')

    def ratio_row(label, value, fmt_fn, lo, hi, rev=False):
        if value is None:
            color = "#95a5a6"
            signal = "N/A"
        elif not rev:
            color  = "#27ae60" if value >= hi else "#f39c12" if value >= lo else "#e74c3c"
            signal = "✅" if value >= hi else "🟡" if value >= lo else "🔴"
        else:
            color  = "#27ae60" if value <= lo else "#f39c12" if value <= hi else "#e74c3c"
            signal = "✅" if value <= lo else "🟡" if value <= hi else "🔴"
        return (
            f'<tr><td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#666">{label}</td>')  + (
            f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;font-weight:600;color:{color}">{fmt_fn(value)}</td>') + (
            f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:{color}">{signal}</td></tr>')

    a(ratio_row("Current ratio",      R["current_ratio"],     _fmt_x, 1.0, 2.0))
    a(ratio_row("Interest coverage",  R["interest_coverage"], _fmt_x, 3.0, 5.0))
    a(ratio_row("Debt / Equity",      R["debt_to_equity"],    _fmt_x, 1.0, 2.0, rev=True))
    a('</tbody></table>')

    a('</div>')
    return "".join(rows)


print("balance_quality.py loaded.")
print("Primary function: run_balance_quality(ticker)")
print("Covers: Ch 9 balance sheet quality,")
print("        Ch 13 Altman Z-score and Piotroski F-score")
