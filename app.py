import streamlit as st
import pandas as pd
import datetime
import yfinance as yf
import feedparser
import requests

st.set_page_config(page_title="Macro & Earnings Catalyst Hub", layout="wide")

st.title("🎯 4-Week Catalyst & Binary Event Matrix")

# Read Finnhub key from Streamlit Secrets or manual sidebar input
finnhub_key = st.secrets.get("FINNHUB_KEY", "")
with st.sidebar:
    st.header("Watchlist Settings")
    watchlist_input = st.text_input(
        "Watchlist (comma-separated)", 
        "NVDA, AAPL, MU, RTX, JPM, XOM, TSLA", 
        key="watchlist_v2"  # Incrementing this forces a clean reset
    )
    tickers = [t.strip().upper() for t in watchlist_input.split(",") if t.strip()]
    if not finnhub_key:
        finnhub_key = st.text_input("Finnhub API Key (Optional)", type="password")

@st.cache_data(ttl=3600)
def get_earnings_calendar(ticker_list):
    events = []
    for sym in ticker_list:
        try:
            t = yf.Ticker(sym)
            cal = t.calendar
            if cal is not None and not cal.empty:
                if 'Earnings Date' in cal.index:
                    dates = cal.loc['Earnings Date']
                    earn_date = dates.iloc[0] if isinstance(dates, pd.Series) else dates[0]
                    events.append({
                        "Event": f"{sym} Earnings",
                        "Category": "Single Stock",
                        "Date": pd.to_datetime(earn_date).strftime("%Y-%m-%d"),
                        "Details": "Quarterly Financial Release",
                        "Risk Tier": "🚨 High Volatility"
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
                "Event": title,
                "Category": "Central Bank",
                "Date": pd.to_datetime(entry.published).strftime("%Y-%m-%d"),
                "Details": entry.get("summary", "Federal Reserve Event"),
                "Risk Tier": "⚠️ Rate Guidance"
            })
    return speech_events

@st.cache_data(ttl=3600)
def get_macro_calendar(api_key):
    macro_events = []
    if api_key:
        try:
            today = datetime.date.today()
            end = today + datetime.timedelta(days=30)
            url = f"https://finnhub.io/api/v1/calendar/economic?from={today}&to={end}&token={api_key}"
            res = requests.get(url).json()
            for item in res.get("economicCalendar", []):
                if item.get("impact") in ["high", 3] and item.get("country") == "US":
                    macro_events.append({
                        "Event": item.get("event"),
                        "Category": "Macro Economic",
                        "Date": item.get("time", "").split(" ")[0],
                        "Details": f"Impact: {item.get('impact')}",
                        "Risk Tier": "🔴 Macro Pivot"
                    })
        except Exception:
            pass
            
    if not macro_events:
        today = datetime.date.today()
        macro_events = [
            {"Event": "US CPI Inflation Print", "Category": "Macro Economic", "Date": (today + datetime.timedelta(days=8)).strftime("%Y-%m-%d"), "Details": "Headline & Core CPI", "Risk Tier": "🔴 Macro Pivot"},
            {"Event": "FOMC Rate Decision", "Category": "Macro Economic", "Date": (today + datetime.timedelta(days=14)).strftime("%Y-%m-%d"), "Details": "Policy Decision + Presser", "Risk Tier": "🔴 Macro Pivot"},
            {"Event": "NFP Labor Report", "Category": "Macro Economic", "Date": (today + datetime.timedelta(days=21)).strftime("%Y-%m-%d"), "Details": "Non-Farm Payrolls", "Risk Tier": "⚠️ Rate Guidance"},
            {"Event": "EIA Petroleum Stocks", "Category": "Energy", "Date": (today + datetime.timedelta(days=(2 - today.weekday()) % 7)).strftime("%Y-%m-%d"), "Details": "Weekly Commercial Crude Delta", "Risk Tier": "🟡 Commodity Beta"}
        ]
    return macro_events

all_events = []
all_events.extend(get_earnings_calendar(tickers))
all_events.extend(get_fed_speeches())
all_events.extend(get_macro_calendar(finnhub_key))

df = pd.DataFrame(all_events)
if not df.empty:
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values(by="Date", ascending=True).reset_index(drop=True)
    df["Days Remaining"] = (df["Date"].dt.date - datetime.date.today()).apply(
        lambda x: f"In {x.days} Days" if x.days > 0 else ("TODAY" if x.days == 0 else "Passed")
    )
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    col1, col2, col3 = st.columns(3)
    col1.metric("Tracked Equities", len(tickers))
    col2.metric("Total Upcoming Catalysts", len(df))
    col3.metric("High-Risk Events (Next 7D)", len(df[df["Days Remaining"].str.contains("0|1|2|3|4|5|6|7|TODAY")]))

    st.subheader("Upcoming Catalyst Timeline")
    st.dataframe(df[["Date", "Days Remaining", "Event", "Category", "Risk Tier", "Details"]], use_container_width=True)
