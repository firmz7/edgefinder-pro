from __future__ import annotations
import time
import os, json, sqlite3, math, re, feedparser, requests, yfinance as yf
from datetime import datetime, timezone, timedelta, date as date_cls
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo
import pandas as pd, numpy as np, plotly.graph_objects as go, plotly.express as px, streamlit as st
from dotenv import load_dotenv
import streamlit.components.v1 as components
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

load_dotenv()

# ---------- Timezone helpers ----------
NY = ZoneInfo("America/New_York")
UK = ZoneInfo("Europe/London")
UTC = timezone.utc

def _ny_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a yfinance DataFrame index to America/New_York, tz-aware."""
    if df is None or df.empty:
        return df
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(NY)
    return df

def _ny_today() -> date_cls:
    return datetime.now(NY).date()

# ---------- Asset config ----------
ASSETS = {
    "MGC": {"symbol":"MGC","name":"Micro Gold","ticker":"MGC=F","tv_ticker":"CME_MINI:MGC1!","news_queries":["gold","MGC","micro gold"],"inverse_dxy":True,"safe_haven":True,"type":"Futures","favors":"Low Yields, High VIX"},
    "MNQ": {"symbol":"MNQ","name":"Micro Nasdaq","ticker":"MNQ=F","tv_ticker":"CME_MINI:MNQ1!","news_queries":["Nasdaq","MNQ","micro nasdaq"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates, Tech Surge"},
    "MES": {"symbol":"MES","name":"Micro S&P 500","ticker":"MES=F","tv_ticker":"CME_MINI:MES1!","news_queries":["S&P 500","MES","micro sp"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates, Low VIX"},
    "M2K": {"symbol":"M2K","name":"Micro Russell 2000","ticker":"M2K=F","tv_ticker":"CME_MINI:M2K1!","news_queries":["Russell","M2K","micro russell"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates"},
    "BTC": {"symbol":"BTC","name":"Micro Bitcoin","ticker":"BTC=F","tv_ticker":"CME_MINI:BTC1!","news_queries":["Bitcoin","BTC","crypto"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Risk-On, Liquidity"},
    "MCL": {"symbol":"MCL","name":"Micro Crude Oil","ticker":"MCL=F","tv_ticker":"CME_MINI:MCL1!","news_queries":["crude","oil","MCL"],"inverse_dxy":False,"safe_haven":False,"type":"Futures","favors":"Inflation, Supply"},
    "MNK": {"symbol":"MNK","name":"Micro Nikkei 225","ticker":"MNK=F","tv_ticker":"CME_MINI:MNK1!","news_queries":["Nikkei","MNK","micro nikkei"],"inverse_dxy":False,"safe_haven":False,"type":"Futures","favors":"Asian Markets, Tech"},
    "US30": {"symbol":"US30","name":"Micro Dow","ticker":"US30=F","tv_ticker":"CBOT_MINI:YM1!","news_queries":["Dow","US30","micro dow"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates, Industrial"},
    "SIL": {"symbol":"SIL","name":"Micro Silver","ticker":"SIL=F","tv_ticker":"CME_MINI:SI1!","news_queries":["silver","SIL","micro silver"],"inverse_dxy":True,"safe_haven":True,"type":"Futures","favors":"Industrial Demand, Inflation"},
    "US02Y": {"symbol":"US02Y","name":"2-Year Treasury Yield","ticker":"^IRX","tv_ticker":"TVC:US02Y","news_queries":["2Y","IRX","treasury"],"inverse_dxy":False,"safe_haven":False,"type":"Yield","favors":"High Rates"},
    "US10Y": {"symbol":"US10Y","name":"10-Year Treasury Yield","ticker":"^TNX","tv_ticker":"TVC:US10Y","news_queries":["10Y","TNX","treasury"],"inverse_dxy":False,"safe_haven":False,"type":"Yield","favors":"High Rates"},
    "US30Y": {"symbol":"US30Y","name":"30-Year Treasury Yield","ticker":"^TYX","tv_ticker":"TVC:US30Y","news_queries":["30Y","TYX","treasury"],"inverse_dxy":False,"safe_haven":False,"type":"Yield","favors":"High Rates"},
    "DXY": {"symbol":"DXY","name":"US Dollar Index","ticker":"DX-Y.NYB","tv_ticker":"TVC:DXY","news_queries":["DXY","dollar index"],"inverse_dxy":False,"safe_haven":False,"type":"Currency","favors":"High Yields"},
    "VIX": {"symbol":"VIX","name":"CBOE Volatility Index","ticker":"^VIX","tv_ticker":"^VIX","news_queries":["VIX","volatility"],"inverse_dxy":False,"safe_haven":False,"type":"Index","favors":"Panic"},
    "N225": {"symbol":"N225","name":"Nikkei 225","ticker":"N225","tv_ticker":"N225","news_queries":["Nikkei","N225","japan"],"inverse_dxy":False,"safe_haven":False,"type":"Index","favors":"Asian Tech, Weak Yen"},
    "KS11": {"symbol":"KS11","name":"KOSPI Index","ticker":"^KS11","tv_ticker":"KS11","news_queries":["KOSPI","KS11","south korea"],"inverse_dxy":False,"safe_haven":False,"type":"Index","favors":"Semiconductors"},
    "SAMSUNG": {"symbol":"SAMSUNG","name":"Samsung Electronics","ticker":"005930.KS","tv_ticker":"005930.KS","news_queries":["Samsung","005930","electronics"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"Semiconductors, Memory"},
    "SKHYNIX": {"symbol":"SKHYNIX","name":"SK Hynix","ticker":"000660.KS","tv_ticker":"000660.KS","news_queries":["SK Hynix","000660","memory"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"Semiconductors, Memory"},
    "NVDA": {"symbol":"NVDA","name":"NVIDIA","ticker":"NVDA","tv_ticker":"NASDAQ:NVDA","news_queries":["NVIDIA","NVDA","AI"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"AI, Growth"},
    "TSLA": {"symbol":"TSLA","name":"Tesla","ticker":"TSLA","tv_ticker":"NASDAQ:TSLA","news_queries":["Tesla","TSLA","EV"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"EV, Growth"},
    "META": {"symbol":"META","name":"Meta","ticker":"META","tv_ticker":"NASDAQ:META","news_queries":["Meta","META","Facebook"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"Advertising, AI"},
    "AMZN": {"symbol":"AMZN","name":"Amazon","ticker":"AMZN","tv_ticker":"NASDAQ:AMZN","news_queries":["Amazon","AMZN","AWS"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"E-commerce, Cloud"},
    "SMH": {"symbol":"SMH","name":"Semiconductor ETF","ticker":"SMH","tv_ticker":"AMEX:SMH","news_queries":["SMH","semiconductors","chips"],"inverse_dxy":True,"safe_haven":False,"type":"ETF","favors":"AI, Chips"},
    "PLTR": {"symbol":"PLTR","name":"Palantir","ticker":"PLTR","tv_ticker":"NYSE:PLTR","news_queries":["Palantir","PLTR","defense"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"AI, Defense"},
    "NOW": {"symbol":"NOW","name":"ServiceNow","ticker":"NOW","tv_ticker":"NYSE:NOW","news_queries":["ServiceNow","NOW","cloud"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"Cloud, AI"},
}

RSS_FEEDS=[
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/news/wealth",
    "https://finance.yahoo.com/news/rssindex",
    "https://www.marketwatch.com/rss/topstories",
]
POSITIVE_TERMS={"surge","beats","beat","rally","gain","gains","jump","bullish","strong","cooling inflation","rate cut","soft landing","upgrade","record high","rebound","outperform"}
NEGATIVE_TERMS={"drop","falls","fall","misses","miss","selloff","bearish","weak","hot inflation","rate hike","downgrade","recession","warning","tariffs","war","outflows"}

# ---------- Treasury intervention ----------
class TreasuryIntervention:
    YIELD_CAP_10Y = 4.75
    YIELD_CAP_30Y = 5.25
    BUYBACK_START = datetime(2026, 9, 9, tzinfo=UTC)
    BUYBACK_END = datetime(2026, 11, 4, tzinfo=UTC)

    @staticmethod
    def get_buyback_status():
        now = datetime.now(UTC)
        if TreasuryIntervention.BUYBACK_START <= now <= TreasuryIntervention.BUYBACK_END:
            return "ACTIVE", "🟢"
        elif now < TreasuryIntervention.BUYBACK_START:
            days = (TreasuryIntervention.BUYBACK_START - now).days
            return f"STARTS IN {days} DAYS", "🟡"
        return "COMPLETED", "⚪"

    @staticmethod
    def calculate_yield_stress(ten_year, thirty_year):
        stress_10y = max(0, (ten_year / TreasuryIntervention.YIELD_CAP_10Y - 1) * 100)
        stress_30y = max(0, (thirty_year / TreasuryIntervention.YIELD_CAP_30Y - 1) * 100)
        return stress_10y, stress_30y

class SMCSignal:
    def __init__(self):
        self.bullish_bos = False
        self.bearish_bos = False
        self.bullish_choch = False
        self.bearish_choch = False
        self.strong_high = 0.0
        self.weak_high = 0.0
        self.strong_low = 0.0
        self.weak_low = 0.0
        self.structure_bias = "NEUTRAL"

# ---------- Economic calendar ----------
def get_economic_calendar() -> List[Dict]:
    api_key = os.getenv("FOREXFACTORY_API_KEY")
    if not api_key:
        return get_economic_calendar_fallback()
    try:
        url = "https://www.jblanked.com/news/api/list/"
        headers = {"Content-Type": "application/json", "Authorization": f"Api-Key {api_key}"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            now = datetime.now(UTC)
            upcoming = []
            for item in data:
                try:
                    event_date = datetime.fromisoformat(item.get("date", "").replace("Z", "+00:00"))
                    if event_date > now:
                        d = event_date - now
                        days = d.days
                        h, r = divmod(d.seconds, 3600)
                        m, _ = divmod(r, 60)
                        c = f"{days}d {h}h {m}m" if days > 0 else f"{h}h {m}m"
                        upcoming.append({"name": f"🇺🇸 {item.get('title', '').replace('**', '')}", "countdown": c})
                except Exception:
                    continue
            return upcoming[:3]
        return get_economic_calendar_fallback()
    except Exception:
        return get_economic_calendar_fallback()

def get_economic_calendar_fallback() -> List[Dict]:
    now = datetime.now(UTC)
    events = [
        {"name": "🇺🇸 FOMC Rate Decision", "date": datetime(2026, 7, 29, 18, 0, tzinfo=UTC)},
        {"name": "🇺🇸 CPI Data (MoM)", "date": datetime(2026, 8, 12, 12, 30, tzinfo=UTC)},
        {"name": "🇺🇸 NFP (Non-Farm Payrolls)", "date": datetime(2026, 8, 7, 12, 30, tzinfo=UTC)},
    ]
    upcoming = []
    for e in events:
        if e["date"] > now:
            d = e["date"] - now
            days = d.days
            h, r = divmod(d.seconds, 3600)
            m, _ = divmod(r, 60)
            c = f"{days}d {h}h {m}m" if days > 0 else f"{h}h {m}m"
            upcoming.append({"name": e["name"], "countdown": c})
    return upcoming[:3]

# ---------- Options sentiment ----------
def get_options_sentiment(ticker="SPY") -> Dict:
    try:
        t = yf.Ticker(ticker)
        exps = t.options
        if not exps:
            return {"ratio": 0.5, "sentiment": "Neutral", "calls": 0, "puts": 0}
        oc = t.option_chain(exps[0])
        c = oc.calls['volume'].sum()
        p = oc.puts['volume'].sum()
        if c + p == 0:
            return {"ratio": 0.5, "sentiment": "Neutral", "calls": 0, "puts": 0}
        pcr = p / c
        s = ("🐻 Bearish" if pcr > 0.8 else
             "⚖️ Neutral-Bearish" if pcr > 0.6 else
             "⚖️ Neutral-Bullish" if pcr > 0.4 else
             "🐂 Bullish")
        return {"ratio": round(pcr, 2), "sentiment": s, "puts": int(p), "calls": int(c)}
    except Exception:
        return {"ratio": 0.5, "sentiment": "Neutral", "calls": 0, "puts": 0}

def calc_fear_greed(vix, pcr, dxy) -> Dict:
    vs = 10 if vix > 30 else 30 if vix > 20 else 60 if vix > 14 else 85
    ps = 20 if pcr > 0.8 else 40 if pcr > 0.65 else 60 if pcr > 0.5 else 80
    ds = 20 if dxy > 106 else 40 if dxy > 103 else 60 if dxy > 100 else 80
    o = int((vs * 0.4) + (ps * 0.4) + (ds * 0.2))
    l = ("🔴 Extreme Fear" if o < 20 else "😨 Fear" if o < 40 else
         "😐 Neutral" if o < 60 else "😀 Greed" if o < 80 else "🟢 Extreme Greed")
    return {"score": o, "label": l}

# ---------- Macro ----------
def get_macro_data() -> Dict:
    try:
        dxy_data = yf.Ticker("DX-Y.NYB").history(period="1d", interval="1m")
        dxy = dxy_data['Close'].iloc[-1] if not dxy_data.empty else 102.0
    except Exception:
        dxy = 102.0
    try:
        vix_data = yf.Ticker("^VIX").history(period="1d", interval="1m")
        vix = vix_data['Close'].iloc[-1] if not vix_data.empty else 18.0
    except Exception:
        vix = 18.0
    ry = float(os.getenv("EDGEFINDER_REAL_YIELD_FALLBACK", "1.8"))
    try:
        tnx_data = yf.Ticker("^TNX").history(period="1d", interval="1m")
        tnx = tnx_data['Close'].iloc[-1] if not tnx_data.empty else 4.20
    except Exception:
        tnx = 4.20
    try:
        tyx_data = yf.Ticker("^TYX").history(period="1d", interval="1m")
        tyx = tyx_data['Close'].iloc[-1] if not tyx_data.empty else 4.50
    except Exception:
        tyx = 4.50
    buyback_status, buyback_icon = TreasuryIntervention.get_buyback_status()
    stress_10y, stress_30y = TreasuryIntervention.calculate_yield_stress(tnx, tyx)
    return {
        "dxy": dxy, "vix": vix, "real_yield_10y": ry,
        "yield_10y": tnx, "yield_30y": tyx,
        "buyback_status": buyback_status, "buyback_icon": buyback_icon,
        "yield_stress_10y": stress_10y, "yield_stress_30y": stress_30y,
        "yield_cap_10y": TreasuryIntervention.YIELD_CAP_10Y,
        "yield_cap_30y": TreasuryIntervention.YIELD_CAP_30Y,
    }

# ---------- News ----------
def _clean(t): return re.sub(r"\s+", " ", t.strip().lower())

def _headline_score(t):
    t = _clean(t)
    s = 0.0
    for term in POSITIVE_TERMS:
        s += 1.0 if term in t else 0
    for term in NEGATIVE_TERMS:
        s -= 1.0 if term in t else 0
    return max(-1.0, min(1.0, s / 3.0))

def get_news_data(asset_name, queries) -> Dict:
    matches = []
    lq = [_clean(q) for q in queries]
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                hay = _clean(entry.title) + " " + _clean(entry.summary)
                if any(q in hay for q in lq):
                    matches.append(_headline_score(entry.title))
        except Exception:
            continue
    sentiment = sum(matches) / len(matches) if matches else 0.0
    return {"asset": asset_name, "sentiment": sentiment, "headlines": len(matches)}

# ---------- Bias ----------
class Bias(str, Enum):
    VERY_BEARISH = "Very Bearish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"
    BULLISH = "Bullish"
    VERY_BULLISH = "Very Bullish"

def score_to_bias(score: int) -> Bias:
    if score <= 2: return Bias.VERY_BEARISH
    if score <= 4: return Bias.BEARISH
    if score == 5: return Bias.NEUTRAL
    if score <= 7: return Bias.BULLISH
    return Bias.VERY_BULLISH

@dataclass
class IndicatorReading:
    name: str
    value: float
    score: int
    bias: Bias
    note: str = ""

@dataclass
class AssetSnapshot:
    symbol: str
    name: str
    price: float
    technical_score: int
    macro_score: int
    news_score: int
    overall_score: int
    overall_bias: Bias
    technical_details: List[IndicatorReading] = field(default_factory=list)
    macro_details: List[IndicatorReading] = field(default_factory=list)
    news_details: List[IndicatorReading] = field(default_factory=list)

# ---------- Technicals (RSI fixed to use most recent 14 bars) ----------
def calc_rsi(closes, period: int = 14) -> float:
    if closes is None or len(closes) < period + 1:
        return 50.0
    recent = list(closes)[-(period + 1):]
    gains = [max(recent[i] - recent[i - 1], 0) for i in range(1, len(recent))]
    losses = [abs(min(recent[i] - recent[i - 1], 0)) for i in range(1, len(recent))]
    ag = sum(gains) / period
    al = sum(losses) / period
    if al == 0:
        return 100.0
    return 100 - (100 / (1 + ag / al))

def sma(values, p) -> float:
    if len(values) < p:
        return sum(values) / len(values)
    return sum(values[-p:]) / p

def score_rsi(rsi) -> int:
    return 3 if rsi < 30 else 4 if rsi < 40 else 5 if rsi < 50 else 6 if rsi < 60 else 7 if rsi < 70 else 6

def score_trend_pct(tp) -> int:
    return 9 if tp > 8 else 8 if tp > 4 else 7 if tp > 1 else 5 if tp > -1 else 4 if tp > -4 else 3 if tp > -8 else 2

def score_dxy(value, inverse) -> int:
    b = 3 if value > 108 else 4 if value > 104 else 5 if value > 100 else 6 if value > 96 else 7
    return 10 - b if inverse else b

def score_vix(value, safe_haven) -> int:
    return 8 if value > 30 else 6 if value > 20 else 5 if safe_haven else (5 if value < 14 else 7 if value < 20 else 4 if value < 30 else 2)

def score_real_yield(value, inverse) -> int:
    b = 7 if value < 0 else 6 if value < 1 else 4 if value < 2 else 2
    return b if inverse else 10 - b

def score_news(sentiment) -> int:
    return max(0, min(10, int(round(5 + sentiment * 5))))

# ---------- DB ----------
DB_PATH = Path("edgefinder.db")

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            technical_score INTEGER NOT NULL,
            macro_score INTEGER NOT NULL,
            news_score INTEGER NOT NULL,
            overall_score INTEGER NOT NULL,
            overall_bias TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_snapshot(snapshot) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO snapshots (ts_utc, symbol, name, price, technical_score, macro_score, news_score, overall_score, overall_bias, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(UTC).isoformat(), snapshot.symbol, snapshot.name, snapshot.price,
            snapshot.technical_score, snapshot.macro_score, snapshot.news_score,
            snapshot.overall_score, snapshot.overall_bias.value,
            json.dumps({"symbol": snapshot.symbol, "name": snapshot.name}),
        ),
    )
    conn.commit()
    conn.close()

# ---------- Snapshot builder ----------
def build_swing_snapshot(config, macro, news) -> AssetSnapshot:
    ticker = config["ticker"]
    try:
        daily = yf.Ticker(ticker).history(period="6mo")
        if daily.empty:
            daily = yf.Ticker(ticker).history(period="1mo")
        if daily.empty:
            closes = [100.0]; p = 100.0; r = 50.0; m50 = 100.0; m200 = 100.0; tp = 0.0; ts = 5
            td = [
                IndicatorReading("RSI 14", r, score_rsi(r), score_to_bias(score_rsi(r))),
                IndicatorReading("Trend vs 50D MA %", tp, score_trend_pct(tp), score_to_bias(score_trend_pct(tp))),
            ]
        else:
            closes = daily['Close'].tolist()
            p = closes[-1]
            r = calc_rsi(closes)
            m50 = sma(closes, 50)
            m200 = sma(closes, 200)
            tp = ((p - m50) / m50) * 100 if m50 else 0
            ts = (score_rsi(r) + score_trend_pct(tp)) // 2
            td = [
                IndicatorReading("RSI 14", r, score_rsi(r), score_to_bias(score_rsi(r))),
                IndicatorReading("Trend vs 50D MA %", tp, score_trend_pct(tp), score_to_bias(score_trend_pct(tp))),
            ]
    except Exception:
        closes = [100.0]; p = 100.0; r = 50.0; m50 = 100.0; m200 = 100.0; tp = 0.0; ts = 5
        td = [
            IndicatorReading("RSI 14", r, score_rsi(r), score_to_bias(score_rsi(r))),
            IndicatorReading("Trend vs 50D MA %", tp, score_trend_pct(tp), score_to_bias(score_trend_pct(tp))),
        ]
    inv = config.get("inverse_dxy", False)
    safe = config.get("safe_haven", False)
    md = [
        IndicatorReading("DXY", macro["dxy"], score_dxy(macro["dxy"], inv), score_to_bias(score_dxy(macro["dxy"], inv))),
        IndicatorReading("VIX", macro["vix"], score_vix(macro["vix"], safe), score_to_bias(score_vix(macro["vix"], safe))),
        IndicatorReading("Real Yield", macro["real_yield_10y"], score_real_yield(macro["real_yield_10y"], inv), score_to_bias(score_real_yield(macro["real_yield_10y"], inv))),
    ]
    ms = sum([x.score for x in md]) // 3
    ns = score_news(news.get("sentiment", 0.0))
    o = int(round(ts * 0.45 + ms * 0.30 + ns * 0.25))
    return AssetSnapshot(
        symbol=config["symbol"], name=config["name"], price=p,
        technical_score=ts, macro_score=ms, news_score=ns,
        overall_score=o, overall_bias=score_to_bias(o),
        technical_details=td, macro_details=md,
        news_details=[IndicatorReading("News Sentiment", news.get("sentiment", 0), ns, score_to_bias(ns))],
    )

# ---------- Market classification ----------
def classify_market_conditions(ticker="MNQ=F"):
    try:
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
        if data.empty:
            return {"classification": "UNKNOWN", "reason": "No data available"}
        data = _ny_frame(data)
        today = _ny_today()
        data_today = data[data.index.date == today]
        if data_today.empty:
            data_today = data.tail(100)
        high = data_today['High']; low = data_today['Low']; close = data_today['Close']
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        atr = tr.rolling(14).mean().iloc[-1] if len(tr) >= 14 else tr.mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean().iloc[-1] / atr) if atr > 0 else 0
        minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean().iloc[-1] / atr) if atr > 0 else 0
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        adx = dx
        vwap = (data_today['Close'] * data_today['Volume']).cumsum() / data_today['Volume'].cumsum()
        current_vwap = vwap.iloc[-1]
        vwap_slope = (vwap.iloc[-1] - vwap.iloc[-5]) / vwap.iloc[-5] * 100 if len(vwap) >= 5 else 0
        ema9 = data_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        ema20 = data_today['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = data_today['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        current_price = data_today['Close'].iloc[-1]
        ema_separation = abs(ema9 - ema20) / current_price * 100
        ny_data = data_today.between_time('08:00', '09:29')
        ny_range = (ny_data['High'].max() - ny_data['Low'].min()) if not ny_data.empty else 0
        if current_price > ema9 > ema20 > ema50:
            trend_direction = "UP"
        elif current_price < ema9 < ema20 < ema50:
            trend_direction = "DOWN"
        else:
            trend_direction = "MIXED"
        trending_signals = 0
        ranging_signals = 0
        if adx > 25: trending_signals += 1
        elif adx < 20: ranging_signals += 1
        if abs(vwap_slope) > 0.1: trending_signals += 1
        elif abs(vwap_slope) < 0.05: ranging_signals += 1
        if ema_separation > 0.15: trending_signals += 1
        elif ema_separation < 0.05: ranging_signals += 1
        if ny_range > 40: trending_signals += 1
        elif ny_range < 25: ranging_signals += 1
        ema200 = data_today['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
        if abs(current_price - ema200) / current_price > 0.005:
            trending_signals += 1
        else:
            ranging_signals += 1
        if trending_signals >= 3:
            classification = "TRENDING"; confidence = min(100, 50 + trending_signals * 10)
        elif ranging_signals >= 3:
            classification = "RANGING"; confidence = min(100, 50 + ranging_signals * 10)
        else:
            classification = "UNCLEAR"; confidence = 50
        return {
            "classification": classification, "confidence": confidence,
            "adx": round(adx, 1), "vwap_slope": round(vwap_slope, 3),
            "ema_separation": round(ema_separation, 3), "ny_range": round(ny_range, 1),
            "trend_direction": trend_direction, "current_price": current_price,
            "ema9": ema9, "ema20": ema20, "ema50": ema50, "ema200": ema200,
            "vwap": current_vwap,
        }
    except Exception as e:
        return {"classification": "UNKNOWN", "reason": str(e)}

# ---------- Render asset ----------
def render_asset(asset_key, auto_save):
    cfg = ASSETS[asset_key]
    macro = get_macro_data()
    news = get_news_data(cfg["name"], cfg["news_queries"])
    snapshot = build_swing_snapshot(cfg, macro, news)
    if auto_save:
        save_snapshot(snapshot)
    st.markdown(f"### {snapshot.name} ({snapshot.symbol})")
    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Price", f"${snapshot.price:,.2f}")
        st.metric("Overall Score", f"{snapshot.overall_score}/10")
        st.markdown(f"**Bias:** {snapshot.overall_bias.value}")
    with c2:
        tech_df = pd.DataFrame([
            {"Indicator": x.name, "Value": round(x.value, 2), "Bias": x.bias.value}
            for x in snapshot.technical_details
        ])
        st.dataframe(tech_df, width='stretch', hide_index=True)

# ---------- Strategy Selector ----------
def run_strategy_selector():
    st.subheader("🎯 Strategy Selector & Decision Engine")
    st.caption("Automatically recommends the best strategy based on current market conditions")
    macro = get_macro_data()
    tnx = macro.get('yield_10y', 4.20); vix = macro.get('vix', 18.0); dxy = macro.get('dxy', 102.0)
    market = classify_market_conditions("MNQ=F")
    market_class = market.get('classification', 'UNKNOWN')
    trend_direction = market.get('trend_direction', 'MIXED')
    is_high_yield = tnx > 4.5
    is_elevated_yield = 4.3 < tnx <= 4.5
    is_normal_yield = tnx <= 4.3
    is_high_volatility = vix > 30

    if is_high_volatility:
        recommended_strategy = "⛔ NO TRADE - SIT OUT"; position_size = "0%"
        reasoning = [f"🔴 VIX > 30 ({vix:.2f})", "❌ No strategy works reliably", "⛔ SIT OUT"]
    elif is_high_yield and market_class == "RANGING":
        recommended_strategy = "⚡ High Yield Protocol"; position_size = "25%"
        reasoning = [f"🔴 US10Y > 4.5% ({tnx:.2f}%)", f"📊 Market RANGING (ADX: {market.get('adx', 0):.1f})", "✅ Fade extremes"]
    elif is_high_yield and market_class == "TRENDING":
        recommended_strategy = "⛔ NO TRADE - SIT OUT"; position_size = "0%"
        reasoning = [f"🔴 US10Y > 4.5%", "📊 Market TRENDING", "❌ No strategy works", "⛔ SIT OUT"]
    elif is_normal_yield and market_class == "TRENDING":
        recommended_strategy = "📈 Trend-Fade Hybrid"; position_size = "50-75%"
        reasoning = [f"🟢 US10Y < 4.3%", f"📊 Market TRENDING (Dir: {trend_direction})", "✅ Fade pullbacks WITH trend"]
    elif is_normal_yield and market_class == "RANGING":
        recommended_strategy = "⚡ High Yield Protocol (Low Yield Variant)"; position_size = "50%"
        reasoning = [f"🟢 US10Y < 4.3%", "📊 Market RANGING", "✅ Fade extremes"]
    elif is_elevated_yield:
        if market_class == "TRENDING":
            recommended_strategy = "📈 Trend-Fade Hybrid (Reduced)"; position_size = "50%"
            reasoning = [f"🟡 US10Y 4.3-4.5%", "📊 Market TRENDING", "⚠️ Reduce size"]
        else:
            recommended_strategy = "⚡ High Yield Protocol (Reduced)"; position_size = "50%"
            reasoning = [f"🟡 US10Y 4.3-4.5%", "⚠️ Caution", "📉 Reduce size"]
    else:
        recommended_strategy = "⛔ NO TRADE - SIT OUT"; position_size = "0%"
        reasoning = [f"🟡 Market UNCLEAR", "⛔ SIT OUT"]

    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### 📊 Market Conditions")
        st.markdown(f"**US10Y:** {tnx:.2f}%")
        st.markdown(f"**VIX:** {vix:.2f}")
        st.markdown(f"**DXY:** {dxy:.2f}")
        st.markdown(f"**Market Type:** {market_class}")
        st.markdown(f"**Trend:** {trend_direction}")
        st.markdown(f"**ADX:** {market.get('adx', 0):.1f}")
    with col2:
        st.markdown("### 🎯 Recommended Strategy")
        if "NO TRADE" in recommended_strategy:
            st.error(f"### {recommended_strategy}")
        elif "Trend-Fade" in recommended_strategy:
            st.success(f"### {recommended_strategy}")
        else:
            st.warning(f"### {recommended_strategy}")
        st.markdown(f"**Position Size:** {position_size}")
        st.markdown("#### 📋 Reasoning")
        for r in reasoning:
            st.info(r)

# ---------- High Yield Protocol (MNQ, generic) ----------
def run_high_yield_protocol():
    st.subheader("⚡ High Yield Protocol (4.5%+ Yields)")
    macro = get_macro_data()
    tnx = macro['yield_10y']; vix = macro['vix']
    if tnx < 4.5:
        st.success(f"🟢 Yields below 4.5% ({tnx:.2f}%). Use VWAP & EMA strategy.")
        return
    st.warning(f"🔴 HIGH YIELD MODE (US10Y: {tnx:.2f}%)")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1: st.metric("US10Y", f"{tnx:.2f}%")
    with col_m2: st.metric("VIX", f"{vix:.2f}")
    with col_m3: st.metric("DXY", f"{macro['dxy']:.2f}")
    st.markdown("---")
    asset_choice = st.selectbox("Select Asset", ["MNQ (Micro Nasdaq)", "MGC (Micro Gold)", "MES (Micro S&P 500)"], key="hy_asset")
    ticker = {"MNQ (Micro Nasdaq)": "MNQ=F", "MGC (Micro Gold)": "MGC=F", "MES (Micro S&P 500)": "MES=F"}[asset_choice]
    with st.spinner("Loading data..."):
        data = _ny_frame(yf.Ticker(ticker).history(period="2d", interval="5m"))
    if data.empty:
        st.warning("No data"); return
    today = _ny_today()
    data_today = data[data.index.date == today]
    ny_data = data_today.between_time('08:00', '09:29')
    if ny_data.empty:
        st.warning("NY Pre-Market data unavailable"); return
    ny_high = ny_data['High'].max(); ny_low = ny_data['Low'].min(); ny_range = ny_high - ny_low
    current_price = data_today['Close'].iloc[-1]
    col_l1, col_l2, col_l3, col_l4 = st.columns(4)
    with col_l1: st.metric("NY High", f"{ny_high:.2f}")
    with col_l2: st.metric("NY Low", f"{ny_low:.2f}")
    with col_l3: st.metric("Range", f"{ny_range:.2f}")
    with col_l4: st.metric("Current", f"{current_price:.2f}")
    if current_price > ny_high - 10:
        st.error(f"✅ SHORT — Entry: {current_price:.2f} | SL: {ny_high + 5:.2f} | TP: {current_price - (ny_range * 0.5):.2f}")
    elif current_price < ny_low + 10:
        st.success(f"✅ LONG — Entry: {current_price:.2f} | SL: {ny_low - 5:.2f} | TP: {current_price + (ny_range * 0.5):.2f}")
    else:
        st.info("⏳ No signal — middle of range")

# ---------- High Yield Protocol - MES ----------
def run_high_yield_protocol_mes():
    st.subheader("⚡ High Yield Protocol — MES (Micro S&P 500)")
    st.caption("Tighter stops for MES. Buffer 5 pts | SL 3 pts beyond | Target 0.5x NY Range")
    macro = get_macro_data()
    tnx = macro['yield_10y']; vix = macro['vix']
    if tnx < 4.5:
        st.success(f"🟢 Yields below 4.5% ({tnx:.2f}%). Use VWAP & EMA strategy instead.")
        return
    if vix > 30:
        st.error(f"⛔ VIX > 30 ({vix:.2f}) — SIT OUT")
        return
    st.warning(f"🔴 HIGH YIELD MODE — MES (US10Y: {tnx:.2f}%)")

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1: st.metric("US10Y", f"{tnx:.2f}%")
    with col_m2: st.metric("VIX", f"{vix:.2f}")
    with col_m3: st.metric("DXY", f"{macro['dxy']:.2f}")

    st.markdown("---")
    st.markdown("### 📏 MES Parameters")
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1: st.metric("Buffer", "5 pts")
    with col_p2: st.metric("Stop Loss", "3 pts beyond")
    with col_p3: st.metric("Typical Move", "5-10 pts")
    with col_p4: st.metric("Position Size", "2 contracts (25%)")

    ticker = "MES=F"
    with st.spinner("Loading MES data..."):
        data = _ny_frame(yf.Ticker(ticker).history(period="2d", interval="5m"))
    if data.empty:
        st.warning("No data"); return

    today = _ny_today()
    data_today = data[data.index.date == today]
    ny_data = data_today.between_time('08:00', '09:29')
    if ny_data.empty:
        st.warning("NY Pre-Market data unavailable"); return

    ny_high = ny_data['High'].max(); ny_low = ny_data['Low'].min()
    ny_range = ny_high - ny_low
    current_price = data_today['Close'].iloc[-1]

    col_l1, col_l2, col_l3, col_l4 = st.columns(4)
    with col_l1: st.metric("NY High", f"{ny_high:.2f}")
    with col_l2: st.metric("NY Low", f"{ny_low:.2f}")
    with col_l3: st.metric("Range", f"{ny_range:.2f}")
    with col_l4: st.metric("Current", f"{current_price:.2f}")

    st.markdown("---")
    BUF = 5.0   # MES buffer
    SL = 3.0    # MES stop beyond
    if ny_range < 5:
        st.info(f"⏳ NY Range too tight ({ny_range:.2f}) — skip")
    elif current_price > ny_high - BUF:
        target = current_price - (ny_range * 0.5)
        st.error(
            f"✅ SHORT MES — Entry: {current_price:.2f} | "
            f"SL: {ny_high + SL:.2f} | TP: {target:.2f}"
        )
    elif current_price < ny_low + BUF:
        target = current_price + (ny_range * 0.5)
        st.success(
            f"✅ LONG MES — Entry: {current_price:.2f} | "
            f"SL: {ny_low - SL:.2f} | TP: {target:.2f}"
        )
    else:
        st.info("⏳ No signal — middle of range")

# ---------- Trend-Fade Hybrid ----------
def run_trend_fade_hybrid():
    st.subheader("📈 Trend-Fade Hybrid")
    st.caption("Fade pullbacks WITHIN the trend. Best time: 3:00-4:00 PM UK")
    market = classify_market_conditions("MNQ=F")
    if market['classification'] == "TRENDING":
        st.success(f"🟢 TREND MODE — Confidence: {market.get('confidence', 0)}%")
    elif market['classification'] == "RANGING":
        st.error("🔴 RANGE MODE — Switch to High Yield Protocol")
        return
    else:
        st.warning("🟡 UNCLEAR MARKET — Sit out")
        return

    now_utc = datetime.now(UTC)
    uk_time = now_utc.astimezone(UK)
    st.markdown(f"**Current UK Time:** {uk_time.strftime('%H:%M')}")
    st.markdown(f"**Trend Direction:** {market['trend_direction']}")
    st.markdown("---")

    asset_choice = st.selectbox("Select Asset", ["MNQ (Micro Nasdaq)", "MGC (Micro Gold)", "MES (Micro S&P 500)"], key="tfh_asset")
    ticker = {"MNQ (Micro Nasdaq)": "MNQ=F", "MGC (Micro Gold)": "MGC=F", "MES (Micro S&P 500)": "MES=F"}[asset_choice]
    with st.spinner("Loading data..."):
        data = _ny_frame(yf.Ticker(ticker).history(period="2d", interval="5m"))
        if data.empty:
            st.warning("No data"); return
        today = _ny_today()
        data_today = data[data.index.date == today]
        if data_today.empty:
            data_today = data.tail(100)
        current_price = data_today['Close'].iloc[-1]
        vwap = (data_today['Close'] * data_today['Volume']).cumsum() / data_today['Volume'].cumsum()
        current_vwap = vwap.iloc[-1]
        ema9 = data_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]

    st.markdown("### 📊 Key Levels")
    col_l1, col_l2, col_l3, col_l4 = st.columns(4)
    with col_l1: st.metric("Current Price", f"{current_price:.2f}")
    with col_l2: st.metric("VWAP", f"{current_vwap:.2f}")
    with col_l3: st.metric("9 EMA", f"{ema9:.2f}")
    with col_l4: st.metric("Trend", market['trend_direction'])
    st.markdown("---")

    macro = get_macro_data()
    tnx = macro.get('yield_10y', 4.20); dxy = macro.get('dxy', 102.0)
    if market['trend_direction'] == "UP":
        macro_ok = dxy < 103 and tnx < 4.5
        vwap_ok = current_price > current_vwap
        ema_ok = current_price > ema9
    elif market['trend_direction'] == "DOWN":
        macro_ok = dxy > 103 or tnx > 4.5
        vwap_ok = current_price < current_vwap
        ema_ok = current_price < ema9
    else:
        st.warning("Mixed signals — no trade"); return

    st.markdown("### ✅ Three-Confirmation Rule")
    st.markdown(f"{'✅' if macro_ok else '❌'} **Macro**")
    st.markdown(f"{'✅' if vwap_ok else '❌'} **VWAP**")
    st.markdown(f"{'✅' if ema_ok else '❌'} **9 EMA**")
    if macro_ok and vwap_ok and ema_ok:
        st.success("🟢 Setup valid!")
    else:
        st.error("🔴 DO NOT TRADE")
    st.markdown("---")

    st.markdown("### 🛡️ Discipline Tracker")
    if 'tfh_daily_pnl' not in st.session_state: st.session_state.tfh_daily_pnl = 0
    if 'tfh_trade_count' not in st.session_state: st.session_state.tfh_trade_count = 0
    if 'tfh_loss_count' not in st.session_state: st.session_state.tfh_loss_count = 0
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1: st.metric("P&L", f"${st.session_state.tfh_daily_pnl:.2f}")
    with col_d2: st.metric("Trades", f"{st.session_state.tfh_trade_count}/3")
    with col_d3: st.metric("Losses", f"{st.session_state.tfh_loss_count}/2")
    col_log1, col_log2 = st.columns(2)
    with col_log1:
        if st.button("✅ Log Win"):
            st.session_state.tfh_daily_pnl += 50
            st.session_state.tfh_trade_count += 1
            st.session_state.tfh_loss_count = 0
            st.rerun()
    with col_log2:
        if st.button("❌ Log Loss"):
            st.session_state.tfh_daily_pnl -= 50
            st.session_state.tfh_trade_count += 1
            st.session_state.tfh_loss_count += 1
            st.rerun()

# ---------- Trend-Fade Hybrid - MES ----------
def run_trend_fade_hybrid_mes():
    st.subheader("📈 Trend-Fade Hybrid — MES (Micro S&P 500)")
    st.caption("Tighter stops for MES. SL 5 pts beyond pullback | Target prior swing (10-15 pts)")
    market = classify_market_conditions("MES=F")
    if market['classification'] == "TRENDING":
        st.success(f"🟢 TREND MODE — Confidence: {market.get('confidence', 0)}%")
    elif market['classification'] == "RANGING":
        st.error("🔴 RANGE MODE — Switch to High Yield Protocol (MES)")
        return
    else:
        st.warning("🟡 UNCLEAR MARKET — Sit out")
        return

    now_utc = datetime.now(UTC)
    uk_time = now_utc.astimezone(UK)
    st.markdown(f"**Current UK Time:** {uk_time.strftime('%H:%M')}")
    st.markdown(f"**Trend Direction:** {market['trend_direction']}")
    st.markdown("---")

    st.markdown("### 📏 MES Parameters")
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1: st.metric("Buffer", "5 pts")
    with col_p2: st.metric("Stop Loss", "5 pts beyond pullback")
    with col_p3: st.metric("Target", "10-15 pts (prior swing)")
    with col_p4: st.metric("Position Size", "2 contracts (25%)")

    ticker = "MES=F"
    with st.spinner("Loading MES data..."):
        data = _ny_frame(yf.Ticker(ticker).history(period="2d", interval="5m"))
        if data.empty:
            st.warning("No data"); return
        today = _ny_today()
        data_today = data[data.index.date == today]
        if data_today.empty:
            data_today = data.tail(100)
        current_price = data_today['Close'].iloc[-1]
        vwap = (data_today['Close'] * data_today['Volume']).cumsum() / data_today['Volume'].cumsum()
        current_vwap = vwap.iloc[-1]
        ema9 = data_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        # prior swing for target reference
        recent_high = data_today['High'].iloc[-30:].max()
        recent_low = data_today['Low'].iloc[-30:].min()

    st.markdown("### 📊 Key Levels")
    col_l1, col_l2, col_l3, col_l4 = st.columns(4)
    with col_l1: st.metric("Current Price", f"{current_price:.2f}")
    with col_l2: st.metric("VWAP", f"{current_vwap:.2f}")
    with col_l3: st.metric("9 EMA", f"{ema9:.2f}")
    with col_l4: st.metric("Trend", market['trend_direction'])
    st.markdown("---")

    macro = get_macro_data()
    tnx = macro.get('yield_10y', 4.20); dxy = macro.get('dxy', 102.0)
    if market['trend_direction'] == "UP":
        macro_ok = dxy < 103 and tnx < 4.5
        vwap_ok = current_price > current_vwap
        ema_ok = current_price > ema9
    elif market['trend_direction'] == "DOWN":
        macro_ok = dxy > 103 or tnx > 4.5
        vwap_ok = current_price < current_vwap
        ema_ok = current_price < ema9
    else:
        st.warning("Mixed signals — no trade"); return

    st.markdown("### ✅ Three-Confirmation Rule")
    st.markdown(f"{'✅' if macro_ok else '❌'} **Macro**")
    st.markdown(f"{'✅' if vwap_ok else '❌'} **VWAP**")
    st.markdown(f"{'✅' if ema_ok else '❌'} **9 EMA**")

    if macro_ok and vwap_ok and ema_ok:
        SL_PTS = 5.0
        if market['trend_direction'] == "UP":
            entry = current_price
            stop = current_vwap - SL_PTS
            target = min(entry + 15, recent_high) if recent_high > entry else entry + 15
            st.success(f"🟢 LONG MES — Entry: {entry:.2f} | SL: {stop:.2f} | TP: {target:.2f}")
        else:
            entry = current_price
            stop = current_vwap + SL_PTS
            target = max(entry - 15, recent_low) if recent_low < entry else entry - 15
            st.error(f"🔴 SHORT MES — Entry: {entry:.2f} | SL: {stop:.2f} | TP: {target:.2f}")
    else:
        st.error("🔴 DO NOT TRADE")

    st.markdown("---")
    st.markdown("### 🛡️ Discipline Tracker (MES)")
    if 'tfh_mes_pnl' not in st.session_state: st.session_state.tfh_mes_pnl = 0
    if 'tfh_mes_trades' not in st.session_state: st.session_state.tfh_mes_trades = 0
    if 'tfh_mes_losses' not in st.session_state: st.session_state.tfh_mes_losses = 0
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1: st.metric("P&L", f"${st.session_state.tfh_mes_pnl:.2f}")
    with col_d2: st.metric("Trades", f"{st.session_state.tfh_mes_trades}/3")
    with col_d3: st.metric("Losses", f"{st.session_state.tfh_mes_losses}/2")
    col_log1, col_log2 = st.columns(2)
    with col_log1:
        if st.button("✅ Log Win (MES)"):
            st.session_state.tfh_mes_pnl += 50
            st.session_state.tfh_mes_trades += 1
            st.session_state.tfh_mes_losses = 0
            st.rerun()
    with col_log2:
        if st.button("❌ Log Loss (MES)"):
            st.session_state.tfh_mes_pnl -= 50
            st.session_state.tfh_mes_trades += 1
            st.session_state.tfh_mes_losses += 1
            st.rerun()

# ---------- MGC Macro Watch ----------
def run_mgc_macro_watch():
    st.subheader("🥇 MGC — Macro Watch (Gold)")
    st.caption("Gold is macro-driven. No mechanical NY-range or trend-fade strategy is applied here.")
    st.info(
        "💡 Gold is not a range-bound index future. It reacts to DXY and yields. "
        "Use this tab to monitor the macro regime. Only enter MGC when DXY and yields agree with your direction."
    )

    macro = get_macro_data()
    dxy = macro['dxy']; tnx = macro['yield_10y']; tyx = macro['yield_30y']; vix = macro['vix']

    # Get gold data
    try:
        mgc_daily = yf.Ticker("MGC=F").history(period="5d", interval="1d")
        mgc_1m = _ny_frame(yf.Ticker("MGC=F").history(period="2d", interval="5m"))
    except Exception as e:
        st.error(f"Failed to load MGC data: {e}"); return

    if mgc_daily.empty:
        st.warning("No MGC daily data"); return

    gold_price = mgc_daily['Close'].iloc[-1]
    prev_close = mgc_daily['Close'].iloc[-2] if len(mgc_daily) > 1 else gold_price
    gold_chg_pct = (gold_price - prev_close) / prev_close * 100

    # Top row: gold price + DXY + yields
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("MGC Price", f"${gold_price:,.2f}", f"{gold_chg_pct:+.2f}%")
    with c2:
        dxy_trend = "🔻 Weak (Bullish Gold)" if dxy < 100 else "🔺 Strong (Bearish Gold)" if dxy > 104 else "⚖️ Neutral"
        st.metric("DXY", f"{dxy:.2f}", dxy_trend)
    with c3:
        tnx_trend = "🔻 Falling (Bullish Gold)" if tnx < 4.0 else "🔺 Rising (Bearish Gold)" if tnx > 4.5 else "⚖️ Neutral"
        st.metric("US10Y", f"{tnx:.2f}%", tnx_trend)
    with c4:
        tyx_trend = "🔻 Falling" if tyx < 4.5 else "🔺 Rising" if tyx > 5.0 else "⚖️ Neutral"
        st.metric("US30Y", f"{tyx:.2f}%", tyx_trend)

    st.markdown("---")

    # Macro regime classifier
    st.markdown("### 🧭 Gold Macro Regime")
    dxy_bull = dxy < 100
    dxy_bear = dxy > 104
    yield_bull = tnx < 4.0
    yield_bear = tnx > 4.5
    vix_high = vix > 25

    if dxy_bull and yield_bull:
        st.success("🟢 **STRONG BULLISH GOLD REGIME** — Weak DXY + Low Yields")
        bias = "LONG bias only"
    elif dxy_bear and yield_bear:
        st.error("🔴 **STRONG BEARISH GOLD REGIME** — Strong DXY + High Yields")
        bias = "SHORT bias only"
    elif vix_high:
        st.warning("🟡 **SAFE-HAVEN REGIME** — High VIX, mixed DXY/yields")
        bias = "Wait for DXY confirmation"
    else:
        st.info("⚪ **MIXED / NEUTRAL REGIME** — No clear macro edge")
        bias = "Stand aside"

    st.markdown(f"**Recommended bias:** {bias}")

    st.markdown("---")

    # Intraday key levels for MGC
    st.markdown("### 📊 MGC Intraday Reference Levels")
    if mgc_1m.empty:
        st.info("No intraday MGC data")
    else:
        today = _ny_today()
        d_today = mgc_1m[mgc_1m.index.date == today]
        if d_today.empty:
            d_today = mgc_1m.tail(100)
        cur = d_today['Close'].iloc[-1]
        vwap = (d_today['Close'] * d_today['Volume']).cumsum() / d_today['Volume'].cumsum()
        cur_vwap = vwap.iloc[-1]
        ema9 = d_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        ny = d_today.between_time('08:00', '09:29')
        ny_high = ny['High'].max() if not ny.empty else float('nan')
        ny_low = ny['Low'].min() if not ny.empty else float('nan')

        lc1, lc2, lc3, lc4, lc5 = st.columns(5)
        with lc1: st.metric("Current", f"{cur:.2f}")
        with lc2: st.metric("VWAP", f"{cur_vwap:.2f}")
        with lc3: st.metric("9 EMA", f"{ema9:.2f}")
        with lc4: st.metric("NY High", f"{ny_high:.2f}" if not math.isnan(ny_high) else "N/A")
        with lc5: st.metric("NY Low", f"{ny_low:.2f}" if not math.isnan(ny_low) else "N/A")

        st.markdown("### 📋 Observations (not signals)")
        if cur > cur_vwap and dxy_bull:
            st.success("Gold above VWAP + weak DXY → observe for continuation longs")
        elif cur < cur_vwap and dxy_bear:
            st.error("Gold below VWAP + strong DXY → observe for continuation shorts")
        else:
            st.info("No aligned observation. Wait for DXY/yield confirmation.")

    st.markdown("---")

    # Simple checklist
    st.markdown("### ✅ MGC Pre-Trade Checklist")
    st.checkbox("DXY is falling (or below 100)", key="mgc_chk_dxy")
    st.checkbox("US10Y is falling (or below 4.0%)", key="mgc_chk_10y")
    st.checkbox("No major US event within 30 min", key="mgc_chk_event")
    st.checkbox("VIX not spiking above 25", key="mgc_chk_vix")
    st.checkbox("Price is above VWAP for longs / below VWAP for shorts", key="mgc_chk_vwap")
    st.caption("⚠️ Only take MGC trades when 4+ boxes are checked. Mechanical NY-range fading is disabled for MGC.")

# ---------- NY Afternoon Sniper ----------
def run_ny_afternoon_sniper():
    st.subheader("🇺🇸 NY Afternoon Sniper (3:30-4:30 PM UK)")
    now_utc = datetime.now(UTC)
    uk_time = now_utc.astimezone(UK)
    st.markdown(f"**Current UK Time:** {uk_time.strftime('%H:%M')}")
    asset_choice = st.selectbox("Select Asset", ["MNQ (Micro Nasdaq)", "MGC (Micro Gold)", "MES (Micro S&P 500)"], key="ny_asset")
    ticker = {"MNQ (Micro Nasdaq)": "MNQ=F", "MGC (Micro Gold)": "MGC=F", "MES (Micro S&P 500)": "MES=F"}[asset_choice]
    with st.spinner("Loading data..."):
        data = _ny_frame(yf.Ticker(ticker).history(period="2d", interval="5m"))
    if data.empty:
        st.warning("No data"); return
    today = _ny_today()
    data_today = data[data.index.date == today]
    ny_data = data_today.between_time('08:00', '09:29')
    if ny_data.empty:
        st.warning("NY Pre-Market data unavailable"); return
    ny_high = ny_data['High'].max(); ny_low = ny_data['Low'].min()
    ny_range = ny_high - ny_low
    afternoon_data = data_today.between_time('08:00', '16:30')
    if afternoon_data.empty:
        st.warning("Afternoon data unavailable"); return
    current_price = afternoon_data['Close'].iloc[-1]
    vwap = (afternoon_data['Close'] * afternoon_data['Volume']).cumsum() / afternoon_data['Volume'].cumsum()
    current_vwap = vwap.iloc[-1]
    st.markdown(f"**Price:** {current_price:.2f} | **NY Range:** {ny_high:.2f}-{ny_low:.2f} | **VWAP:** {current_vwap:.2f}")
    if current_price > ny_high + 15 and current_price > current_vwap:
        st.success(f"✅ LONG — Entry: {current_price:.2f} | SL: {ny_high - 15:.2f} | TP: {current_price + (ny_range * 2):.2f}")
    elif current_price < ny_low - 15 and current_price < current_vwap:
        st.error(f"✅ SHORT — Entry: {current_price:.2f} | SL: {ny_low + 15:.2f} | TP: {current_price - (ny_range * 2):.2f}")
    else:
        st.info("⏳ No breakout signal")

# ---------- Global Session Sniper ----------
def run_level_marker():
    st.subheader("🎯 Global Session Sniper Triggers")
    with st.spinner("Scanning global session data..."):
        mnq_data = _ny_frame(yf.Ticker("MNQ=F").history(period="2d", interval="1m"))
        mgc_data = _ny_frame(yf.Ticker("MGC=F").history(period="2d", interval="1m"))
        sil_data = _ny_frame(yf.Ticker("SIL=F").history(period="2d", interval="1m"))
        mes_data = _ny_frame(yf.Ticker("MES=F").history(period="2d", interval="1m"))
    if mnq_data.empty or mgc_data.empty or sil_data.empty or mes_data.empty:
        st.warning("No session data available"); return
    today = _ny_today()
    macro = get_macro_data()
    tnx_val = macro['yield_10y']
    tab_london, tab_ny = st.tabs(["🇬🇧 London Open Sniper", "🇺🇸 NY Open Sniper"])
    buffer = 15
    with tab_london:
        st.markdown("### 🇬🇧 London Open (2:00 AM EST)")
        cols = st.columns(4)
        for i, (name, data, check_gold) in enumerate([("MNQ", mnq_data, False), ("MGC", mgc_data, True), ("SIL", sil_data, True), ("MES", mes_data, False)]):
            with cols[i]:
                st.markdown(f"#### {name}")
                p_data = data[data.index.date == (today - timedelta(days=1))]
                asia = p_data.between_time('17:00', '23:59')
                if not asia.empty:
                    ah = asia['High'].max(); al = asia['Low'].min(); ar = ah - al
                    if check_gold and tnx_val > 4.3:
                        st.warning("⚠️ 10Y > 4.3% — gold longs risky")
                    st.markdown(f"**LONG:** > {ah + buffer:.2f}")
                    st.markdown(f"**SHORT:** < {al - buffer:.2f}")
                    st.caption(f"Range: {ar:.2f}")
                else:
                    st.info("No Asia data")
    with tab_ny:
        st.markdown("### 🇺🇸 NY Open (9:30 AM EST)")
        cols = st.columns(4)
        for i, (name, data, check_gold) in enumerate([("MNQ", mnq_data, False), ("MGC", mgc_data, True), ("SIL", sil_data, True), ("MES", mes_data, False)]):
            with cols[i]:
                st.markdown(f"#### {name}")
                t_data = data[data.index.date == today]
                ny = t_data.between_time('08:00', '09:29')
                if not ny.empty:
                    nh = ny['High'].max(); nl = ny['Low'].min(); nr = nh - nl
                    if check_gold and tnx_val > 4.3:
                        st.warning("⚠️ 10Y > 4.3% — gold longs risky")
                    st.markdown(f"**LONG:** > {nh + buffer:.2f}")
                    st.markdown(f"**SHORT:** < {nl - buffer:.2f}")
                    st.caption(f"Range: {nr:.2f}")
                else:
                    st.info("NY data unavailable")

# ---------- Smart Money Levels ----------
def run_smart_money_levels():
    st.subheader("🎯 Smart Money Levels")
    macro = get_macro_data()
    tnx = macro['yield_10y']
    if tnx > 4.5: st.warning(f"⚠️ HIGH YIELD ({tnx:.2f}%)")
    elif tnx > 4.3: st.info(f"⚡ ELEVATED ({tnx:.2f}%)")
    else: st.success(f"✅ NORMAL ({tnx:.2f}%)")
    asset_choice = st.selectbox("Select Asset", ["MNQ (Micro Nasdaq)", "MGC (Micro Gold)", "MES (Micro S&P 500)"], key="smc_asset")
    ticker = {"MNQ (Micro Nasdaq)": "MNQ=F", "MGC (Micro Gold)": "MGC=F", "MES (Micro S&P 500)": "MES=F"}[asset_choice]
    with st.spinner("Loading..."):
        data = _ny_frame(yf.Ticker(ticker).history(period="5d", interval="5m"))
    if data.empty:
        st.warning("No data"); return
    today = _ny_today()
    data_today = data[data.index.date == today]
    current_price = data_today['Close'].iloc[-1] if not data_today.empty else data['Close'].iloc[-1]
    yesterday = today - timedelta(days=1)
    data_yesterday = data[data.index.date == yesterday]
    prev_high = data_yesterday['High'].max() if not data_yesterday.empty else 0
    prev_low = data_yesterday['Low'].min() if not data_yesterday.empty else 0
    lookback = min(50, len(data))
    recent_high = data['High'].iloc[-lookback:].max()
    recent_low = data['Low'].iloc[-lookback:].min()
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Current Price", f"{current_price:.2f}")
    with col2: st.metric("Prev Day High", f"{prev_high:.2f}" if prev_high else "N/A")
    with col3: st.metric("Prev Day Low", f"{prev_low:.2f}" if prev_low else "N/A")
    st.markdown("---")
    st.markdown("### 📦 Order Blocks")
    bullish_ob = recent_low - 5 if recent_low else prev_low
    bearish_ob = recent_high + 5 if recent_high else prev_high
    col_ob1, col_ob2 = st.columns(2)
    with col_ob1: st.success(f"🟢 Bullish OB: {bullish_ob:.2f}")
    with col_ob2: st.error(f"🔴 Bearish OB: {bearish_ob:.2f}")
    st.markdown("---")
    st.markdown("### 📊 Premium & Discount Zones")
    range_high = recent_high if recent_high else current_price + 100
    range_low = recent_low if recent_low else current_price - 100
    range_mid = (range_high + range_low) / 2
    premium_zone_bottom = range_mid + (range_high - range_mid) * 0.382
    discount_zone_top = range_mid - (range_mid - range_low) * 0.382
    if current_price > premium_zone_bottom: zone = "🔴 PREMIUM"
    elif current_price < discount_zone_top: zone = "🟢 DISCOUNT"
    else: zone = "⚪ EQUILIBRIUM"
    st.info(f"📍 Current Zone: {zone}")
    st.caption(f"Premium: {premium_zone_bottom:.2f} - {range_high:.2f}")
    st.caption(f"Equilibrium: {range_mid:.2f}")
    st.caption(f"Discount: {range_low:.2f} - {discount_zone_top:.2f}")

# ---------- Journal ----------
DB_JOURNAL_PATH = Path("trading_journal.db")

def init_journal_db():
    conn = sqlite3.connect(DB_JOURNAL_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL, symbol TEXT NOT NULL, direction TEXT NOT NULL,
            entry_price REAL NOT NULL, stop_loss REAL NOT NULL, take_profit REAL NOT NULL,
            exit_price REAL, pnl REAL, outcome TEXT, macro_snapshot TEXT, notes TEXT
        )
    """)
    conn.commit(); conn.close()

