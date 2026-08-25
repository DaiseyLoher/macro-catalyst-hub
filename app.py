import streamlit as st
import pandas as pd
import datetime
import requests
import feedparser

st.set_page_config(page_title="Macro & Earnings Catalyst Hub", layout="wide")
st.title("🎯 4-Week Tactical Catalyst & Binary Event Horizon")

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
    default_top20 = "NVDA, MSFT, AAPL, AMZN, GOOGL, META, TSLA, TSM, ASML, AMD, JPM, GS, WMT, COST, HD, CAT, FDX, XOM, UNH, ORCL"
    watchlist_input = st.text_input(
        "Tickers (comma-separated)", 
        default_top20, 
        key="watchlist_input_v11"
    )
    tickers = [t.strip().upper() for t in watchlist_input.split(",") if t.strip()]

    st.subheader("Filters & Feeds")
    min_impact = st.selectbox("Minimum Event Impact", ["High Impact Only", "Medium & High", "All Impacts"], index=0)
    use_ff   = st.checkbox("ForexFactory (Economic & Speeches)", value=True)
    use_fred = st.checkbox("St. Louis Fed (FRED 30-Day)", value=True)
    use_fed  = st.checkbox("Central Bank Speeches & Keynotes", value=True)
    use_eia  = st.checkbox("EIA Crude Inventory Delta", value=True)

today = datetime.date.today()
end_date = today + datetime.timedelta(days=28)
today_str = today.strftime("%Y-%m-%d")
end_str = end_date.strftime("%Y-%m-%d")

# ==========================================
# 2. SPEECH TIERING ENGINE
# ==========================================
def classify_speech_impact(title, summary=""):
    text = (title + " " + summary).lower()
    tier_1_speakers = ["powell", "jefferson", "williams", "chair", "vice chair"]
    tier_1_venues = ["jackson hole", "testimony", "monetary policy report", "humphrey-hawkins", "press conference"]
    
    tier_2_speakers = ["waller", "bowman", "barr", "cook", "kugler", "bostic", "goolsbee", "kashkari", "logan"]
    tier_2_topics = ["economic outlook", "inflation", "monetary policy", "interest rates", "balance sheet", "qt"]

    if any(s in text for s in tier_1_speakers) or any(v in text for v in tier_1_venues):
        if not any(k in text for k in ["welcoming remarks", "opening remarks", "adjournment"]):
            return "🔴 Macro Pivot (High)", "Tier 1: Fed Leadership / Policy Shift"
            
    if any(s in text for s in tier_2_speakers) and any(t in text for t in tier_2_topics):
        return "⚠️ Rate Guidance (Mid)", "Tier 2: FOMC Voter Policy Discussion"
        
    return "🟡 Low Impact", "Tier 3: Academic / Routine Remarks"

# ==========================================
# 3. DATA PIPELINES
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
                
                if is_speech:
                    tier, desc = classify_speech_impact(title)
                    category = "Central Bank"
                    risk = tier
                    details = desc
                else:
                    category = "Macro Economic"
                    risk = "🔴 Macro Pivot" if impact == "High" else "⚠️ Mid Impact"
                    forecast = item.get("forecast", "N/A")
                    prev = item.get("previous", "N/A")
                    details = f"Forecast: {forecast} | Previous: {prev}"

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

