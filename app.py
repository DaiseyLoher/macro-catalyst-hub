import streamlit as st
import pandas as pd
import datetime
import requests
import feedparser

st.set_page_config(page_title="Macro & Earnings Catalyst Hub", layout="wide")
st.title("🎯 4-Week Catalyst & Binary Event Matrix")

# ==========================================
# 1. SECRETS & SIDEBAR CONFIGURATION
# ==========================================
fmp_key     = st.secrets.get("FMP_KEY", "")
finnhub_key = st.secrets.get("FINNHUB_KEY", "")
fred_key    = st.secrets.get("FRED_KEY", "")

with st.sidebar:
    st.header("⚙️ API Configuration")
    if not fmp_key:
        fmp_key = st.text_input("FMP API Key (Economic Calendar)", type="password")
    if not finnhub_key:
        finnhub_key = st.text_input("Finnhub API Key (Earnings)", type="password")
    if not fred_key:
        fred_key = st.text_input("FRED API Key (Official US Macro)", type="password")
    
    st.subheader("Watchlist")
    watchlist_input = st.text_input(
        "Tickers (comma-separated)", 
        "NVDA, AAPL, BRK.B, RTX, JPM, XOM", 
        key="watchlist_input_v8"
    )
    tickers = [t.strip().upper() for t in watchlist_input.split(",") if t.strip()]

    st.subheader("Lookahead & Filters")
    lookahead_days = st.slider("Lookahead Window (Days)", min_value=7, max_value=45, value=28)
    min_impact = st.selectbox("Minimum Event Impact", ["High Impact Only", "Medium & High", "All Impacts"], index=0)
    
    st.subheader("Active Data Pipelines")
    use_fmp  = st.checkbox("Financial Modeling Prep (FMP)", value=True)
    use_ff   = st.checkbox("ForexFactory (Live Current Week)", value=True)
    use_fred = st.checkbox("St. Louis Fed (FRED)", value=True)
    use_fed  = st.checkbox("Fed Speeches & Keynotes (RSS)", value=True)
    use_eia  = st.checkbox("EIA Crude Inventory Delta", value=True)

today = datetime.date.today()
end_date = today + datetime.timedelta(days=lookahead_days)
today_str = today.strftime("%Y-%m-%d")
end_str = end_date.strftime("%Y-%m-%d")

# ==========================================
# 2. PIPELINE A: FMP ECONOMIC CALENDAR (UPDATED V4 API)
# ==========================================
@st.cache_data(ttl=1800)
def get_fmp_economic_calendar(api_key, start_d, end_d, impact_choice):
    events = []
    if not api_key:
        return events
    
    # Modern v4 Endpoint
    url = f"https://financialmodelingprep.com/api/v4/economic-calendar?from={start_d}&to={end_d}&apikey={api_key}"
    try:
        response = requests.get(url, timeout=10)
        res = response.json()
        
        # Check for API errors or tier restrictions
        if isinstance(res, dict):
            if "Error Message" in res or "message" in res:
                err_msg = res.get("Error Message") or res.get("message")
                st.sidebar.warning(f"FMP Notice: {err_msg}")
            return events
            
        if isinstance(res, list):
            for item in res:
                country = str(item.get("country", "")).upper()
                if country not in ["US", "USA", "UNITED STATES"]:
                    continue
                
                impact = str(item.get("impact", "Low")).capitalize()
                if impact_choice == "High Impact Only" and impact != "High":
                    continue
                elif impact_choice == "Medium & High" and impact not in ["High", "Medium"]:
                    continue
                
                raw_date = item.get("date", "")
                event_date = raw_date.split(" ")[0] if " " in raw_date else raw_date
                event_name = item.get("event", "Macro Event")
                estimate = item.get("estimate", "N/A")
                previous = item.get("previous", "N/A")
                unit = item.get("unit", "")
                
                details = f"Impact: {impact.upper()} | Est: {estimate} {unit} | Prev: {previous} {unit}"
                
                events.append({
                    "Date": event_date,
                    "Event": f"[US] {event_name}",
                    "Category": "Macro Economic",
                    "Source": "FMP",
                    "Risk Tier": "🔴 Macro Pivot" if impact == "High" else "⚠️ Mid Impact",
                    "Details": details
                })
    except Exception as e:
        st.sidebar.warning(f"FMP Connection Issue: {e}")
        
    return events

