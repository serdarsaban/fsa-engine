import pandas as pd
import numpy as np


# ============================================================
# PENMAN & POPE — BALANCE SHEET REFORMULATION MODULE
#
# Calibrated against:
#   Microsoft FY2023:      NOA=$157,341m  ND=-$48,882m  B=$206,223m
#   Delta Air Lines 2019:  NOA=$29,731m   ND=$14,373m   B=$15,358m
#
# Three reformulation methods:
#   1. reformulate_from_financing()  — identity-based (recommended)
#   2. reformulate_from_buckets()    — direct bucket input
#   3. reformulate_balance_sheet()   — keyword classifier
# ============================================================


# ── METHOD 1: IDENTITY-BASED (PRIMARY METHOD) ────────────────
# Most robust. Identify financing items only.
# Operating items derived automatically from balance sheet identity.
#
# Key insight: once financing assets and financing liabilities
# are correctly identified, everything else is operating by definition.
#
# Financing assets  = cash + short-term investments
# Financing liab    = explicit debt + operating lease liabilities
# Operating items   = total assets/liabilities minus financing items

def reformulate_from_financing(
    total_assets:          float,
    total_liabilities:     float,
    financing_assets:      float,
    financing_liabilities: float,
) -> dict:
    """
    Derive NOA, ND, B from the balance sheet identity.

    Inputs (all in $millions):
        total_assets          — from balance sheet face
        total_liabilities     — from balance sheet face
        financing_assets      — cash + ST investments (check footnotes)
        financing_liabilities — debt + operating lease liabilities

    Formulas (Penman & Pope):
        Operating Assets      = Total Assets      - Financing Assets
        Operating Liabilities = Total Liabilities - Financing Liabilities
        NOA = Operating Assets - Operating Liabilities
        ND  = Financing Liabilities - Financing Assets
        B   = NOA - ND  (must equal reported common equity)

    Anchor check: B must equal Total Assets - Total Liabilities.
    If anchor_check is False, financing items are misclassified.
    """
    op_assets = total_assets      - financing_assets
    op_liab   = total_liabilities - financing_liabilities

    NOA = op_assets - op_liab
    ND  = financing_liabilities - financing_assets
    B   = NOA - ND

    reported_equity = total_assets - total_liabilities

    return {
        "operating_assets":      round(op_assets, 1),
        "operating_liabilities": round(op_liab, 1),
        "financing_assets":      round(financing_assets, 1),
        "financing_liabilities": round(financing_liabilities, 1),
        "NOA":                   round(NOA, 1),
        "ND":                    round(ND, 1),
        "B":                     round(B, 1),
        "reported_equity":       round(reported_equity, 1),
        "anchor_check":          abs(B - reported_equity) < 1,
    }


# ── METHOD 2: DIRECT BUCKET INPUT ────────────────────────────
# Use when you have already classified each line item.
# Pass four dicts — one per bucket.

def reformulate_from_buckets(
    operating_assets:      dict,
    operating_liabilities: dict,
    financing_assets:      dict,
    financing_liabilities: dict,
) -> dict:
    """
    Reformulate directly from pre-classified buckets.

    Each input is a dict of {label: value_in_millions}.

    Formulas (Penman & Pope):
        NOA = Operating Assets - Operating Liabilities
        ND  = Financing Liabilities - Financing Assets
        B   = NOA - ND
    """
    op_a  = sum(operating_assets.values())
    op_l  = sum(operating_liabilities.values())
    fin_a = sum(financing_assets.values())
    fin_l = sum(financing_liabilities.values())

    NOA = op_a  - op_l
    ND  = fin_l - fin_a
    B   = NOA   - ND

    return {
        "operating_assets":      round(op_a, 1),
        "operating_liabilities": round(op_l, 1),
        "financing_assets":      round(fin_a, 1),
        "financing_liabilities": round(fin_l, 1),
        "NOA": round(NOA, 1),
        "ND":  round(ND, 1),
        "B":   round(B, 1),
    }