def save_trade(symbol, direction, entry, sl, tp, macro_data, notes):
    conn = sqlite3.connect(DB_JOURNAL_PATH)
    macro_json = json.dumps(macro_data)
    conn.execute(
        "INSERT INTO trades (ts_utc, symbol, direction, entry_price, stop_loss, take_profit, macro_snapshot, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(UTC).isoformat(), symbol, direction, entry, sl, tp, macro_json, notes),
    )
    conn.commit(); conn.close()

def get_recent_trades(limit=20):
    conn = sqlite3.connect(DB_JOURNAL_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, ts_utc, symbol, direction, entry_price, stop_loss, take_profit, exit_price, outcome, pnl, macro_snapshot, notes FROM trades ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def run_journal_tab():
    st.subheader("📝 Trading Journal")
    macro = get_macro_data()
    with st.expander("➕ Log New Trade", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            j_symbol = st.selectbox("Symbol", ["MNQ", "MGC", "MES", "NVDA", "SMH"])
            j_direction = st.selectbox("Direction", ["Long", "Short"])
        with c2:
            j_entry = st.number_input("Entry", step=0.25)
            j_stop = st.number_input("Stop", step=0.25)
        with c3:
            j_target = st.number_input("Target", step=0.25)
        j_notes = st.text_area("Notes", height=80)
        if st.button("📌 Log Trade", type="primary"):
            macro_snap = {"dxy": macro['dxy'], "yield_10y": macro['yield_10y'], "vix": macro['vix']}
            save_trade(j_symbol, j_direction, j_entry, j_stop, j_target, macro_snap, j_notes)
            st.success("Logged!"); st.rerun()
    st.markdown("---")
    trades = get_recent_trades(20)
    if trades:
        df = pd.DataFrame(trades)
        df['ts_utc'] = pd.to_datetime(df['ts_utc']).dt.strftime('%Y-%m-%d %H:%M')
        st.dataframe(df[['ts_utc', 'symbol', 'direction', 'entry_price', 'stop_loss', 'take_profit']], width='stretch', hide_index=True)
    else:
        st.info("No trades yet")

# ---------- Treasury dashboard ----------
def run_treasury_dashboard():
    st.subheader("🏛️ Treasury Intervention Tracker")
    macro = get_macro_data()
    status, icon = TreasuryIntervention.get_buyback_status()
    col_status1, col_status2, col_status3 = st.columns(3)
    with col_status1: st.metric("Buyback", f"{icon} {status}")
    with col_status2: st.metric("10Y Cap", f"{TreasuryIntervention.YIELD_CAP_10Y:.2f}%")
    with col_status3: st.metric("30Y Cap", f"{TreasuryIntervention.YIELD_CAP_30Y:.2f}%")
    st.markdown("---")
    tnx = macro.get('yield_10y', 4.20); tyx = macro.get('yield_30y', 4.50)
    col_y1, col_y2, col_y3 = st.columns(3)
    with col_y1: st.metric("10Y Yield", f"{tnx:.2f}%")
    with col_y2: st.metric("30Y Yield", f"{tyx:.2f}%")
    with col_y3:
        spread = tyx - tnx
        st.metric("30Y-10Y", f"{spread:.2f}%")
        if spread < 0: st.error("🔴 Inverted")
        elif spread > 0.5: st.success("🟢 Steep")
        else: st.info("🟡 Normal")

# ---------- VWAP & EMA ----------
def run_vwap_ema_strategy():
    st.subheader("📊 VWAP & 9 EMA Strategy")
    st.markdown("""<div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'><h4 style='color: #4ade80;'>✅ LONG Setup Conditions</h4><ul style='color: #e8ecf1;'><li>Price ABOVE 9 EMA</li><li>Price ABOVE VWAP</li><li>Higher highs structure</li><li>DXY weak, yields low</li></ul></div>""", unsafe_allow_html=True)
    st.markdown("""<div style='background-color: #1c2129; padding: 15px; border-radius: 8px; border-left: 4px solid #facc15; margin-top: 15px;'><h4 style='color: #facc15;'>🎯 Entry</h4><ul style='color: #e8ecf1;'><li>Price pulls back to VWAP</li><li>Bounces off VWAP</li><li>Bullish candle closes above</li></ul></div>""", unsafe_allow_html=True)
    st.info("**Enter:** On bounce | **Stop:** Below VWAP | **Target:** 2x Range")

# ---------- Indices & Bond ----------
def run_indices_bond_tracker():
    st.subheader("📊 Indices & Bond Tracker")
    st.markdown("### 🌪️ VIX Volatility Map")
    col_v1, col_v2, col_v3, col_v4 = st.columns(4)
    with col_v1: st.success("**VIX < 15**\n🟢 ZERO FEAR")
    with col_v2: st.info("**15 < VIX < 20**\n⚖️ NORMAL")
    with col_v3: st.warning("**20 < VIX < 30**\n🟡 HIGH FEAR")
    with col_v4: st.error("**VIX > 30**\n🔴 EXTREME PANIC")
    st.markdown("---")
    st.markdown("### 📉 Yield Curve")
    col_b1, col_b2, col_b3, col_b4 = st.columns(4)
    with col_b1: st.info("**US02Y < 4.0%**\nAccommodative")
    with col_b2: st.warning("**US02Y > 4.5%**\nTightening")
    with col_b3: st.success("**US10Y < 4.0%**\nGrowth Tailwind")
    with col_b4: st.error("**US10Y > 4.5%**\nGrowth Headwind")
    st.markdown("---")
    st.markdown("### 🧠 The 30-Year Yield")
    col_30_1, col_30_2, col_30_3 = st.columns(3)
    with col_30_1: st.success("**US30Y > US10Y**\nNormal Curve")
    with col_30_2: st.warning("**US30Y < US10Y**\nInverted Curve")
    with col_30_3: st.error("**US30Y > 5.0%**\nCrisis Signal")

# ---------- News Cheat Sheet ----------
def render_news_cheat_sheet():
    st.subheader("📰 News Impact Cheat Sheet")
    st.caption("How each US economic event impacts Nasdaq (MNQ) and Gold (MGC)")
    tab1, tab2, tab3, tab4 = st.tabs(["📊 All Events", "💼 Employment", "📈 Inflation", "🏛️ FOMC / Rates"])
    with tab1:
        all_events = [
            {"Event": "NFP > Forecast (Strong)", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Fed hawkish → yields up"},
            {"Event": "NFP < Forecast (Weak)", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Fed cuts → yields down"},
            {"Event": "CPI > Forecast (Hot)", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Inflation → yields up"},
            {"Event": "CPI < Forecast (Cooling)", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Inflation cooling"},
            {"Event": "Core PCE > 2.0% (Hot)", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Fed target not met"},
            {"Event": "Core PCE < 2.0% (Cooling)", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Fed target met"},
            {"Event": "Rate HIKE", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Higher rates → tech down"},
            {"Event": "Rate CUT", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Lower rates → tech up"},
            {"Event": "Powell Hawkish", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Persistent inflation"},
            {"Event": "Powell Dovish", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Progress on inflation"},
            {"Event": "Jobless Claims RISING", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Labor weakness"},
            {"Event": "Jobless Claims FALLING", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Labor strength"},
            {"Event": "GDP > Forecast (Strong)", "Gold": "⬇️ DOWN", "NQ": "⚠️ MIXED", "Why": "Yields up BUT earnings strong"},
            {"Event": "GDP < Forecast (Weak)", "Gold": "⬆️ UP", "NQ": "⚠️ MIXED", "Why": "Yields down BUT earnings weak"},
            {"Event": "ISM > 50 (Expansion)", "Gold": "⬇️ DOWN", "NQ": "⬆️ UP", "Why": "Expansion → earnings up"},
            {"Event": "ISM < 50 (Contraction)", "Gold": "⬆️ UP", "NQ": "⬇️ DOWN", "Why": "Contraction → earnings down"},
            {"Event": "Retail Sales > Forecast", "Gold": "⬇️ DOWN", "NQ": "⚠️ MIXED", "Why": "Strong consumer"},
            {"Event": "Retail Sales < Forecast", "Gold": "⬆️ UP", "NQ": "⚠️ MIXED", "Why": "Weak consumer"},
        ]
        st.dataframe(pd.DataFrame(all_events), use_container_width=True, hide_index=True, height=600)
    with tab2:
        emp = [
            {"Event": "NFP Strong", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Fed hawkish"},
            {"Event": "NFP Weak", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Fed cuts coming"},
            {"Event": "AHE > Forecast", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Wage inflation"},
            {"Event": "AHE < Forecast", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Wage cooling"},
        ]
        st.dataframe(pd.DataFrame(emp), use_container_width=True, hide_index=True)
        st.markdown("**NFP:** > 200K Strong | 150-200K Goldilocks | < 100K Weak")
    with tab3:
        inf = [
            {"Event": "CPI Hot", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Inflation → yields up"},
            {"Event": "CPI Cooling", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Inflation cooling"},
            {"Event": "Core PCE > 2.0%", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Target not met"},
            {"Event": "Core PCE < 2.0%", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Target met"},
        ]
        st.dataframe(pd.DataFrame(inf), use_container_width=True, hide_index=True)
        st.markdown("**CPI:** m/m > 0.4% Hot | 0.2-0.4% Normal | < 0.2% Cool")
    with tab4:
        fomc = [
            {"Event": "Rate HIKE", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "Higher rates"},
            {"Event": "Rate HOLD (Hawkish)", "Gold": "⬇️ DOWN", "NQ": "⬇️ DOWN", "Why": "More hikes"},
            {"Event": "Rate HOLD (Dovish)", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Cuts coming"},
            {"Event": "Rate CUT", "Gold": "⬆️ UP", "NQ": "⬆️ UP", "Why": "Lower rates"},
        ]
        st.dataframe(pd.DataFrame(fomc), use_container_width=True, hide_index=True)

# ---------- App ----------
def run_app():
    load_dotenv()
    init_db()
    init_journal_db()
    st.set_page_config(page_title="TradeTerminal Pro", layout="wide", initial_sidebar_state="expanded")
    st.markdown("""
    <style>
    .stApp { background-color: #0f1116; color: #e8ecf1; }
    .eco-card { background: #1c2129; padding: 15px; border-radius: 10px; border-left: 4px solid #4c6fff; }
    .sidebar-logo { text-align: center; padding: 20px 0 30px 0; border-bottom: 1px solid #2a2a2a; margin-bottom: 20px; }
    .sidebar-logo h1 { color: #4c6fff; font-size: 24px; margin: 0; font-weight: 700; }
    .sidebar-logo p { color: #a0aec0; font-size: 12px; margin: 5px 0 0 0; }
    .sidebar-divider { border-top: 1px solid #2a2a2a; margin: 15px 0; }
    .stMetric { background-color: #1c2129; padding: 10px; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("""<div class="sidebar-logo"><h1>⚡ TradeTerminal</h1><p>Pro Market Terminal</p></div>""", unsafe_allow_html=True)
        nav_section = st.radio(
            "Navigation",
            [
                "🏠 Dashboard",
                "🎯 Strategy Selector",
                "⚡ High Yield Protocol",
                "⚡ High Yield Protocol - MES",
                "📈 Trend-Fade Hybrid",
                "📈 Trend-Fade Hybrid - MES",
                "🥇 MGC Macro Watch",
                "🇺🇸 NY Afternoon",
                "🎯 Market Levels",
                "🎯 Smart Money Levels",
                "📝 Journal",
                "🏛️ Treasury Tracker",
                "📈 VWAP & 9 EMA",
                "📰 News Cheat Sheet",
                "📊 Indices & Bond Tracker",
            ],
            index=0,
            key="sidebar_navigation",
            label_visibility="collapsed",
        )
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()
        auto_save = st.checkbox("💾 Auto-Save", value=True)
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        st.markdown("### 📊 Market Status")
        try:
            macro = get_macro_data()
            tnx = macro.get('yield_10y', 4.20)
            vix = macro.get('vix', 18.0)
            dxy = macro.get('dxy', 102.0)
            st.markdown(f"**10Y Yield:** {tnx:.2f}%")
            st.markdown(f"**VIX:** {vix:.2f}")
            st.markdown(f"**DXY:** {dxy:.2f}")
        except Exception:
            pass
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        st.caption("⚡ TradeTerminal Pro v2.1")

    st.title("⚡ TradeTerminal Pro - Market Terminal")

    if nav_section == "🏠 Dashboard":
        try:
            mt = get_macro_data()
            od = get_options_sentiment("SPY")
            fg = calc_fear_greed(mt['vix'], od['ratio'], mt['dxy'])
            ev = get_economic_calendar()
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(f"<div class='eco-card'><h4>🧠 Fear & Greed</h4><h2>{fg['label']}</h2><small>Score: {fg['score']}/100</small></div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<div class='eco-card'><h4>📊 PCR (SPY)</h4><h3>{od['ratio']}</h3></div>", unsafe_allow_html=True)
            with c3:
                txt = ""
                for e in ev:
                    txt += f"**{e['name']}** — {e['countdown']}\n\n"
                st.markdown(f"<div class='eco-card'><h4>🕒 Events</h4>{txt}</div>", unsafe_allow_html=True)
            with c4:
                st.markdown(
                    f"<div class='eco-card'><h4>Bond Yields</h4>"
                    f"<b>10Y:</b> {mt['yield_10y']:.2f}%<br>"
                    f"<b>30Y:</b> {mt['yield_30y']:.2f}%<br>"
                    f"<b>Buyback:</b> {mt['buyback_icon']} {mt['buyback_status']}</div>",
                    unsafe_allow_html=True,
                )
        except Exception:
            pass
    elif nav_section == "🎯 Strategy Selector": run_strategy_selector()
    elif nav_section == "⚡ High Yield Protocol": run_high_yield_protocol()
    elif nav_section == "⚡ High Yield Protocol - MES": run_high_yield_protocol_mes()
    elif nav_section == "📈 Trend-Fade Hybrid": run_trend_fade_hybrid()
    elif nav_section == "📈 Trend-Fade Hybrid - MES": run_trend_fade_hybrid_mes()
    elif nav_section == "🥇 MGC Macro Watch": run_mgc_macro_watch()
    elif nav_section == "🇺🇸 NY Afternoon": run_ny_afternoon_sniper()
    elif nav_section == "🎯 Market Levels": run_level_marker()
    elif nav_section == "🎯 Smart Money Levels": run_smart_money_levels()
    elif nav_section == "📝 Journal": run_journal_tab()
    elif nav_section == "🏛️ Treasury Tracker": run_treasury_dashboard()
    elif nav_section == "📈 VWAP & 9 EMA": run_vwap_ema_strategy()
    elif nav_section == "📰 News Cheat Sheet": render_news_cheat_sheet()
    elif nav_section == "📊 Indices & Bond Tracker": run_indices_bond_tracker()

if __name__ == "__main__":
    run_app()