@st.cache_data(ttl=1800)
def get_forexfactory_thisweek(impact_choice):
    events = []
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5).json()
        for item in res:
            curr = item.get("country", "")
            impact = item.get("impact", "")
            if curr == "USD":
                if impact_choice == "High Impact Only" and impact != "High":
                    continue
                elif impact_choice == "Medium & High" and impact not in ["High", "Medium"]:
                    continue
                
                raw_date = item.get("date", "")
                event_date = raw_date.split("T")[0] if "T" in raw_date else raw_date
                events.append({
                    "Date": event_date,
                    "Event": f"[USD] {item.get('title')}",
                    "Category": "Macro Economic",
                    "Source": "ForexFactory",
                    "Risk Tier": "🔴 Macro Pivot" if impact == "High" else "⚠️ Mid Impact",
                    "Details": f"Forecast: {item.get('forecast', 'N/A')} | Previous: {item.get('previous', 'N/A')}"
                })
    except Exception:
        pass
    return events

@st.cache_data(ttl=14400)
def get_fred_calendar(api_key, start_d, end_d):
    events = []
    if not api_key:
        return events
    tracked_releases = {
        10: "US CPI Inflation (Headline & Core)",
        11: "US PPI Producer Price Index",
        50: "US Employment Situation (NFP & Unemployment)",
        53: "US Gross Domestic Product (GDP)",
        9:  "US Advance Monthly Retail Sales",
        22: "US Industrial Production",
        27: "US Housing Starts & Building Permits",
        323:"FOMC Policy Materials"
    }
    url = (
        f"https://api.stlouisfed.org/fred/releases/dates?"
        f"api_key={api_key}&file_type=json&include_release_dates_with_no_data=true&"
        f"realtime_start={start_d}&realtime_end={end_d}"
    )
    try:
        res = requests.get(url, timeout=8).json()
        for item in res.get("release_dates", []):
            rel_id = item.get("release_id")
            if rel_id in tracked_releases:
                events.append({
                    "Date": item.get("date"),
                    "Event": f"[US] {tracked_releases[rel_id]}",
                    "Category": "Macro Economic",
                    "Source": "FRED",
                    "Risk Tier": "🔴 Macro Pivot",
                    "Details": f"Official Federal Release (FRED ID: {rel_id})"
                })
    except Exception:
        pass
    return events

@st.cache_data(ttl=1800)
def get_finnhub_earnings(api_key, ticker_list, start_d, end_d):
    events = []
    if not api_key:
        return events
    for sym in ticker_list:
        clean_sym = sym.replace("-", ".")
        url = f"https://finnhub.io/api/v1/calendar/earnings?from={start_d}&to={end_d}&symbol={clean_sym}&token={api_key}"
        try:
            res = requests.get(url, timeout=5).json()
            for item in res.get("earningsCalendar", []):
                e_hour = item.get("hour", "").upper()
                timing = "BMO" if e_hour == "BMO" else ("AMC" if e_hour == "AMC" else "Session")
                eps_est = item.get("epsEstimate")
                details = f"Timing: {timing} | EPS Est: ${eps_est:.2f}" if eps_est is not None else f"Timing: {timing}"
                events.append({
                    "Date": item.get("date"),
                    "Event": f"{sym} Earnings",
                    "Category": "Single Stock",
                    "Source": "Finnhub",
                    "Risk Tier": "🚨 High Volatility",
                    "Details": details
                })
        except Exception:
            continue
    return events

@st.cache_data(ttl=1800)
def get_fed_speeches():
    feed = feedparser.parse("https://www.federalreserve.gov/feeds/press_all.xml")
    speech_events = []
    for entry in feed.entries[:15]:
        title = entry.title
        if any(k in title.lower() for k in ["speech", "testimony", "statement", "fomc", "symposium"]):
            speech_events.append({
                "Date": pd.to_datetime(entry.published).strftime("%Y-%m-%d"),
                "Event": title,
                "Category": "Central Bank",
                "Source": "Fed RSS",
                "Risk Tier": "⚠️ Rate Guidance",
                "Details": entry.get("summary", "Federal Reserve Speech")
            })
    return speech_events

def get_eia_releases(start_d, lookahead):
    events = []
    for i in range(lookahead):
        d = start_d + datetime.timedelta(days=i)
        if d.weekday() == 2:
            events.append({
                "Date": d.strftime("%Y-%m-%d"),
                "Event": "[USD] EIA Petroleum Status Report",
                "Category": "Energy",
                "Source": "EIA Petroleum",
                "Risk Tier": "🟡 Commodity Beta",
                "Details": "10:30 AM EST | Commercial Crude Inventory Delta"
            })
    return events