@st.cache_data(ttl=14400)
def get_fred_calendar(api_key, start_d, end_d):
    events = []
    if not api_key:
        return events
    
    # Strict tiering: Only CPI, NFP, and FOMC get Tier-1 Macro Pivot status
    release_metadata = {
        10:  ("US CPI Inflation (Headline & Core)", "🔴 Macro Pivot (High)", "Tier 1: CPI Inflation Shock Risk"),
        50:  ("US Employment Situation (NFP & Unemployment)", "🔴 Macro Pivot (High)", "Tier 1: Labor & Fed Pivot Risk"),
        323: ("FOMC Policy Materials / Decision", "🔴 Macro Pivot (High)", "Tier 1: Fed Rate Decision"),
        11:  ("US PPI Producer Price Index", "⚠️ Mid Impact", "Tier 2: Wholesale Inflation"),
        53:  ("US Gross Domestic Product (GDP)", "⚠️ Mid Impact", "Tier 2: Quarterly Growth"),
        9:   ("US Advance Monthly Retail Sales", "⚠️ Mid Impact", "Tier 2: Consumer Spending"),
        22:  ("US Industrial Production", "🟡 Low Impact", "Tier 3: Manufacturing Output"),
        27:  ("US Housing Starts & Permits", "🟡 Low Impact", "Tier 3: Real Estate Activity")
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
            if rel_id in release_metadata:
                name, risk_tier, desc = release_metadata[rel_id]
                events.append({
                    "Date": item.get("date"),
                    "Event": f"[US] {name}",
                    "Category": "Macro Economic",
                    "Source": "FRED",
                    "Risk Tier": risk_tier,
                    "Details": desc
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
def get_central_bank_events(start_d, end_d):
    events = []
    try:
        feed = feedparser.parse("https://www.federalreserve.gov/feeds/speeches.xml")
        for entry in feed.entries[:10]:
            pub_date = pd.to_datetime(entry.published).strftime("%Y-%m-%d")
            tier, desc = classify_speech_impact(entry.title, entry.get("summary", ""))
            events.append({
                "Date": pub_date,
                "Event": f"[Fed] {entry.title}",
                "Category": "Central Bank",
                "Source": "Fed RSS",
                "Risk Tier": tier,
                "Details": desc
            })
    except Exception:
        pass
    
    # Jackson Hole Symposium
    cur_year = start_d.year
    jh_date = datetime.date(cur_year, 8, 27)
    if start_d <= jh_date <= end_d:
        events.append({
            "Date": jh_date.strftime("%Y-%m-%d"),
            "Event": "[Fed] Jackson Hole Economic Policy Symposium",
            "Category": "Central Bank",
            "Source": "Fed Calendar",
            "Risk Tier": "🔴 Macro Pivot (High)",
            "Details": "Global Central Banking Keynote | Macro Policy Framework"
        })
    return events

def get_eia_releases(start_d, lookahead=28):
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
                "Details": "10:30 AM EST | Official Crude Inventory Delta"
            })
    return events

# ==========================================
# 4. ROW COLOR STYLING
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
# 1. ACCURATELY TIERED FRED MACRO CALENDAR
# ==========================================
@st.cache_data(ttl=14400)
def get_fred_calendar(api_key, start_d, end_d):
    events = []
    if not api_key:
        return events
    
    # Strict tiering: Only CPI, NFP, and FOMC get Tier-1 Macro Pivot status
    release_metadata = {
        10:  ("US CPI Inflation (Headline & Core)", "🔴 Macro Pivot (High)", "Tier 1: CPI Inflation Shock Risk"),
        50:  ("US Employment Situation (NFP & Unemployment)", "🔴 Macro Pivot (High)", "Tier 1: Labor & Fed Pivot Risk"),
        323: ("FOMC Policy Materials / Decision", "🔴 Macro Pivot (High)", "Tier 1: Fed Rate Decision"),
        11:  ("US PPI Producer Price Index", "⚠️ Mid Impact", "Tier 2: Wholesale Inflation"),
        53:  ("US Gross Domestic Product (GDP)", "⚠️ Mid Impact", "Tier 2: Quarterly Growth"),
        9:   ("US Advance Monthly Retail Sales", "⚠️ Mid Impact", "Tier 2: Consumer Spending"),
        22:  ("US Industrial Production", "🟡 Low Impact", "Tier 3: Manufacturing Output"),
        27:  ("US Housing Starts & Permits", "🟡 Low Impact", "Tier 3: Real Estate Activity")
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
            if rel_id in release_metadata:
                name, risk_tier, desc = release_metadata[rel_id]
                events.append({
                    "Date": item.get("date"),
                    "Event": f"[US] {name}",
                    "Category": "Macro Economic",
                    "Source": "FRED",
                    "Risk Tier": risk_tier,
                    "Details": desc
                })
    except Exception:
        pass
    return events

# ==========================================
# 2. CALIBRATED WEIGHTED REGIME CLASSIFIER
# ==========================================
def analyze_week_regime(week_df):
    """
    Weighted scoring model that prevents false-positive binary alerts.
    """
    if week_df.empty:
        return {
            "regime": "📈 Trend Continuation / Clear Horizon",
            "color": "#00E676",
            "summary": "Zero scheduled macro or corporate catalysts. Optimal backdrop for technical swing setups and uninterrupted trend continuation."
        }

    score = 0
    tier1_macro_count = 0
    mag7_earnings_count = 0
    mag7_tickers = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA"]

    for _, row in week_df.iterrows():
        event = str(row.get("Event", "")).upper()
        cat = row.get("Category", "")
        risk = str(row.get("Risk Tier", ""))

        # 1. Tier-1 Macro Shocks (3 Points each)
        if any(k in event for k in ["CPI", "NON-FARM", "EMPLOYMENT SITUATION", "FOMC RATE", "JACKSON HOLE KEYNOTE"]):
            score += 3
            tier1_macro_count += 1
        # 2. Mega-Weight Mag-7 Earnings (2 Points each)
        elif cat == "Single Stock" and any(t in event for t in mag7_tickers):
            score += 2
            mag7_earnings_count += 1
        # 3. Central Bank Leadership / High Volatility Speeches (2 Points)
        elif cat == "Central Bank" and "🔴" in risk:
            score += 2
        # 4. Standard Earnings or Mid-Tier Macro (1 Point each)
        elif cat == "Single Stock" or "⚠️" in risk:
            score += 1

    # Regime Determination
    if score >= 3:
        return {
            "regime": "🚨 High Binary Risk / Volatility Cluster",
            "color": "#FF1744",
            "summary": f"Binary event density is elevated ({tier1_macro_count} Tier-1 Macro print(s), {mag7_earnings_count} Mag-7 report(s)). Expect elevated implied volatility, directional gap risk, and choppy pre-event price action."
        }
    elif score == 2:
        return {
            "regime": "⚠️ Policy Guidance / Selective Binary Risk",
            "color": "#E040FB",
            "summary": "Moderate headline catalyst scheduled (isolated mega-cap earnings or Fed rate guidance). Index trend is tradable, but exercise caution around event release windows."
        }
    elif score == 1:
        return {
            "regime": "📊 Single-Stock Dispersion / Low Macro Beta",
            "color": "#00E5FF",
            "summary": "No broad index shocks scheduled. Macro backdrop is quiet; individual stock setups will trade on idiosyncratic fundamentals rather than broad market beta."
        }
    else:
        return {
            "regime": "📈 Trend Friendly / Low Catalyst Density",
            "color": "#FFD600",
            "summary": "Low-impact routine data only. Clean environment for standard technical breakout, pullbacks, and momentum strategies."
        }
# ==========================================
# 6. CONSOLIDATE & BUILD DASHBOARD
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
    all_catalysts.extend(get_eia_releases(today, 28))

df = pd.DataFrame(all_catalysts)

if not df.empty:
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[df["Date"].dt.date >= today]
    df = df.drop_duplicates(subset=["Date", "Event"]).sort_values(by="Date", ascending=True).reset_index(drop=True)
    df["Days Left"] = (df["Date"].dt.date - today).apply(lambda x: "TODAY" if x.days == 0 else f"In {x.days}D")
    df["Formatted Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # ==========================================
    # VIEW SELECTOR: TACTICAL WEEKLY VS RAW TIMELINE
    # ==========================================
    tab1, tab2 = st.tabs(["🗓️ 4-Week Tactical Horizon (Regime View)", "📋 Raw Master Timeline"])

    with tab1:
        st.subheader("Tactical Weekly Categorization & Risk Profiles")
        
        # Build 4 Distinct 7-Day Tranches
        weeks = [
            ("Week 1: Current Window", today, today + datetime.timedelta(days=6)),
            ("Week 2: Next Week", today + datetime.timedelta(days=7), today + datetime.timedelta(days=13)),
            ("Week 3: Forward Horizon", today + datetime.timedelta(days=14), today + datetime.timedelta(days=20)),
            ("Week 4: Extended Horizon", today + datetime.timedelta(days=21), today + datetime.timedelta(days=27))
        ]

        for title, w_start, w_end in weeks:
            w_df = df[(df["Date"].dt.date >= w_start) & (df["Date"].dt.date <= w_end)]
            analysis = analyze_week_regime(w_df)
            
            with st.expander(f"{title} ({w_start.strftime('%b %d')} - {w_end.strftime('%b %d')}) — {analysis['regime']}", expanded=(w_start == today)):
                st.markdown(
                    f"""
                    <div style="background-color: rgba(255,255,255,0.03); padding: 12px; border-left: 5px solid {analysis['color']}; border-radius: 4px; margin-bottom: 12px;">
                        <h4 style="margin:0; color: {analysis['color']};">{analysis['regime']}</h4>
                        <p style="margin: 5px 0 0 0; font-size: 0.95rem; color: #ddd;">{analysis['summary']}</p>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                if not w_df.empty:
                    w_display = w_df[["Formatted Date", "Days Left", "Event", "Category", "Source", "Risk Tier", "Details"]].rename(columns={"Formatted Date": "Date"})
                    w_styled = w_display.style.apply(style_row_by_category, axis=1)
                    st.dataframe(w_styled, use_container_width=True, hide_index=True)
                else:
                    st.caption("No binary catalysts detected in this window.")

    with tab2:
        st.subheader("Master Catalyst Stream")
        
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            selected_cats = st.multiselect("Filter Category", options=df["Category"].unique(), default=df["Category"].unique())
        with f_col2:
            selected_sources = st.multiselect("Filter Source", options=df["Source"].unique(), default=df["Source"].unique())
            
        filtered_df = df[df["Category"].isin(selected_cats) & df["Source"].isin(selected_sources)]
        display_df = filtered_df[["Formatted Date", "Days Left", "Event", "Category", "Source", "Risk Tier", "Details"]].rename(columns={"Formatted Date": "Date"})
        styled_df = display_df.style.apply(style_row_by_category, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

else:
    st.warning("No scheduled catalysts found. Verify API keys or configuration.")