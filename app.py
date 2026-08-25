import streamlit as st
import pandas as pd
import datetime
import requests
import feedparser

st.set_page_config(page_title="Macro & Earnings Catalyst Hub", layout="wide")
st.title("🎯 4-Week Catalyst & Binary Event Matrix")

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
finnhub_key = st.secrets.get("FINNHUB_KEY", "")

with st.sidebar:
    st.header("⚙️ Configuration")
    if not finnhub_key:
        finnhub_key = st.text_input("Finnhub API Key", type="password")
    
    st.subheader("Watchlist")
    watchlist_input = st.text_input(
        "Tickers (comma-separated)", 
        "NVDA, AAPL, BRK.B, RTX, JPM, XOM", 
        key="watchlist_input_v2"
    )
    # Clean tickers: convert BRK.B to BRK-B or BRK.B depending on API
    tickers = [t.strip().upper() for t in watchlist_input.split(",") if t.strip()]

    st.subheader("Macro Calendar Filters")
    min_impact = st.selectbox("Minimum Event Impact", ["High Impact Only", "Medium & High", "All Events"], index=0)
    lookahead_days = st.slider("Lookahead Window (Days)", min_value=7, max_value=45, value=28)
    
    track_fed = st.checkbox("Track Fed Speeches (RSS)", value=True)
    track_eia = st.checkbox("Track Weekly EIA Crude Oil Prints", value=True)

# Date calculations
today = datetime.date.today()
end_date = today + datetime.timedelta(days=lookahead_days)
today_str = today.strftime("%Y-%m-%d")
end_str = end_date.strftime("%Y-%m-%d")

# ==========================================
# 2. EARNINGS PIPELINE (FINNHUB NATIVE)
# ==========================================
@st.cache_data(ttl=1800)
def get_finnhub_earnings(api_key, ticker_list, start_d, end_d):
    events = []
    if not api_key:
        return events
    
    for sym in ticker_list:
        # Finnhub uses BRK.B format
        clean_sym = sym.replace("-", ".")
        url = f"https://finnhub.io/api/v1/calendar/earnings?from={start_d}&to={end_d}&symbol={clean_sym}&token={api_key}"
        try:
            res = requests.get(url, timeout=5).json()
            earnings_list = res.get("earningsCalendar", [])
            for item in earnings_list:
                e_date = item.get("date")
                e_hour = item.get("hour", "").upper()
                timing = "Before Open (BMO)" if e_hour == "BMO" else ("After Close (AMC)" if e_hour == "AMC" else "During Session")
                eps_est = item.get("epsEstimate")
                details = f"Timing: {timing} | EPS Est: ${eps_est:.2f}" if eps_est is not None else f"Timing: {timing}"
                
                events.append({
                    "Date": e_date,
                    "Event": f"{sym} Earnings",
                    "Category": "Single Stock",
                    "Risk Tier": "🚨 High Volatility",
                    "Details": details
                })
        except Exception:
            continue
    return events

# ==========================================
# 3. MACRO ECONOMIC CALENDAR (FINNHUB)
# ==========================================
@st.cache_data(ttl=3600)
def get_finnhub_macro(api_key, start_d, end_d, impact_level):
    events = []
    if not api_key:
        return events
    
    url = f"https://finnhub.io/api/v1/calendar/economic?from={start_d}&to={end_d}&token={api_key}"
    try:
        res = requests.get(url, timeout=5).json()
        raw_events = res.get("economicCalendar", [])
        
        # Whitelist of high-signal macro releases
        macro_keywords = ["cpi", "fomc", "fed", "nonfarm", "unemployment", "ppi", "pce", "gdp", "retail sales", "ism", "interest rate"]
        
        for item in raw_events:
            if item.get("country") != "US":
                continue
            
            raw_impact = str(item.get("impact", "")).lower()
            event_title = item.get("event", "")
            
            # Impact filtering
            is_high = raw_impact in ["high", "3"]
            is_med = raw_impact in ["medium", "2"]
            matches_keyword = any(k in event_title.lower() for k in macro_keywords)
            
            if impact_level == "High Impact Only" and not (is_high or matches_keyword):
                continue
            elif impact_level == "Medium & High" and not (is_high or is_med or matches_keyword):
                continue
            
            raw_time = item.get("time", "")
            date_str = raw_time.split(" ")[0] if raw_time else today_str
            
            events.append({
                "Date": date_str,
                "Event": event_title,
                "Category": "Macro Economic",
                "Risk Tier": "🔴 Macro Pivot" if is_high or matches_keyword else "⚠️ Mid Impact",
                "Details": f"Impact: {raw_impact.upper()} | Prev: {item.get('prev', 'N/A')} | Est: {item.get('estimate', 'N/A')}"
            })
    except Exception:
        pass
    return events

