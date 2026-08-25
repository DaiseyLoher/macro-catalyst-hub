import streamlit as st
import pandas as pd
import datetime
import requests
import feedparser

st.set_page_config(page_title="Macro & Earnings Catalyst Hub", layout="wide")
st.title("🎯 4-Week Catalyst & Binary Event Matrix")

def classify_speech_impact(title, summary=""):
    text = (title + " " + summary).lower()
    
    # Tier 1: Fed Leadership
    tier_1_speakers = ["powell", "jefferson", "williams", "chair", "vice chair"]
    tier_1_venues = ["jackson hole", "testimony", "monetary policy report", "humphrey-hawkins", "press conference"]
    
    # Tier 2: Influential Governors & Key Voters
    tier_2_speakers = ["waller", "bowman", "barr", "cook", "kugler", "bostic", "goolsbee", "kashkari", "logan"]
    tier_2_topics = ["economic outlook", "inflation", "monetary policy", "interest rates", "balance sheet", "qt"]

    # Check Tier 1
    if any(s in text for s in tier_1_speakers) or any(v in text for v in tier_1_venues):
        if not any(k in text for k in ["welcoming remarks", "opening remarks", "adjournment"]):
            return "🔴 Macro Pivot (High)", "Tier 1: Leadership / High Policy Beta"
            
    # Check Tier 2
    if any(s in text for s in tier_2_speakers) and any(t in text for t in tier_2_topics):
        return "⚠️ Rate Guidance (Mid)", "Tier 2: FOMC Voter Policy Discussion"
        
    return "🟡 Low Impact", "Tier 3: Academic / Non-Monetary Remarks"

# ==========================================
# 1. SECRETS & SIDEBAR CONFIGURATION
# ==========================================
finnhub_key = st.secrets.get("FINNHUB_KEY", "")
fred_key    = st.secrets.get("FRED_KEY", "")

with st.sidebar:
    st.header("⚙️ API Configuration")
    if not finnhub_key:
        finnhub_key = st.text_input("Finnhub API Key (Earnings)", type="password")
    if not fred_key:
        fred_key = st.text_input("FRED API Key (Official US Macro)", type="password")
    
    st.subheader("Watchlist")
    watchlist_input = st.text_input(
        "Tickers (comma-separated)", 
        "NVDA, MSFT, AAPL, AMZN, GOOGL, META, TSLA, TSM, ASML, AMD, JPM, GS, WMT, COST, HD, CAT, FDX, XOM, UNH, ORCL", 
        key="watchlist_input_v10"
    )
    tickers = [t.strip().upper() for t in watchlist_input.split(",") if t.strip()]

    st.subheader("Lookahead & Filters")
    lookahead_days = st.slider("Lookahead Window (Days)", min_value=7, max_value=45, value=28)
    min_impact = st.selectbox("Minimum Event Impact", ["High Impact Only", "Medium & High", "All Impacts"], index=0)
    
    st.subheader("Active Data Pipelines")
    use_ff   = st.checkbox("ForexFactory (Economic & Speeches)", value=True)
    use_fred = st.checkbox("St. Louis Fed (FRED 30-Day)", value=True)
    use_fed  = st.checkbox("Central Bank Speeches & Keynotes", value=True)
    use_eia  = st.checkbox("EIA Crude Inventory Delta", value=True)

today = datetime.date.today()
end_date = today + datetime.timedelta(days=lookahead_days)
today_str = today.strftime("%Y-%m-%d")
end_str = end_date.strftime("%Y-%m-%d")

# ==========================================
# 2. PIPELINE A: FOREXFACTORY (CALENDAR & SPEECHES)
# ==========================================
@st.cache_data(ttl=1800)
def get_forexfactory_thisweek(impact_choice):
    events = []
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5).json()
        speech_keywords = ["speaks", "speech", "testimony", "press conference", "panel", "symposium"]
        
        for item in res:
            curr = item.get("country", "")
            impact = item.get("impact", "")
            title = item.get("title", "")
            
            if curr == "USD":
                is_speech = any(k in title.lower() for k in speech_keywords)
                
                if impact_choice == "High Impact Only" and impact != "High" and not is_speech:
                    continue
                elif impact_choice == "Medium & High" and impact not in ["High", "Medium"] and not is_speech:
                    continue
                
                raw_date = item.get("date", "")
                event_date = raw_date.split("T")[0] if "T" in raw_date else raw_date
                
                # Categorize speeches under Central Bank
                category = "Central Bank" if is_speech else "Macro Economic"
                risk = "⚠️ Rate Guidance" if is_speech else ("🔴 Macro Pivot" if impact == "High" else "⚠️ Mid Impact")
                
                forecast = item.get("forecast", "N/A")
                prev = item.get("previous", "N/A")
                details = f"Scheduled Central Bank Event" if is_speech else f"Forecast: {forecast} | Prev: {prev}"
                
                events.append({
                    "Date": event_date,
                    "Event": f"[{curr}] {title}",
                    "Category": category,
                    "Source": "ForexFactory",
                    "Risk Tier": risk,
                    "Details": details
                })
    except Exception:
        pass
    return events