# ── METHOD 3: KEYWORD CLASSIFIER ─────────────────────────────
# Use for quick classification of unknown line items.
# Less reliable than Method 1 — always verify with anchor check.

FINANCING_ASSET_KEYWORDS = [
    "cash and cash equivalents",
    "short term investments",
    "short-term investments",
    "marketable securities",
]

FINANCING_LIABILITY_KEYWORDS = [
    "long term debt",
    "long-term debt",
    "current maturities of debt",
    "current portion of long term debt",
    "current portion of long-term debt",
    "short term debt",
    "commercial paper",
    "notes payable",
    "bonds payable",
    "finance lease",
    "capital lease",
    "operating lease liability",
    "operating lease obligation",
    "current maturities of operating lease",
    "noncurrent operating lease",
]

OPERATING_LIABILITY_KEYWORDS = [
    "accounts payable",
    "accrued",
    "deferred revenue",
    "unearned revenue",
    "contract with customer liability",
    "air traffic liability",
    "income tax",
    "pension",
    "postretirement",
    "warranty",
    "restructuring",
    "other current liabilities",
    "other noncurrent liabilities",
    "other long term liabilities",
    "deferred tax liability",
    "fuel card",
]


def classify_item(label: str) -> str:
    """Classify a balance sheet label into a bucket."""
    s = label.lower().strip()

    for kw in FINANCING_LIABILITY_KEYWORDS:
        if kw in s:
            return "financing_liability"

    for kw in FINANCING_ASSET_KEYWORDS:
        if kw in s:
            return "financing_asset"

    for kw in OPERATING_LIABILITY_KEYWORDS:
        if kw in s:
            return "operating_liability"

    liability_signals = [
        "payable", "liability", "liabilities",
        "obligation", "accrued", "deferred",
        "revenue", "lease",
    ]
    for sig in liability_signals:
        if sig in s:
            return "operating_liability"

    return "operating_asset"


def reformulate_balance_sheet(items: dict) -> dict:
    """
    Reformulate using keyword classification.

    Input:  {label: value_in_millions}
    Output: NOA, ND, B plus per-item classification.

    Always run anchor check after: B must equal reported equity.
    """
    classified    = {}
    unknown_items = []
    op_a = op_l = fin_a = fin_l = 0.0

    for label, value in items.items():
        bucket = classify_item(label)
        classified[label] = {"value": value, "bucket": bucket}

        if   bucket == "operating_asset":       op_a  += value
        elif bucket == "operating_liability":   op_l  += value
        elif bucket == "financing_asset":       fin_a += value
        elif bucket == "financing_liability":   fin_l += value
        else:                                   unknown_items.append(label)

    NOA = op_a  - op_l
    ND  = fin_l - fin_a
    B   = NOA   - ND

    return {
        "operating_assets":      round(op_a, 1),
        "operating_liabilities": round(op_l, 1),
        "financing_assets":      round(fin_a, 1),
        "financing_liabilities": round(fin_l, 1),
        "NOA":          round(NOA, 1),
        "ND":           round(ND, 1),
        "B":            round(B, 1),
        "classified":   classified,
        "unknown_items": unknown_items,
    }


# ── INCOME STATEMENT REFORMULATION ───────────────────────────

