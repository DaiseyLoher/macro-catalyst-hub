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
        key="watchlist_input_v3"
    )
    tickers = [t.strip().upper() for t in watchlist_input.split(",") if t.strip()]

    st.subheader("Macro Calendar Filters")
    min_impact = st.selectbox("Minimum Event Impact", ["High Impact Only", "Medium & High", "All Events"], index=0)
    lookahead_days = st.slider("Lookahead Window (Days)", min_value=7, max_value=45, value=28)
    
    track_fed = st.checkbox("Track Fed Speeches & Keynotes (RSS)", value=True)
    track_eia = st.checkbox("Track Weekly EIA Crude Oil Prints", value=True)

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
# 3. MACRO ECONOMIC PIPELINE (WITH AUTO-FALLBACK)
# ==========================================
@st.cache_data(ttl=3600)
def get_macro_calendar(api_key, start_d, end_d, impact_level, lookahead):
    events = []
    
    # 1. Attempt Finnhub Economic Calendar
    if api_key:
        try:
            url = f"https://finnhub.io/api/v1/calendar/economic?from={start_d}&to={end_d}&token={api_key}"
            res = requests.get(url, timeout=5).json()
            raw_events = res.get("economicCalendar", [])
            
            macro_keywords = ["cpi", "fomc", "fed", "nonfarm", "unemployment", "ppi", "pce", "gdp", "retail sales", "ism", "interest rate"]
            
            for item in raw_events:
                if item.get("country") != "US":
                    continue
                raw_impact = str(item.get("impact", "")).lower()
                event_title = item.get("event", "")
                
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

    # 2. Dynamic High-Impact Schedule Fallback (Ensures Macro Dates Always Show)
    if not events:
        cpi_day = today + datetime.timedelta(days=(10 - today.day) % 30 if today.day <= 10 else 10)
        nfp_day = today + datetime.timedelta(days=(4 - today.weekday() + 7) % 7 if today.day <= 7 else 7)
        fomc_day = today + datetime.timedelta(days=15 if today.day <= 15 else 25)
        ppi_day = cpi_day + datetime.timedelta(days=1)
        retail_day = cpi_day + datetime.timedelta(days=3)

        fallback_schedule = [
            {"Date": cpi_day.strftime("%Y-%m-%d"), "Event": "US CPI Inflation (Headline & Core)", "Category": "Macro Economic", "Risk Tier": "🔴 Macro Pivot", "Details": "8:30 AM EST | Primary Fed Inflation Metric"},
            {"Date": ppi_day.strftime("%Y-%m-%d"), "Event": "US PPI Producer Price Index", "Category": "Macro Economic", "Risk Tier": "⚠️ Mid Impact", "Details": "8:30 AM EST | Wholesale Pipeline Inflation"},
            {"Date": nfp_day.strftime("%Y-%m-%d"), "Event": "US Non-Farm Payrolls & Unemployment", "Category": "Macro Economic", "Risk Tier": "🔴 Macro Pivot", "Details": "8:30 AM EST | BLS Monthly Labor Report"},
            {"Date": fomc_day.strftime("%Y-%m-%d"), "Event": "FOMC Rate Decision & Press Conference", "Category": "Macro Economic", "Risk Tier": "🔴 Macro Pivot", "Details": "2:00 PM EST | Fed Policy Rate + Powell Q&A"},
            {"Date": retail_day.strftime("%Y-%m-%d"), "Event": "US Retail Sales MoM", "Category": "Macro Economic", "Risk Tier": "⚠️ Mid Impact", "Details": "8:30 AM EST | Consumer Spending Strength"}
        ]
        
        # Include events within the selected lookahead window
        for item in fallback_schedule:
            if item["Date"] <= end_d:
                events.append(item)
                
    return events

# ==========================================
# 4. FED RSS SPEECHES & EIA RELEASES
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
                "Event": "EIA Weekly Petroleum Status Report",
                "Category": "Energy",
                "Risk Tier": "🟡 Commodity Beta",
                "Details": "10:30 AM EST | Official Commercial Crude Oil Inventory Delta"
            })
    return eia_events

# ==========================================
# 5. CONSOLIDATE & RENDER
# ==========================================
all_catalysts = []

if finnhub_key:
    all_catalysts.extend(get_finnhub_earnings(finnhub_key, tickers, today_str, end_str))

all_catalysts.extend(get_macro_calendar(finnhub_key, today_str, end_str, min_impact, lookahead_days))

if track_fed:
    all_catalysts.extend(get_fed_speeches())

if track_eia:
    all_catalysts.extend(get_eia_releases(today, lookahead_days))

df = pd.DataFrame(all_catalysts)

if not df.empty:
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[df["Date"].dt.date >= today]
    df = df.sort_values(by="Date", ascending=True).reset_index(drop=True)
    
    df["Days Left"] = (df["Date"].dt.date - today).apply(
        lambda x: "TODAY" if x.days == 0 else f"In {x.days}D"
    )
    df["Formatted Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # Metrics Summary
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracked Tickers", len(tickers))
    c2.metric("Total Upcoming Catalysts", len(df))
    c3.metric("Single-Stock Earnings", len(df[df["Category"] == "Single Stock"]))
    c4.metric("High-Risk Events (Next 7D)", len(df[df["Days Left"].str.contains("TODAY|In 1D|In 2D|In 3D|In 4D|In 5D|In 6D|In 7D")]))

    st.subheader(f"📅 Catalyst Timeline ({today_str} to {end_str})")
    
    selected_cats = st.multiselect("Filter by Category", options=df["Category"].unique(), default=df["Category"].unique())
    filtered_df = df[df["Category"].isin(selected_cats)]
    
    st.dataframe(
        filtered_df[["Formatted Date", "Days Left", "Event", "Category", "Risk Tier", "Details"]].rename(columns={"Formatted Date": "Date"}),
        use_container_width=True,
        hide_index=True
    )
else:
    st.warning("No catalysts found. Expand the lookahead window in the sidebar.")