# ==========================================
# 3. PIPELINE B: FRED API (OFFICIAL 30-DAY MACRO)
# ==========================================
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

# ==========================================
# 4. PIPELINE C: FINNHUB EARNINGS
# ==========================================
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

# ==========================================
# 5. PIPELINE D: CENTRAL BANK SPEECHES & SYMPOSIUMS
# ==========================================
@st.cache_data(ttl=1800)
def get_central_bank_events(start_d, end_d):
    events = []
    
    # 1. Live Fed Speeches Feed (Transcripts & remarks published today)
    try:
        feed = feedparser.parse("https://www.federalreserve.gov/feeds/speeches.xml")
        for entry in feed.entries[:10]:
            pub_date = pd.to_datetime(entry.published).strftime("%Y-%m-%d")
            events.append({
                "Date": pub_date,
                "Event": f"[Fed] {entry.title}",
                "Category": "Central Bank",
                "Source": "Fed RSS",
                "Risk Tier": "⚠️ Rate Guidance",
                "Details": "Federal Reserve Governor Speech / Remarks"
            })
    except Exception:
        pass

    # 2. Major Scheduled Annual Keynotes & Symposia
    cur_year = start_d.year
    
    # Jackson Hole Symposium (Late August)
    jh_date = datetime.date(cur_year, 8, 27)
    if start_d <= jh_date <= end_d:
        events.append({
            "Date": jh_date.strftime("%Y-%m-%d"),
            "Event": "[Fed] Jackson Hole Economic Policy Symposium",
            "Category": "Central Bank",
            "Source": "Fed Calendar",
            "Risk Tier": "🔴 Macro Pivot",
            "Details": "Global Central Banking Conference | Keynote on Monetary Policy"
        })
        
    return events

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
# 6. ROW STYLING ENGINE
# ==========================================
def style_row_by_category(row):
    cat = row.get("Category", "")
    if cat == "Single Stock":
        return ["background-color: rgba(0, 229, 255, 0.14)"] * len(row)
    elif cat == "Macro Economic":
        return ["background-color: rgba(255, 23, 68, 0.14)"] * len(row)
    elif cat == "Energy":
        return ["background-color: rgba(255, 214, 0, 0.15)"] * len(row)
    elif cat == "Central Bank":
        return ["background-color: rgba(224, 64, 251, 0.14)"] * len(row)
    return [""] * len(row)

# ==========================================
# 7. CONSOLIDATE, STYLE & RENDER
# ==========================================
all_catalysts = []

if use_ff:
    all_catalysts.extend(get_forexfactory_thisweek(min_impact))
if use_fred and fred_key:
    all_catalysts.extend(get_fred_calendar(fred_key, today_str, end_str))
if finnhub_key:
    all_catalysts.extend(get_finnhub_earnings(finnhub_key, tickers, today_str, end_str))
if use_fed:
    all_catalysts.extend(get_central_bank_events(today, end_date))
if use_eia:
    all_catalysts.extend(get_eia_releases(today, lookahead_days))

df = pd.DataFrame(all_catalysts)

if not df.empty:
    df["Date"] = pd.to_datetime(df["Date"])
    # Include today and future events
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
    c3.metric("Central Bank Speeches", len(df[df["Category"] == "Central Bank"]))
    c4.metric("High-Risk Events (Next 7D)", len(df[df["Days Left"].str.contains("TODAY|In 1D|In 2D|In 3D|In 4D|In 5D|In 6D|In 7D")]))

    st.subheader(f"📅 Consolidated Catalyst Timeline ({today_str} to {end_str})")
    
    # Legend Guide
    st.markdown(
        """
        <div style="display: flex; gap: 20px; font-size: 0.85rem; margin-bottom: 12px;">
            <span><span style="display:inline-block;width:12px;height:12px;background:rgba(0,229,255,0.4);border-radius:2px;margin-right:6px;"></span><b>Single Stock</b></span>
            <span><span style="display:inline-block;width:12px;height:12px;background:rgba(255,23,68,0.4);border-radius:2px;margin-right:6px;"></span><b>Macro Economic</b></span>
            <span><span style="display:inline-block;width:12px;height:12px;background:rgba(255,214,0,0.4);border-radius:2px;margin-right:6px;"></span><b>Energy</b></span>
            <span><span style="display:inline-block;width:12px;height:12px;background:rgba(224,64,251,0.4);border-radius:2px;margin-right:6px;"></span><b>Central Bank (Speeches)</b></span>
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
    
    display_df = filtered_df[["Date", "Days Left", "Event", "Category", "Source", "Risk Tier", "Details"]]
    styled_df = display_df.style.apply(style_row_by_category, axis=1)

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True
    )
else:
    st.warning("No scheduled catalysts found. Check your API keys or expand the lookahead window.")