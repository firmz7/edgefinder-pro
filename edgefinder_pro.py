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

# ============ ASSET-SPECIFIC VOLATILITY PROFILES ============
ASSET_VOLATILITY_PROFILES = {
    "MNQ=F":  {"trending_min": 40,  "ranging_max": 25,  "name": "MNQ (Nasdaq)",   "typical_range": "40-80"},
    "M2K=F":  {"trending_min": 20,  "ranging_max": 12,  "name": "M2K (Russell)",  "typical_range": "15-30"},
    "YM=F":   {"trending_min": 200, "ranging_max": 120, "name": "US30 (Dow)",     "typical_range": "150-350"},
    "MES=F":  {"trending_min": 30,  "ranging_max": 18,  "name": "MES (S&P 500)",  "typical_range": "20-40"},
    "MGC=F":  {"trending_min": 15,  "ranging_max": 8,   "name": "MGC (Gold)",     "typical_range": "8-20"},
}

# ============ PER-ASSET STOP BUFFERS (points) ============
STOP_BUFFERS = {
    "MNQ": 5,
    "M2K": 3,
    "US30": 20,
    "MGC": 2,
    "MES": 5,
}

# ============ MINIMUM NY RANGE (points) — below this, signals are unreliable ============
MIN_NY_RANGE = {
    "MNQ": 10,
    "M2K": 5,
    "US30": 40,
    "MGC": 4,
    "MES": 8,
}

# ============ TICK VALUES ($ per point per contract) ============
TICK_VALUES = {
    "MNQ": 2.0,
    "M2K": 5.0,
    "US30": 0.5,
    "MGC": 10.0,
    "MES": 5.0,
}

def safe_stop(entry: float, direction: str, anchor_level: float, asset: str) -> float:
    """
    Returns a stop-loss that is ALWAYS on the correct side of entry.
    direction: 'LONG' or 'SHORT'
    anchor_level: the level we WANT the stop to be near (e.g. ny_high, swing_low)
    asset: symbol key like 'MNQ', 'US30', etc.
    """
    buf = STOP_BUFFERS.get(asset, 5)
    if direction == "SHORT":
        return max(anchor_level + buf, entry + buf)
    elif direction == "LONG":
        return min(anchor_level - buf, entry - buf)
    return entry

def clamp_rr(rr: float, max_rr: float = 10.0) -> float:
    if rr <= 0 or not math.isfinite(rr):
        return 0.0
    return min(rr, max_rr)

class TreasuryIntervention:
    YIELD_CAP_10Y = 4.75
    YIELD_CAP_30Y = 5.25
    BUYBACK_START = datetime(2026, 9, 9)
    BUYBACK_END = datetime(2026, 11, 4)
    
    @staticmethod
    def get_buyback_status():
        now = datetime.now()
        if TreasuryIntervention.BUYBACK_START <= now <= TreasuryIntervention.BUYBACK_END:
            return "ACTIVE", "🟢"
        elif now < TreasuryIntervention.BUYBACK_START:
            days = (TreasuryIntervention.BUYBACK_START - now).days
            return f"STARTS IN {days} DAYS", "🟡"
        else:
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
                        d = event_date - now
                        days = d.days; h, r = divmod(d.seconds, 3600); m, _ = divmod(r, 60)
                        c = f"{days}d {h}h {m}m" if days > 0 else f"{h}h {m}m"
                        upcoming.append({"name": f"🇺🇸 {item.get('title', '').replace('**', '')}", "countdown": c})
                except Exception: continue
            return upcoming[:3]
        return get_economic_calendar_fallback()
    except Exception:
        return get_economic_calendar_fallback()

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
            d = e["date"] - now
            days = d.days; h, r = divmod(d.seconds, 3600); m, _ = divmod(r, 60)
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
        d = yf.Ticker(ticker).history(period="5d", interval="1d")
        ph = d["High"].iloc[-2] if len(d) > 1 else d["Close"].iloc[-1]
        pl = d["Low"].iloc[-2] if len(d) > 1 else d["Close"].iloc[-1]
        h5 = yf.Ticker(ticker).history(period="1d", interval="5m")
        if h5.empty: return {"error": "No intraday data available (Market might be closed)"}
        h1 = yf.Ticker(ticker).history(period="1d", interval="1m")
        h1['EMA_9'] = h1['Close'].ewm(span=9, adjust=False).mean()
        h1['EMA_20'] = h1['Close'].ewm(span=20, adjust=False).mean()
        h1['EMA_50'] = h1['Close'].ewm(span=50, adjust=False).mean()
        h1['VWAP'] = (h1['Close'] * h1['Volume']).cumsum() / h1['Volume'].cumsum()
        return {"current_price": h1['Close'].iloc[-1], "hist_1m": h1, "hist_5m": h5, "vwap": h1['VWAP'].iloc[-1], "ema9": h1['EMA_9'].iloc[-1], "ema20": h1['EMA_20'].iloc[-1], "ema50": h1['EMA_50'].iloc[-1], "prev_high": ph, "prev_low": pl, "source": "Yahoo"}
    except Exception as e:
        return {"error": str(e)}

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
        kr10y_data = yf.Ticker("^KR10YT=RR").history(period="1d", interval="1m")
        kr10y = kr10y_data['Close'].iloc[-1] if not kr10y_data.empty else 3.50
    except: kr10y = 3.50
    try:
        jp10y_data = yf.Ticker("^JGB10Y").history(period="1d", interval="1m")
        jp10y = jp10y_data['Close'].iloc[-1] if not jp10y_data.empty else 1.00
    except: jp10y = 1.00
    try:
        jp30y_data = yf.Ticker("^JGB30Y").history(period="1d", interval="1m")
        jp30y = jp30y_data['Close'].iloc[-1] if not jp30y_data.empty else 2.00
    except: jp30y = 2.00
    buyback_status, buyback_icon = TreasuryIntervention.get_buyback_status()
    stress_10y, stress_30y = TreasuryIntervention.calculate_yield_stress(tnx, tyx)
    return {"dxy": dxy, "vix": vix, "real_yield_10y": ry, "yield_10y": tnx, "yield_30y": tyx,
            "kr10y": kr10y, "jp10y": jp10y, "jp30y": jp30y, "buyback_status": buyback_status,
            "buyback_icon": buyback_icon, "yield_stress_10y": stress_10y, "yield_stress_30y": stress_30y,
            "yield_cap_10y": TreasuryIntervention.YIELD_CAP_10Y, "yield_cap_30y": TreasuryIntervention.YIELD_CAP_30Y}

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

def score_dxy_technical(price,ma50,ma200,rsi)->int:
 if price>ma50 and price>ma200: t=9
 elif price>ma200: t=7
 elif price>ma50: t=5
 else: t=3
 rs=8 if rsi<30 else 3 if rsi>70 else 5
 return int((t+rs)/2)

def score_dxy_macro(real_yield,vix)->int:
 y=9 if real_yield>2.5 else 7 if real_yield>2.0 else 5 if real_yield>1.5 else 3
 v=9 if vix>30 else 7 if vix>20 else 5
 return int((y+v)/2)