# ==========================================
# 4. FED SPEECHES & EIA RELEASES
# ==========================================
@st.cache_data(ttl=1800)
def get_fed_speeches():
    feed_url = "https://www.federalreserve.gov/feeds/press_all.xml"
    feed = feedparser.parse(feed_url)
    speech_events = []
    
    for entry in feed.entries[:15]:
        title = entry.title
        if any(k in title.lower() for k in ["speech", "testimony", "statement", "fomc", "symposium", "conference"]):
            pub_date = pd.to_datetime(entry.published).strftime("%Y-%m-%d")
            speech_events.append({
                "Date": pub_date,
                "Event": title,
                "Category": "Central Bank",
                "Risk Tier": "⚠️ Rate Guidance",
                "Details": entry.get("summary", "Federal Reserve Speech")
            })
    return speech_events

def get_eia_releases(start_d, lookahead):
    eia_events = []
    for i in range(lookahead):
        d = start_d + datetime.timedelta(days=i)
        if d.weekday() == 2:  # Wednesday
            eia_events.append({
                "Date": d.strftime("%Y-%m-%d"),
                "Event": "EIA Weekly Crude Oil Stocks Change",
                "Category": "Energy",
                "Risk Tier": "🟡 Commodity Beta",
                "Details": "Official US Petroleum Inventory Delta (10:30 AM EST)"
            })
    return eia_events

# ==========================================
# 5. AGGREGATE & RENDER DASHBOARD
# ==========================================
all_catalysts = []

# Pull data
if finnhub_key:
    all_catalysts.extend(get_finnhub_earnings(finnhub_key, tickers, today_str, end_str))
    all_catalysts.extend(get_finnhub_macro(finnhub_key, today_str, end_str, min_impact))
else:
    st.info("💡 Add your Finnhub API Key in Streamlit Secrets or the sidebar to enable automated earnings and economic calendars.")

if track_fed:
    all_catalysts.extend(get_fed_speeches())

if track_eia:
    all_catalysts.extend(get_eia_releases(today, lookahead_days))

df = pd.DataFrame(all_catalysts)

if not df.empty:
    df["Date"] = pd.to_datetime(df["Date"])
    # Filter only future or today events
    df = df[df["Date"].dt.date >= today]
    df = df.sort_values(by="Date", ascending=True).reset_index(drop=True)
    
    df["Days Left"] = (df["Date"].dt.date - today).apply(
        lambda x: "TODAY" if x.days == 0 else f"In {x.days}D"
    )
    df["Formatted Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # Metrics Summary
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracked Tickers", len(tickers))
    c2.metric("Total Catalysts (Next 4W)", len(df))
    c3.metric("Single-Stock Earnings", len(df[df["Category"] == "Single Stock"]))
    c4.metric("High-Risk Events (Next 7D)", len(df[df["Days Left"].str.contains("TODAY|In 1D|In 2D|In 3D|In 4D|In 5D|In 6D|In 7D")]))

    # Display Table
    st.subheader(f"📅 Catalyst Timeline ({today_str} to {end_str})")
    
    # Category Filter
    selected_cats = st.multiselect("Filter by Category", options=df["Category"].unique(), default=df["Category"].unique())
    filtered_df = df[df["Category"].isin(selected_cats)]
    
    st.dataframe(
        filtered_df[["Formatted Date", "Days Left", "Event", "Category", "Risk Tier", "Details"]].rename(columns={"Formatted Date": "Date"}),
        use_container_width=True,
        hide_index=True
    )
else:
    st.warning("No scheduled catalysts found within this date range. Verify your API key or expand the lookahead window.")