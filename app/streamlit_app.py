import streamlit as st
import sys
import os

# ── PROJECT ROOT ─────────────────────────────────────────────
# Works both in Colab and Streamlit Cloud
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_PATH    = os.path.join(PROJECT_ROOT, "core")

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, CORE_PATH)

# ── PAGE CONFIG ──────────────────────────────────────────────
st.set_page_config(
    page_title="FSA Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CUSTOM CSS ───────────────────────────────────────────────
st.markdown("""
<style>
  .main { background-color: #f5f6fa; }
  .stButton > button {
    width: 100%;
    background-color: #1a1a2e;
    color: white;
    border: none;
    padding: 12px;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 600;
  }
  .stButton > button:hover { background-color: #2d2d5e; }
  .title-block {
    background: #1a1a2e;
    color: white;
    padding: 24px;
    border-radius: 10px;
    margin-bottom: 20px;
  }
  .title-block h1 { font-size: 28px; font-weight: 700; margin: 0; }
  .title-block p  { color: #aaa; margin: 6px 0 0; font-size: 14px; }
  .info-box {
    background: #e8f4fd;
    border-left: 3px solid #2980b9;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    font-size: 14px;
    margin-bottom: 16px;
  }
</style>
""", unsafe_allow_html=True)

# ── HEADER ───────────────────────────────────────────────────
st.markdown("""
<div class="title-block">
  <h1>📊 FSA Engine</h1>
  <p>Financial Statement Analysis · Based on Penman &amp; Pope methodology</p>
</div>
""", unsafe_allow_html=True)

# ── SIDEBAR ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Analysis Settings")
    st.markdown("---")

    ticker = st.text_input(
        "Stock Ticker",
        value="AAPL",
        placeholder="e.g. MSFT, AAPL, NVDA",
        help="Enter any US-listed stock ticker"
    ).upper().strip()

    r = st.slider(
        "Required Return (%)",
        min_value=5,
        max_value=15,
        value=9,
        step=1,
        help="Your hurdle rate for value creation"
    ) / 100

    st.markdown("---")
    run_button = st.button("Run Analysis", type="primary")

    st.markdown("---")
    st.markdown("**How to use:**")
    st.markdown("""
    1. Enter a US stock ticker
    2. Set your required return
    3. Click Run Analysis
    4. Download the report
    """)

    st.markdown("---")
    st.markdown("**Data sources:**")
    st.markdown("SEC EDGAR · Yahoo Finance")
    st.markdown("---")
    st.markdown(
        "<div style='font-size:11px;color:#999'>"
        "Based on: Financial Statement Analysis "
        "for Value Investing<br>"
        "Penman &amp; Pope</div>",
        unsafe_allow_html=True
    )

# ── MAIN AREA ────────────────────────────────────────────────
if not run_button:
    st.markdown("""
    <div class="info-box">
    Enter a stock ticker in the sidebar and click
    <strong>Run Analysis</strong> to generate a complete
    FSA research report.
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("#### 📈 What you get")
        st.markdown("""
        - Residual earnings valuation
        - Implied growth rate g*
        - Market challenge analysis
        - Bull / Base / Bear scenarios
        """)
    with col2:
        st.markdown("#### 🔍 Analysis modules")
        st.markdown("""
        - Profitability (RNOA, PM, ATO)
        - Leverage (LEV, NBC, Spread)
        - Earnings quality (accruals)
        - Investment summary
        """)
    with col3:
        st.markdown("#### 📚 Methodology")
        st.markdown("""
        - Penman & Pope framework
        - SEC EDGAR live data
        - Textbook-exact formulas
        - Plain English commentary
        """)
else:
    if not ticker:
        st.error("Please enter a stock ticker.")
    else:
        with st.spinner(f"Analysing {ticker}... this takes about 30 seconds"):
            try:
                from report import generate_report
                import datetime

                html  = generate_report(ticker, r=r,
                                        project_root=PROJECT_ROOT)
                today = datetime.date.today().strftime("%Y-%m-%d")
                fname = f"{ticker}_{today}.html"

                st.success(f"Report generated for {ticker}")

                st.download_button(
                    label="⬇️ Download Report",
                    data=html,
                    file_name=fname,
                    mime="text/html",
                )

                st.markdown("---")
                st.components.v1.html(html, height=4000, scrolling=True)

            except Exception as e:
                st.error(f"Error analysing {ticker}: {str(e)}")
                st.markdown("""
                **Possible causes:**
                - Ticker not found in SEC EDGAR
                - Insufficient filing history
                - Data fetch timeout
                """)
                st.exception(e)