def get_macro_drivers(asset_key)->List[Dict]:
    d=[]
    try:
        dxy_data = yf.Ticker("DX-Y.NYB").history(period="1d", interval="1m")
        dxy = dxy_data['Close'].iloc[-1] if not dxy_data.empty else 102.0
    except: dxy = 102.0
    try:
        vix_data = yf.Ticker("^VIX").history(period="1d", interval="1m")
        vix = vix_data['Close'].iloc[-1] if not vix_data.empty else 18.0
    except: vix = 18.0
    ry = float(os.getenv("EDGEFINDER_REAL_YIELD_FALLBACK", "1.8"))
    if asset_key in ["SPY","NDX","QQQ","MNQ","MES","NVDA","TSLA","META","AMZN","SMH","PLTR","NOW"]:
        d.append({"category":"Growth & Risk","metric":"DXY","bias":"Bearish" if dxy>104 else "Bullish","actual":f"{dxy:.2f}","forecast":"103.50","surprise":f"{dxy-103.50:.2f}","interpretation":"Strong dollar weighs on exports."})
        d.append({"category":"Growth & Risk","metric":"VIX","bias":"Bearish" if vix>20 else "Bullish","actual":f"{vix:.2f}","forecast":"18.50","surprise":f"{vix-18.50:.2f}","interpretation":"Low VIX = Risk-on."})
        d.append({"category":"Monetary Policy","metric":"10Y Real Yield","bias":"Bearish" if ry>2.0 else "Bullish","actual":f"{ry:.2f}%","forecast":"2.10%","surprise":f"{ry-2.10:.2f}%","interpretation":"High yields steal liquidity."})
    elif asset_key=="MGC" or asset_key=="GOLD":
        d.append({"category":"Macro Drivers","metric":"DXY","bias":"Bullish" if dxy<104 else "Bearish","actual":f"{dxy:.2f}","forecast":"103.50","surprise":f"{dxy-103.50:.2f}","interpretation":"Inverse correlation."})
        d.append({"category":"Macro Drivers","metric":"10Y Real Yield","bias":"Bullish" if ry<1.8 else "Bearish","actual":f"{ry:.2f}%","forecast":"2.00%","surprise":f"{ry-2.00:.2f}%","interpretation":"Gold thrives on falling yields."})
        d.append({"category":"Geopolitics","metric":"VIX","bias":"Bullish" if vix>20 else "Neutral","actual":f"{vix:.2f}","forecast":"18.50","surprise":f"{vix-18.50:.2f}","interpretation":"Safe haven flows."})
    return d

def render_macro_drivers(drivers):
 st.markdown("### 📊 Macro & Fundamental Drivers")
 for driver in drivers:
  bc="background-color: #1a3a2a; color: #4ade80;" if "Bullish" in driver["bias"] else "background-color: #3a1a1a; color: #f87171;"
  with st.container():
   c=st.columns([2,1,1.5,1.5,1.5,2])
   with c[0]: st.caption(driver["category"]); st.markdown(f"**{driver['metric']}**")
   with c[1]: st.markdown(f"<div style='{bc}; text-align: center; padding: 4px 8px; border-radius: 6px; font-weight: bold;'>{driver['bias']}</div>", unsafe_allow_html=True)
   with c[2]: st.markdown(f"<div style='text-align: center;'><b>{driver['actual']}</b></div>", unsafe_allow_html=True)
   with c[3]: st.markdown(f"<div style='text-align: center;'>{driver['forecast']}</div>", unsafe_allow_html=True)
   with c[4]:
    val=float(driver["surprise"].replace("%","")); color="#4ade80" if val>=0 else "#f87171"
    st.markdown(f"<div style='text-align: center; color: {color}; font-weight: bold;'>{driver['surprise']}</div>", unsafe_allow_html=True)
   with c[5]: st.caption(driver["interpretation"]); st.markdown("---")

def calc_rsi(closes)->float:
 if len(closes)<15: return 50.0
 g=[max(closes[i]-closes[i-1],0) for i in range(1,15)]; l=[abs(min(closes[i]-closes[i-1],0)) for i in range(1,15)]
 ag=sum(g)/14; al=sum(l)/14
 if al==0: return 100.0
 return 100-(100/(1+ag/al))

def sma(values,p)->float:
 if len(values)<p: return sum(values)/len(values)
 return sum(values[-p:])/p

def render_dxy_dashboard():
 st.subheader("💵 US Dollar Index (DXY) - Macro & Technical Analysis")
 ticker="DX-Y.NYB"; intraday=get_intraday_data(ticker); macro=get_macro_data()
 try:
     daily=yf.Ticker(ticker).history(period="6mo")
     closes=daily['Close'].tolist(); price=closes[-1]
     rsi=calc_rsi(closes); ma50=sma(closes,50); ma200=sma(closes,200)
     ts=score_dxy_technical(price,ma50,ma200,rsi); ms=score_dxy_macro(macro["real_yield_10y"],macro["vix"])
     os=int((ts*0.5)+(ms*0.5))
     c1,c2,c3,c4=st.columns(4); c1.metric("Current Price",f"{price:.2f}"); c2.metric("DXY Overall Score",f"{os}/10",score_to_bias(os).value); c3.metric("Technical Score",f"{ts}/10"); c4.metric("Macro Score",f"{ms}/10")
 except Exception as e:
     st.warning(f"DXY data unavailable: {e}")
 st.markdown("---"); drivers=get_macro_drivers("DXY"); render_macro_drivers(drivers)