# ==========================================
# 3. ROW COLOR FORMATTING ENGINE
# ==========================================
def style_row_by_category(row):
    """Applies subtle background tints based on category for readability."""
    cat = row.get("Category", "")
    if cat == "Single Stock":
        # Cyan / Blue Tint (Equity Catalysts)
        return ["background-color: rgba(0, 229, 255, 0.14)"] * len(row)
    elif cat == "Macro Economic":
        # Red / Rose Tint (High Macro Impact)
        return ["background-color: rgba(255, 23, 68, 0.14)"] * len(row)
    elif cat == "Energy":
        # Amber / Gold Tint (Commodities)
        return ["background-color: rgba(255, 214, 0, 0.15)"] * len(row)
    elif cat == "Central Bank":
        # Purple / Violet Tint (Speeches / Fed)
        return ["background-color: rgba(224, 64, 251, 0.14)"] * len(row)
    return [""] * len(row)

# ==========================================
# 4. CONSOLIDATE, STYLE & RENDER
# ==========================================
all_catalysts = []

if use_fmp and fmp_key:
    all_catalysts.extend(get_fmp_economic_calendar(fmp_key, today_str, end_str, min_impact))
if use_ff:
    all_catalysts.extend(get_forexfactory_thisweek(min_impact))
if use_fred and fred_key:
    all_catalysts.extend(get_fred_calendar(fred_key, today_str, end_str))
if finnhub_key:
    all_catalysts.extend(get_finnhub_earnings(finnhub_key, tickers, today_str, end_str))
if use_fed:
    all_catalysts.extend(get_fed_speeches())
if use_eia:
    all_catalysts.extend(get_eia_releases(today, lookahead_days))

df = pd.DataFrame(all_catalysts)

if not df.empty:
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[df["Date"].dt.date >= today]
    df = df.drop_duplicates(subset=["Date", "Event"]).sort_values(by="Date", ascending=True).reset_index(drop=True)
    
    df["Days Left"] = (df["Date"].dt.date - today).apply(
        lambda x: "TODAY" if x.days == 0 else f"In {x.days}D"
    )
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # KPI Summary Cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracked Tickers", len(tickers))
    c2.metric("Total Catalysts", len(df))
    c3.metric("Single-Stock Earnings", len(df[df["Category"] == "Single Stock"]))
    c4.metric("High-Risk Events (Next 7D)", len(df[df["Days Left"].str.contains("TODAY|In 1D|In 2D|In 3D|In 4D|In 5D|In 6D|In 7D")]))

    st.subheader(f"📅 Consolidated Catalyst Timeline ({today_str} to {end_str})")
    
    # Legend Guide
    st.markdown(
        """
        <div style="display: flex; gap: 20px; font-size: 0.85rem; margin-bottom: 12px;">
            <span><span style="display:inline-block;width:12px;height:12px;background:rgba(0,229,255,0.4);border-radius:2px;margin-right:6px;"></span><b>Single Stock</b></span>
            <span><span style="display:inline-block;width:12px;height:12px;background:rgba(255,23,68,0.4);border-radius:2px;margin-right:6px;"></span><b>Macro Economic</b></span>
            <span><span style="display:inline-block;width:12px;height:12px;background:rgba(255,214,0,0.4);border-radius:2px;margin-right:6px;"></span><b>Energy</b></span>
            <span><span style="display:inline-block;width:12px;height:12px;background:rgba(224,64,251,0.4);border-radius:2px;margin-right:6px;"></span><b>Central Bank</b></span>
        </div>
        """, 
        unsafe_allow_html=True
    )

    f_col1, f_col2 = st.columns(2)
    with f_col1:
        selected_cats = st.multiselect("Filter by Category", options=df["Category"].unique(), default=df["Category"].unique())
    with f_col2:
        selected_sources = st.multiselect("Filter by Source", options=df["Source"].unique(), default=df["Source"].unique())
        
    filtered_df = df[df["Category"].isin(selected_cats) & df["Source"].isin(selected_sources)]
    
    # Reorder columns & apply row-level background styling
    display_df = filtered_df[["Date", "Days Left", "Event", "Category", "Source", "Risk Tier", "Details"]]
    styled_df = display_df.style.apply(style_row_by_category, axis=1)

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True
    )
else:
    st.warning("No scheduled catalysts found. Check your API keys or expand the lookahead window.")