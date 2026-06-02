import pandas as pd
import numpy as np


# ============================================================
# PENMAN & POPE — CH 6 PROFITABILITY MODULE
#
# Implements full DuPont decomposition:
#   Level 1: RNOA = PM × ATO
#   Level 2: PM drivers (gross margin, R&D, SGA, tax)
#   Level 2: ATO drivers (AR, PPE, AP intensities)
#   Cash Conversion Cycle: DSO, DIO, DPO, CCC
#   OLLEV: Operating Liability Leverage
#   2×2 DuPont grid verdict
#
# Primary function: run_profitability(ticker)
# ============================================================


def get_pm_decomposition(facts: dict, fy_dates: list) -> pd.DataFrame:
    """
    Level 2 PM decomposition — each driver as % of sales.
    Formulas: Penman & Pope Chapter 6.
    """
    from data_fetch import get_concept_value

    rows = []
    for fy in fy_dates:
        def get(concept):
            return get_concept_value(facts, concept, fy) or 0

        revenue = (
            get("RevenueFromContractWithCustomerExcludingAssessedTax") or
            get("Revenues") or get("SalesRevenueNet")
        )
        if revenue == 0:
            continue

        gross_profit = get("GrossProfit") or get("GrossProfitLoss")
        rd_expense   = (
            get("ResearchAndDevelopmentExpense") or
            get("ResearchAndDevelopmentExpenseExcludingAcquiredInProcess")
        )
        sga_expense  = (
            get("SellingGeneralAndAdministrativeExpense") or
            get("GeneralAndAdministrativeExpense")
        )
        dna_expense  = (
            get("DepreciationDepletionAndAmortization") or
            get("DepreciationAndAmortization")
        )
        tax_expense    = get("IncomeTaxExpenseBenefit")
        op_income      = get("OperatingIncomeLoss")
        inc_before_tax = get(
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
        )
        tax_rate    = (tax_expense / inc_before_tax
                       if inc_before_tax and inc_before_tax != 0 else 0.21)
        oi_aftertax = op_income * (1 - tax_rate) if op_income else None

        rows.append({
            "fiscal_year_end":  fy,
            "revenue":          revenue,
            "gross_profit":     gross_profit,
            "rd_expense":       rd_expense,
            "sga_expense":      sga_expense,
            "dna_expense":      dna_expense,
            "tax_expense":      tax_expense,
            "op_income":        op_income,
            "oi_aftertax":      oi_aftertax,
            "tax_rate":         round(tax_rate, 4),
            "gross_margin_pct": gross_profit / revenue if gross_profit else None,
            "rd_pct":           rd_expense   / revenue if rd_expense   else None,
            "sga_pct":          sga_expense  / revenue if sga_expense  else None,
            "dna_pct":          dna_expense  / revenue if dna_expense  else None,
            "tax_burden_pct":   tax_expense  / revenue if tax_expense  else None,
            "pm_pct":           oi_aftertax  / revenue if oi_aftertax  else None,
        })

    return (pd.DataFrame(rows)
            .sort_values("fiscal_year_end")
            .reset_index(drop=True))