def render_asset(asset_key, auto_save):
    cfg = ASSETS[asset_key]
    intraday = get_intraday_data(cfg["ticker"])
    macro = get_macro_data()
    news = get_news_data(cfg["name"], cfg["news_queries"])
    snapshot = build_swing_snapshot(cfg, macro, news)
    if auto_save: save_snapshot(snapshot)
    try:
        cpi = yf.Ticker("^CPI").history(period="1mo"); cpi_val = cpi['Close'].iloc[-1] if not cpi.empty else 3.2
        nfp = yf.Ticker("^NFP").history(period="1mo"); nfp_val = nfp['Close'].iloc[-1] if not nfp.empty else 150
        unemp = yf.Ticker("UNRATE").history(period="1mo"); unemp_val = unemp['Close'].iloc[-1] if not unemp.empty else 4.0
    except: cpi_val, nfp_val, unemp_val = 3.2, 150, 4.0
    st.markdown(f"""
    <div style='display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2a2a2a; padding-bottom: 15px; margin-bottom: 20px;'>
        <div><h2 style='margin: 0; color: #e8ecf1;'>{snapshot.name}</h2><span style='color: #a0aec0; font-size: 14px;'>{snapshot.symbol}</span></div>
        <div><span style='background-color: {"#1a3a2a" if "Bullish" in snapshot.overall_bias.value else "#3a1a1a" if "Bearish" in snapshot.overall_bias.value else "#2a2a1a"}; color: {"#4ade80" if "Bullish" in snapshot.overall_bias.value else "#f87171" if "Bearish" in snapshot.overall_bias.value else "#facc15"}; padding: 5px 15px; border-radius: 20px; font-weight: bold;'>{snapshot.overall_bias.value}</span></div>
    </div>
    """, unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("### 📊 Asset Scorecard")
        st.metric("Price", f"${snapshot.price:,.2f}")
        st.markdown("#### Breakdown")
        c_s1, c_s2, c_s3 = st.columns(3)
        c_s1.metric("Technical", f"{snapshot.technical_score}/10")
        c_s2.metric("Macro", f"{snapshot.macro_score}/10")
        c_s3.metric("News", f"{snapshot.news_score}/10")
    with c2:
        st.markdown("### 🔍 Macro & Technical Drivers")
        tech_df = pd.DataFrame([{"Indicator": x.name, "Value": round(x.value, 2), "Bias": x.bias.value} for x in snapshot.technical_details])
        st.dataframe(tech_df, width='stretch', hide_index=True, use_container_width=True)
        macro_df = pd.DataFrame([{"Indicator": x.name, "Value": round(x.value, 2), "Bias": x.bias.value} for x in snapshot.macro_details])
        st.dataframe(macro_df, width='stretch', hide_index=True, use_container_width=True)

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
            td = [IndicatorReading("RSI 14", 50.0, 5, score_to_bias(5)), IndicatorReading("Trend vs 50D MA %", 0.0, 5, score_to_bias(5))]
            p = 100.0
        else:
            closes = daily['Close'].tolist(); p = closes[-1]; r = calc_rsi(closes)
            m50 = sma(closes, 50); tp = ((p - m50) / m50) * 100 if m50 else 0
            td = [IndicatorReading("RSI 14", r, score_rsi(r), score_to_bias(score_rsi(r))), IndicatorReading("Trend vs 50D MA %", tp, score_trend_pct(tp), score_to_bias(score_trend_pct(tp)))]
    except Exception:
        td = [IndicatorReading("RSI 14", 50.0, 5, score_to_bias(5)), IndicatorReading("Trend vs 50D MA %", 0.0, 5, score_to_bias(5))]
        p = 100.0
    inv=config.get("inverse_dxy",False); safe=config.get("safe_haven",False)
    md=[IndicatorReading("DXY",macro["dxy"],score_dxy(macro["dxy"],inv),score_to_bias(score_dxy(macro["dxy"],inv))),IndicatorReading("VIX",macro["vix"],score_vix(macro["vix"],safe),score_to_bias(score_vix(macro["vix"],safe))),IndicatorReading("Real Yield",macro["real_yield_10y"],score_real_yield(macro["real_yield_10y"],inv),score_to_bias(score_real_yield(macro["real_yield_10y"],inv)))]
    ms=sum([x.score for x in md])//3; ns=score_news(news.get("sentiment",0.0)); o=int(round((td[0].score+td[1].score)//2*0.45+ms*0.30+ns*0.25))
    return AssetSnapshot(symbol=config["symbol"],name=config["name"],price=p,technical_score=(td[0].score+td[1].score)//2,macro_score=ms,news_score=ns,overall_score=o,overall_bias=score_to_bias(o),technical_details=td,macro_details=md,news_details=[IndicatorReading("News Sentiment",news.get("sentiment",0),ns,score_to_bias(ns))])

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

def render_smc_cheat_sheet():
    st.subheader("🎯 Smart Money Concepts (SMC) Cheat Sheet")
    st.markdown("""
    <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border: 2px solid #f87171; margin-bottom: 20px;'>
        <h4 style='color: #f87171; margin: 0;'>⚠️ CRITICAL: Weak High = SELL-OFF ZONE</h4>
        <p style='color: #e8ecf1; font-size: 14px;'><b>Weak Highs are NOT breakout zones!</b> They are <b>DISTRIBUTION ZONES</b>.</p>
    </div>
    """, unsafe_allow_html=True)
    decision_data = {
        "SMC Signal": ["🟡 Weak High", "🔴 Strong High", "🟢 Strong Low", "🔵 Weak Low"],
        "Best Action": ["❌ SELL on rejection", "❌ SHORT on rejection", "✅ BUY on bounce", "✅ BUY on bounce"]
    }
    st.dataframe(pd.DataFrame(decision_data), width='stretch', hide_index=True, use_container_width=True)

def run_sniper_entry_theory():
    st.subheader("🎯 Sniper Entry Theory - Visual Guide")
    st.info("💡 15-point buffer filters 70-80% of fakeouts. Never enter within 5 points of a level.")

def run_indices_bond_tracker():
    st.subheader("📊 Indices & Bond Tracker")
    col_v1, col_v2, col_v3, col_v4 = st.columns(4)
    with col_v1: st.markdown("<div style='background-color: #163a1a; padding: 12px; border-radius: 8px; text-align: center;'><h3 style='color: #4ade80;'>VIX < 15</h3><p style='color: #4ade80;'><b>🟢 ZERO FEAR</b></p></div>", unsafe_allow_html=True)
    with col_v2: st.markdown("<div style='background-color: #1a2a3a; padding: 12px; border-radius: 8px; text-align: center;'><h3 style='color: #60a5fa;'>15-20</h3><p style='color: #60a5fa;'><b>⚖️ NORMAL</b></p></div>", unsafe_allow_html=True)
    with col_v3: st.markdown("<div style='background-color: #3a2a1a; padding: 12px; border-radius: 8px; text-align: center;'><h3 style='color: #facc15;'>20-30</h3><p style='color: #facc15;'><b>🟡 HIGH FEAR</b></p></div>", unsafe_allow_html=True)
    with col_v4: st.markdown("<div style='background-color: #3a1a1a; padding: 12px; border-radius: 8px; text-align: center;'><h3 style='color: #f87171;'>VIX > 30</h3><p style='color: #f87171;'><b>🔴 EXTREME</b></p></div>", unsafe_allow_html=True)

def run_vwap_ema_strategy():
    st.subheader("📊 VWAP & 9 EMA Strategy")
    st.success("✅ LONG: Price ABOVE 9 EMA + ABOVE VWAP + Higher highs + DXY weak")

def run_ny_afternoon_sniper():
    st.subheader("🇺🇸 NY Afternoon Sniper (3:30-4:30 PM UK)")
    st.info("Better price action after initial NY chaos settles.")

def run_smart_money_levels():
    st.subheader("🎯 Smart Money Levels")

def classify_market_conditions(ticker="MNQ=F"):
    try:
        profile = ASSET_VOLATILITY_PROFILES.get(ticker, ASSET_VOLATILITY_PROFILES["MNQ=F"])
        trending_min = profile["trending_min"]; ranging_max = profile["ranging_max"]
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
        if data.empty: return {"classification": "UNKNOWN", "reason": "No data available"}
        # FIX: use UTC date to avoid timezone mismatch
        today_utc = datetime.now(timezone.utc).date()
        data_today = data[data.index.date == today_utc]
        if data_today.empty: data_today = data.tail(100)
        high = data_today['High']; low = data_today['Low']; close = data_today['Close']
        tr1 = high - low; tr2 = abs(high - close.shift(1)); tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        up_move = high - high.shift(1); down_move = low.shift(1) - low
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        atr = tr.rolling(14).mean().iloc[-1] if len(tr) >= 14 else tr.mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean().iloc[-1] / atr) if atr > 0 else 0
        minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean().iloc[-1] / atr) if atr > 0 else 0
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        adx = dx
        vwap = (data_today['Close'] * data_today['Volume']).cumsum() / data_today['Volume'].cumsum()
        vwap_slope = (vwap.iloc[-1] - vwap.iloc[-5]) / vwap.iloc[-5] * 100 if len(vwap) >= 5 else 0
        ema9 = data_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        ema20 = data_today['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = data_today['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        current_price = data_today['Close'].iloc[-1]
        ema_separation = abs(ema9 - ema20) / current_price * 100
        ny_data = data_today.between_time('08:00', '09:29')
        if ny_data.empty or len(ny_data) < 5:
            ny_data = data_today.between_time('07:30', '09:29')
        if not ny_data.empty: ny_range = ny_data['High'].max() - ny_data['Low'].min()
        else: ny_range = 0
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
        ema200 = data_today['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
        if abs(current_price - ema200) / current_price > 0.005: trending_signals += 1
        else: ranging_signals += 1
        if trending_signals >= 3: classification = "TRENDING"; strategy = "Trend-Fade Hybrid"; confidence = min(100, 50 + trending_signals * 10)
        elif ranging_signals >= 3: classification = "RANGING"; strategy = "High Yield Protocol"; confidence = min(100, 50 + ranging_signals * 10)
        else: classification = "UNCLEAR"; strategy = "SIT OUT"; confidence = 50
        return {"classification": classification, "strategy": strategy, "confidence": confidence, "asset_name": profile["name"], "typical_range": profile["typical_range"], "adx": round(adx, 1), "vwap_slope": round(vwap_slope, 3), "ema_separation": round(ema_separation, 3), "ny_range": round(ny_range, 1), "trend_direction": trend_direction, "current_price": current_price, "ema9": ema9, "ema20": ema20, "ema50": ema50, "ema200": ema200, "vwap": vwap.iloc[-1], "trending_signals": trending_signals, "ranging_signals": ranging_signals}
    except Exception as e:
        return {"classification": "UNKNOWN", "reason": str(e)}

# ============ PART 2 of 2 ============
def run_high_yield_protocol():
    st.subheader("⚡ High Yield Protocol (4.5%+ Yields)")
    st.caption("Contrarian strategy — fades extremes and trades ranges. US Session only.")
    macro = get_macro_data()
    tnx = macro['yield_10y']; vix = macro['vix']; dxy = macro['dxy']
    if tnx < 4.5:
        st.success(f"🟢 Yields below 4.5% ({tnx:.2f}%). Use normal VWAP & EMA strategy.")
        st.info("👀 Preview: On high-yield days this page offers Fade Extremes + Range Trading on MNQ, M2K, US30, MES, MGC.")
        return
    st.warning(f"🔴 HIGH YIELD MODE ACTIVE (US10Y: {tnx:.2f}%)")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1: st.metric("US10Y Yield", f"{tnx:.2f}%", delta="HIGH", delta_color="inverse")
    with col_m2: st.metric("VIX", f"{vix:.2f}")
    with col_m3: st.metric("DXY", f"{dxy:.2f}")
    st.markdown("---")
    asset_choice = st.selectbox("Select Asset", ["MNQ (Micro Nasdaq)", "M2K (Micro Russell 2000)", "US30 (Micro Dow)", "MGC (Micro Gold)", "MES (Micro S&P 500)"], index=0, key="high_yield_asset_select")
    asset_map = {"MNQ (Micro Nasdaq)": ("MNQ=F","MNQ"), "M2K (Micro Russell 2000)": ("M2K=F","M2K"), "US30 (Micro Dow)": ("YM=F","US30"), "MGC (Micro Gold)": ("MGC=F","MGC"), "MES (Micro S&P 500)": ("MES=F","MES")}
    ticker, asset_key = asset_map[asset_choice]
    asset_name = asset_choice.split(" (")[0]
    with st.spinner(f"Fetching NY session data for {asset_name}..."):
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
    if data.empty: st.warning(f"No data for {asset_name}."); return
    today_utc = datetime.now(timezone.utc).date()
    data_today = data[data.index.date == today_utc]
    if data_today.empty: data_today = data.tail(100)
    ny_data = data_today.between_time('08:00', '09:29')
    if ny_data.empty or len(ny_data) < 5:
        ny_data = data_today.between_time('07:30', '09:29')
    if ny_data.empty: st.warning("NY Pre-Market data not available."); return
    ny_high = ny_data['High'].max(); ny_low = ny_data['Low'].min()
    ny_range = ny_high - ny_low; current_price = data_today['Close'].iloc[-1]
    min_range = MIN_NY_RANGE.get(asset_key, 5)
    if ny_range < min_range:
        st.error(f"🚫 NY Range too small for {asset_name} ({ny_range:.1f} pts < min {min_range} pts). Signals unreliable — WAIT.")
        return
    st.markdown(f"### 📊 {asset_name} Key NY Levels")
    col_l1, col_l2, col_l3, col_l4 = st.columns(4)
    with col_l1: st.metric("NY High", f"{ny_high:.2f}")
    with col_l2: st.metric("NY Low", f"{ny_low:.2f}")
    with col_l3: st.metric("Range", f"{ny_range:.2f} pts")
    with col_l4: st.metric("Price", f"{current_price:.2f}")
    range_top = ny_high - (ny_range * 0.15); range_bottom = ny_low + (ny_range * 0.15)
    near_high = current_price > (ny_high - ny_range * 0.1)
    near_low = current_price < (ny_low + ny_range * 0.1)
    above_range_top = current_price > range_top; below_range_bottom = current_price < range_bottom
    if near_high and not near_low: zone = "🔴 EXTREME HIGH"; zone_color = "#3a1a1a"; valid_signal = "SHORT"
    elif near_low and not near_high: zone = "🟢 EXTREME LOW"; zone_color = "#1a3a2a"; valid_signal = "LONG"
    elif above_range_top and not near_high: zone = "🔴 RANGE TOP"; zone_color = "#3a1a1a"; valid_signal = "SHORT"
    elif below_range_bottom and not near_low: zone = "🟢 RANGE BOTTOM"; zone_color = "#1a3a2a"; valid_signal = "LONG"
    else: zone = "⚪ MIDDLE"; zone_color = "#1c2129"; valid_signal = "NONE"
    st.markdown(f"""<div style='background-color: {zone_color}; padding: 15px; border-radius: 8px; border: 1px solid #facc15;'><h4 style='color: #facc15;'>📍 {zone}</h4><ul style='color: #e8ecf1;'><li><b>Price:</b> {current_price:.2f}</li><li><b>Valid:</b> {valid_signal}</li></ul></div>""", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### 📉 Signal 1: Fade Extremes")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown("#### 🟢 Fade High (SHORT)")
        if near_high and not near_low:
            entry = current_price
            stop = safe_stop(entry, "SHORT", ny_high, asset_key)
            target = entry - (ny_range * 0.5)
            risk = stop - entry
            reward = entry - target
            rr = clamp_rr(reward / risk) if risk > 0.01 else 0.0
            dollar_risk = risk * TICK_VALUES.get(asset_key, 1.0)
            st.error("✅ SHORT SIGNAL")
            st.markdown(f"<div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'><b>Entry:</b> {entry:.2f}<br><b>Stop:</b> {stop:.2f} <small>(above entry ✅)</small><br><b>Target:</b> {target:.2f}<br><b>Risk:</b> {risk:.2f} pts (${dollar_risk:.2f}/contract)<br><b>Reward:</b> {reward:.2f} pts<br><b>R:R:</b> 1:{rr:.1f}</div>", unsafe_allow_html=True)
        else:
            st.info(f"⏳ Need price within 10% of NY High ({ny_high:.2f})")
    with col_s2:
        st.markdown("#### 🔴 Fade Low (LONG)")
        if near_low and not near_high:
            entry = current_price
            stop = safe_stop(entry, "LONG", ny_low, asset_key)
            target = entry + (ny_range * 0.5)
            risk = entry - stop
            reward = target - entry
            rr = clamp_rr(reward / risk) if risk > 0.01 else 0.0
            dollar_risk = risk * TICK_VALUES.get(asset_key, 1.0)
            st.success("✅ LONG SIGNAL")
            st.markdown(f"<div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'><b>Entry:</b> {entry:.2f}<br><b>Stop:</b> {stop:.2f} <small>(below entry ✅)</small><br><b>Target:</b> {target:.2f}<br><b>Risk:</b> {risk:.2f} pts (${dollar_risk:.2f}/contract)<br><b>Reward:</b> {reward:.2f} pts<br><b>R:R:</b> 1:{rr:.1f}</div>", unsafe_allow_html=True)
        else:
            st.info(f"⏳ Need price within 10% of NY Low ({ny_low:.2f})")
    st.markdown("---")
    st.markdown("### 📊 Signal 2: Range Trading")
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.markdown("#### 📈 Range Top (SHORT)")
        if above_range_top and not near_high:
            entry = current_price
            stop = safe_stop(entry, "SHORT", ny_high, asset_key)
            target = ny_low + (ny_range * 0.3)
            risk = stop - entry
            reward = entry - target
            rr = clamp_rr(reward / risk) if risk > 0.01 else 0.0
            st.error("✅ RANGE SHORT")
            st.markdown(f"<div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px;'><b>Entry:</b> {entry:.2f}<br><b>Stop:</b> {stop:.2f}<br><b>Target:</b> {target:.2f}<br><b>Risk:</b> {risk:.2f} pts<br><b>R:R:</b> 1:{rr:.1f}</div>", unsafe_allow_html=True)
        else: st.info("⏳ Waiting for range edge")
    with col_r2:
        st.markdown("#### 📉 Range Bottom (LONG)")
        if below_range_bottom and not near_low:
            entry = current_price
            stop = safe_stop(entry, "LONG", ny_low, asset_key)
            target = ny_high - (ny_range * 0.3)
            risk = entry - stop
            reward = target - entry
            rr = clamp_rr(reward / risk) if risk > 0.01 else 0.0
            st.success("✅ RANGE LONG")
            st.markdown(f"<div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px;'><b>Entry:</b> {entry:.2f}<br><b>Stop:</b> {stop:.2f}<br><b>Target:</b> {target:.2f}<br><b>Risk:</b> {risk:.2f} pts<br><b>R:R:</b> 1:{rr:.1f}</div>", unsafe_allow_html=True)
        else: st.info("⏳ Waiting for range edge")
    st.markdown("---")
    st.warning("⚠️ CONTRARIAN strategy — 25% POSITION SIZE — EXIT BY 4:30 PM UK")

def run_trend_fade_hybrid():
    st.subheader("📈 Trend-Fade Hybrid")
    st.caption("Fade pullbacks WITHIN the trend. Works when markets are trending. Best: 3:00-4:00 PM UK")
    asset_choice = st.selectbox("Select Asset", ["MNQ (Micro Nasdaq)", "M2K (Micro Russell 2000)", "US30 (Micro Dow)", "MGC (Micro Gold)", "MES (Micro S&P 500)"], index=0, key="tfh_asset_select")
    asset_map = {"MNQ (Micro Nasdaq)": ("MNQ=F","MNQ"), "M2K (Micro Russell 2000)": ("M2K=F","M2K"), "US30 (Micro Dow)": ("YM=F","US30"), "MGC (Micro Gold)": ("MGC=F","MGC"), "MES (Micro S&P 500)": ("MES=F","MES")}
    ticker, asset_key = asset_map[asset_choice]
    asset_name = asset_choice.split(" (")[0]
    market = classify_market_conditions(ticker)
    if market['classification'] == "TRENDING":
        banner_color = "#1a3a2a"; border_color = "#4ade80"; icon = "🟢"; title = "TREND MODE ACTIVE"
        subtitle = "Fade pullbacks in the direction of the trend"
    elif market['classification'] == "RANGING":
        banner_color = "#3a1a1a"; border_color = "#f87171"; icon = "🔴"; title = "RANGE MODE ACTIVE"
        subtitle = "DO NOT use Trend-Fade — switch to High Yield Protocol"
    else:
        banner_color = "#2a2a1a"; border_color = "#facc15"; icon = "🟡"; title = "UNCLEAR MARKET"
        subtitle = "Sit out — no clear trend or range"
    st.markdown(f"""<div style='background-color: {banner_color}; padding: 20px; border-radius: 10px; border: 2px solid {border_color}; margin-bottom: 20px;'><h2 style='color: {border_color}; margin: 0;'>{icon} {title} — {asset_name}</h2><p style='color: #e8ecf1;'>{subtitle}</p><p style='color: #a0aec0; font-size: 13px;'>Confidence: {market.get('confidence', 0)}%</p></div>""", unsafe_allow_html=True)
    if market['classification'] != "TRENDING":
        st.warning(f"⚠️ TREND-FADE NOT RECOMMENDED for {asset_name}.")
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        with col_c1: st.metric("ADX", market.get('adx', 0))
        with col_c2: st.metric("VWAP Slope", f"{market.get('vwap_slope', 0):.3f}%")
        with col_c3: st.metric("EMA Sep", f"{market.get('ema_separation', 0):.3f}%")
        with col_c4: st.metric("NY Range", f"{market.get('ny_range', 0):.1f}")
        return
    now_utc = datetime.now(timezone.utc); uk_time = now_utc.astimezone(ZoneInfo("Europe/London"))
    current_hour = uk_time.hour; current_minute = uk_time.minute
    in_primary_window = (current_hour == 15) or (current_hour == 16 and current_minute <= 0)
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1: st.metric("UK Time", uk_time.strftime("%H:%M"))
    with col_t2:
        if in_primary_window: st.success("✅ PRIMARY WINDOW")
        else: st.warning("⏳ Outside optimal window")
    with col_t3: st.metric("Trend", market['trend_direction'])
    st.markdown("---")
    with st.spinner(f"Loading {asset_name} data..."):
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
        if data.empty: st.warning(f"No data for {asset_name}"); return
        today_utc = datetime.now(timezone.utc).date()
        data_today = data[data.index.date == today_utc]
        if data_today.empty: data_today = data.tail(100)
        current_price = data_today['Close'].iloc[-1]
        vwap = (data_today['Close'] * data_today['Volume']).cumsum() / data_today['Volume'].cumsum()
        current_vwap = vwap.iloc[-1]
        ema9 = data_today['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        ema20 = data_today['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ny_data = data_today.between_time('08:00', '09:29')
        if ny_data.empty or len(ny_data) < 5:
            ny_data = data_today.between_time('07:30', '09:29')
        ny_range = (ny_data['High'].max() - ny_data['Low'].min()) if not ny_data.empty else 0
        highs = data_today['High'].values; lows = data_today['Low'].values
        swing_highs = []; swing_lows = []
        for i in range(5, len(data_today) - 5):
            if highs[i] > max(highs[max(0,i-5):i]) and highs[i] > max(highs[i+1:min(len(highs),i+6)]): swing_highs.append(highs[i])
            if lows[i] < min(lows[max(0,i-5):i]) and lows[i] < min(lows[i+1:min(len(lows),i+6)]): swing_lows.append(lows[i])
    st.markdown("### 📊 Key Levels")
    col_l1, col_l2, col_l3, col_l4 = st.columns(4)
    with col_l1: st.metric("Price", f"{current_price:.2f}")
    with col_l2: st.metric("VWAP", f"{current_vwap:.2f}", delta=f"{current_price - current_vwap:+.2f}")
    with col_l3: st.metric("9 EMA", f"{ema9:.2f}", delta=f"{current_price - ema9:+.2f}")
    with col_l4: st.metric("20 EMA", f"{ema20:.2f}", delta=f"{current_price - ema20:+.2f}")
    st.markdown("---")
    st.markdown("### 🎯 Trend Analysis")
    fallback_dist = ny_range if ny_range > 0 else (20 if asset_key == "MNQ" else 10 if asset_key == "M2K" else 100 if asset_key == "US30" else 8)
    if market['trend_direction'] == "UP":
        st.success(f"🟢 UPTREND on {asset_name} — LONG pullback entries")
        trade_direction = "LONG"
        entry_zone_low = min(ema9, current_vwap); entry_zone_high = max(ema9, current_vwap)
        target = max(swing_highs[-3:]) if len(swing_highs) >= 3 else current_price + fallback_dist
        raw_stop = min(swing_lows[-2:]) if len(swing_lows) >= 2 else current_price - fallback_dist
        stop = min(raw_stop, current_price - STOP_BUFFERS.get(asset_key, 5))
    elif market['trend_direction'] == "DOWN":
        st.error(f"🔴 DOWNTREND on {asset_name} — SHORT pullback entries")
        trade_direction = "SHORT"
        entry_zone_low = min(ema9, current_vwap); entry_zone_high = max(ema9, current_vwap)
        target = min(swing_lows[-3:]) if len(swing_lows) >= 3 else current_price - fallback_dist
        raw_stop = max(swing_highs[-2:]) if len(swing_highs) >= 2 else current_price + fallback_dist
        stop = max(raw_stop, current_price + STOP_BUFFERS.get(asset_key, 5))
    else:
        st.warning("⚪ MIXED SIGNALS")
        trade_direction = "WAIT"; entry_zone_low = entry_zone_high = target = stop = 0
    if trade_direction != "WAIT":
        st.markdown("### 🎯 Trade Setup")
        if trade_direction == "LONG":
            risk = current_price - stop; reward = target - current_price
            rr = clamp_rr(reward / risk) if risk > 0.01 else 0.0
            st.markdown(f"""<div style='background-color: #1a3a2a; padding: 20px; border-radius: 10px; border-left: 4px solid #4ade80;'><h4 style='color: #4ade80;'>📈 LONG — {asset_name}</h4><p style='color: #e8ecf1;'><b>Entry Zone:</b> {entry_zone_low:.2f} — {entry_zone_high:.2f}<br><b>Stop:</b> {stop:.2f} <small>(below entry ✅)</small><br><b>Target:</b> {target:.2f}<br><b>Risk:</b> {risk:.2f} pts<br><b>Reward:</b> {reward:.2f} pts<br><b>R:R:</b> 1:{rr:.1f}</p></div>""", unsafe_allow_html=True)
        else:
            risk = stop - current_price; reward = current_price - target
            rr = clamp_rr(reward / risk) if risk > 0.01 else 0.0
            st.markdown(f"""<div style='background-color: #3a1a1a; padding: 20px; border-radius: 10px; border-left: 4px solid #f87171;'><h4 style='color: #f87171;'>📉 SHORT — {asset_name}</h4><p style='color: #e8ecf1;'><b>Entry Zone:</b> {entry_zone_low:.2f} — {entry_zone_high:.2f}<br><b>Stop:</b> {stop:.2f} <small>(above entry ✅)</small><br><b>Target:</b> {target:.2f}<br><b>Risk:</b> {risk:.2f} pts<br><b>Reward:</b> {reward:.2f} pts<br><b>R:R:</b> 1:{rr:.1f}</p></div>""", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### ✅ Three-Confirmation Rule")
    macro = get_macro_data()
    tnx = macro.get('yield_10y', 4.20); dxy = macro.get('dxy', 102.0)
    confirmations = []
    if trade_direction == "LONG": macro_ok = dxy < 103 and tnx < 4.5
    else: macro_ok = dxy > 103 or tnx > 4.5
    confirmations.append({"name": "Macro", "passed": macro_ok, "reason": f"DXY {dxy:.2f}, 10Y {tnx:.2f}%"})
    if trade_direction == "LONG": vwap_ok = current_price > current_vwap
    else: vwap_ok = current_price < current_vwap
    confirmations.append({"name": "VWAP", "passed": vwap_ok, "reason": f"Price vs VWAP"})
    if trade_direction == "LONG": ema_ok = current_price > ema9
    else: ema_ok = current_price < ema9
    confirmations.append({"name": "9 EMA", "passed": ema_ok, "reason": f"Price vs 9 EMA"})
    for c in confirmations:
        if c['passed']: st.success(f"✅ **{c['name']}** — {c['reason']}")
        else: st.error(f"❌ **{c['name']}** — {c['reason']}")
    if all(c['passed'] for c in confirmations): st.success(f"🟢 ALL PASSED — {asset_name} valid!")
    else: st.error(f"🔴 NOT ALL PASSED — DO NOT TRADE")
    st.markdown("### 📌 Asset-Specific Notes")
    if "M2K" in asset_name: st.info("**🏭 M2K:** Small caps rate-sensitive. Typical range 15-30 pts. Avoid if 10Y > 4.5%.")
    elif "US30" in asset_name: st.info("**🏛️ US30:** Trends beautifully. 5-8× MNQ range. Typical 150-350 pts. Buffer = 20 pts.")
    elif "MGC" in asset_name: st.warning("**🥇 MGC:** HATES rising yields. Hard stop if 10Y > 4.3%. Typical 8-20 pts.")
    elif "MES" in asset_name: st.info("**📈 MES:** Broadest index. Typical 20-40 pts.")
    elif "MNQ" in asset_name: st.info("**📈 MNQ:** Most volatile. Typical 40-80 pts.")

def run_strategy_selector():
    st.subheader("🎯 Strategy Selector & Decision Engine")
    st.caption("Automatically recommends the best strategy based on current market conditions")
    macro = get_macro_data()
    tnx = macro.get('yield_10y', 4.20); vix = macro.get('vix', 18.0); dxy = macro.get('dxy', 102.0)
    analyze_asset = st.selectbox("🎯 Analyze which market?", ["MNQ=F", "M2K=F", "YM=F", "MES=F", "MGC=F"], format_func=lambda x: ASSET_VOLATILITY_PROFILES.get(x, {}).get("name", x), index=0, key="strategy_selector_asset")
    market = classify_market_conditions(analyze_asset)
    market_class = market.get('classification', 'UNKNOWN')
    trend_direction = market.get('trend_direction', 'MIXED')
    st.info(f"📊 Analyzing **{market.get('asset_name', analyze_asset)}** — Typical NY Range: {market.get('typical_range', 'N/A')} pts")
    is_high_yield = tnx > 4.5; is_elevated_yield = 4.3 < tnx <= 4.5; is_normal_yield = tnx <= 4.3
    is_high_volatility = vix > 30
    now_utc = datetime.now(timezone.utc); uk_time = now_utc.astimezone(ZoneInfo("Europe/London"))
    in_primary_window = (uk_time.hour == 15) or (uk_time.hour == 16 and uk_time.minute <= 30)
    if is_high_volatility: recommended_strategy = "⛔ NO TRADE - SIT OUT"; position_size = "0%"
    elif is_high_yield and market_class == "RANGING": recommended_strategy = "⚡ High Yield Protocol"; position_size = "25%"
    elif is_high_yield and market_class == "TRENDING": recommended_strategy = "⛔ NO TRADE - SIT OUT"; position_size = "0%"
    elif is_normal_yield and market_class == "TRENDING": recommended_strategy = "📈 Trend-Fade Hybrid"; position_size = "50-75%"
    elif is_normal_yield and market_class == "RANGING": recommended_strategy = "⚡ High Yield Protocol (Low Yield)"; position_size = "50%"
    elif is_elevated_yield:
        recommended_strategy = "📈 Trend-Fade Hybrid (Reduced)" if market_class == "TRENDING" else "⚡ High Yield Protocol (Reduced)"
        position_size = "50%"
    else: recommended_strategy = "⛔ NO TRADE - SIT OUT"; position_size = "0%"
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### 📊 Current Market Conditions")
        yield_color = "#f87171" if is_high_yield else "#facc15" if is_elevated_yield else "#4ade80"
        st.markdown(f"<div style='background-color: #1c2129; padding: 12px; border-radius: 8px; margin-bottom: 8px;'><b>US10Y:</b> <span style='color: {yield_color};'>{tnx:.2f}%</span></div>", unsafe_allow_html=True)
        vix_color = "#4ade80" if vix < 25 else "#facc15" if vix < 30 else "#f87171"
        st.markdown(f"<div style='background-color: #1c2129; padding: 12px; border-radius: 8px; margin-bottom: 8px;'><b>VIX:</b> <span style='color: {vix_color};'>{vix:.2f}</span></div>", unsafe_allow_html=True)
        market_color = "#4ade80" if market_class == "TRENDING" else "#facc15" if market_class == "RANGING" else "#f87171"
        st.markdown(f"<div style='background-color: #1c2129; padding: 12px; border-radius: 8px; margin-bottom: 8px;'><b>Market:</b> <span style='color: {market_color};'>{market_class}</span><br><small>ADX: {market.get('adx', 0):.1f} | NY Range: {market.get('ny_range', 0):.1f}</small></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='background-color: #1c2129; padding: 12px; border-radius: 8px;'><b>Trend:</b> {trend_direction} | <b>DXY:</b> {dxy:.2f}</div>", unsafe_allow_html=True)
    with col2:
        st.markdown("### 🎯 Recommended Strategy")
        if "NO TRADE" in recommended_strategy:
            st.markdown(f"<div style='background-color: #3a1a1a; padding: 20px; border-radius: 8px; border: 3px solid #f87171; text-align: center;'><h2 style='color: #f87171;'>{recommended_strategy}</h2><p style='color: #a0aec0;'>Position: {position_size}</p></div>", unsafe_allow_html=True)
        elif "Trend-Fade" in recommended_strategy:
            st.markdown(f"<div style='background-color: #1a3a2a; padding: 20px; border-radius: 8px; border: 3px solid #4ade80; text-align: center;'><h2 style='color: #4ade80;'>{recommended_strategy}</h2><p style='color: #a0aec0;'>Position: {position_size}</p></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='background-color: #3a2a1a; padding: 20px; border-radius: 8px; border: 3px solid #facc15; text-align: center;'><h2 style='color: #facc15;'>{recommended_strategy}</h2><p style='color: #a0aec0;'>Position: {position_size}</p></div>", unsafe_allow_html=True)
    st.markdown("---")
    st.metric("Current UK Time", uk_time.strftime("%H:%M"), delta="✅ Primary Window" if in_primary_window else "⏳ Outside Window")

DB_JOURNAL_PATH = Path("trading_journal.db")
def init_journal_db():
    conn = sqlite3.connect(DB_JOURNAL_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT NOT NULL, symbol TEXT NOT NULL, direction TEXT NOT NULL, entry_price REAL NOT NULL, stop_loss REAL NOT NULL, take_profit REAL NOT NULL, exit_price REAL, pnl REAL, outcome TEXT, macro_snapshot TEXT, notes TEXT)""")
    conn.commit(); conn.close()

def run_journal_tab():
    st.subheader("📝 Private Trading Journal")
    with st.expander("➕ Log New Trade Entry", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            j_symbol = st.selectbox("Symbol", ["MNQ", "M2K", "US30", "MGC", "MES", "NVDA", "SMH"])
            j_direction = st.selectbox("Direction", ["Long (Buy)", "Short (Sell)"])
        with c2:
            step = 0.10 if j_symbol == "M2K" else 0.25
            j_entry = st.number_input("Entry Price", step=step)
            j_stop = st.number_input("Stop Loss", step=step)
        with c3:
            j_target = st.number_input("Take Profit", step=step)
        j_notes = st.text_area("Why did you take this trade?", height=100)
        if st.button("📌 Log This Trade", type="primary"): st.success("Trade logged!")

def run_treasury_dashboard():
    st.subheader("🏛️ Treasury Intervention Tracker")
    status, icon = TreasuryIntervention.get_buyback_status()
    col_status1, col_status2, col_status3 = st.columns(3)
    with col_status1: st.metric("Buyback Program", f"{icon} {status}")
    with col_status2: st.metric("10Y Cap", f"{TreasuryIntervention.YIELD_CAP_10Y:.2f}%")
    with col_status3: st.metric("30Y Cap", f"{TreasuryIntervention.YIELD_CAP_30Y:.2f}%")

def run_asia_sniper():
    st.subheader("🌏 Asia Session Sniper Triggers")
    st.info("Loading Asian market data...")

def run_level_marker():
    st.subheader("🎯 Global Session Sniper Triggers")
    st.info("Loading session data...")

def run_m2k_shortcut():
    st.subheader("📉 M2K (Micro Russell 2000) — Direct Analysis")
    st.caption("Small cap focus — High Yield + Trend-Fade recommendations")
    market = classify_market_conditions("M2K=F")
    st.markdown(f"**Market Classification:** {market.get('classification', 'UNKNOWN')}")
    st.markdown(f"**Typical NY Range:** {market.get('typical_range', 'N/A')} pts")
    st.markdown(f"**Confidence:** {market.get('confidence', 0)}%")
    st.markdown(f"**Stop Buffer:** {STOP_BUFFERS.get('M2K', 5)} pts")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⚡ Launch High Yield Protocol (M2K)", key="m2k_hy_btn", use_container_width=True):
            st.session_state['nav_redirect'] = "⚡ High Yield Protocol"
            st.rerun()
    with col2:
        if st.button("📈 Launch Trend-Fade Hybrid (M2K)", key="m2k_tfh_btn", use_container_width=True):
            st.session_state['nav_redirect'] = "📈 Trend-Fade Hybrid"
            st.rerun()
    st.markdown("---")
    st.info("**🏭 M2K Notes:** Rate-sensitive. Tighter ranges. Best VIX 18-25. Typical NY Range: **15-30 pts**. Buffer: **3 pts**.")

def run_us30_shortcut():
    st.subheader("🏛️ US30 (Micro Dow) — Direct Analysis")
    st.caption("Blue chip focus — High Yield + Trend-Fade recommendations")
    market = classify_market_conditions("YM=F")
    st.markdown(f"**Market Classification:** {market.get('classification', 'UNKNOWN')}")
    st.markdown(f"**Typical NY Range:** {market.get('typical_range', 'N/A')} pts")
    st.markdown(f"**Confidence:** {market.get('confidence', 0)}%")
    st.markdown(f"**Stop Buffer:** {STOP_BUFFERS.get('US30', 20)} pts")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⚡ Launch High Yield Protocol (US30)", key="us30_hy_btn", use_container_width=True):
            st.session_state['nav_redirect'] = "⚡ High Yield Protocol"
            st.rerun()
    with col2:
        if st.button("📈 Launch Trend-Fade Hybrid (US30)", key="us30_tfh_btn", use_container_width=True):
            st.session_state['nav_redirect'] = "📈 Trend-Fade Hybrid"
            st.rerun()
    st.markdown("---")
    st.info("**🏛️ US30 Notes:** Trends beautifully. Ranges 5-8× MNQ. Typical NY Range: **150-350 pts**. Buffer: **20 pts**. Ticker: `YM=F`.")

# ============ MAIN APP ============
def run_app():
    load_dotenv(); init_db(); init_journal_db()
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
        "🏠 Dashboard", "📈 Charts", "📅 Regime Report", "🤖 AI Bubble Watch",
        "💵 DXY Dashboard", "📊 Indices & Bond Tracker", "🎯 Market Levels", "📝 Journal",
        "🌏 Asia Sniper", "🇺🇸 NY Afternoon", "📈 VWAP & 9 EMA", "⚡ High Yield Protocol",
        "📈 Trend-Fade Hybrid", "📉 M2K (Russell 2000)", "🏛️ US30 (Dow Jones)",
        "🎯 Smart Money Levels", "📋 SMC Cheat Sheet", "🏛️ Treasury Tracker",
        "🎯 Strategy Selector", "🎯 Sniper Entry Theory",
    ]
    if 'nav_redirect' not in st.session_state: st.session_state['nav_redirect'] = None
    if 'nav_selection' not in st.session_state: st.session_state['nav_selection'] = DEFAULT_NAV
    if st.session_state['nav_redirect'] is not None:
        target = st.session_state['nav_redirect']
        if target in NAV_OPTIONS: st.session_state['nav_selection'] = target
        st.session_state['nav_redirect'] = None
    if st.session_state['nav_selection'] not in NAV_OPTIONS:
        st.session_state['nav_selection'] = DEFAULT_NAV
    with st.sidebar:
        st.markdown("""<div class="sidebar-logo"><h1>⚡ TradeTerminal</h1><p>Pro Market Terminal</p></div>""", unsafe_allow_html=True)
        nav_section = st.radio("Navigation", NAV_OPTIONS, index=NAV_OPTIONS.index(st.session_state['nav_selection']), key="nav_selection", label_visibility="collapsed")
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        if st.button("🔄 Refresh Data", use_container_width=True): st.rerun()
        auto_save = st.checkbox("💾 Auto-Save Snapshots", value=True)
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        st.markdown("### 📊 Market Status")
        try:
            macro = get_macro_data()
            tnx = macro.get('yield_10y', 4.20); vix = macro.get('vix', 18.0)
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                yc = "#f87171" if tnx > 4.5 else "#facc15" if tnx > 4.3 else "#4ade80"
                st.markdown(f"<div style='text-align:center;'><span style='color:#a0aec0; font-size:11px;'>10Y</span><br><span style='color:{yc}; font-size:16px; font-weight:bold;'>{tnx:.2f}%</span></div>", unsafe_allow_html=True)
            with col_s2:
                vc = "#4ade80" if vix < 20 else "#facc15" if vix < 30 else "#f87171"
                st.markdown(f"<div style='text-align:center;'><span style='color:#a0aec0; font-size:11px;'>VIX</span><br><span style='color:{vc}; font-size:16px; font-weight:bold;'>{vix:.2f}</span></div>", unsafe_allow_html=True)
        except: pass
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        st.caption("⚡ TradeTerminal Pro v2.1 — Bug-Fixed Build")
    st.title("⚡ TradeTerminal Pro - Market Terminal")
    if nav_section == "🏠 Dashboard":
        try:
            mt = get_macro_data(); od = get_options_sentiment("SPY")
            fg = calc_fear_greed(mt['vix'], od['ratio'], mt['dxy']); ev = get_economic_calendar()
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(f"<div class='eco-card'><h4>🧠 Fear & Greed</h4><h2>{fg['label']}</h2><small>Score: {fg['score']}/100</small></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='eco-card'><h4>📊 Options (SPY)</h4><h3>PCR: {od['ratio']}</h3><small>{od['sentiment']}</small></div>", unsafe_allow_html=True)
            with c3:
                txt = "".join([f"**{e['name']}**\n⏳ {e['countdown']}\n\n" for e in ev])
                st.markdown(f"<div class='eco-card'><h4>🕒 Economic Countdown</h4>{txt}</div>", unsafe_allow_html=True)
            with c4: st.markdown(f"<div class='eco-card'><h4>Bond Yields</h4><b>10Y:</b> {mt['yield_10y']:.2f}%<br><b>30Y:</b> {mt['yield_30y']:.2f}%<br><b>Buyback:</b> {mt['buyback_icon']} {mt['buyback_status']}</div>", unsafe_allow_html=True)
        except: pass
    elif nav_section == "📈 Charts":
        st.subheader("📈 Asset Analysis")
        asset_keys = list(ASSETS.keys())
        cols_per_row = 6
        for i in range(0, len(asset_keys), cols_per_row):
            row_keys = asset_keys[i:i+cols_per_row]; cols = st.columns(cols_per_row)
            for j, key in enumerate(row_keys):
                with cols[j]:
                    if st.button(ASSETS[key]['symbol'], key=f"asset_btn_{key}", use_container_width=True):
                        st.session_state['selected_asset'] = key
        if 'selected_asset' not in st.session_state: st.session_state['selected_asset'] = "MNQ"
        render_asset(st.session_state['selected_asset'], auto_save)
    elif nav_section == "📅 Regime Report":
        st.subheader("📅 12-Month Regime Report")
        selected_assets = st.multiselect("Select Assets", options=list(ASSETS.keys()), default=["MGC","MNQ","MES"])
        for asset_key in selected_assets:
            monthly = get_monthly_regime_report(asset_key)
            if monthly is not None:
                st.subheader(f"📈 {ASSETS[asset_key]['symbol']} Monthly Regime")
                for i, row in monthly.iterrows(): st.write(f"{row['month_str']}: {row['overall_score']:.1f}/10 — {row['overall_bias']}")
            else: st.info(f"No historical data for {ASSETS[asset_key]['symbol']} yet.")
    elif nav_section == "🤖 AI Bubble Watch":
        st.subheader("🤖 AI & Semiconductor Bubble Watch")
        try:
            nvda = yf.Ticker("NVDA").history(period="6mo"); smh = yf.Ticker("SMH").history(period="6mo")
            mnq = yf.Ticker("MNQ=F").history(period="1d", interval="5m")
            dxy = yf.Ticker("DX-Y.NYB").history(period="1d", interval="5m")
            tnx = yf.Ticker("^TNX").history(period="1d", interval="5m")
            nvda_price = nvda['Close'].iloc[-1] if not nvda.empty else 0.0
            nvda_200 = sma(nvda['Close'].tolist(), 200) if not nvda.empty else 0.0
            smh_price = smh['Close'].iloc[-1] if not smh.empty else 0.0
            smh_200 = sma(smh['Close'].tolist(), 200) if not smh.empty else 0.0
            dxy_val = dxy['Close'].iloc[-1] if not dxy.empty else 0.0
            tnx_val = tnx['Close'].iloc[-1] if not tnx.empty else 0.0
            mnq_change = ((mnq['Close'].iloc[-1] - mnq['Close'].iloc[0]) / mnq['Close'].iloc[0]) * 100 if not mnq.empty else 0.0
            risk_score = 0; warnings = []
            if nvda_price > 0 and nvda_200 > 0 and nvda_price < nvda_200 * 0.95:
                risk_score += 30; warnings.append("🔴 NVDA BROKEN 200-DMA")
            if smh_price > 0 and smh_200 > 0 and smh_price < smh_200 * 0.95:
                risk_score += 30; warnings.append("🔴 SMH BROKEN 200-DMA")
            if dxy_val > 105 or tnx_val > 4.8: risk_score += 20; warnings.append("🔴 High Macro Pressure")
            elif dxy_val > 103 or tnx_val > 4.5: risk_score += 10; warnings.append("⚠️ Moderate Macro Pressure")
            if mnq_change < -1.5: risk_score += 20; warnings.append("🔴 MNQ Down > 1.5%")
            elif mnq_change < -0.5: risk_score += 10; warnings.append("⚠️ MNQ Weak")
            if risk_score >= 70: alert_color = "#f87171"; alert_icon = "🔴"; alert_text = "HIGH RISK"
            elif risk_score >= 40: alert_color = "#facc15"; alert_icon = "🟡"; alert_text = "MODERATE RISK"
            else: alert_color = "#4ade80"; alert_icon = "🟢"; alert_text = "LOW RISK"
            col_b1, col_b2 = st.columns([1, 2])
            with col_b1: st.markdown(f"<div class='eco-card'><h3 style='color: {alert_color};'>{alert_icon} {alert_text}</h3><h1 style='color: {alert_color}; font-size: 48px;'>{risk_score}/100</h1><small>Risk Score</small></div>", unsafe_allow_html=True)
            with col_b2: st.markdown(f"<div class='eco-card'><h4>📊 Key Metrics</h4><b>NVDA:</b> ${nvda_price:.2f}<br><b>SMH:</b> ${smh_price:.2f}<br><b>DXY:</b> {dxy_val:.2f} | <b>10Y:</b> {tnx_val:.2f}%</div>", unsafe_allow_html=True)
            if warnings: st.warning("**⚠️ Alerts:** " + " | ".join(warnings))
        except: st.warning("🤖 AI Bubble Watch temporarily offline.")
    elif nav_section == "💵 DXY Dashboard": render_dxy_dashboard()
    elif nav_section == "📊 Indices & Bond Tracker": run_indices_bond_tracker()
    elif nav_section == "🎯 Market Levels": run_level_marker()
    elif nav_section == "📝 Journal": run_journal_tab()
    elif nav_section == "🌏 Asia Sniper": run_asia_sniper()
    elif nav_section == "🇺🇸 NY Afternoon": run_ny_afternoon_sniper()
    elif nav_section == "📈 VWAP & 9 EMA": run_vwap_ema_strategy()
    elif nav_section == "⚡ High Yield Protocol": run_high_yield_protocol()
    elif nav_section == "📈 Trend-Fade Hybrid": run_trend_fade_hybrid()
    elif nav_section == "📉 M2K (Russell 2000)": run_m2k_shortcut()
    elif nav_section == "🏛️ US30 (Dow Jones)": run_us30_shortcut()
    elif nav_section == "🎯 Smart Money Levels": run_smart_money_levels()
    elif nav_section == "📋 SMC Cheat Sheet": render_smc_cheat_sheet()
    elif nav_section == "🏛️ Treasury Tracker": run_treasury_dashboard()
    elif nav_section == "🎯 Strategy Selector": run_strategy_selector()
    elif nav_section == "🎯 Sniper Entry Theory": run_sniper_entry_theory()

if __name__ == "__main__":
    run_app()