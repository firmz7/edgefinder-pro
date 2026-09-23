# ============ PART 1 of 2 ============
from __future__ import annotations
import time
import os, json, sqlite3, math, re, feedparser, requests, yfinance as yf
from datetime import datetime, timezone, timedelta
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

ASSETS = {
    "MGC": {"symbol":"MGC","name":"Micro Gold","ticker":"MGC=F","tv_ticker":"CME_MINI:MGC1!","news_queries":["gold","MGC","micro gold"],"inverse_dxy":True,"safe_haven":True,"type":"Futures","favors":"Low Yields, High VIX"},
    "MNQ": {"symbol":"MNQ","name":"Micro Nasdaq","ticker":"MNQ=F","tv_ticker":"CME_MINI:MNQ1!","news_queries":["Nasdaq","MNQ","micro nasdaq"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates, Tech Surge"},
    "MES": {"symbol":"MES","name":"Micro S&P 500","ticker":"MES=F","tv_ticker":"CME_MINI:MES1!","news_queries":["S&P 500","MES","micro sp"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates, Low VIX"},
    "M2K": {"symbol":"M2K","name":"Micro Russell 2000","ticker":"M2K=F","tv_ticker":"CME_MINI:M2K1!","news_queries":["Russell","M2K","micro russell"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates"},
    "BTC": {"symbol":"BTC","name":"Micro Bitcoin","ticker":"BTC=F","tv_ticker":"CME_MINI:BTC1!","news_queries":["Bitcoin","BTC","crypto"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Risk-On, Liquidity"},
    "MCL": {"symbol":"MCL","name":"Micro Crude Oil","ticker":"MCL=F","tv_ticker":"CME_MINI:MCL1!","news_queries":["crude","oil","MCL"],"inverse_dxy":False,"safe_haven":False,"type":"Futures","favors":"Inflation, Supply"},
    "MNK": {"symbol":"MNK","name":"Micro Nikkei 225","ticker":"MNK=F","tv_ticker":"CME_MINI:MNK1!","news_queries":["Nikkei","MNK","micro nikkei"],"inverse_dxy":False,"safe_haven":False,"type":"Futures","favors":"Asian Markets, Tech"},
    "US30": {"symbol":"US30","name":"Micro Dow","ticker":"YM=F","tv_ticker":"CBOT_MINI:YM1!","news_queries":["Dow","US30","micro dow"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates, Industrial"},
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

RSS_FEEDS=["https://feeds.reuters.com/reuters/businessNews","https://feeds.reuters.com/news/wealth","https://finance.yahoo.com/news/rssindex","https://www.marketwatch.com/rss/topstories"]
POSITIVE_TERMS={"surge","beats","beat","rally","gain","gains","jump","bullish","strong","cooling inflation","rate cut","soft landing","upgrade","record high","rebound","outperform"}
NEGATIVE_TERMS={"drop","falls","fall","misses","miss","selloff","bearish","weak","hot inflation","rate hike","downgrade","recession","warning","tariffs","war","outflows"}

ASSET_VOLATILITY_PROFILES = {
    "MNQ=F":  {"trending_min": 40,  "ranging_max": 25,  "name": "MNQ (Nasdaq)",   "typical_range": "40-80"},
    "M2K=F":  {"trending_min": 20,  "ranging_max": 12,  "name": "M2K (Russell)",  "typical_range": "15-30"},
    "YM=F":   {"trending_min": 200, "ranging_max": 120, "name": "US30 (Dow)",     "typical_range": "150-350"},
    "MES=F":  {"trending_min": 30,  "ranging_max": 18,  "name": "MES (S&P 500)",  "typical_range": "20-40"},
    "MGC=F":  {"trending_min": 15,  "ranging_max": 8,   "name": "MGC (Gold)",     "typical_range": "8-20"},
}

STOP_BUFFERS = {"MNQ": 5, "M2K": 3, "US30": 20, "MGC": 2, "MES": 5}
MIN_NY_RANGE = {"MNQ": 10, "M2K": 5, "US30": 40, "MGC": 4, "MES": 8}
TICK_VALUES = {"MNQ": 2.0, "M2K": 5.0, "US30": 0.5, "MGC": 10.0, "MES": 5.0}

SESSIONS = {
    "LONDON":    {"start": "07:30", "end": "08:30", "size": 0.75, "rating": 4, "name": "🌅 London"},
    "NY_OPEN":   {"start": "14:45", "end": "16:00", "size": 1.00, "rating": 5, "name": "🌆 NY Open"},
    "AFTERNOON": {"start": "19:00", "end": "20:00", "size": 0.50, "rating": 3, "name": "🌃 Afternoon"},
}
BLACKOUTS = [
    ("14:30", "14:45", "NY open chaos"),
    ("16:00", "19:00", "Mid-day lull"),
    ("20:00", "23:59", "Overnight"),
    ("00:00", "07:30", "Overnight"),
]

def parse_time_hm(tstr):
    h, m = tstr.split(":"); return int(h) * 60 + int(m)

def get_current_session(now_uk):
    now_min = now_uk.hour * 60 + now_uk.minute
    for key, sess in SESSIONS.items():
        s = parse_time_hm(sess["start"]); e = parse_time_hm(sess["end"])
        if s <= now_min <= e:
            remaining = (e - now_min) * 60 - now_uk.second
            next_key, next_delta = _next_session_after(now_min)
            return key, sess, remaining, next_key, next_delta
    next_key, next_delta = _next_session_after(now_min)
    return None, None, 0, next_key, next_delta

def _next_session_after(now_min):
    best_key, best_delta = None, 999999
    for key, sess in SESSIONS.items():
        s = parse_time_hm(sess["start"])
        delta = s - now_min
        if delta < 0: delta += 24 * 60
        if delta < best_delta:
            best_delta = delta; best_key = key
    return best_key, best_delta * 60

def is_blackout(now_uk):
    now_min = now_uk.hour * 60 + now_uk.minute
    for start, end, reason in BLACKOUTS:
        s = parse_time_hm(start); e = parse_time_hm(end)
        if s <= e:
            if s <= now_min <= e: return True, reason
        else:
            if now_min >= s or now_min <= e: return True, reason
    return False, None

def fmt_countdown(secs):
    if secs < 0: secs = 0
    h = secs // 3600; m = (secs % 3600) // 60
    if h > 0: return f"{h}h {m}m"
    return f"{m}m"

def get_yield_regime(tnx):
    if tnx < 3.5:
        return ("EASY", "🟢 EASY MONEY", 1.00, 1.0, ["MNQ", "MES", "M2K", "US30", "MGC"], "Full size allowed")
    if tnx < 4.0:
        return ("NEUTRAL", "🟢 NEUTRAL", 1.00, 1.0, ["MNQ", "MES", "M2K", "US30", "MGC"], "Normal size")
    if tnx < 4.5:
        return ("TIGHT", "🟡 TIGHT MONEY", 0.75, 0.85, ["US30", "MES", "MNQ", "MGC", "M2K"], "Reduced size (75%)")
    if tnx < 5.0:
        return ("VERY_TIGHT", "🔴 VERY TIGHT", 0.50, 0.70, ["US30", "MES", "MGC"], "50% size — prefer US30/MES")
    return ("CRISIS", "🚨 CRISIS", 0.25, 0.50, ["US30", "MGC"], "25% size — best setups only")

def safe_stop(entry: float, direction: str, anchor_level: float, asset: str) -> float:
    buf = STOP_BUFFERS.get(asset, 5)
    if direction == "SHORT": return max(anchor_level + buf, entry + buf)
    if direction == "LONG":  return min(anchor_level - buf, entry - buf)
    return entry + buf if direction in ("SHORT", "short") else entry - buf

def clamp_rr(rr: float, max_rr: float = 10.0) -> float:
    if rr <= 0 or not math.isfinite(rr): return 0.0
    return min(rr, max_rr)

def calc_atr(df, period=14):
    if len(df) < period + 1: return 0.0
    high = df['High']; low = df['Low']; close = df['Close']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

def calc_adx(df, period=14):
    if len(df) < period * 2: return 0.0, 0.0, 0.0
    high = df['High']; low = df['Low']; close = df['Close']
    tr1 = high - low; tr2 = abs(high - close.shift(1)); tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    up_move = high - high.shift(1); down_move = low.shift(1) - low
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=df.index)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, np.nan))
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(period).mean()
    pdi = plus_di.iloc[-1] if not plus_di.empty else 0
    mdi = minus_di.iloc[-1] if not minus_di.empty else 0
    a = adx.iloc[-1] if not adx.empty else 0
    if pd.isna(a): a = 0.0
    if pd.isna(pdi): pdi = 0.0
    if pd.isna(mdi): mdi = 0.0
    return float(a), float(pdi), float(mdi)

class TreasuryIntervention:
    YIELD_CAP_10Y = 4.75
    YIELD_CAP_30Y = 5.25
    BUYBACK_START = datetime(2026, 9, 9)
    BUYBACK_END = datetime(2026, 11, 4)
    @staticmethod
    def get_buyback_status():
        now = datetime.now()
        if TreasuryIntervention.BUYBACK_START <= now <= TreasuryIntervention.BUYBACK_END: return "ACTIVE", "🟢"
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
        self.bullish_bos = False; self.bearish_bos = False
        self.bullish_choch = False; self.bearish_choch = False
        self.strong_high = 0.0; self.weak_high = 0.0
        self.strong_low = 0.0; self.weak_low = 0.0
        self.bullish_ob = []; self.bearish_ob = []
        self.bullish_fvg = []; self.bearish_fvg = []
        self.structure_bias = "NEUTRAL"

def get_economic_calendar()->List[Dict]:
    api_key = os.getenv("FOREXFACTORY_API_KEY")
    if not api_key: return get_economic_calendar_fallback()
    try:
        url = "https://www.jblanked.com/news/api/list/"
        headers = {"Content-Type": "application/json", "Authorization": f"Api-Key {api_key}"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json(); now = datetime.now(timezone.utc); upcoming = []
            for item in data:
                try:
                    event_date = datetime.fromisoformat(item.get("date", "").replace("Z", "+00:00"))
                    if event_date > now:
                        d = event_date - now; days = d.days
                        h, r = divmod(d.seconds, 3600); m, _ = divmod(r, 60)
                        c = f"{days}d {h}h {m}m" if days > 0 else f"{h}h {m}m"
                        upcoming.append({"name": f"🇺🇸 {item.get('title', '').replace('**', '')}", "countdown": c})
                except Exception: continue
            return upcoming[:3]
        return get_economic_calendar_fallback()
    except Exception: return get_economic_calendar_fallback()

def get_economic_calendar_fallback()->List[Dict]:
    now = datetime.now(timezone.utc)
    events = [
        {"name": "🇺🇸 FOMC Rate Decision", "date": datetime(2026, 7, 29, 18, 0, tzinfo=timezone.utc)},
        {"name": "🇺🇸 CPI Data (MoM)", "date": datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)},
        {"name": "🇺🇸 NFP (Non-Farm Payrolls)", "date": datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)}
    ]
    upcoming = []
    for e in events:
        if e["date"] > now:
            d = e["date"] - now; days = d.days
            h, r = divmod(d.seconds, 3600); m, _ = divmod(r, 60)
            c = f"{days}d {h}h {m}m" if days > 0 else f"{h}h {m}m"
            upcoming.append({"name": e["name"], "countdown": c})
    return upcoming[:3]

def get_options_sentiment(ticker="SPY")->Dict:
 try:
  t=yf.Ticker(ticker); exps=t.options
  if not exps: return {"ratio":0.5,"sentiment":"Neutral","calls":0,"puts":0}
  oc=t.option_chain(exps[0]); c=oc.calls['volume'].sum(); p=oc.puts['volume'].sum()
  if c+p==0: return {"ratio":0.5,"sentiment":"Neutral","calls":0,"puts":0}
  pcr=p/c; s="🐻 Bearish" if pcr>0.8 else "⚖️ Neutral-Bearish" if pcr>0.6 else "⚖️ Neutral-Bullish" if pcr>0.4 else "🐂 Bullish"
  return {"ratio":round(pcr,2),"sentiment":s,"puts":int(p),"calls":int(c)}
 except: return {"ratio":0.5,"sentiment":"Neutral","calls":0,"puts":0}

def calc_fear_greed(vix,pcr,dxy)->Dict:
 vs=10 if vix>30 else 30 if vix>20 else 60 if vix>14 else 85; ps=20 if pcr>0.8 else 40 if pcr>0.65 else 60 if pcr>0.5 else 80; ds=20 if dxy>106 else 40 if dxy>103 else 60 if dxy>100 else 80
 o=int((vs*0.4)+(ps*0.4)+(ds*0.2)); l="🔴 Extreme Fear" if o<20 else "😨 Fear" if o<40 else "😐 Neutral" if o<60 else "😀 Greed" if o<80 else "🟢 Extreme Greed"
 return {"score":o,"label":l}

def get_intraday_data(ticker)->Dict:
    try:
        h5 = yf.Ticker(ticker).history(period="1d", interval="5m")
        if h5.empty: return {"error": "No intraday data available"}
        h1 = yf.Ticker(ticker).history(period="1d", interval="1m")
        h1['EMA_9'] = h1['Close'].ewm(span=9, adjust=False).mean()
        h1['EMA_20'] = h1['Close'].ewm(span=20, adjust=False).mean()
        h1['EMA_50'] = h1['Close'].ewm(span=50, adjust=False).mean()
        h1['VWAP'] = (h1['Close'] * h1['Volume']).cumsum() / h1['Volume'].cumsum()
        return {"current_price": h1['Close'].iloc[-1], "hist_1m": h1, "hist_5m": h5, "vwap": h1['VWAP'].iloc[-1], "ema9": h1['EMA_9'].iloc[-1], "ema20": h1['EMA_20'].iloc[-1], "ema50": h1['EMA_50'].iloc[-1]}
    except Exception as e: return {"error": str(e)}

def get_macro_data()->Dict:
    try:
        dxy_data = yf.Ticker("DX-Y.NYB").history(period="1d", interval="1m")
        dxy = dxy_data['Close'].iloc[-1] if not dxy_data.empty else 102.0
    except: dxy = 102.0
    try:
        vix_data = yf.Ticker("^VIX").history(period="1d", interval="1m")
        vix = vix_data['Close'].iloc[-1] if not vix_data.empty else 18.0
    except: vix = 18.0
    ry = float(os.getenv("EDGEFINDER_REAL_YIELD_FALLBACK", "1.8"))
    try:
        tnx_data = yf.Ticker("^TNX").history(period="1d", interval="1m")
        tnx = tnx_data['Close'].iloc[-1] if not tnx_data.empty else 4.20
    except: tnx = 4.20
    try:
        tyx_data = yf.Ticker("^TYX").history(period="1d", interval="1m")
        tyx = tyx_data['Close'].iloc[-1] if not tyx_data.empty else 4.50
    except: tyx = 4.50
    try:
        tnx_prev = yf.Ticker("^TNX").history(period="2d", interval="1d")
        tnx_change = (tnx_prev['Close'].iloc[-1] - tnx_prev['Close'].iloc[-2]) if len(tnx_prev) >= 2 else 0
    except: tnx_change = 0
    buyback_status, buyback_icon = TreasuryIntervention.get_buyback_status()
    stress_10y, stress_30y = TreasuryIntervention.calculate_yield_stress(tnx, tyx)
    return {"dxy": dxy, "vix": vix, "real_yield_10y": ry, "yield_10y": tnx, "yield_30y": tyx,
            "yield_10y_change": tnx_change, "buyback_status": buyback_status, "buyback_icon": buyback_icon,
            "yield_stress_10y": stress_10y, "yield_stress_30y": stress_30y}

def _clean(t): return re.sub(r"\s+"," ",t.strip().lower())
def _headline_score(t):
 t=_clean(t); s=0.0
 for term in POSITIVE_TERMS: s+=1.0 if term in t else 0
 for term in NEGATIVE_TERMS: s-=1.0 if term in t else 0
 return max(-1.0,min(1.0,s/3.0))

def get_news_data(asset_name,queries)->Dict:
 matches=[]; lq=[_clean(q) for q in queries]
 for url in RSS_FEEDS:
  try:
   feed=feedparser.parse(url)
   for entry in feed.entries[:15]:
    hay=_clean(entry.title)+" "+_clean(entry.summary)
    if any(q in hay for q in lq): matches.append(_headline_score(entry.title))
  except: continue
 sentiment=sum(matches)/len(matches) if matches else 0.0
 return {"asset":asset_name,"sentiment":sentiment,"headlines":len(matches)}

class Bias(str, Enum): VERY_BEARISH="Very Bearish"; BEARISH="Bearish"; NEUTRAL="Neutral"; BULLISH="Bullish"; VERY_BULLISH="Very Bullish"
def score_to_bias(score:int)->Bias:
 if score<=2: return Bias.VERY_BEARISH
 if score<=4: return Bias.BEARISH
 if score==5: return Bias.NEUTRAL
 if score<=7: return Bias.BULLISH
 return Bias.VERY_BULLISH

@dataclass
class IndicatorReading: name:str; value:float; score:int; bias:Bias; note:str=""
@dataclass
class AssetSnapshot: symbol:str; name:str; price:float; technical_score:int; macro_score:int; news_score:int; overall_score:int; overall_bias:Bias; technical_details:List[IndicatorReading]=field(default_factory=list); macro_details:List[IndicatorReading]=field(default_factory=list); news_details:List[IndicatorReading]=field(default_factory=list)

def calc_rsi(closes)->float:
 if len(closes)<15: return 50.0
 g=[max(closes[i]-closes[i-1],0) for i in range(1,15)]; l=[abs(min(closes[i]-closes[i-1],0)) for i in range(1,15)]
 ag=sum(g)/14; al=sum(l)/14
 if al==0: return 100.0
 return 100-(100/(1+ag/al))

def sma(values,p)->float:
 if len(values)<p: return sum(values)/len(values)
 return sum(values[-p:])/p

def score_rsi(rsi)->int: return 3 if rsi<30 else 4 if rsi<40 else 5 if rsi<50 else 6 if rsi<60 else 7 if rsi<70 else 6
def score_trend_pct(tp)->int: return 9 if tp>8 else 8 if tp>4 else 7 if tp>1 else 5 if tp>-1 else 4 if tp>-4 else 3 if tp>-8 else 2
def score_dxy(value,inverse)->int: b=3 if value>108 else 4 if value>104 else 5 if value>100 else 6 if value>96 else 7; return 10-b if inverse else b
def score_vix(value,safe_haven)->int: return 8 if value>30 else 6 if value>20 else 5 if safe_haven else (5 if value<14 else 7 if value<20 else 4 if value<30 else 2)
def score_real_yield(value,inverse)->int: b=7 if value<0 else 6 if value<1 else 4 if value<2 else 2; return b if inverse else 10-b
def score_news(sentiment)->int: return max(0,min(10,int(round(5+sentiment*5))))

DB_PATH=Path("edgefinder.db")
def get_conn()->sqlite3.Connection: conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row; return conn
def init_db()->None:
 conn=get_conn(); conn.execute("CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT NOT NULL, symbol TEXT NOT NULL, name TEXT NOT NULL, price REAL NOT NULL, technical_score INTEGER NOT NULL, macro_score INTEGER NOT NULL, news_score INTEGER NOT NULL, overall_score INTEGER NOT NULL, overall_bias TEXT NOT NULL, payload_json TEXT NOT NULL)"); conn.commit(); conn.close()
def save_snapshot(snapshot)->None:
 conn=get_conn(); conn.execute("INSERT INTO snapshots (ts_utc, symbol, name, price, technical_score, macro_score, news_score, overall_score, overall_bias, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (datetime.now(timezone.utc).isoformat(), snapshot.symbol, snapshot.name, snapshot.price, snapshot.technical_score, snapshot.macro_score, snapshot.news_score, snapshot.overall_score, snapshot.overall_bias.value, json.dumps({"symbol":snapshot.symbol,"name":snapshot.name}))); conn.commit(); conn.close()

def build_swing_snapshot(config,macro,news)->AssetSnapshot:
    ticker=config["ticker"]
    try:
        daily = yf.Ticker(ticker).history(period="6mo")
        if daily.empty: daily = yf.Ticker(ticker).history(period="1mo")
        if daily.empty:
            td = [IndicatorReading("RSI 14", 50.0, 5, score_to_bias(5))]
            p = 100.0
        else:
            closes = daily['Close'].tolist(); p = closes[-1]; r = calc_rsi(closes)
            m50 = sma(closes, 50); tp = ((p - m50) / m50) * 100 if m50 else 0
            td = [IndicatorReading("RSI 14", r, score_rsi(r), score_to_bias(score_rsi(r))), IndicatorReading("Trend vs 50D MA %", tp, score_trend_pct(tp), score_to_bias(score_trend_pct(tp)))]
    except Exception:
        td = [IndicatorReading("RSI 14", 50.0, 5, score_to_bias(5))]
        p = 100.0
    inv=config.get("inverse_dxy",False); safe=config.get("safe_haven",False)
    md=[IndicatorReading("DXY",macro["dxy"],score_dxy(macro["dxy"],inv),score_to_bias(score_dxy(macro["dxy"],inv))),IndicatorReading("VIX",macro["vix"],score_vix(macro["vix"],safe),score_to_bias(score_vix(macro["vix"],safe))),IndicatorReading("Real Yield",macro["real_yield_10y"],score_real_yield(macro["real_yield_10y"],inv),score_to_bias(score_real_yield(macro["real_yield_10y"],inv)))]
    ms=sum([x.score for x in md])//3; ns=score_news(news.get("sentiment",0.0)); o=int(round((td[0].score if td else 5)*0.45+ms*0.30+ns*0.25))
    return AssetSnapshot(symbol=config["symbol"],name=config["name"],price=p,technical_score=td[0].score if td else 5,macro_score=ms,news_score=ns,overall_score=o,overall_bias=score_to_bias(o),technical_details=td,macro_details=md,news_details=[IndicatorReading("News Sentiment",news.get("sentiment",0),ns,score_to_bias(ns))])

def get_monthly_regime_report(asset_key):
    conn = get_conn(); symbol = ASSETS[asset_key]["symbol"]
    rows = conn.execute("SELECT ts_utc, overall_score, overall_bias FROM snapshots WHERE symbol = ? ORDER BY ts_utc DESC", (symbol,)).fetchall()
    conn.close()
    if rows:
        df = pd.DataFrame([dict(r) for r in rows]); df['ts_utc'] = pd.to_datetime(df['ts_utc']); df['month'] = df['ts_utc'].dt.to_period('M')
        monthly = df.groupby('month').agg({'overall_score':'mean','overall_bias':lambda x: x.mode()[0] if not x.empty else "Neutral"}).reset_index()
        monthly = monthly.sort_values('month', ascending=False).head(12); monthly['month_str'] = monthly['month'].astype(str)
        return monthly
    return None

def classify_market_conditions(ticker="MNQ=F"):
    try:
        profile = ASSET_VOLATILITY_PROFILES.get(ticker, ASSET_VOLATILITY_PROFILES["MNQ=F"])
        trending_min = profile["trending_min"]; ranging_max = profile["ranging_max"]
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
        if data.empty: return {"classification": "UNKNOWN", "reason": "No data"}
        today_utc = datetime.now(timezone.utc).date()
        data_today = data[data.index.date == today_utc]
        if data_today.empty: data_today = data.tail(100)
        adx, plus_di, minus_di = calc_adx(data_today)
        vwap = (data_today['Close'] * data_today['Volume']).cumsum() / data_today['Volume'].cumsum()
        vwap_slope = (vwap.iloc[-1] - vwap.iloc[-5]) / vwap.iloc[-5] * 100 if len(vwap) >= 5 else 0
        ema9 = data_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        ema20 = data_today['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = data_today['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        current_price = data_today['Close'].iloc[-1]
        ema_separation = abs(ema9 - ema20) / current_price * 100
        ny_data = data_today.between_time('08:00', '09:29')
        if ny_data.empty or len(ny_data) < 5: ny_data = data_today.between_time('07:30', '09:29')
        ny_range = (ny_data['High'].max() - ny_data['Low'].min()) if not ny_data.empty else 0
        if current_price > ema9 > ema20 > ema50: trend_direction = "UP"
        elif current_price < ema9 < ema20 < ema50: trend_direction = "DOWN"
        else: trend_direction = "MIXED"
        trending_signals = 0; ranging_signals = 0
        if adx > 25: trending_signals += 1
        elif adx < 20: ranging_signals += 1
        if abs(vwap_slope) > 0.1: trending_signals += 1
        elif abs(vwap_slope) < 0.05: ranging_signals += 1
        if ema_separation > 0.15: trending_signals += 1
        elif ema_separation < 0.05: ranging_signals += 1
        if ny_range > trending_min: trending_signals += 1
        elif ny_range < ranging_max: ranging_signals += 1
        if trending_signals >= 3: classification = "TRENDING"
        elif ranging_signals >= 3: classification = "RANGING"
        else: classification = "UNCLEAR"
        return {"classification": classification, "asset_name": profile["name"], "typical_range": profile["typical_range"], "adx": round(adx, 1), "plus_di": round(plus_di, 1), "minus_di": round(minus_di, 1), "vwap_slope": round(vwap_slope, 3), "ema_separation": round(ema_separation, 3), "ny_range": round(ny_range, 1), "trend_direction": trend_direction, "current_price": current_price, "ema9": ema9, "ema20": ema20, "ema50": ema50, "ema200": data_today['Close'].ewm(span=200, adjust=False).mean().iloc[-1], "vwap": vwap.iloc[-1], "trending_signals": trending_signals, "ranging_signals": ranging_signals}
    except Exception as e:
        return {"classification": "UNKNOWN", "reason": str(e)}

def detect_breakout(df, direction="UP", lookback=20):
    if len(df) < lookback + 2: return False, 0.0, 0.0
    if direction == "UP":
        prior_swing = df['High'].iloc[-lookback:-1].max()
        current_close = df['Close'].iloc[-1]
        return current_close > prior_swing, prior_swing, current_close
    else:
        prior_swing = df['Low'].iloc[-lookback:-1].min()
        current_close = df['Close'].iloc[-1]
        return current_close < prior_swing, prior_swing, current_close

def get_last_swing_levels(df, lookback=30):
    if len(df) < lookback: return df['High'].max(), df['Low'].min()
    highs = df['High'].values; lows = df['Low'].values
    swing_highs = []; swing_lows = []
    for i in range(3, len(df) - 3):
        if highs[i] > max(highs[max(0,i-3):i]) and highs[i] > max(highs[i+1:min(len(highs),i+4)]): swing_highs.append(highs[i])
        if lows[i] < min(lows[max(0,i-3):i]) and lows[i] < min(lows[i+1:min(len(lows),i+4)]): swing_lows.append(lows[i])
    last_high = swing_highs[-1] if swing_highs else df['High'].max()
    last_low = swing_lows[-1] if swing_lows else df['Low'].min()
    return last_high, last_low

# ============ PART 2 of 2 ============

# ============ 🚀 PURE TREND RIDER ============
def run_pure_trend_rider():
    st.subheader("🚀 Pure Trend Rider")
    st.caption("Ride the trend with trailing stops. Breakout entries with all filters.")
    asset_choice = st.selectbox("Select Asset", ["MNQ (Micro Nasdaq)", "M2K (Micro Russell 2000)", "US30 (Micro Dow)", "MES (Micro S&P 500)", "MGC (Micro Gold)"], index=2, key="ptr_asset_select")
    asset_map = {"MNQ (Micro Nasdaq)": ("MNQ=F", "MNQ"), "M2K (Micro Russell 2000)": ("M2K=F", "M2K"), "US30 (Micro Dow)": ("YM=F", "US30"), "MES (Micro S&P 500)": ("MES=F", "MES"), "MGC (Micro Gold)": ("MGC=F", "MGC")}
    ticker, asset_key = asset_map[asset_choice]
    asset_name = asset_choice.split(" (")[0]
    now_utc = datetime.now(timezone.utc); uk_time = now_utc.astimezone(ZoneInfo("Europe/London"))
    session_key, session_info, session_remaining, next_key, until_next = get_current_session(uk_time)
    blackout, blackout_reason = is_blackout(uk_time)
    macro = get_macro_data()
    tnx = macro['yield_10y']; vix = macro['vix']; dxy = macro['dxy']
    regime_key, regime_label, regime_size, regime_trail, regime_assets, regime_note = get_yield_regime(tnx)
    if session_key:
        st.markdown(f"""<div style='background-color: #1a3a2a; padding: 20px; border-radius: 10px; border: 2px solid #4ade80; margin-bottom: 20px;'><h2 style='color: #4ade80; margin: 0;'>🟢 {session_info["name"]} WINDOW ACTIVE</h2><p style='color: #e8ecf1;'>Time remaining: <b>{fmt_countdown(session_remaining)}</b></p></div>""", unsafe_allow_html=True)
    elif blackout:
        st.markdown(f"""<div style='background-color: #3a1a1a; padding: 20px; border-radius: 10px; border: 2px solid #f87171; margin-bottom: 20px;'><h2 style='color: #f87171; margin: 0;'>🔴 BLACKOUT — DO NOT TRADE</h2><p style='color: #e8ecf1;'>Reason: {blackout_reason}</p><p style='color: #a0aec0; font-size: 13px;'>Next: {SESSIONS[next_key]["name"] if next_key else "—"} in {fmt_countdown(until_next)}</p></div>""", unsafe_allow_html=True)
        return
    else:
        st.markdown(f"""<div style='background-color: #2a2a1a; padding: 20px; border-radius: 10px; border: 2px solid #facc15; margin-bottom: 20px;'><h2 style='color: #facc15; margin: 0;'>⏳ BETWEEN SESSIONS</h2><p style='color: #e8ecf1;'>Next: <b>{SESSIONS[next_key]["name"] if next_key else "—"}</b> in <b>{fmt_countdown(until_next)}</b></p></div>""", unsafe_allow_html=True)
        return
    st.markdown(f"""<div style='background-color: #1c2129; padding: 15px; border-radius: 10px; border-left: 4px solid #facc15; margin-bottom: 20px;'><h4 style='color: #facc15; margin: 0 0 8px 0;'>📊 YIELD REGIME: {regime_label} (US10Y: {tnx:.2f}%)</h4><b>Position size:</b> {int(regime_size*100)}% of normal<br><b>Preferred assets:</b> {", ".join(regime_assets)}<br><b>Trail distance:</b> {regime_trail:.2f} ATR<br><b>Note:</b> {regime_note}</div>""", unsafe_allow_html=True)
    if asset_key not in regime_assets:
        st.error(f"🚫 {asset_name} is NOT in the preferred list for {regime_label} regime. Switch to: {', '.join(regime_assets)}")
        return
    if uk_time.weekday() == 4 and uk_time.hour >= 18:
        st.error("🚫 Friday after 6 PM UK — NO TRADING"); return
    with st.spinner(f"Analyzing {asset_name}..."):
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
        if data.empty: st.warning(f"No data for {asset_name}"); return
        today_utc = datetime.now(timezone.utc).date()
        data_today = data[data.index.date == today_utc]
        if data_today.empty: data_today = data.tail(100)
        current_price = data_today['Close'].iloc[-1]
        atr = calc_atr(data_today)
        adx, plus_di, minus_di = calc_adx(data_today)
        vwap = (data_today['Close'] * data_today['Volume']).cumsum() / data_today['Volume'].cumsum()
        current_vwap = vwap.iloc[-1]
        ema9 = data_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        ema20 = data_today['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = data_today['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        last_swing_high, last_swing_low = get_last_swing_levels(data_today)
    st.markdown("### ✅ Filter Checklist")
    checks = []
    adx_pass = adx > 25
    checks.append(("ADX > 25", adx_pass, f"ADX = {adx:.1f}", "+3-5% win rate"))
    bullish_stack = current_price > ema9 > ema20 > ema50
    bearish_stack = current_price < ema9 < ema20 < ema50
    stack_pass = bullish_stack or bearish_stack
    stack_dir = "LONG" if bullish_stack else "SHORT" if bearish_stack else "MIXED"
    checks.append(("EMA Stack Aligned", stack_pass, f"Direction: {stack_dir}", "+3-4% win rate"))
    vwap_long = current_price > current_vwap; vwap_short = current_price < current_vwap
    vwap_pass = vwap_long or vwap_short
    checks.append(("VWAP Alignment", vwap_pass, f"Price {'above' if vwap_long else 'below'} VWAP", "+3-4% win rate"))
    macro_score = 0
    if dxy < 103: macro_score += 1
    if tnx < 4.5: macro_score += 1
    if vix < 25: macro_score += 1
    macro_pass = macro_score >= 2
    checks.append(("Macro 2/3 Alignment", macro_pass, f"DXY {dxy:.2f}, 10Y {tnx:.2f}%, VIX {vix:.2f} — {macro_score}/3", "+2-3% win rate"))
    vix_pass = vix < 30
    checks.append(("VIX < 30", vix_pass, f"VIX = {vix:.2f}", "+5% win rate"))
    day_pass = not (uk_time.weekday() == 4)
    checks.append(("Not Friday", day_pass, f"Day = {uk_time.strftime('%A')}", "+2-3% win rate"))
    all_pass = all(c[1] for c in checks); passed_count = sum(1 for c in checks if c[1])
    for name, passed, detail, boost in checks:
        icon = "✅" if passed else "❌"; color = "#4ade80" if passed else "#f87171"
        st.markdown(f"<div style='padding: 8px; border-left: 3px solid {color}; margin: 4px 0;'>{icon} <b>{name}</b> — {detail} <span style='color: #a0aec0; font-size: 12px;'>({boost})</span></div>", unsafe_allow_html=True)
    if not vix_pass: st.error(f"🚫 VIX > 30 ({vix:.2f}) — EXTREME VOLATILITY."); return
    if not all_pass: st.warning(f"⚠️ {passed_count}/6 filters passed. Pure Trend Rider requires ALL filters. WAIT."); return
    st.success(f"🟢 ALL 6 FILTERS PASSED — Setup valid!")
    st.markdown("---"); st.markdown("### 📈 Trend Analysis")
    if bullish_stack and vwap_long:
        direction = "LONG"; is_breakout, prior_swing, _ = detect_breakout(data_today, "UP", lookback=20)
        st.success(f"🟢 BULLISH TREND — Looking for LONG breakout")
    elif bearish_stack and vwap_short:
        direction = "SHORT"; is_breakout, prior_swing, _ = detect_breakout(data_today, "DOWN", lookback=20)
        st.error(f"🔴 BEARISH TREND — Looking for SHORT breakout")
    else: st.warning("⚪ CONFLICT: EMA stack and VWAP disagree"); return
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    with col_t1: st.metric("ADX", f"{adx:.1f}")
    with col_t2: st.metric("+DI / -DI", f"{plus_di:.1f} / {minus_di:.1f}")
    with col_t3: st.metric("ATR", f"{atr:.2f}")
    with col_t4: st.metric("Price", f"{current_price:.2f}")
    if not is_breakout: st.info(f"⏳ No breakout yet. Waiting for close beyond {prior_swing:.2f}"); return
    st.markdown("---"); st.markdown("### 🚀 BREAKOUT DETECTED")
    st.success(f"✅ Price closed {'above' if direction == 'LONG' else 'below'} prior swing {prior_swing:.2f}")
    distance_from_swing = abs(current_price - prior_swing)
    if distance_from_swing > (atr * 0.5): st.warning(f"⚠️ Price already moved {distance_from_swing:.2f} pts past the swing — DO NOT CHASE."); return
    if direction == "LONG":
        entry = current_price; stop = safe_stop(entry, "LONG", last_swing_low, asset_key)
    else:
        entry = current_price; stop = safe_stop(entry, "SHORT", last_swing_high, asset_key)
    risk = abs(stop - entry); dollar_risk = risk * TICK_VALUES.get(asset_key, 1.0)
    base_contracts = 1; final_size = base_contracts * session_info["size"] * regime_size
    display_size = max(1, round(final_size))
    st.markdown("### 📋 TRADE PLAN")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.metric("Direction", direction); st.metric("Entry", f"{entry:.2f}")
        st.metric("Stop", f"{stop:.2f}", delta=f"{'above' if direction=='SHORT' else 'below'} entry ✅")
        st.metric("Risk", f"{risk:.2f} pts (${dollar_risk:.2f}/contract)")
    with col_p2:
        st.metric("Target", "NONE — TRAIL"); st.metric("Size", f"{display_size} contract(s)")
        st.metric("Session", session_info["name"]); st.metric("Regime", regime_label)
    st.markdown("---"); st.markdown("### 🎯 TRAILING STOP RULES")
    if direction == "LONG":
        st.markdown(f"""<div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px;'><b>Entry:</b> {entry:.2f} | <b>Initial Stop:</b> {stop:.2f}<br><br><b>Stage 1 (1R):</b> Move stop to <b>{entry:.2f}</b> (breakeven)<br><b>Stage 2 (2R):</b> Move stop to <b>{last_swing_low:.2f}</b><br><b>Stage 3 (3R):</b> Trail by <b>{atr * regime_trail:.2f}</b> pts<br><b>Stage 4 (4R+):</b> Trail by <b>{atr * regime_trail * 0.5:.2f}</b> pts</div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px;'><b>Entry:</b> {entry:.2f} | <b>Initial Stop:</b> {stop:.2f}<br><br><b>Stage 1 (1R):</b> Move stop to <b>{entry:.2f}</b> (breakeven)<br><b>Stage 2 (2R):</b> Move stop to <b>{last_swing_high:.2f}</b><br><b>Stage 3 (3R):</b> Trail by <b>{atr * regime_trail:.2f}</b> pts<br><b>Stage 4 (4R+):</b> Trail by <b>{atr * regime_trail * 0.5:.2f}</b> pts</div>""", unsafe_allow_html=True)
    st.markdown("---"); st.markdown("### ⚠️ CRITICAL REMINDERS")
    st.markdown(f"- 🚫 Do NOT add to losing positions\n- 🚫 Do NOT chase\n- 🚫 Do NOT move stops wider\n- ✅ Exit by end of session ({session_info['end']} UK)\n- ✅ Take partial at 2R")


# ============ 📈 TREND-FADE HYBRID ============
def run_trend_fade_hybrid():
    st.subheader("📈 Trend-Fade Hybrid")
    st.caption("Fade pullbacks WITHIN the trend. Fires early when trend detected.")
    asset_choice = st.selectbox("Select Asset", ["MNQ (Micro Nasdaq)", "M2K (Micro Russell 2000)", "US30 (Micro Dow)", "MGC (Micro Gold)", "MES (Micro S&P 500)"], index=0, key="tfh_asset_select")
    asset_map = {"MNQ (Micro Nasdaq)": ("MNQ=F", "MNQ"), "M2K (Micro Russell 2000)": ("M2K=F", "M2K"), "US30 (Micro Dow)": ("YM=F", "US30"), "MGC (Micro Gold)": ("MGC=F", "MGC"), "MES (Micro S&P 500)": ("MES=F", "MES")}
    ticker, asset_key = asset_map[asset_choice]
    asset_name = asset_choice.split(" (")[0]
    market = classify_market_conditions(ticker)
    market_class = market.get('classification', 'UNKNOWN'); adx = market.get('adx', 0)
    if market_class != "TRENDING": st.warning(f"⚠️ Market is {market_class}, not TRENDING."); return
    if adx < 25: st.warning(f"⚠️ ADX is {adx:.1f} (< 25). WAIT for ADX > 25."); return
    now_utc = datetime.now(timezone.utc); uk_time = now_utc.astimezone(ZoneInfo("Europe/London"))
    session_key, session_info, session_remaining, next_key, until_next = get_current_session(uk_time)
    if not session_key: st.warning(f"⏳ Not in a session window. Next: {SESSIONS[next_key]['name']} in {fmt_countdown(until_next)}"); return
    st.success(f"🟢 {session_info['name']} WINDOW — {fmt_countdown(session_remaining)} remaining")
    with st.spinner(f"Loading {asset_name}..."):
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
        if data.empty: st.warning("No data."); return
        today_utc = datetime.now(timezone.utc).date()
        data_today = data[data.index.date == today_utc]
        if data_today.empty: data_today = data.tail(100)
        current_price = data_today['Close'].iloc[-1]
        vwap = (data_today['Close'] * data_today['Volume']).cumsum() / data_today['Volume'].cumsum()
        current_vwap = vwap.iloc[-1]
        ema9 = data_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        last_high, last_low = get_last_swing_levels(data_today)
    if market['trend_direction'] == "UP":
        direction = "LONG"; entry_zone = min(ema9, current_vwap)
        stop = safe_stop(current_price, "LONG", last_low, asset_key)
        target = last_high if last_high > current_price else current_price + (current_price - stop) * 2.5
    elif market['trend_direction'] == "DOWN":
        direction = "SHORT"; entry_zone = max(ema9, current_vwap)
        stop = safe_stop(current_price, "SHORT", last_high, asset_key)
        target = last_low if last_low < current_price else current_price - (stop - current_price) * 2.5
    else: st.warning("⚪ Mixed signals."); return
    if direction == "LONG": risk = current_price - stop; reward = target - current_price
    else: risk = stop - current_price; reward = current_price - target
    rr = clamp_rr(reward / risk) if risk > 0.01 else 0
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Direction", direction)
    with col2: st.metric("Pullback Zone", f"{entry_zone:.2f}")
    with col3: st.metric("Current", f"{current_price:.2f}")
    st.markdown(f"<div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px;'><b>Entry:</b> {current_price:.2f}<br><b>Stop:</b> {stop:.2f}<br><b>Target:</b> {target:.2f}<br><b>Risk:</b> {risk:.2f} pts<br><b>R:R:</b> 1:{rr:.1f}</div>", unsafe_allow_html=True)
    st.caption(f"💡 Early signal: Prefer entry at pullback zone ({entry_zone:.2f}) when reached.")


# ============ 🚀 SESSION BREAKOUT ============
def run_session_breakout():
    st.subheader("🚀 Session Breakout")
    st.caption("Trades the breakout of PM High/Low with confirmation. Works with the trend.")
    asset_choice = st.selectbox("Select Asset", ["MNQ (Micro Nasdaq)", "M2K (Micro Russell 2000)", "US30 (Micro Dow)", "MES (Micro S&P 500)", "MGC (Micro Gold)"], index=0, key="sb_asset_select")
    asset_map = {"MNQ (Micro Nasdaq)": ("MNQ=F", "MNQ"), "M2K (Micro Russell 2000)": ("M2K=F", "M2K"), "US30 (Micro Dow)": ("YM=F", "US30"), "MES (Micro S&P 500)": ("MES=F", "MES"), "MGC (Micro Gold)": ("MGC=F", "MGC")}
    ticker, asset_key = asset_map[asset_choice]
    asset_name = asset_choice.split(" (")[0]
    now_utc = datetime.now(timezone.utc); uk_time = now_utc.astimezone(ZoneInfo("Europe/London"))
    session_key, session_info, session_remaining, next_key, until_next = get_current_session(uk_time)
    blackout, blackout_reason = is_blackout(uk_time)
    macro = get_macro_data()
    tnx = macro['yield_10y']; vix = macro['vix']; dxy = macro['dxy']
    regime_key, regime_label, regime_size, regime_trail, regime_assets, regime_note = get_yield_regime(tnx)
    if session_key:
        st.markdown(f"""<div style='background-color: #1a3a2a; padding: 20px; border-radius: 10px; border: 2px solid #4ade80;'><h2 style='color: #4ade80; margin: 0;'>🟢 {session_info["name"]} WINDOW ACTIVE</h2><p style='color: #e8ecf1;'>Time remaining: <b>{fmt_countdown(session_remaining)}</b></p></div>""", unsafe_allow_html=True)
    elif blackout:
        st.markdown(f"""<div style='background-color: #3a1a1a; padding: 20px; border-radius: 10px; border: 2px solid #f87171;'><h2 style='color: #f87171; margin: 0;'>🔴 BLACKOUT — DO NOT TRADE</h2><p style='color: #e8ecf1;'>Reason: {blackout_reason}</p></div>""", unsafe_allow_html=True); return
    else:
        st.markdown(f"""<div style='background-color: #2a2a1a; padding: 20px; border-radius: 10px; border: 2px solid #facc15;'><h2 style='color: #facc15; margin: 0;'>⏳ BETWEEN SESSIONS</h2><p style='color: #e8ecf1;'>Next: <b>{SESSIONS[next_key]["name"]}</b> in <b>{fmt_countdown(until_next)}</b></p></div>""", unsafe_allow_html=True); return
    if vix > 30: st.error(f"🚫 VIX > 30 ({vix:.2f})"); return
    if uk_time.weekday() == 4 and uk_time.hour >= 18: st.error("🚫 Friday after 6 PM UK"); return
    with st.spinner(f"Analyzing {asset_name}..."):
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
        if data.empty: st.warning(f"No data for {asset_name}"); return
        today_utc = datetime.now(timezone.utc).date()
        data_today = data[data.index.date == today_utc]
        if data_today.empty: data_today = data.tail(100)
        current_price = data_today['Close'].iloc[-1]
        atr = calc_atr(data_today); adx, plus_di, minus_di = calc_adx(data_today)
        vwap = (data_today['Close'] * data_today['Volume']).cumsum() / data_today['Volume'].cumsum()
        current_vwap = vwap.iloc[-1]
        ema9 = data_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        ema20 = data_today['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = data_today['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        ny_data = data_today.between_time('08:00', '09:29')
        if ny_data.empty or len(ny_data) < 5: ny_data = data_today.between_time('07:30', '09:29')
        if ny_data.empty: st.warning("PM range data not available."); return
        pm_high = ny_data['High'].max(); pm_low = ny_data['Low'].min(); pm_range = pm_high - pm_low
    st.markdown("### ✅ Filter Checklist"); checks = []
    adx_pass = adx > 25; checks.append(("ADX > 25", adx_pass, f"ADX = {adx:.1f}", "+3-5%"))
    bullish_stack = current_price > ema9 > ema20 > ema50; bearish_stack = current_price < ema9 < ema20 < ema50
    stack_pass = bullish_stack or bearish_stack; stack_dir = "LONG" if bullish_stack else "SHORT" if bearish_stack else "MIXED"
    checks.append(("EMA Stack", stack_pass, f"Direction: {stack_dir}", "+3-4%"))
    vwap_long = current_price > current_vwap; vwap_short = current_price < current_vwap
    vwap_pass = vwap_long or vwap_short
    checks.append(("VWAP", vwap_pass, f"Price {'above' if vwap_long else 'below'} VWAP", "+3-4%"))
    macro_score = 0
    if dxy < 103: macro_score += 1
    if tnx < 4.5: macro_score += 1
    if vix < 25: macro_score += 1
    macro_pass = macro_score >= 2
    checks.append(("Macro 2/3", macro_pass, f"DXY {dxy:.2f}, 10Y {tnx:.2f}%, VIX {vix:.2f} — {macro_score}/3", "+2-3%"))
    vix_pass = vix < 30; checks.append(("VIX < 30", vix_pass, f"VIX = {vix:.2f}", "+5%"))
    min_range = MIN_NY_RANGE.get(asset_key, 5); range_pass = pm_range >= min_range
    checks.append(("PM Range Adequate", range_pass, f"{pm_range:.2f} pts (min {min_range})", "prevents fakeouts"))
    all_pass = all(c[1] for c in checks); passed_count = sum(1 for c in checks if c[1])
    for name, passed, detail, boost in checks:
        icon = "✅" if passed else "❌"; color = "#4ade80" if passed else "#f87171"
        st.markdown(f"<div style='padding: 8px; border-left: 3px solid {color}; margin: 4px 0;'>{icon} <b>{name}</b> — {detail} <span style='color: #a0aec0; font-size: 12px;'>({boost})</span></div>", unsafe_allow_html=True)
    if not all_pass: st.warning(f"⚠️ {passed_count}/6 filters passed."); return
    st.success("🟢 ALL 6 FILTERS PASSED")
    st.markdown("---"); st.markdown("### 📊 Pre-Market Range")
    col_pm1, col_pm2, col_pm3, col_pm4 = st.columns(4)
    with col_pm1: st.metric("PM High", f"{pm_high:.2f}")
    with col_pm2: st.metric("PM Low", f"{pm_low:.2f}")
    with col_pm3: st.metric("PM Range", f"{pm_range:.2f} pts")
    with col_pm4: st.metric("Current", f"{current_price:.2f}")
    breakout_buffer = STOP_BUFFERS.get(asset_key, 5)
    above_high = current_price > pm_high + breakout_buffer
    below_low = current_price < pm_low - breakout_buffer
    st.markdown("---"); st.markdown("### 🚀 Breakout Detection")
    if above_high and bullish_stack and vwap_long:
        direction = "LONG"; entry = current_price; stop = safe_stop(entry, "LONG", pm_high, asset_key)
        risk = entry - stop; target = entry + (pm_range * 1.5)
        st.success(f"✅ UPSIDE BREAKOUT — above PM High + {breakout_buffer} pts")
    elif below_low and bearish_stack and vwap_short:
        direction = "SHORT"; entry = current_price; stop = safe_stop(entry, "SHORT", pm_low, asset_key)
        risk = stop - entry; target = entry - (pm_range * 1.5)
        st.error(f"✅ DOWNSIDE BREAKOUT — below PM Low - {breakout_buffer} pts")
    else:
        st.info(f"⏳ No confirmed breakout yet.")
        if not above_high and not below_low:
            st.markdown(f"- Price inside PM range ({pm_low:.2f} — {pm_high:.2f})")
            st.markdown(f"- LONG needs: price > **{pm_high + breakout_buffer:.2f}**")
            st.markdown(f"- SHORT needs: price < **{pm_low - breakout_buffer:.2f}**")
        return
    rr = clamp_rr((target - entry) / risk) if risk > 0.01 else 0
    dollar_risk = risk * TICK_VALUES.get(asset_key, 1.0)
    base_contracts = 1; final_size = base_contracts * session_info["size"] * regime_size
    display_size = max(1, round(final_size))
    st.markdown("### 📋 TRADE PLAN")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.metric("Direction", direction); st.metric("Entry", f"{entry:.2f}")
        st.metric("Stop", f"{stop:.2f}"); st.metric("Risk", f"{risk:.2f} pts (${dollar_risk:.2f}/contract)")
    with col_p2:
        st.metric("Target", f"{target:.2f}"); st.metric("R:R", f"1:{rr:.1f}")
        st.metric("Size", f"{display_size} contract(s)"); st.metric("Session", session_info["name"])
    st.markdown("---"); st.markdown("### ⚠️ REMINDERS")
    st.markdown(f"- ✅ Trade WITH the breakout\n- ✅ Stop opposite PM edge\n- ✅ Target = 1.5× PM Range\n- 🚫 Do NOT chase > 1× ATR past breakout\n- ✅ Exit by {session_info['end']} UK")


# ============ STRATEGY SELECTOR ============
def run_strategy_selector():
    st.subheader("🎯 Strategy Selector — 3-Way Decision Engine")
    st.caption("Recommends the best of 3 strategies based on live market conditions.")
    macro = get_macro_data()
    tnx = macro.get('yield_10y', 4.20); vix = macro.get('vix', 18.0); dxy = macro.get('dxy', 102.0)
    analyze_asset = st.selectbox("🎯 Analyze which market?", ["MNQ=F", "M2K=F", "YM=F", "MES=F", "MGC=F"],
                                  format_func=lambda x: ASSET_VOLATILITY_PROFILES.get(x, {}).get("name", x),
                                  index=0, key="ss_asset")
    market = classify_market_conditions(analyze_asset)
    market_class = market.get('classification', 'UNKNOWN'); adx = market.get('adx', 0); trend_dir = market.get('trend_direction', 'MIXED')
    regime_key, regime_label, regime_size, regime_trail, regime_assets, regime_note = get_yield_regime(tnx)
    now_utc = datetime.now(timezone.utc); uk_time = now_utc.astimezone(ZoneInfo("Europe/London"))
    session_key, session_info, _, next_key, until_next = get_current_session(uk_time)
    blackout, reason = is_blackout(uk_time)
    st.info(f"📊 Analyzing **{market.get('asset_name', analyze_asset)}** — Typical NY Range: {market.get('typical_range', 'N/A')}")
    if session_key and not blackout: session_mult = session_info["size"]
    else: session_mult = 0.0
    combined_mult = session_mult * regime_size
    if vix > 30:
        rec = "⛔ SIT OUT — VIX > 30"; position = "0%"; why = [f"🔴 VIX {vix:.2f} extreme volatility", "No strategy works here"]
    elif blackout or not session_key:
        rec = "⛔ SIT OUT — OUTSIDE SESSION"; position = "0%"; why = [f"🔴 {reason if blackout else 'Not in active window'}", f"⏳ Next: {SESSIONS[next_key]['name']} in {fmt_countdown(until_next)}"]
    elif market_class == "TRENDING" and adx > 30:
        rec = "🚀 Session Breakout"; position = f"{int(combined_mult * 100)}%"; why = [f"🟢 Strong trend (ADX {adx})", f"📈 Direction: {trend_dir}", "PM High/Low breakout with confirmation"]
    elif market_class == "TRENDING" and adx > 25:
        rec = "🚀 Pure Trend Rider"; position = f"{int(combined_mult * 100)}%"; why = [f"🟢 Market TRENDING (ADX {adx})", f"📈 Direction: {trend_dir}", "Breakout with trailing stops"]
    elif market_class == "TRENDING":
        rec = "📈 Trend-Fade Hybrid"; position = f"{int(combined_mult * 75)}%"; why = [f"🟡 Trend forming (ADX {adx})", "Use pullback entries", "Wait for ADX > 25 for breakout"]
    elif market_class == "RANGING":
        rec = "⛔ SIT OUT — RANGING MARKET"; position = "0%"; why = ["🟡 Market is ranging", "No high-quality setup available"]
    else:
        rec = "⛔ SIT OUT — UNCLEAR"; position = "0%"; why = ["🟡 No clear trend or range"]
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### 📊 Current Conditions")
        st.markdown(f"<div style='background-color: #1c2129; padding: 12px; border-radius: 8px; margin: 6px 0;'><b>US10Y:</b> {tnx:.2f}% ({regime_label})</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='background-color: #1c2129; padding: 12px; border-radius: 8px; margin: 6px 0;'><b>VIX:</b> {vix:.2f}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='background-color: #1c2129; padding: 12px; border-radius: 8px; margin: 6px 0;'><b>Market:</b> {market_class} (ADX {adx})</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='background-color: #1c2129; padding: 12px; border-radius: 8px; margin: 6px 0;'><b>Session:</b> {session_info['name'] if session_info else 'BLACKOUT'}</div>", unsafe_allow_html=True)
    with col2:
        st.markdown("### 🎯 Recommended Strategy")
        color = "#f87171" if "SIT OUT" in rec else "#4ade80" if "Trend" in rec else "#facc15"
        st.markdown(f"<div style='background-color: #1c2129; padding: 20px; border-radius: 8px; border: 3px solid {color}; text-align: center;'><h2 style='color: {color};'>{rec}</h2><p style='color: #a0aec0;'>Position size: {position}</p></div>", unsafe_allow_html=True)
    st.markdown("### 📋 Decision Reasoning")
    for w in why: st.markdown(f"- {w}")
    st.markdown("---"); st.markdown("### 📊 3-Strategy Comparison")
    comp = pd.DataFrame({
        "Feature": ["Market Condition", "Entry Type", "Stop", "Target", "Size", "Win Rate"],
        "📈 Trend-Fade": ["TRENDING (ADX > 25)", "Pullback to 9 EMA/VWAP", "Beyond pullback swing", "Prior swing high/low", "50-75%", "50-60%"],
        "🚀 Trend Rider": ["TRENDING (ADX > 25)", "Breakout + trail", "Prior swing ± buffer", "None — trail", "50-100%", "48-55%"],
        "🚀 Session Breakout": ["TRENDING (ADX > 30)", "PM High/Low + buffer", "PM edge ± buffer", "1.5× PM Range", "50-100%", "55-65%"],
    })
    st.dataframe(comp, hide_index=True, use_container_width=True)


# ============ STUBS ============
def render_smc_cheat_sheet(): st.subheader("🎯 SMC Cheat Sheet"); st.info("Weak High = SELL ZONE. Weak Low = BOUNCE ZONE.")
def run_sniper_entry_theory(): st.subheader("🎯 Sniper Entry Theory"); st.info("15-point buffer filters fakeouts.")
def run_indices_bond_tracker(): st.subheader("📊 Indices & Bond Tracker"); st.info("VIX / Bond reference guide.")
def run_vwap_ema_strategy(): st.subheader("📊 VWAP & 9 EMA Strategy"); st.success("✅ LONG: Price > 9 EMA + > VWAP + DXY weak")
def run_ny_afternoon_sniper(): st.subheader("🇺🇸 NY Afternoon Sniper"); st.info("3:30-4:30 PM UK session.")
def run_smart_money_levels(): st.subheader("🎯 Smart Money Levels")
def run_asia_sniper(): st.subheader("🌏 Asia Session Sniper"); st.info("Loading Asian market data...")
def run_level_marker(): st.subheader("🎯 Global Session Sniper Triggers"); st.info("Loading session data...")
def run_treasury_dashboard():
    st.subheader("🏛️ Treasury Intervention Tracker")
    status, icon = TreasuryIntervention.get_buyback_status()
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Buyback Program", f"{icon} {status}")
    with col2: st.metric("10Y Cap", f"{TreasuryIntervention.YIELD_CAP_10Y:.2f}%")
    with col3: st.metric("30Y Cap", f"{TreasuryIntervention.YIELD_CAP_30Y:.2f}%")
def run_m2k_shortcut():
    st.subheader("📉 M2K (Micro Russell 2000)")
    market = classify_market_conditions("M2K=F")
    st.markdown(f"**Classification:** {market.get('classification')}")
    st.markdown(f"**Typical Range:** {market.get('typical_range')}")
def run_us30_shortcut():
    st.subheader("🏛️ US30 (Micro Dow)")
    market = classify_market_conditions("YM=F")
    st.markdown(f"**Classification:** {market.get('classification')}")
    st.markdown(f"**Typical Range:** {market.get('typical_range')}")


# ============ MAIN APP ============
def run_app():
    load_dotenv(); init_db()
    st.set_page_config(page_title="TradeTerminal Pro", layout="wide", initial_sidebar_state="expanded")
    st.markdown("""
    <style>
    .stApp { background-color: #0f1116; color: #e8ecf1; }
    .eco-card { background: #1c2129; padding: 15px; border-radius: 10px; border-left: 4px solid #4c6fff; }
    .sidebar-logo { text-align: center; padding: 20px 0 30px 0; border-bottom: 1px solid #2a2a2a; margin-bottom: 20px; }
    .sidebar-logo h1 { color: #4c6fff; font-size: 24px; margin: 0; font-weight: 700; }
    .sidebar-logo p { color: #a0aec0; font-size: 12px; margin: 5px 0 0 0; }
    .sidebar-divider { border-top: 1px solid #2a2a2a; margin: 15px 0; }
    </style>
    """, unsafe_allow_html=True)
    DEFAULT_NAV = "🏠 Dashboard"
    NAV_OPTIONS = [
        "🏠 Dashboard", "📈 Charts", "🎯 Strategy Selector",
        "🚀 Pure Trend Rider", "📈 Trend-Fade Hybrid", "🚀 Session Breakout",
        "📉 M2K (Russell 2000)", "🏛️ US30 (Dow Jones)",
        "📊 Indices & Bond Tracker", "📈 VWAP & 9 EMA", "🇺🇸 NY Afternoon",
        "🌏 Asia Sniper", "🎯 Market Levels", "🎯 Smart Money Levels",
        "📋 SMC Cheat Sheet", "🏛️ Treasury Tracker", "🎯 Sniper Entry Theory",
    ]
    if 'nav_redirect' not in st.session_state: st.session_state['nav_redirect'] = None
    if 'nav_selection' not in st.session_state: st.session_state['nav_selection'] = DEFAULT_NAV
    if st.session_state['nav_redirect'] is not None:
        tgt = st.session_state['nav_redirect']
        if tgt in NAV_OPTIONS: st.session_state['nav_selection'] = tgt
        st.session_state['nav_redirect'] = None
    if st.session_state['nav_selection'] not in NAV_OPTIONS: st.session_state['nav_selection'] = DEFAULT_NAV
    with st.sidebar:
        st.markdown("""<div class="sidebar-logo"><h1>⚡ TradeTerminal</h1><p>Pro v2.3 — Breakout</p></div>""", unsafe_allow_html=True)
        nav_section = st.radio("Navigation", NAV_OPTIONS, index=NAV_OPTIONS.index(st.session_state['nav_selection']), key="nav_selection", label_visibility="collapsed")
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        st.markdown("### 🕐 Session Clock")
        now_utc = datetime.now(timezone.utc); uk = now_utc.astimezone(ZoneInfo("Europe/London"))
        st.markdown(f"**UK:** {uk.strftime('%H:%M')}")
        s_key, s_info, s_rem, n_key, n_delta = get_current_session(uk)
        if s_key: st.success(f"{s_info['name']} — {fmt_countdown(s_rem)} left")
        else: st.info(f"⏳ {SESSIONS[n_key]['name']} in {fmt_countdown(n_delta)}")
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        st.markdown("### 📊 Macro")
        try:
            macro = get_macro_data()
            tnx = macro.get('yield_10y', 4.20); vix = macro.get('vix', 18.0)
            rk, rl, _, _, _, _ = get_yield_regime(tnx)
            yc = "#f87171" if tnx > 4.5 else "#facc15" if tnx > 4.3 else "#4ade80"
            vc = "#4ade80" if vix < 20 else "#facc15" if vix < 30 else "#f87171"
            st.markdown(f"<div style='font-size:13px;'><b>10Y:</b> <span style='color:{yc};'>{tnx:.2f}%</span> ({rl})</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:13px;'><b>VIX:</b> <span style='color:{vc};'>{vix:.2f}</span></div>", unsafe_allow_html=True)
        except: pass
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        if st.button("🔄 Refresh", use_container_width=True): st.rerun()
        st.caption("⚡ v2.3")
    st.title("⚡ TradeTerminal Pro")
    if nav_section == "🏠 Dashboard":
        try:
            mt = get_macro_data(); fg = calc_fear_greed(mt['vix'], 0.5, mt['dxy'])
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(f"<div class='eco-card'><h4>🧠 Fear & Greed</h4><h2>{fg['label']}</h2><small>{fg['score']}/100</small></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='eco-card'><h4>📊 US10Y</h4><h2>{mt['yield_10y']:.2f}%</h2></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='eco-card'><h4>😱 VIX</h4><h2>{mt['vix']:.2f}</h2></div>", unsafe_allow_html=True)
            with c4: st.markdown(f"<div class='eco-card'><h4>💵 DXY</h4><h2>{mt['dxy']:.2f}</h2></div>", unsafe_allow_html=True)
        except: pass
        st.markdown("---"); st.markdown("### 🎯 Quick Actions")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("🎯 Strategy Selector", use_container_width=True, key="dash_ss"):
                st.session_state['nav_redirect'] = "🎯 Strategy Selector"; st.rerun()
        with col_b:
            if st.button("🚀 Pure Trend Rider", use_container_width=True, key="dash_ptr"):
                st.session_state['nav_redirect'] = "🚀 Pure Trend Rider"; st.rerun()
        with col_c:
            if st.button("🚀 Session Breakout", use_container_width=True, key="dash_sb"):
                st.session_state['nav_redirect'] = "🚀 Session Breakout"; st.rerun()
    elif nav_section == "📈 Charts":
        st.subheader("📈 Asset Analysis")
        asset_keys = list(ASSETS.keys()); cols_per_row = 6
        for i in range(0, len(asset_keys), cols_per_row):
            row_keys = asset_keys[i:i+cols_per_row]; cols = st.columns(cols_per_row)
            for j, key in enumerate(row_keys):
                with cols[j]:
                    if st.button(ASSETS[key]['symbol'], key=f"asset_btn_{key}", use_container_width=True):
                        st.session_state['selected_asset'] = key
        if 'selected_asset' not in st.session_state: st.session_state['selected_asset'] = "MNQ"
        st.info(f"Selected: {st.session_state['selected_asset']} (chart module simplified)")
    elif nav_section == "🎯 Strategy Selector": run_strategy_selector()
    elif nav_section == "🚀 Pure Trend Rider": run_pure_trend_rider()
    elif nav_section == "📈 Trend-Fade Hybrid": run_trend_fade_hybrid()
    elif nav_section == "🚀 Session Breakout": run_session_breakout()
    elif nav_section == "📉 M2K (Russell 2000)": run_m2k_shortcut()
    elif nav_section == "🏛️ US30 (Dow Jones)": run_us30_shortcut()
    elif nav_section == "📊 Indices & Bond Tracker": run_indices_bond_tracker()
    elif nav_section == "📈 VWAP & 9 EMA": run_vwap_ema_strategy()
    elif nav_section == "🇺🇸 NY Afternoon": run_ny_afternoon_sniper()
    elif nav_section == "🌏 Asia Sniper": run_asia_sniper()
    elif nav_section == "🎯 Market Levels": run_level_marker()
    elif nav_section == "🎯 Smart Money Levels": run_smart_money_levels()
    elif nav_section == "📋 SMC Cheat Sheet": render_smc_cheat_sheet()
    elif nav_section == "🏛️ Treasury Tracker": run_treasury_dashboard()
    elif nav_section == "🎯 Sniper Entry Theory": run_sniper_entry_theory()

if __name__ == "__main__":
    run_app()