def get_ato_decomposition(facts: dict, fy_dates: list) -> pd.DataFrame:
    """
    Level 2 ATO decomposition — each driver as % of sales.
    Includes Cash Conversion Cycle.
    Formulas: Penman & Pope Chapter 6.
    """
    from data_fetch import get_concept_value

    rows = []
    for fy in fy_dates:
        def get(concept):
            return get_concept_value(facts, concept, fy) or 0

        revenue = (
            get("RevenueFromContractWithCustomerExcludingAssessedTax") or
            get("Revenues") or get("SalesRevenueNet")
        )
        if revenue == 0:
            continue

        cogs      = (get("CostOfGoodsAndServicesSold") or
                     get("CostOfRevenue") or get("CostOfGoodsSold"))
        ar        = get("AccountsReceivableNetCurrent") or get("ReceivablesNetCurrent")
        inventory = get("InventoryNet") or get("InventoriesNet")
        ppe       = get("PropertyPlantAndEquipmentNet")
        ap        = get("AccountsPayableCurrent")
        def_rev   = (get("DeferredRevenueCurrent") or
                     get("ContractWithCustomerLiabilityCurrent"))

        ar_int   = ar        / revenue if ar        else 0
        inv_int  = inventory / revenue if inventory else 0
        ppe_int  = ppe       / revenue if ppe       else 0
        ap_int   = ap        / revenue if ap        else 0
        dr_int   = def_rev   / revenue if def_rev   else 0

        one_over_ato = ar_int + inv_int + ppe_int - ap_int - dr_int

        # Use NOA-based ATO as the primary measure
        # Individual intensities are for trend analysis only
        # This avoids distortion when operating liabilities
        # exceed operating assets (e.g. Apple, retailers)
        total_liab = get_concept_value(facts, "Liabilities", fy) or 0
        if total_liab == 0:
            for eq_c in ["StockholdersEquity",
                         "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]:
                eq_v = get_concept_value(facts, eq_c, fy)
                if eq_v:
                    total_liab = (get_concept_value(facts, "Assets", fy) or 0) - eq_v
                    break

        total_assets_v = get_concept_value(facts, "Assets", fy) or 0
        cash_v   = get_concept_value(facts, "CashAndCashEquivalentsAtCarryingValue", fy) or 0
        st_inv_v = get_concept_value(facts, "ShortTermInvestments", fy) or 0
        ltd_c_v  = (get_concept_value(facts, "LongTermDebtCurrent", fy) or 0)
        ltd_nc_v = (get_concept_value(facts, "LongTermDebtNoncurrent", fy) or 0)
        ol_nc_v  = get_concept_value(facts, "OperatingLeaseLiabilityNoncurrent", fy) or 0
        ol_c_v   = get_concept_value(facts, "OperatingLeaseLiabilityCurrent", fy) or 0
        if ol_c_v == 0:
            ol_tot = get_concept_value(facts, "OperatingLeaseLiability", fy) or 0
            if ol_tot > 0 and ol_nc_v > 0:
                ol_c_v = ol_tot - ol_nc_v
        fin_a = cash_v + st_inv_v
        fin_l = ltd_c_v + ltd_nc_v + ol_c_v + ol_nc_v
        NOA_v = (total_assets_v - fin_a) - (total_liab - fin_l)
        ato   = revenue / NOA_v if NOA_v != 0 else None
        one_over_ato = 1 / ato if ato else one_over_ato

        dso = ar        / revenue * 365   if ar              else None
        dio = inventory / cogs    * 365   if (inventory and cogs) else None
        dpo = ap        / cogs    * 365   if (ap and cogs)        else None
        ccc = dso + dio - dpo             if (dso and dio and dpo) else None

        rows.append({
            "fiscal_year_end": fy,
            "revenue":         revenue,
            "ar":              ar,
            "inventory":       inventory,
            "ppe":             ppe,
            "ap":              ap,
            "deferred_rev":    def_rev,
            "ar_intensity":    round(ar_int,       4),
            "inv_intensity":   round(inv_int,      4),
            "ppe_intensity":   round(ppe_int,      4),
            "ap_intensity":    round(ap_int,       4),
            "dr_intensity":    round(dr_int,       4),
            "one_over_ato":    round(one_over_ato, 4),
            "ato_calc":        round(ato,          4) if ato else None,
            "DSO":             round(dso, 1) if dso else None,
            "DIO":             round(dio, 1) if dio else None,
            "DPO":             round(dpo, 1) if dpo else None,
            "CCC":             round(ccc, 1) if ccc else None,
        })

    return (pd.DataFrame(rows)
            .sort_values("fiscal_year_end")
            .reset_index(drop=True))


def get_ollev(facts: dict, fy_dates: list) -> pd.DataFrame:
    """
    Operating Liability Leverage (Penman & Pope Ch 6).

    OLLEV = Operating Liabilities / NOA
    ROOA  = OI (after tax) / Operating Assets
    RNOA  = ROOA + OLLEV × (ROOA − Implicit Borrowing Cost)

    The OLLEV boost = RNOA - ROOA shows how much of reported
    RNOA comes from operating leverage rather than asset returns.
    """
    from data_fetch import get_concept_value

    rows = []
    for fy in fy_dates:
        def get(concept):
            return get_concept_value(facts, concept, fy) or 0

        total_assets      = get("Assets")
        total_liabilities = get("Liabilities")

        if total_liabilities == 0:
            for eq_c in [
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
            ]:
                eq = get_concept_value(facts, eq_c, fy)
                if eq:
                    total_liabilities = total_assets - eq
                    break

        cash    = get("CashAndCashEquivalentsAtCarryingValue")
        st_inv  = get("ShortTermInvestments")
        ltd_c   = (get("LongTermDebtCurrent") or
                   get("LongTermDebtAndCapitalLeaseObligationsCurrent"))
        ltd_nc  = (get("LongTermDebtNoncurrent") or
                   get("LongTermDebtAndCapitalLeaseObligations"))
        ol_nc   = get("OperatingLeaseLiabilityNoncurrent")
        ol_c    = get("OperatingLeaseLiabilityCurrent")
        if ol_c == 0:
            ol_total = get("OperatingLeaseLiability")
            if ol_total > 0 and ol_nc > 0:
                ol_c = ol_total - ol_nc
        st_debt = get("ShortTermBorrowings") or get("CommercialPaper") or 0

        fin_assets = cash + st_inv
        fin_liab   = ltd_c + ltd_nc + ol_c + ol_nc + st_debt
        op_assets  = total_assets      - fin_assets
        op_liab    = total_liabilities - fin_liab
        NOA        = op_assets - op_liab

        op_income  = get("OperatingIncomeLoss")
        inc_bt     = get(
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
        )
        tax        = get("IncomeTaxExpenseBenefit")
        tax_rate   = (tax / inc_bt if inc_bt and inc_bt != 0 else 0.21)
        OI         = op_income * (1 - tax_rate) if op_income else None

        OLLEV      = op_liab / NOA      if NOA       != 0 else None
        ROOA       = OI / op_assets     if (OI and op_assets != 0) else None
        RNOA       = OI / NOA           if (OI and NOA != 0) else None

        rows.append({
            "fiscal_year_end": fy,
            "op_assets":       round(op_assets, 1),
            "op_liab":         round(op_liab,   1),
            "NOA":             round(NOA,        1),
            "OI":              round(OI,         1) if OI else None,
            "OLLEV":           round(OLLEV,      4) if OLLEV else None,
            "ROOA":            round(ROOA,       4) if ROOA  else None,
            "RNOA":            round(RNOA,       4) if RNOA  else None,
            "OLLEV_boost":     round(RNOA - ROOA, 4) if (RNOA and ROOA) else None,
        })

    return (pd.DataFrame(rows)
            .sort_values("fiscal_year_end")
            .reset_index(drop=True))


def get_dupont_verdict(pm_df: pd.DataFrame,
                       ato_df: pd.DataFrame) -> dict:
    """
    Penman & Pope 2×2 DuPont grid verdict.

        PM↑ ATO↑ → Genuine improvement        ✅
        PM↑ ATO↓ → More asset-intensive        🟡
        PM↓ ATO↑ → Margin for volume           🟡
        PM↓ ATO↓ → Structural deterioration   🔴
    """
    if len(pm_df) < 2 or len(ato_df) < 2:
        return {"verdict": "Insufficient data", "color": "#95a5a6",
                "detail": "", "pm_trend": 0, "ato_trend": 0}

    pm_trend  = pm_df["pm_pct"].iloc[-1]   - pm_df["pm_pct"].iloc[-2]
    ato_trend = ato_df["ato_calc"].iloc[-1] - ato_df["ato_calc"].iloc[-2]

    pm_up  = pm_trend  >  0.005
    pm_dn  = pm_trend  < -0.005
    ato_up = ato_trend >  0.05
    ato_dn = ato_trend < -0.05

    if pm_up and ato_up:
        return dict(verdict="✅ Genuine improvement — PM and ATO both rising",
                    color="#27ae60",
                    detail=("Both profit margin and asset turnover improving. "
                            "The strongest quality signal in the DuPont framework."),
                    pm_trend=pm_trend, ato_trend=ato_trend)
    elif pm_up and ato_dn:
        return dict(verdict="🟡 Asset-intensive — margin rising, ATO falling",
                    color="#f39c12",
                    detail=("Margin improving but the company needs more assets "
                            "per dollar of revenue. Investigate whether capex "
                            "will generate proportional future revenue growth."),
                    pm_trend=pm_trend, ato_trend=ato_trend)
    elif pm_dn and ato_up:
        return dict(verdict="🟡 Volume growth — margin falling, ATO rising",
                    color="#f39c12",
                    detail=("Asset efficiency improving but margin under pressure. "
                            "May be sacrificing price for volume. Sustainable only "
                            "if margin recovers as scale benefits materialise."),
                    pm_trend=pm_trend, ato_trend=ato_trend)
    elif pm_dn and ato_dn:
        return dict(verdict="🔴 Structural deterioration — PM and ATO both falling",
                    color="#e74c3c",
                    detail=("Both margin and asset efficiency declining simultaneously. "
                            "The most concerning DuPont pattern — challenge the thesis."),
                    pm_trend=pm_trend, ato_trend=ato_trend)
    else:
        return dict(verdict="➡️ Stable — no significant trend",
                    color="#3498db",
                    detail="Profit margin and asset turnover broadly unchanged.",
                    pm_trend=pm_trend, ato_trend=ato_trend)


def run_profitability(ticker: str, years: int = 4) -> dict:
    """
    Run full Ch 6 profitability diagnostic for any ticker.

    Returns dict with:
        pm_df     — PM decomposition DataFrame
        ato_df    — ATO decomposition DataFrame
        ollev_df  — OLLEV DataFrame
        verdict   — DuPont 2×2 verdict dict
        html      — HTML section for embedding in report
    """
    from data_fetch import get_cik, get_xbrl_facts
    from rnoa       import get_fiscal_year_dates

    cik      = get_cik(ticker)
    facts    = get_xbrl_facts(cik)
    fy_dates = get_fiscal_year_dates(facts, years)

    pm_df    = get_pm_decomposition(facts, fy_dates)
    ato_df   = get_ato_decomposition(facts, fy_dates)
    ollev_df = get_ollev(facts, fy_dates)
    verdict  = get_dupont_verdict(pm_df, ato_df)
    html     = _render_html(ticker, pm_df, ato_df, ollev_df, verdict)

    return {
        "ticker":   ticker.upper(),
        "pm_df":    pm_df,
        "ato_df":   ato_df,
        "ollev_df": ollev_df,
        "verdict":  verdict,
        "html":     html,
    }


def _fmt_pct(v):
    return f"{v:.1%}" if v is not None else "—"

def _fmt_d(v):
    return f"{v:.0f}d" if v is not None else "—"

def _fmt_x(v):
    return f"{v:.2f}x" if v is not None else "—"


AMBER_STYLE_P = 'style="background:#fffbf0;border-left:3px solid #f39c12;border-radius:0 6px 6px 0;padding:10px 14px;font-size:13px;color:#444;line-height:1.6;margin-top:8px"'

def _render_html(ticker, pm_df, ato_df, ollev_df, verdict) -> str:
    """Render Ch 6 profitability as HTML section."""
    rows = []
    a = rows.append

    a('<div style="font-family:-apple-system,sans-serif;color:#2c3e50;font-size:14px">')
    a('<p style="color:#666;font-size:12px;margin-bottom:12px">')
    a('Chapter 6 — Full DuPont decomposition: RNOA = PM × ATO, ')
    a('operating liability leverage, and cash conversion cycle.</p>')

    # ── PM Decomposition table ────────────────────────────────
    a('<p style="font-weight:600;margin:0 0 4px">PM Decomposition (% of Sales)</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
    a('Gross margin is the starting point. R&D, SG&A and tax are costs that reduce it. ')
    a('Net PM is what remains as after-tax operating profit per dollar of revenue. ')
    a('Rising gross margin = pricing power. Rising R&D = investing in future growth. ')
    a('Falling SG&A = operating efficiency.</p>')
    a('<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    headers = ["FY End", "Gross Margin", "R&D", "SG&A", "Tax Burden", "Net PM"]
    a('<thead><tr>')
    for h in headers:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;text-align:right;font-weight:500;font-size:12px;color:#555;white-space:nowrap">{h}</th>')
    a('</tr></thead><tbody>')
    for _, row in pm_df.iterrows():
        a('<tr>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#666">{row["fiscal_year_end"]}</td>')
        gm_c = "#27ae60" if row["gross_margin_pct"] and row["gross_margin_pct"] > 0.40 else "#e67e22"
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600;color:{gm_c}">{_fmt_pct(row["gross_margin_pct"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#e74c3c">{_fmt_pct(row["rd_pct"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#e74c3c">{_fmt_pct(row["sga_pct"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#e74c3c">{_fmt_pct(row["tax_burden_pct"])}</td>')
        pm_c = "#27ae60" if row["pm_pct"] and row["pm_pct"] > 0.15 else "#e74c3c"
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600;color:{pm_c}">{_fmt_pct(row["pm_pct"])}</td>')
        a('</tr>')
    a('</tbody></table></div>')

    # ── ATO Decomposition table ───────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 4px">ATO Decomposition (% of Sales = 1/ATO Drivers)</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
    a('Each item shows how many cents of assets or liabilities exist per dollar of sales. ')
    a('Asset items (AR, Inventory, PPE) increase 1/ATO and reduce efficiency. ')
    a('Liability items (AP, Deferred Revenue) reduce 1/ATO — suppliers and customers ')
    a('are financing the business. Rising PPE% means heavy capital investment. ')
    a('Rising AP% means stronger supplier terms.</p>')
    a('<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    headers2 = ["FY End", "AR%", "Inv%", "PPE%", "AP%", "Def Rev%", "1/ATO", "ATO"]
    a('<thead><tr>')
    for h in headers2:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;text-align:right;font-weight:500;font-size:12px;color:#555;white-space:nowrap">{h}</th>')
    a('</tr></thead><tbody>')
    for _, row in ato_df.iterrows():
        a('<tr>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#666">{row["fiscal_year_end"]}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right">{_fmt_pct(row["ar_intensity"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right">{_fmt_pct(row["inv_intensity"])}</td>')
        ppe_c = "#e74c3c" if row["ppe_intensity"] and row["ppe_intensity"] > 0.50 else "#2c3e50"
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:{ppe_c}">{_fmt_pct(row["ppe_intensity"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#27ae60">{_fmt_pct(row["ap_intensity"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#27ae60">{_fmt_pct(row["dr_intensity"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600">{_fmt_x(row["one_over_ato"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600;color:#1a1a2e">{_fmt_x(row["ato_calc"])}</td>')
        a('</tr>')
    a('</tbody></table></div>')

    # ── CCC table ─────────────────────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 4px">Cash Conversion Cycle</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">')
    a('DSO = days to collect from customers. DIO = days inventory sits unsold. ')
    a('DPO = days before paying suppliers. CCC = DSO + DIO − DPO. ')
    a('Negative CCC means the company collects cash before paying suppliers — ')
    a('a strong sign of business quality (e.g. Amazon, Apple).</p>')
    a('<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<thead><tr>')
    for h in ["FY End", "DSO", "DIO", "DPO", "CCC"]:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;text-align:right;font-weight:500;font-size:12px;color:#555">{h}</th>')
    a('</tr></thead><tbody>')
    for _, row in ato_df.iterrows():
        ccc_val = row["CCC"]
        if ccc_val is None:
            ccc_c    = "#95a5a6"
            ccc_disp = "N/A"
        elif ccc_val < 0:
            ccc_c    = "#27ae60"
            ccc_disp = _fmt_d(ccc_val)
        else:
            ccc_c    = "#e74c3c"
            ccc_disp = _fmt_d(ccc_val)
        a('<tr>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#666">{row["fiscal_year_end"]}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#888">{_fmt_d(row["DSO"]) if row["DSO"] else "N/A"}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#888">{_fmt_d(row["DIO"]) if row["DIO"] else "N/A"}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right">{_fmt_d(row["DPO"]) if row["DPO"] else "N/A"}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600;color:{ccc_c}">{ccc_disp}</td>')
        a('</tr>')
    a('</tbody></table></div>')

    # ── OLLEV table ───────────────────────────────────────────
    a('<p style="font-weight:600;margin:14px 0 8px">Operating Liability Leverage (OLLEV)</p>')
    a('<p style="color:#888;font-size:12px;margin-bottom:8px">RNOA = ROOA + OLLEV × (ROOA − Implicit Cost). ')
    a('OLLEV boost shows how much of RNOA comes from operating leverage vs pure asset returns.</p>')
    a('<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">')
    a('<thead><tr>')
    for h in ["FY End", "Op Assets", "Op Liab", "NOA", "OLLEV", "ROOA", "RNOA", "Boost"]:
        a(f'<th style="background:#f0f2f5;padding:8px 10px;text-align:right;font-weight:500;font-size:12px;color:#555;white-space:nowrap">{h}</th>')
    a('</tr></thead><tbody>')
    for _, row in ollev_df.iterrows():
        a('<tr>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;color:#666">{row["fiscal_year_end"]}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#888">${row["op_assets"]/1000:.1f}bn</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;color:#888">${row["op_liab"]/1000:.1f}bn</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600">${row["NOA"]/1000:.1f}bn</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right">{_fmt_x(row["OLLEV"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right">{_fmt_pct(row["ROOA"])}</td>')
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600">{_fmt_pct(row["RNOA"])}</td>')
        boost_c = "#27ae60" if row["OLLEV_boost"] and row["OLLEV_boost"] > 0 else "#e74c3c"
        a(f'<td style="padding:8px 10px;border-bottom:1px solid #f0f2f5;text-align:right;font-weight:600;color:{boost_c}">{_fmt_pct(row["OLLEV_boost"])}</td>')
        a('</tr>')
    a('</tbody></table></div>')

    # ── DuPont 2×2 verdict ────────────────────────────────────
    a(f'<div style="background:#f8f9fa;border-left:3px solid {verdict["color"]};')
    a('padding:12px 16px;border-radius:0 6px 6px 0;margin-top:8px">')
    a(f'<strong>DuPont 2×2 Verdict:</strong> {verdict["verdict"]}<br>')
    a(f'<span style="color:#666;font-size:13px">{verdict["detail"]}</span><br>')
    a(f'<span style="color:#888;font-size:12px">PM trend: {verdict["pm_trend"]:+.1%} &nbsp;|&nbsp; ATO trend: {verdict["ato_trend"]:+.2f}x</span>')
    a('</div>')

    a('</div>')
    return "".join(rows)


print("profitability.py loaded.")
print("Primary function: run_profitability(ticker)")
print("Returns: pm_df, ato_df, ollev_df, verdict, html")