def reformulate_income_statement(
    revenue:             float,
    operating_income:    float,
    interest_expense:    float,
    interest_income:     float,
    tax_rate:            float,
    unsustainable_items: dict = None,
) -> dict:
    """
    Split income statement into operating and financing components.

    Formulas (Penman & Pope):
        OI = (Operating Income - Unsustainable Items) x (1 - tax_rate)
        NE = (Interest Expense - Interest Income)     x (1 - tax_rate)
        CI = OI - NE
    """
    if unsustainable_items is None:
        unsustainable_items = {}

    total_unsustainable   = sum(unsustainable_items.values())
    sustainable_OI_pretax = operating_income - total_unsustainable
    OI = sustainable_OI_pretax * (1 - tax_rate)
    NE = (interest_expense - interest_income) * (1 - tax_rate)
    CI = OI - NE

    return {
        "revenue":               round(revenue, 1),
        "reported_OI_pretax":    round(operating_income, 1),
        "total_unsustainable":   round(total_unsustainable, 1),
        "sustainable_OI_pretax": round(sustainable_OI_pretax, 1),
        "tax_rate":              tax_rate,
        "OI":                    round(OI, 1),
        "NE":                    round(NE, 1),
        "CI":                    round(CI, 1),
        "unsustainable_items":   unsustainable_items,
    }


# ── RNOA AND DUPONT ───────────────────────────────────────────

def calculate_rnoa(
    OI: float, NOA_start: float, NOA_end: float
) -> float:
    """
    RNOA = OI (after tax) / Average NOA
    Penman & Pope use average NOA as denominator.
    """
    avg_NOA = (NOA_start + NOA_end) / 2
    return OI / avg_NOA if avg_NOA != 0 else None


def dupont_decomposition(
    OI: float, revenue: float,
    NOA_start: float, NOA_end: float,
) -> dict:
    """
    RNOA = PM x ATO  (Penman & Pope Chapter 6)

    PM  = OI (after tax) / Revenue
    ATO = Revenue / Average NOA
    """
    avg_NOA = (NOA_start + NOA_end) / 2
    PM      = OI / revenue    if revenue  != 0 else None
    ATO     = revenue / avg_NOA if avg_NOA != 0 else None
    RNOA    = calculate_rnoa(OI, NOA_start, NOA_end)

    return {
        "PM":         round(PM, 4)   if PM   else None,
        "ATO":        round(ATO, 4)  if ATO  else None,
        "RNOA":       round(RNOA, 4) if RNOA else None,
        "RNOA_check": round(PM * ATO, 4) if (PM and ATO) else None,
    }


# ── RESIDUAL OPERATING INCOME ─────────────────────────────────

def calculate_reoi(
    RNOA: float, r: float, NOA_start: float
) -> float:
    """
    ReOI = (RNOA - r) x NOA_start

    Where r = required return on operations (cost of capital).
    ReOI > 0: firm creates value above the hurdle rate.
    ReOI < 0: firm destroys value.
    """
    return round((RNOA - r) * NOA_start, 1)


# ── LEVERAGE DECOMPOSITION ────────────────────────────────────

def leverage_decomposition(
    RNOA: float, NBC: float, ND: float, B: float
) -> dict:
    """
    ROE leverage decomposition (Penman & Pope):
        ROE = RNOA + LEV x (RNOA - NBC)

    LEV    = ND / B           (book leverage)
    NBC    = NE / Average ND  (net borrowing cost, after tax)
    Spread = RNOA - NBC
    """
    LEV    = ND / B     if B   != 0    else None
    spread = RNOA - NBC if NBC is not None else None
    ROE    = (RNOA + LEV * spread
              if (LEV is not None and spread is not None)
              else None)

    return {
        "RNOA":   round(RNOA, 4),
        "LEV":    round(LEV, 4)    if LEV    is not None else None,
        "NBC":    round(NBC, 4)    if NBC    is not None else None,
        "spread": round(spread, 4) if spread is not None else None,
        "ROE":    round(ROE, 4)    if ROE    is not None else None,
    }


print("reformulation.py loaded.")
print()
print("Primary method:   reformulate_from_financing()")
print("Secondary method: reformulate_from_buckets()")
print("Classifier:       reformulate_balance_sheet()")
print("Income stmt:      reformulate_income_statement()")
print("Analytics:        calculate_rnoa(), dupont_decomposition(),")
print("                  calculate_reoi(), leverage_decomposition()")
