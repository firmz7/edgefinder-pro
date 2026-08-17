from __future__ import annotations
import time
import os, json, sqlite3, math, re, feedparser, requests, yfinance as yf
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd, numpy as np, plotly.graph_objects as go, plotly.express as px, streamlit as st
from dotenv import load_dotenv
import streamlit.components.v1 as components
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

# ============ LOAD ENVIRONMENT VARIABLES ============
load_dotenv()

ASSETS = {
    # --- FUTURES ---
    "MGC": {"symbol":"MGC","name":"Micro Gold","ticker":"MGC=F","tv_ticker":"CME_MINI:MGC1!","news_queries":["gold","MGC","micro gold"],"inverse_dxy":True,"safe_haven":True,"type":"Futures","favors":"Low Yields, High VIX"},
    "MNQ": {"symbol":"MNQ","name":"Micro Nasdaq","ticker":"MNQ=F","tv_ticker":"CME_MINI:MNQ1!","news_queries":["Nasdaq","MNQ","micro nasdaq"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates, Tech Surge"},
    "MES": {"symbol":"MES","name":"Micro S&P 500","ticker":"MES=F","tv_ticker":"CME_MINI:MES1!","news_queries":["S&P 500","MES","micro sp"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates, Low VIX"},
    "M2K": {"symbol":"M2K","name":"Micro Russell 2000","ticker":"M2K=F","tv_ticker":"CME_MINI:M2K1!","news_queries":["Russell","M2K","micro russell"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates"},
    "BTC": {"symbol":"BTC","name":"Micro Bitcoin","ticker":"BTC=F","tv_ticker":"CME_MINI:BTC1!","news_queries":["Bitcoin","BTC","crypto"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Risk-On, Liquidity"},
    "MCL": {"symbol":"MCL","name":"Micro Crude Oil","ticker":"MCL=F","tv_ticker":"CME_MINI:MCL1!","news_queries":["crude","oil","MCL"],"inverse_dxy":False,"safe_haven":False,"type":"Futures","favors":"Inflation, Supply"},
    "MNK": {"symbol":"MNK","name":"Micro Nikkei 225","ticker":"MNK=F","tv_ticker":"CME_MINI:MNK1!","news_queries":["Nikkei","MNK","micro nikkei"],"inverse_dxy":False,"safe_haven":False,"type":"Futures","favors":"Asian Markets, Tech"},
    "US30": {"symbol":"US30","name":"Micro Dow","ticker":"US30=F","tv_ticker":"CBOT_MINI:YM1!","news_queries":["Dow","US30","micro dow"],"inverse_dxy":True,"safe_haven":False,"type":"Futures","favors":"Low Rates, Industrial"},
    "SIL": {"symbol":"SIL","name":"Micro Silver","ticker":"SIL=F","tv_ticker":"CME_MINI:SI1!","news_queries":["silver","SIL","micro silver"],"inverse_dxy":True,"safe_haven":True,"type":"Futures","favors":"Industrial Demand, Inflation"},
    
    # --- BOND YIELDS ---
    "US02Y": {"symbol":"US02Y","name":"2-Year Treasury Yield","ticker":"^IRX","tv_ticker":"TVC:US02Y","news_queries":["2Y","IRX","treasury"],"inverse_dxy":False,"safe_haven":False,"type":"Yield","favors":"High Rates"},
    "US10Y": {"symbol":"US10Y","name":"10-Year Treasury Yield","ticker":"^TNX","tv_ticker":"TVC:US10Y","news_queries":["10Y","TNX","treasury"],"inverse_dxy":False,"safe_haven":False,"type":"Yield","favors":"High Rates"},
    "US30Y": {"symbol":"US30Y","name":"30-Year Treasury Yield","ticker":"^TYX","tv_ticker":"TVC:US30Y","news_queries":["30Y","TYX","treasury"],"inverse_dxy":False,"safe_haven":False,"type":"Yield","favors":"High Rates"},

    # --- INDICES ---
    "DXY": {"symbol":"DXY","name":"US Dollar Index","ticker":"DX-Y.NYB","tv_ticker":"TVC:DXY","news_queries":["DXY","dollar index"],"inverse_dxy":False,"safe_haven":False,"type":"Currency","favors":"High Yields"},
    "VIX": {"symbol":"VIX","name":"CBOE Volatility Index","ticker":"^VIX","tv_ticker":"^VIX","news_queries":["VIX","volatility"],"inverse_dxy":False,"safe_haven":False,"type":"Index","favors":"Panic"},
    "N225": {"symbol":"N225","name":"Nikkei 225","ticker":"N225","tv_ticker":"N225","news_queries":["Nikkei","N225","japan"],"inverse_dxy":False,"safe_haven":False,"type":"Index","favors":"Asian Tech, Weak Yen"},

    # --- SOUTH KOREA ---
    "KS11": {"symbol":"KS11","name":"KOSPI Index","ticker":"^KS11","tv_ticker":"KS11","news_queries":["KOSPI","KS11","south korea"],"inverse_dxy":False,"safe_haven":False,"type":"Index","favors":"Semiconductors"},
    "SAMSUNG": {"symbol":"SAMSUNG","name":"Samsung Electronics","ticker":"005930.KS","tv_ticker":"005930.KS","news_queries":["Samsung","005930","electronics"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"Semiconductors, Memory"},
    "SKHYNIX": {"symbol":"SKHYNIX","name":"SK Hynix","ticker":"000660.KS","tv_ticker":"000660.KS","news_queries":["SK Hynix","000660","memory"],"inverse_dxy":True,"safe_haven":False,"type":"Stock","favors":"Semiconductors, Memory"},

    # --- STOCKS ---
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

# ============ SMC CLASS (KEPT SEPARATE) ============
class SMCSignal:
    """Smart Money Concepts Signal Structure - Kept separate from core EdgeFinder"""
    def __init__(self):
        self.bullish_bos = False
        self.bearish_bos = False
        self.bullish_choch = False
        self.bearish_choch = False
        self.strong_high = 0.0
        self.weak_high = 0.0
        self.strong_low = 0.0
        self.weak_low = 0.0
        self.bullish_ob = []
        self.bearish_ob = []
        self.bullish_fvg = []
        self.bearish_fvg = []
        self.structure_bias = "NEUTRAL"

# ============ LIVE ECONOMIC CALENDAR (ForexFactory) ============
def get_economic_calendar()->List[Dict]:
    api_key = os.getenv("FOREXFACTORY_API_KEY")
    if not api_key:
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
                days = d.days
                h, r = divmod(d.seconds, 3600)
                m, _ = divmod(r, 60)
                c = f"{days}d {h}h {m}m" if days > 0 else f"{h}h {m}m"
                upcoming.append({"name": e["name"], "countdown": c})
        return upcoming[:3]
        
    try:
        url = "https://www.jblanked.com/news/api/list/"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {api_key}",
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            now = datetime.now(timezone.utc)
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
                        upcoming.append({
                            "name": f"🇺🇸 {item.get('title', '').replace('**', '')}",
                            "countdown": c
                        })
                except Exception:
                    continue
            return upcoming[:3]
        else:
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
            days = d.days
            h, r = divmod(d.seconds, 3600)
            m, _ = divmod(r, 60)
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
        lse_key = os.getenv("LSE_API_KEY")
        if lse_key:
            try:
                from lse import LSE
                client = LSE(api_key=lse_key)
                catalog = client.catalog()
                symbol_list = [s["symbol"] for s in catalog]
                lse_symbol = ticker
                if "=F" in ticker:
                    if ticker == "MNQ=F": lse_symbol = "MNQ"
                    elif ticker == "MES=F": lse_symbol = "MES"
                    elif ticker == "MGC=F": lse_symbol = "XAU/USD"
                    elif ticker == "BTC=F": lse_symbol = "BTC/USD"
                    elif ticker == "MCL=F": lse_symbol = "WTICO/USD"
                    elif ticker == "M2K=F": lse_symbol = "M2K"
                    elif ticker == "MNK=F": lse_symbol = "MNK"
                    elif ticker == "SIL=F": lse_symbol = "XAG/USD"
                if lse_symbol in symbol_list:
                    for tick in client.stream([lse_symbol]):
                        d = yf.Ticker(ticker).history(period="5d", interval="1d")
                        ph = d["High"].iloc[-2] if len(d) > 1 else d["Close"].iloc[-1]
                        pl = d["Low"].iloc[-2] if len(d) > 1 else d["Close"].iloc[-1]
                        return {
                            "current_price": tick.price,
                            "hist_1m": d,
                            "hist_5m": d,
                            "vwap": tick.price,
                            "ema9": tick.price,
                            "ema20": tick.price,
                            "ema50": tick.price,
                            "prev_high": ph,
                            "prev_low": pl,
                            "source": "LSE_WebSocket"
                        }
            except Exception:
                pass
    except:
        pass

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
        return {
            "current_price": h1['Close'].iloc[-1],
            "hist_1m": h1,
            "hist_5m": h5,
            "vwap": h1['VWAP'].iloc[-1],
            "ema9": h1['EMA_9'].iloc[-1],
            "ema20": h1['EMA_20'].iloc[-1],
            "ema50": h1['EMA_50'].iloc[-1],
            "prev_high": ph,
            "prev_low": pl,
            "source": "Yahoo_Fallback"
        }
    except Exception as e:
        return {"error": str(e)}

def get_macro_data()->Dict:
    try:
        dxy_data = yf.Ticker("DX-Y.NYB").history(period="1d", interval="1m")
        dxy = dxy_data['Close'].iloc[-1] if not dxy_data.empty else 102.0
    except:
        dxy = 102.0
        
    try:
        vix_data = yf.Ticker("^VIX").history(period="1d", interval="1m")
        vix = vix_data['Close'].iloc[-1] if not vix_data.empty else 18.0
    except:
        vix = 18.0
        
    ry = float(os.getenv("EDGEFINDER_REAL_YIELD_FALLBACK", "1.8"))
    
    try:
        tnx_data = yf.Ticker("^TNX").history(period="1d", interval="1m")
        tnx = tnx_data['Close'].iloc[-1] if not tnx_data.empty else 4.20
    except:
        tnx = 4.20
        
    try:
        tyx_data = yf.Ticker("^TYX").history(period="1d", interval="1m")
        tyx = tyx_data['Close'].iloc[-1] if not tyx_data.empty else 4.50
    except:
        tyx = 4.50

    try:
        kr10y_data = yf.Ticker("^KR10YT=RR").history(period="1d", interval="1m")
        kr10y = kr10y_data['Close'].iloc[-1] if not kr10y_data.empty else 3.50
    except:
        kr10y = 3.50

    try:
        jp10y_data = yf.Ticker("^JGB10Y").history(period="1d", interval="1m")
        jp10y = jp10y_data['Close'].iloc[-1] if not jp10y_data.empty else 1.00
    except:
        jp10y = 1.00

    try:
        jp30y_data = yf.Ticker("^JGB30Y").history(period="1d", interval="1m")
        jp30y = jp30y_data['Close'].iloc[-1] if not jp30y_data.empty else 2.00
    except:
        jp30y = 2.00
        
    return {"dxy": dxy, "vix": vix, "real_yield_10y": ry, "yield_10y": tnx, "yield_30y": tyx, "kr10y": kr10y, "jp10y": jp10y, "jp30y": jp30y}

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
 sentiment=sum(matches)/len(matches) if matches else 0.0; return {"asset":asset_name,"sentiment":sentiment,"headlines":len(matches)}

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
 rs=8 if rsi<30 else 3 if rsi>70 else 5; return int((t+rs)/2)

def score_dxy_macro(real_yield,vix)->int:
 y=9 if real_yield>2.5 else 7 if real_yield>2.0 else 5 if real_yield>1.5 else 3; v=9 if vix>30 else 7 if vix>20 else 5; return int((y+v)/2)

def get_macro_drivers(asset_key)->List[Dict]:
    d=[]
    try:
        dxy_data = yf.Ticker("DX-Y.NYB").history(period="1d", interval="1m")
        dxy = dxy_data['Close'].iloc[-1] if not dxy_data.empty else 102.0
    except:
        dxy = 102.0
        
    try:
        vix_data = yf.Ticker("^VIX").history(period="1d", interval="1m")
        vix = vix_data['Close'].iloc[-1] if not vix_data.empty else 18.0
    except:
        vix = 18.0
        
    ry = float(os.getenv("EDGEFINDER_REAL_YIELD_FALLBACK", "1.8"))
    
    if asset_key in ["SPY","NDX","QQQ","MNQ","MES","NVDA","TSLA","META","AMZN","SMH","PLTR","NOW"]:
        d.append({"category":"Growth & Risk","metric":"DXY (Dollar Strength)","bias":"Bearish" if dxy>104 else "Bullish","actual":f"{dxy:.2f}","forecast":"103.50","surprise":f"{dxy-103.50:.2f}","interpretation":"Strong dollar weighs on exports."})
        d.append({"category":"Growth & Risk","metric":"VIX (Fear Index)","bias":"Bearish" if vix>20 else "Bullish","actual":f"{vix:.2f}","forecast":"18.50","surprise":f"{vix-18.50:.2f}","interpretation":"Low VIX = Risk-on environment."})
        d.append({"category":"Monetary Policy","metric":"10Y Real Yield","bias":"Bearish" if ry>2.0 else "Bullish","actual":f"{ry:.2f}%","forecast":"2.10%","surprise":f"{ry-2.10:.2f}%","interpretation":"High yields steal liquidity from growth."})
    elif asset_key=="MGC" or asset_key=="GOLD":
        d.append({"category":"Macro Drivers","metric":"DXY (Dollar Strength)","bias":"Bullish" if dxy<104 else "Bearish","actual":f"{dxy:.2f}","forecast":"103.50","surprise":f"{dxy-103.50:.2f}","interpretation":"Inverse correlation with dollar."})
        d.append({"category":"Macro Drivers","metric":"10Y Real Yield","bias":"Bullish" if ry<1.8 else "Bearish","actual":f"{ry:.2f}%","forecast":"2.00%","surprise":f"{ry-2.00:.2f}%","interpretation":"Gold thrives on falling real yields."})
        d.append({"category":"Geopolitics","metric":"VIX (Fear Index)","bias":"Bullish" if vix>20 else "Neutral","actual":f"{vix:.2f}","forecast":"18.50","surprise":f"{vix-18.50:.2f}","interpretation":"Safe haven flows during market panic."})
    elif asset_key in ["DXY","US02Y","US10Y","US30Y"]:
        d.append({"category":"Interest Rates","metric":"US 2Y Treasury Yield","bias":"Bullish" if ry>2.0 else "Neutral","actual":"4.85%","forecast":"4.75%","surprise":"0.10%","interpretation":"Higher rates attract foreign capital."})
        d.append({"category":"Risk Sentiment","metric":"VIX (Fear Index)","bias":"Bullish" if vix>20 else "Neutral","actual":f"{vix:.2f}","forecast":"18.50","surprise":f"{vix-18.50:.2f}","interpretation":"Safe haven demand during turmoil."})
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
    val=float(driver["surprise"].replace("%","")); color="#4ade80" if val>=0 else "#f87171"; st.markdown(f"<div style='text-align: center; color: {color}; font-weight: bold;'>{driver['surprise']}</div>", unsafe_allow_html=True)
   with c[5]: st.caption(driver["interpretation"]); st.markdown("---")

def render_dxy_dashboard():
 st.subheader("💵 US Dollar Index (DXY) - Macro & Technical Analysis"); st.caption("The Dollar drives global markets. Here is the complete breakdown.")
 ticker="DX-Y.NYB"; intraday=get_intraday_data(ticker); macro=get_macro_data(); daily=yf.Ticker(ticker).history(period="6mo"); closes=daily['Close'].tolist(); price=closes[-1]; rsi=calc_rsi(closes); ma50=sma(closes,50); ma200=sma(closes,200); tp=((price-ma50)/ma50)*100 if ma50 else 0
 ts=score_dxy_technical(price,ma50,ma200,rsi); ms=score_dxy_macro(macro["real_yield_10y"],macro["vix"]); os=int((ts*0.5)+(ms*0.5))
 c1,c2,c3,c4=st.columns(4); c1.metric("Current Price",f"{price:.2f}"); c2.metric("DXY Overall Score",f"{os}/10",score_to_bias(os).value); c3.metric("Technical Score",f"{ts}/10"); c4.metric("Macro Score",f"{ms}/10")
 col_m1,col_m2=st.columns(2)
 with col_m1: st.markdown(f"<div class='eco-card'><h4>📊 DXY Macro Drivers</h4><b>10Y Real Yield:</b> {macro['real_yield_10y']:.2f}% <br><b>VIX (Fear):</b> {macro['vix']:.2f}</div>", unsafe_allow_html=True)
 with col_m2: st.markdown(f"<div class='eco-card'><h4>📉 DXY Technicals</h4><b>RSI:</b> {rsi:.2f}<br><b>200-Day SMA:</b> {ma200:.2f}<br><b>Long Term Trend:</b> {'Bullish' if price > ma200 else 'Bearish'}</div>", unsafe_allow_html=True)
 if "error" in intraday: st.warning(f"Intraday data unavailable: {intraday['error']}")
 else:
  st.info("📊 **DXY Intraday Setup:** VWAP (Blue), 9-EMA (Orange), 20-EMA (Yellow), 50-EMA (Purple)")
  c_i1,c_i2,c_i3,c_i4,c_i5=st.columns(5); c_i1.metric("Price",f"{intraday['current_price']:.2f}"); c_i2.metric("VWAP",f"{intraday['vwap']:.2f}"); c_i3.metric("9 EMA",f"{intraday['ema9']:.2f}"); c_i4.metric("20 EMA",f"{intraday['ema20']:.2f}"); c_i5.metric("50 EMA",f"{intraday['ema50']:.2f}")
  df=intraday['hist_5m']; fig=go.Figure(); fig.add_trace(go.Candlestick(x=df.index,open=df['Open'],high=df['High'],low=df['Low'],close=df['Close']))
  v=intraday['hist_1m']['VWAP'].resample('5min').last().ffill(); fig.add_trace(go.Scatter(x=v.index,y=v,mode='lines',name='VWAP',line=dict(color='royalblue',width=2)))
  e9=intraday['hist_1m']['EMA_9'].resample('5min').last().ffill(); fig.add_trace(go.Scatter(x=e9.index,y=e9,mode='lines',name='9 EMA',line=dict(color='orange',width=2)))
  e20=intraday['hist_1m']['EMA_20'].resample('5min').last().ffill(); fig.add_trace(go.Scatter(x=e20.index,y=e20,mode='lines',name='20 EMA',line=dict(color='gold',width=2)))
  e50=intraday['hist_1m']['EMA_50'].resample('5min').last().ffill(); fig.add_trace(go.Scatter(x=e50.index,y=e50,mode='lines',name='50 EMA',line=dict(color='violet',width=2)))
  fig.add_hline(y=intraday['prev_high'],line_dash="dash",line_color="red",annotation_text="PD High"); fig.add_hline(y=intraday['prev_low'],line_dash="dash",line_color="green",annotation_text="PD Low")
  fig.update_layout(height=450,paper_bgcolor="#0f1116",plot_bgcolor="#0f1116",font={"color":"#e8ecf1"}); st.plotly_chart(fig, width='stretch')
 st.markdown("---"); drivers=get_macro_drivers("DXY"); render_macro_drivers(drivers)
 
 st.markdown("### 🏦 Intraday Treasury Yields")
 st.caption("5-Minute chart of 10Y, 30Y Treasury yields, and their spread. Moves inversely to stocks.")
 try:
  tnx_intra = yf.Ticker("^TNX").history(period="2d", interval="5m")
  tyx_intra = yf.Ticker("^TYX").history(period="2d", interval="5m")
  if not tnx_intra.empty and not tyx_intra.empty:
   spread = tyx_intra['Close'] - tnx_intra['Close']
   fig2 = go.Figure()
   fig2.add_trace(go.Scatter(x=tnx_intra.index, y=tnx_intra['Close'], mode='lines', name='10Y Yield (^TNX)', line=dict(color='gold', width=2)))
   fig2.add_trace(go.Scatter(x=tyx_intra.index, y=tyx_intra['Close'], mode='lines', name='30Y Yield (^TYX)', line=dict(color='purple', width=2)))
   fig2.add_trace(go.Scatter(x=spread.index, y=spread, mode='lines', name='30Y-10Y Spread', line=dict(color='cyan', width=1.5, dash='dash')))
   fig2.update_layout(height=350, paper_bgcolor="#0f1116", plot_bgcolor="#0f1116", font={"color": "#e8ecf1"}, xaxis_rangeslider_visible=False, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
   st.plotly_chart(fig2, width='stretch')
   
   current_spread = spread.iloc[-1] if not spread.empty else 0
   spread_color = "#f87171" if current_spread < 0 else "#4ade80"
   st.markdown(f"""
   <div style='background-color: #1c2129; padding: 12px; border-radius: 8px; margin-top: 10px;'>
       <b>30Y-10Y Spread:</b> <span style='color: {spread_color}; font-weight: bold;'>{current_spread:.2f}%</span>
       <span style='color: #a0aec0; font-size: 14px; margin-left: 15px;'>
           {'🔴 Inverted Curve - Recession Warning' if current_spread < 0 else '🟢 Steep Curve - Growth Optimism'}
       </span>
   </div>
   """, unsafe_allow_html=True)
  else: st.info("Yield data unavailable outside trading hours.")
 except: pass

# ============ RENDER_ASSET FUNCTION ============
def render_asset(asset_key, auto_save):
    cfg = ASSETS[asset_key]
    intraday = get_intraday_data(cfg["ticker"])
    macro = get_macro_data()
    news = get_news_data(cfg["name"], cfg["news_queries"])
    snapshot = build_swing_snapshot(cfg, macro, news)
    
    if auto_save: save_snapshot(snapshot)
    
    # --- ECONOMIC DATA FETCH (CPI, NFP, UNEMPLOYMENT) ---
    try:
        cpi = yf.Ticker("^CPI").history(period="1mo")
        cpi_val = cpi['Close'].iloc[-1] if not cpi.empty else 3.2
        nfp = yf.Ticker("^NFP").history(period="1mo")
        nfp_val = nfp['Close'].iloc[-1] if not nfp.empty else 150
        unemp = yf.Ticker("UNRATE").history(period="1mo")
        unemp_val = unemp['Close'].iloc[-1] if not unemp.empty else 4.0
    except:
        cpi_val, nfp_val, unemp_val = 3.2, 150, 4.0
        
    # --- HEADER ---
    st.markdown(f"""
    <div style='display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2a2a2a; padding-bottom: 15px; margin-bottom: 20px;'>
        <div>
            <h2 style='margin: 0; color: #e8ecf1;'>{snapshot.name}</h2>
            <span style='color: #a0aec0; font-size: 14px;'>{snapshot.symbol}</span>
        </div>
        <div>
            <span style='background-color: {"#1a3a2a" if "Bullish" in snapshot.overall_bias.value else "#3a1a1a" if "Bearish" in snapshot.overall_bias.value else "#2a2a1a"}; color: {"#4ade80" if "Bullish" in snapshot.overall_bias.value else "#f87171" if "Bearish" in snapshot.overall_bias.value else "#facc15"}; padding: 5px 15px; border-radius: 20px; font-weight: bold; border: 1px solid {"#4ade80" if "Bullish" in snapshot.overall_bias.value else "#f87171" if "Bearish" in snapshot.overall_bias.value else "#facc15"};'>
                {snapshot.overall_bias.value}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # --- LAYOUT: TWO CLEAN COLUMNS ---
    c1, c2 = st.columns([1, 2])
    
    # === COLUMN 1: MAIN SCORE & PRICE ===
    with c1:
        st.markdown("### 📊 Asset Scorecard")
        st.metric("Price", f"${snapshot.price:,.2f}")
        
        # Determine Gauge Color
        if snapshot.overall_score >= 7:
            gauge_color = "#4ade80"
            rot = -45
        elif snapshot.overall_score >= 4:
            gauge_color = "#facc15"
            rot = 0
        else:
            gauge_color = "#f87171"
            rot = 45
            
        # CSS Gauge (Speedometer)
        st.markdown(f"""
        <div style="display: flex; justify-content: center; align-items: center; flex-direction: column; margin: 20px 0;">
            <div style="position: relative; width: 150px; height: 75px; overflow: hidden; border-radius: 150px 150px 0 0; border-bottom: 10px solid #2a2a2a;">
                <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: conic-gradient(from 180deg, {gauge_color} 0%, {gauge_color} 50%, #2a2a2a 50%, #2a2a2a 100%); transform: rotate({rot}deg);"></div>
                <div style="position: absolute; bottom: -10px; left: 50%; transform: translateX(-50%); width: 90px; height: 45px; background-color: #0f1116; border-radius: 100px 100px 0 0; display: flex; justify-content: center; align-items: flex-end; padding-bottom: 5px;">
                    <h2 style="margin: 0; color: #e8ecf1; font-size: 28px; font-weight: bold;">{snapshot.overall_score}</h2>
                </div>
            </div>
            <div style="width: 150px; display: flex; justify-content: space-between; color: #a0aec0; font-size: 12px; margin-top: 5px;">
                <span>Bearish</span>
                <span>Bullish</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("#### Breakdown")
        c_s1, c_s2, c_s3 = st.columns(3)
        c_s1.metric("Technical", f"{snapshot.technical_score}/10")
        c_s2.metric("Macro", f"{snapshot.macro_score}/10")
        c_s3.metric("News", f"{snapshot.news_score}/10")
        
        if "error" not in intraday:
            st.markdown("---")
            st.markdown("#### Intraday Setup")
            c_i1, c_i2 = st.columns(2)
            c_i1.metric("VWAP", f"{intraday['vwap']:.2f}")
            c_i2.metric("9 EMA", f"{intraday['ema9']:.2f}")

    # === COLUMN 2: DETAILED METRICS & DRIVERS ===
    with c2:
        st.markdown("### 🔍 Macro & Technical Drivers")
        
        # Technicals Table
        st.markdown("##### 📈 Technicals")
        tech_df = pd.DataFrame([{"Indicator": x.name, "Value": round(x.value, 2), "Bias": x.bias.value} for x in snapshot.technical_details])
        st.dataframe(tech_df, width='stretch', hide_index=True, use_container_width=True)
        
        # Macro Table
        st.markdown("##### 🌍 Macro")
        macro_df = pd.DataFrame([{"Indicator": x.name, "Value": round(x.value, 2), "Bias": x.bias.value} for x in snapshot.macro_details])
        st.dataframe(macro_df, width='stretch', hide_index=True, use_container_width=True)
        
        # News Table
        st.markdown("##### 📰 News Sentiment")
        news_df = pd.DataFrame([{"Indicator": x.name, "Value": round(x.value, 2), "Bias": x.bias.value} for x in snapshot.news_details])
        st.dataframe(news_df, width='stretch', hide_index=True, use_container_width=True)

        # Moving Averages (Vital filters)
        try:
            daily = yf.Ticker(cfg["ticker"]).history(period="6mo")
            if daily.empty:
                daily = yf.Ticker(cfg["ticker"]).history(period="1mo")
                
            if not daily.empty:
                closes = daily['Close'].tolist()
                p = closes[-1]
                m50 = sma(closes, 50)
                m200 = sma(closes, 200)
                
                st.markdown("##### 📉 Trend Filters")
                col_ma1, col_ma2 = st.columns(2)
                col_ma1.metric("50-Day SMA", f"${m50:.2f}", delta=f"{((p-m50)/m50)*100:.1f}%" if m50 else None)
                col_ma2.metric("200-Day SMA", f"${m200:.2f}", delta=f"{((p-m200)/m200)*100:.1f}%" if m200 else None)
        except:
            pass

        # --- US ECONOMIC DATA TABLE ---
        st.markdown("##### 🏛️ US Economic Data")
        econ_df = pd.DataFrame([
            {"Indicator": "Inflation (CPI MoM)", "Actual": f"{cpi_val:.2f}%", "Bias": "Bullish" if cpi_val < 3.0 else "Bearish"},
            {"Indicator": "Non-Farm Payrolls", "Actual": f"{nfp_val:.0f}k", "Bias": "Bullish" if nfp_val > 120 else "Bearish"},
            {"Indicator": "Unemployment Rate", "Actual": f"{unemp_val:.2f}%", "Bias": "Bearish" if unemp_val > 4.2 else "Bullish"}
        ])
        st.dataframe(econ_df, width='stretch', hide_index=True, use_container_width=True)

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
def load_recent(symbol,limit=30)->List[Dict]:
 conn=get_conn(); rows=conn.execute("SELECT ts_utc, symbol, price, overall_score FROM snapshots WHERE symbol = ? ORDER BY id DESC LIMIT ?",(symbol,limit)).fetchall(); conn.close(); return [dict(r) for r in rows][::-1]

# ============ SAFE SWING SNAPSHOT ============
def build_swing_snapshot(config,macro,news)->AssetSnapshot:
    ticker=config["ticker"]
    
    try:
        daily = yf.Ticker(ticker).history(period="6mo")
        if daily.empty:
            daily = yf.Ticker(ticker).history(period="1mo")
        
        if daily.empty:
            closes = [100.0]
            p = 100.0
            r = 50.0
            m50 = 100.0
            m200 = 100.0
            tp = 0.0
            ts = 5
            td = [
                IndicatorReading("RSI 14", r, score_rsi(r), score_to_bias(score_rsi(r))),
                IndicatorReading("Trend vs 50D MA %", tp, score_trend_pct(tp), score_to_bias(score_trend_pct(tp)))
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
                IndicatorReading("Trend vs 50D MA %", tp, score_trend_pct(tp), score_to_bias(score_trend_pct(tp)))
            ]
    except Exception:
        closes = [100.0]
        p = 100.0
        r = 50.0
        m50 = 100.0
        m200 = 100.0
        tp = 0.0
        ts = 5
        td = [
            IndicatorReading("RSI 14", r, score_rsi(r), score_to_bias(score_rsi(r))),
            IndicatorReading("Trend vs 50D MA %", tp, score_trend_pct(tp), score_to_bias(score_trend_pct(tp)))
        ]

    inv=config.get("inverse_dxy",False); safe=config.get("safe_haven",False); md=[IndicatorReading("DXY",macro["dxy"],score_dxy(macro["dxy"],inv),score_to_bias(score_dxy(macro["dxy"],inv))),IndicatorReading("VIX",macro["vix"],score_vix(macro["vix"],safe),score_to_bias(score_vix(macro["vix"],safe))),IndicatorReading("Real Yield",macro["real_yield_10y"],score_real_yield(macro["real_yield_10y"],inv),score_to_bias(score_real_yield(macro["real_yield_10y"],inv)))]; ms=sum([x.score for x in md])//3; ns=score_news(news.get("sentiment",0.0)); o=int(round(ts*0.45+ms*0.30+ns*0.25)); return AssetSnapshot(symbol=config["symbol"],name=config["name"],price=p,technical_score=ts,macro_score=ms,news_score=ns,overall_score=o,overall_bias=score_to_bias(o),technical_details=td,macro_details=md,news_details=[IndicatorReading("News Sentiment",news.get("sentiment",0),ns,score_to_bias(ns))])

# ============ MONTHLY REGIME REPORT ============
def get_monthly_regime_report(asset_key):
    conn = get_conn()
    symbol = ASSETS[asset_key]["symbol"]
    rows = conn.execute("SELECT ts_utc, overall_score, overall_bias FROM snapshots WHERE symbol = ? ORDER BY ts_utc DESC", (symbol,)).fetchall()
    conn.close()
    if rows:
        df = pd.DataFrame([dict(r) for r in rows]); df['ts_utc'] = pd.to_datetime(df['ts_utc']); df['month'] = df['ts_utc'].dt.to_period('M')
        monthly = df.groupby('month').agg({'overall_score':'mean','overall_bias':lambda x: x.mode()[0] if not x.empty else "Neutral"}).reset_index()
        monthly = monthly.sort_values('month', ascending=False).head(12)
        monthly['month_str'] = monthly['month'].astype(str)
        return monthly
    return None

# ============ SMC CHEAT SHEET (STANDALONE) ============
def render_smc_cheat_sheet():
    """
    Standalone SMC Cheat Sheet - No integration with EdgeFinder
    """
    st.markdown("""
    <style>
    .smc-card { background-color: #1c2129; padding: 15px; border-radius: 8px; margin: 5px 0; border-left: 4px solid #60a5fa; }
    .smc-bullish { border-left-color: #4ade80; background-color: #1a3a2a; }
    .smc-bearish { border-left-color: #f87171; background-color: #3a1a1a; }
    .smc-neutral { border-left-color: #facc15; background-color: #2a2a1a; }
    .smc-label { font-weight: bold; font-size: 16px; }
    .smc-desc { color: #a0aec0; font-size: 14px; }
    .smc-warning { background-color: #3a2a1a; border-left-color: #facc15; }
    .smc-danger { background-color: #3a1a1a; border-left-color: #f87171; }
    .smc-success { background-color: #1a3a2a; border-left-color: #4ade80; }
    </style>
    """, unsafe_allow_html=True)
    
    st.subheader("🎯 Smart Money Concepts (SMC) Cheat Sheet")
    st.caption("Quick reference for SMC structure labels - Standalone reference only")
    
    st.markdown("""
    <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border: 2px solid #f87171; margin-bottom: 20px;'>
        <h4 style='color: #f87171; margin: 0;'>⚠️ CRITICAL: Weak High = SELL-OFF ZONE</h4>
        <p style='color: #e8ecf1; font-size: 14px;'>
            <b>Weak Highs are NOT breakout zones!</b> They are <b>DISTRIBUTION ZONES</b> where smart money sells to retail traders.<br>
            The market <b>OFTEN SELLS OFF</b> at Weak Highs as institutions take profits and load shorts.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📈 BULLISH STRUCTURE")
        st.markdown("""
        <div class='smc-card smc-success'>
            <span class='smc-label' style='color: #4ade80;'>🟢 Strong Low</span>
            <p class='smc-desc'><b>What it is:</b> Higher Lows - Major SUPPORT zone<br>
            <b>What happens:</b> Smart money BUYS here, accumulating positions<br>
            <b>Action:</b> ✅ Look for BOUNCE and BUY<br>
            <b>Stop:</b> Below the Strong Low</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class='smc-card smc-warning'>
            <span class='smc-label' style='color: #facc15;'>🟡 Weak High</span>
            <p class='smc-desc'><b>What it is:</b> Higher Highs - WEAK RESISTANCE zone<br>
            <b>What happens:</b> Smart money SELLS here to retail breakout buyers<br>
            <b>Action:</b> ⚠️ Watch for REJECTION - OFTEN SELLS OFF<br>
            <b>Stop:</b> Above the Weak High</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class='smc-card smc-success'>
            <span class='smc-label' style='color: #4ade80;'>📊 Bullish BOS/CHoCH</span>
            <p class='smc-desc'>BOS: Trend continues UP (Higher Highs)<br>
            CHoCH: Structure REVERSAL to UP (from bearish)<br>
            <b>Action:</b> ✅ Trade LONG with trend</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("### 📉 BEARISH STRUCTURE")
        st.markdown("""
        <div class='smc-card smc-danger'>
            <span class='smc-label' style='color: #f87171;'>🔴 Strong High</span>
            <p class='smc-desc'><b>What it is:</b> Lower Highs - Major RESISTANCE zone<br>
            <b>What happens:</b> Smart money DEFENDS this level aggressively<br>
            <b>Action:</b> 🛑 Look for REJECTION and SELL<br>
            <b>Stop:</b> Above the Strong High</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class='smc-card smc-success'>
            <span class='smc-label' style='color: #60a5fa;'>🔵 Weak Low</span>
            <p class='smc-desc'><b>What it is:</b> Lower Lows - WEAK SUPPORT zone<br>
            <b>What happens:</b> Smart money BUYS here from retail sellers<br>
            <b>Action:</b> ✅ Watch for BOUNCE - Often reverses up<br>
            <b>Stop:</b> Below the Weak Low</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class='smc-card smc-danger'>
            <span class='smc-label' style='color: #f87171;'>📊 Bearish BOS/CHoCH</span>
            <p class='smc-desc'>BOS: Trend continues DOWN (Lower Lows)<br>
            CHoCH: Structure REVERSAL to DOWN (from bullish)<br>
            <b>Action:</b> ❌ Trade SHORT with trend</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 📊 SMC Trading Decision Matrix")
    
    decision_data = {
        "SMC Signal": ["🟡 Weak High (SELL ZONE)", "🔴 Strong High (SHORT ZONE)", "🟢 Strong Low (BUY ZONE)", "🔵 Weak Low (BOUNCE ZONE)"],
        "Market Reality": ["Smart money SELLS to retail breakout buyers", "Smart money DEFENDS major resistance", "Smart money BUYS at major support", "Smart money BUYS from retail sellers"],
        "Best Action": ["❌ SELL on rejection", "❌ SHORT on rejection", "✅ BUY on bounce", "✅ BUY on bounce"]
    }
    df_decision = pd.DataFrame(decision_data)
    st.dataframe(df_decision, width='stretch', hide_index=True, use_container_width=True)
    
    st.markdown("---")
    st.info("💡 **The Golden Rule:** Weak Highs are where smart money distributes to retail. Don't be the retail buyer chasing the breakout - be the smart money selling into strength!")

# ============ STRATEGY CHEAT SHEET ============
def run_cheat_sheet():
    st.subheader("📋 Macro & Volatility Cheat Sheet")
    st.caption("Reference guides for VIX, VXN, and Bond Yields.")
    
    st.markdown("### 🌪️ VIX (S&P 500) Volatility Map & Bias Benchmarks")
    st.caption("Use the VIX to gauge general market complacency and panic.")
    
    col_v1, col_v2, col_v3, col_v4 = st.columns(4)
    
    with col_v1:
        st.markdown("""
        <div style='background-color: #163a1a; padding: 12px; border-radius: 8px; border: 1px solid #4ade80; text-align: center;'>
            <h3 style='color: #4ade80; margin: 0;'>VIX < 15</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #4ade80;'>🟢 ZERO FEAR</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Extreme complacency.<br>Markets are too comfortable.<br><b>Action:</b> Look for small pullbacks. Longs are safe, but watch for sudden shocks.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_v2:
        st.markdown("""
        <div style='background-color: #1a2a3a; padding: 12px; border-radius: 8px; border: 1px solid #60a5fa; text-align: center;'>
            <h3 style='color: #60a5fa; margin: 0;'>15 < VIX < 20</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #60a5fa;'>⚖️ NORMAL</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Healthy market volatility.<br>This is the "Goldilocks" zone.<br><b>Action:</b> Trade your normal NQ/MGC setups. The system works best here.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_v3:
        st.markdown("""
        <div style='background-color: #3a2a1a; padding: 12px; border-radius: 8px; border: 1px solid #facc15; text-align: center;'>
            <h3 style='color: #facc15; margin: 0;'>20 < VIX < 30</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #facc15;'>🟡 HIGH FEAR</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Panic is starting to creep in.<br>Expect wide swings (20+ points).<br><b>Action:</b> Tighten stops. Reversals are common.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_v4:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 12px; border-radius: 8px; border: 1px solid #f87171; text-align: center;'>
            <h3 style='color: #f87171; margin: 0;'>VIX > 30</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #f87171;'>🔴 EXTREME PANIC</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Market is bleeding. Fast money is bailing.<br><b>Action:</b> DO NOT short the lows. Watch for a "V-Bottom" reversal. Gold may act as a safe haven here.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    st.markdown("### 🚀 VXN (Nasdaq 100) Volatility Map & Bias Benchmarks")
    st.caption("The VXN measures fear specifically in the Tech sector. Nasdaq (NQ) is highly inversely correlated to this.")
    
    col_vxn1, col_vxn2, col_vxn3, col_vxn4 = st.columns(4)
    
    with col_vxn1:
        st.markdown("""
        <div style='background-color: #1a3a2a; padding: 12px; border-radius: 8px; border: 1px solid #4ade80; text-align: center;'>
            <h3 style='color: #4ade80; margin: 0;'>VXN < 20</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #4ade80;'>🟢 TECH COMPLACENCY</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Tech traders are too comfortable.<br><b>Action:</b> NQ longs are favored, but watch for sudden V-shaped shocks.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_vxn2:
        st.markdown("""
        <div style='background-color: #1a2a3a; padding: 12px; border-radius: 8px; border: 1px solid #60a5fa; text-align: center;'>
            <h3 style='color: #60a5fa; margin: 0;'>20 < VXN < 30</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #60a5fa;'>⚖️ NORMAL TECH VOL</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Healthy tech volatility.<br><b>Action:</b> Normal NQ setups apply here. Use your NY Sniper triggers.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_vxn3:
        st.markdown("""
        <div style='background-color: #3a2a1a; padding: 12px; border-radius: 8px; border: 1px solid #facc15; text-align: center;'>
            <h3 style='color: #facc15; margin: 0;'>30 < VXN < 40</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #facc15;'>🟡 TECH PANIC</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>AI/Tech is getting hammered.<br><b>Action:</b> Extreme caution. Tighten NQ stops. Watch for capitulation bottoms.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_vxn4:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 12px; border-radius: 8px; border: 1px solid #f87171; text-align: center;'>
            <h3 style='color: #f87171; margin: 0;'>VXN > 40</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #f87171;'>🔴 TECH CRISIS</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Nasdaq is bleeding. Fast money is bailing.<br><b>Action:</b> DO NOT short the lows. Watch for the massive "V-Bottom" reversal.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    st.markdown("### 📉 Yield Curve Health & Bias Benchmarks")
    st.caption("Use the Yield Curve to gauge recession risks, inflation, and the Fed's trajectory.")
    
    col_b1, col_b2, col_b3, col_b4 = st.columns(4)
    
    with col_b1:
        st.markdown("""
        <div style='background-color: #1a2a3a; padding: 12px; border-radius: 8px; border: 1px solid #60a5fa; text-align: center;'>
            <h3 style='color: #60a5fa; margin: 0;'>US02Y < 4.0%</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #60a5fa;'>⚖️ ACCOMMODATIVE</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Short-term borrowing is cheap.<br>The Fed is cutting or paused.<br><b>Action:</b> Risk-on environment. Long NQ/MGC is favored.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_b2:
        st.markdown("""
        <div style='background-color: #3a2a1a; padding: 12px; border-radius: 8px; border: 1px solid #facc15; text-align: center;'>
            <h3 style='color: #facc15; margin: 0;'>US02Y > 4.5%</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #facc15;'>🟡 TIGHTENING</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Short-term borrowing is expensive.<br>The Fed is hiking or hawkish.<br><b>Action:</b> Headwinds for NQ. Hold off on large longs.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_b3:
        st.markdown("""
        <div style='background-color: #1a3a2a; padding: 12px; border-radius: 8px; border: 1px solid #4ade80; text-align: center;'>
            <h3 style='color: #4ade80; margin: 0;'>US10Y < 4.0%</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #4ade80;'>🟢 GROWTH TAILWIND</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Long-term borrowing is cheap.<br>Inflation is under control.<br><b>Action:</b> Bullish for NQ. MGC struggles unless yields drop fast.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_b4:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 12px; border-radius: 8px; border: 1px solid #f87171; text-align: center;'>
            <h3 style='color: #f87171; margin: 0;'>US10Y > 4.5%</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #f87171;'>🔴 GROWTH HEADWIND</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Long-term borrowing is expensive.<br>Inflation is sticky.<br><b>Action:</b> Bearish for NQ. <b>AVOID MGC</b> unless yields drop sharply.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    st.markdown("#### 🔄 The 10Y-2Y Spread (Recession Warning)")
    st.caption("When the 2-Year yield is HIGHER than the 10-Year yield, the yield curve is inverted—a historically reliable recession signal.")
    st.markdown("""
    <div style='background-color: #2a1a1a; padding: 15px; border-radius: 8px; border-left: 6px solid #f87171;'>
        <h4 style='color: #f87171; margin: 0;'>⚠️ INVERTED CURVE ALERT</h4>
        <p style='font-size: 14px; color: #e8ecf1; margin-top: 5px;'>
            <b>US02Y > US10Y:</b> The bond market is screaming that a recession is coming within 12-18 months.<br>
            <b>US02Y < US10Y:</b> The curve is normalizing. The economy is healthy.
        </p>
        <p style='font-size: 13px; color: #facc15;'><b>Action:</b> When the curve is inverted, expect violent whipsaws. Reduce position sizes significantly.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    
    st.markdown("### 🧠 What the 30-Year Yield tells you")
    st.caption("The 30-Year Treasury Yield is the ultimate long-term economic signal. Here's how to read it:")
    
    col_30_1, col_30_2, col_30_3 = st.columns(3)
    
    with col_30_1:
        st.markdown("""
        <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border: 1px solid #4ade80; text-align: center; height: 100%;'>
            <h4 style='color: #4ade80;'>📈 Normal Curve</h4>
            <h3 style='color: #4ade80; margin: 0;'>US30Y > US10Y</h3>
            <p style='font-size: 13px; margin-top: 10px; color: #e8ecf1;'>
                The market expects <b>long-term growth</b> and inflation.<br><br>
                📌 <b>Action:</b> Risk-on environment. Long NQ and stocks are favored.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_30_2:
        st.markdown("""
        <div style='background-color: #3a2a1a; padding: 15px; border-radius: 8px; border: 1px solid #facc15; text-align: center; height: 100%;'>
            <h4 style='color: #facc15;'>📉 Inverted Curve</h4>
            <h3 style='color: #facc15; margin: 0;'>US30Y < US10Y</h3>
            <p style='font-size: 13px; margin-top: 10px; color: #e8ecf1;'>
                The market expects a <b>recession</b> in the near future.<br><br>
                📌 <b>Action:</b> Reduce risk. Short NQ, watch for safe-haven flows into Gold.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_30_3:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border: 1px solid #f87171; text-align: center; height: 100%;'>
            <h4 style='color: #f87171;'>🚨 Crisis Signal</h4>
            <h3 style='color: #f87171; margin: 0;'>US30Y > 5.0%</h3>
            <p style='font-size: 13px; margin-top: 10px; color: #e8ecf1;'>
                Global investors are <b>dumping US debt</b>. This is a crisis signal.<br><br>
                📌 <b>Action:</b> Extreme caution. Gold becomes a safe-haven. Expect severe volatility.
            </p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    st.markdown("🌏 Global Bond Yields & Macro Benchmarks")
    st.caption("International yields drive currency moves and global capital flows. Track these to trade the Nikkei and KOSPI.")

    col_j1, col_j2, col_j3, col_j4 = st.columns(4)
    
    with col_j1:
        st.markdown("""
        <div style='background-color: #1a2a3a; padding: 12px; border-radius: 8px; border: 1px solid #60a5fa; text-align: center;'>
            <h3 style='color: #60a5fa; margin: 0;'>🇯🇵 JGB10Y < 1.0%</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #60a5fa;'>🟢 BOJ ACCOMMODATIVE</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Japan yields are essentially zero.<br><b>Action:</b> Risk-on for Nikkei. Weak Yen boosts exports.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_j2:
        st.markdown("""
        <div style='background-color: #3a2a1a; padding: 12px; border-radius: 8px; border: 1px solid #facc15; text-align: center;'>
            <h3 style='color: #facc15; margin: 0;'>🇯🇵 JGB10Y > 1.5%</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #facc15;'>🟡 BOJ TIGHTENING</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>The Bank of Japan is hiking rates.<br><b>Action:</b> Headwinds for Nikkei. Stronger Yen hurts exporters.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_j3:
        st.markdown("""
        <div style='background-color: #1a3a2a; padding: 12px; border-radius: 8px; border: 1px solid #4ade80; text-align: center;'>
            <h3 style='color: #4ade80; margin: 0;'>🇯🇵 JGB30Y > 2.5%</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #4ade80;'>🟢 LONG-TERM GROWTH</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>Japan's long-term yields are rising.<br><b>Action:</b> Watch for Yen strength; Nikkei may struggle.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col_j4:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 12px; border-radius: 8px; border: 1px solid #f87171; text-align: center;'>
            <h3 style='color: #f87171; margin: 0;'>🇰🇷 KR10Y > 4.0%</h3>
            <p style='font-size: 14px; margin-top: 5px;'><b style='color: #f87171;'>🔴 KOREA OVERHEATING</b></p>
            <p style='font-size: 12px; color: #a0aec0;'>South Korean yields are surging.<br><b>Action:</b> Bearish for KOSPI. Heavy pressure on Samsung and SK Hynix.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.info("💡 **Global Macro Tip:** The US 10Y Yield (^TNX) is the 'risk-free baseline' for the world. If US yields rise, global yields (Japan, Korea) usually follow. When Japan and Korea yields spike, their stock markets (Nikkei, KOSPI) usually drop.")

# ============ VWAP & 9 EMA STRATEGY CHEAT SHEET ============
def run_vwap_ema_strategy():
    st.subheader("📊 VWAP & 9 EMA Strategy Cheat Sheet")
    st.caption("Master the VWAP bounce strategy for MNQ, MGC, and MES during NY session (2:30 PM - 4:30 PM UK time).")
    
    st.markdown("### 🟢 Bullish Setup Conditions")
    st.markdown("""
    <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80; margin-bottom: 15px;'>
        <h4 style='color: #4ade80;'>✅ Required Conditions for LONG Setup</h4>
        <ul style='color: #e8ecf1; font-size: 16px;'>
            <li>✅ <b>Price ABOVE 9 EMA</b> - Short-term momentum is bullish</li>
            <li>✅ <b>Price ABOVE VWAP</b> - Bullish trend is confirmed</li>
            <li>✅ <b>Higher highs structure</b> - Price making higher highs and higher lows</li>
            <li>✅ <b>MACRO: DXY weak, yields low</b> - Favorable macro environment</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 📈 VWAP Bounce Entry")
    st.markdown("""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px; border-left: 4px solid #facc15; margin-bottom: 15px;'>
        <h4 style='color: #facc15;'>🎯 Entry Conditions</h4>
        <ul style='color: #e8ecf1; font-size: 16px;'>
            <li>✅ <b>Price pulls back to VWAP</b> - Normal retracement in an uptrend</li>
            <li>✅ <b>Price bounces off VWAP</b> - Rejection of lower prices (bullish)</li>
            <li>✅ <b>Bullish candle closes above VWAP</b> - Confirmation of bounce</li>
            <li>✅ <b>Volume confirmation</b> - Volume increases on the bounce</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 📊 Entry Levels")
    
    col_entry1, col_entry2, col_entry3, col_entry4 = st.columns(4)
    
    with col_entry1:
        st.markdown("""
        <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #4ade80; height: 100%;'>
            <h4 style='color: #4ade80; margin: 0;'>📌 Entry</h4>
            <p style='font-size: 18px; font-weight: bold; color: #e8ecf1;'>On bounce off VWAP</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col_entry2:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #f87171; height: 100%;'>
            <h4 style='color: #f87171; margin: 0;'>🛑 Stop Loss</h4>
            <p style='font-size: 18px; font-weight: bold; color: #e8ecf1;'>Below VWAP (5-10 pts)</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col_entry3:
        st.markdown("""
        <div style='background-color: #1a2a3a; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #60a5fa; height: 100%;'>
            <h4 style='color: #60a5fa; margin: 0;'>🎯 Target 1</h4>
            <p style='font-size: 18px; font-weight: bold; color: #e8ecf1;'>1.5x Range (50% profit)</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col_entry4:
        st.markdown("""
        <div style='background-color: #1a2a3a; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #4ade80; height: 100%;'>
            <h4 style='color: #4ade80; margin: 0;'>🎯 Target 2</h4>
            <p style='font-size: 18px; font-weight: bold; color: #e8ecf1;'>2x Range (Full profit)</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("### 📊 Visual Chart Setup")
    st.markdown("""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px; margin-bottom: 15px;'>
        <h4 style='color: #e8ecf1;'>Chart: MNQ (5-min)</h4>
        <ul style='color: #e8ecf1; font-size: 15px;'>
            <li>🟣 <b>50 EMA</b> - Long-term trend</li>
            <li>🟡 <b>20 EMA</b> - Medium-term trend</li>
            <li>🟠 <b>9 EMA</b> ← <span style='color: #4ade80;'>Price ABOVE this (bullish)</span></li>
            <li>🔵 <b>VWAP</b> ← <span style='color: #facc15;'>Price PULLS BACK to this</span></li>
            <li>💰 <b>Price</b> ← <span style='color: #4ade80;'>BOUNCES OFF VWAP</span></li>
        </ul>
        <div style='background-color: #0f1116; padding: 10px; border-radius: 4px; text-align: center; margin-top: 10px;'>
            <span style='color: #4ade80; font-size: 20px;'>⬆️ ENTRY on bounce</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🔄 Trading Strategy Flow")
    st.markdown("""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px; margin-bottom: 15px;'>
        <h4 style='color: #e8ecf1;'>Normal Bullish Day:</h4>
        <ol style='color: #e8ecf1; font-size: 15px;'>
            <li><b>Price opens above VWAP</b> = Bullish bias</li>
            <li><b>Price pulls back to VWAP</b> = Normal retracement</li>
            <li><b>Price bounces off VWAP</b> = ✅ LONG ENTRY</li>
            <li><b>Price continues higher</b> = ✅ PROFIT</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🎯 How to Use with Your NY Sniper")
    st.markdown("""
    <div style='background-color: #1a2a3a; padding: 15px; border-radius: 8px; border-left: 4px solid #60a5fa; margin-bottom: 15px;'>
        <ol style='color: #e8ecf1; font-size: 15px;'>
            <li><b>NY Opens at 2:30 PM UK</b> - Start watching</li>
            <li><b>Check if Price > VWAP</b> - Bullish confirmation</li>
            <li><b>Watch for pullback to VWAP</b> - Wait for the bounce</li>
            <li><b>If price bounces → ENTRY</b> - Execute the trade</li>
            <li><b>If price breaks below VWAP → NO TRADE</b> - Trend is breaking down</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🚨 When NOT to Take the Trade")
    
    col_avoid1, col_avoid2 = st.columns(2)
    
    with col_avoid1:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border: 1px solid #f87171; height: 100%;'>
            <h4 style='color: #f87171;'>❌ Skip These</h4>
            <ul style='color: #e8ecf1;'>
                <li>Price breaks BELOW VWAP - Trend breaking down</li>
                <li>No bounce (price goes through VWAP) - No rejection</li>
                <li>VIX > 30 - Too volatile</li>
                <li>10Y Yield > 4.3% - Bad macro</li>
                <li>No volume confirmation - Weak signal</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col_avoid2:
        st.markdown("""
        <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border: 1px solid #4ade80; height: 100%;'>
            <h4 style='color: #4ade80;'>✅ Take These</h4>
            <ul style='color: #e8ecf1;'>
                <li>Strong bounce off VWAP</li>
                <li>Bullish candle closes above VWAP</li>
                <li>Volume increases on bounce</li>
                <li>VIX < 25</li>
                <li>10Y Yield < 4.3%</li>
                <li>Macro alignment (weak DXY)</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("### 💡 Pro Tips")
    st.markdown("""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px; margin-bottom: 15px;'>
        <ul style='color: #e8ecf1; font-size: 15px;'>
            <li><b>Wait for the Candle Close</b> - Don't enter on the wick, wait for the candle to close above VWAP</li>
            <li><b>Look for a Doji or Hammer</b> - These candlesticks at VWAP are strong rejection signals</li>
            <li><b>Volume Confirmation</b> - More volume on the bounce = stronger signal</li>
            <li><b>Multiple Timeframe</b> - Check 15-min chart also showing bullish structure</li>
            <li><b>Macro Alignment</b> - Weak DXY, falling yields = better setup</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 📝 Quick Reference Card")
    st.markdown("""
    <div style='background-color: #0f1116; padding: 20px; border-radius: 8px; border: 2px solid #facc15;'>
        <h3 style='color: #facc15; text-align: center;'>MNQ LONG ENTRY (VWAP Bounce)</h3>
        <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0;'>
            <div style='background-color: #1a3a2a; padding: 10px; border-radius: 4px;'>
                <span style='color: #4ade80;'>✅ Price > 9 EMA</span> (bullish)
            </div>
            <div style='background-color: #1a3a2a; padding: 10px; border-radius: 4px;'>
                <span style='color: #4ade80;'>✅ Price touched VWAP</span> (pullback)
            </div>
            <div style='background-color: #1a3a2a; padding: 10px; border-radius: 4px;'>
                <span style='color: #4ade80;'>✅ Price bounced</span> (rejection)
            </div>
            <div style='background-color: #1a3a2a; padding: 10px; border-radius: 4px;'>
                <span style='color: #4ade80;'>✅ Bullish candle closed</span> (confirmation)
            </div>
        </div>
        <div style='text-align: center; margin: 10px 0;'>
            <span style='color: #4ade80; font-weight: bold;'>Enter: On bounce | Stop: Below VWAP | Target: 2x Range</span>
        </div>
        <div style='background-color: #3a1a1a; padding: 10px; border-radius: 4px;'>
            <span style='color: #f87171;'>🔴 AVOID if:</span>
            <span style='color: #e8ecf1;'> Price breaks below VWAP | No bounce | Macro bad (DXY strong, yields high)</span>
        </div>
        <div style='text-align: center; margin-top: 10px; color: #a0aec0; font-size: 14px;'>
            ⏰ This strategy works best during NY session (2:30 PM - 4:30 PM UK time) when liquidity is highest!
        </div>
    </div>
    """, unsafe_allow_html=True)

# ============ HIGH YIELD PROTOCOL STRATEGY (STANDALONE) ============
def run_high_yield_protocol():
    """
    Strategy for high yield markets (US10Y > 4.5%)
    Fades extremes and trades ranges when VWAP/EMA strategy fails
    Supports MNQ, MGC, and MES - COMPLETELY STANDALONE
    """
    st.subheader("⚡ High Yield Protocol (4.5%+ Yields)")
    st.caption("Designed for markets where VWAP & EMA fail. Fades extremes and trades ranges. US Session only.")
    
    # Get current market data
    macro = get_macro_data()
    tnx = macro['yield_10y']
    vix = macro['vix']
    dxy = macro['dxy']
    
    # Check if strategy applies
    if tnx < 4.5:
        st.success(f"🟢 Yields are below 4.5% ({tnx:.2f}%). Use your normal VWAP & EMA strategy.")
        st.info("💡 The High Yield Protocol is only for markets with US10Y > 4.5%.")
        return
    
    # Show active warning
    st.warning(f"🔴 HIGH YIELD MODE ACTIVE (US10Y: {tnx:.2f}%)")
    st.caption("⚠️ VWAP & EMA strategy is INVALID in this environment. Use fade extremes and range trades.")
    
    # Display market conditions
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("US10Y Yield", f"{tnx:.2f}%", delta="HIGH", delta_color="inverse")
    with col_m2:
        st.metric("VIX", f"{vix:.2f}", delta="ELEVATED" if vix > 20 else "NORMAL")
    with col_m3:
        st.metric("DXY", f"{dxy:.2f}", delta="")
    
    st.markdown("---")
    
    # ============ ASSET SELECTION ============
    asset_choice = st.selectbox(
        "Select Asset",
        ["MNQ (Micro Nasdaq)", "MGC (Micro Gold)", "MES (Micro S&P 500)"],
        index=0,
        key="high_yield_asset_select"
    )
    
    # Map selection to ticker
    asset_map = {
        "MNQ (Micro Nasdaq)": "MNQ=F",
        "MGC (Micro Gold)": "MGC=F",
        "MES (Micro S&P 500)": "MES=F"
    }
    ticker = asset_map[asset_choice]
    asset_name = asset_choice.split(" (")[0]
    
    # ============ GET NY DATA ============
    with st.spinner(f"Fetching NY session data for {asset_name}..."):
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
    
    if data.empty:
        st.warning(f"No data available for {asset_name}.")
        return
    
    today = datetime.now().date()
    data_today = data[data.index.date == today]
    ny_data = data_today.between_time('08:00', '09:29')
    
    if ny_data.empty:
        st.warning("NY Pre-Market data not available. Check back after 1:00 PM UK time.")
        return
    
    # ============ KEY LEVELS ============
    ny_high = ny_data['High'].max()
    ny_low = ny_data['Low'].min()
    ny_range = ny_high - ny_low
    
    # Current price (most recent)
    current_price = data_today['Close'].iloc[-1]
    
    # ============ DISPLAY LEVELS ============
    st.markdown(f"### 📊 {asset_name} Key NY Levels")
    
    col_l1, col_l2, col_l3, col_l4 = st.columns(4)
    with col_l1:
        st.metric("NY High", f"{ny_high:.2f}")
    with col_l2:
        st.metric("NY Low", f"{ny_low:.2f}")
    with col_l3:
        st.metric("Range", f"{ny_range:.2f} pts")
    with col_l4:
        st.metric("Current Price", f"{current_price:.2f}")
    
    # ============ CALCULATE ZONES ============
    range_top = ny_high - 10
    range_bottom = ny_low + 10
    
    # Determine which zone price is in
    near_high = current_price > (ny_high - 10)
    near_low = current_price < (ny_low + 10)
    above_range_top = current_price > range_top
    below_range_bottom = current_price < range_bottom
    
    # ============ ZONE INDICATOR ============
    if near_high and not near_low:
        zone = "🔴 EXTREME HIGH ZONE - SHORT signals available"
        zone_color = "#3a1a1a"
        valid_signal = "SHORT"
    elif near_low and not near_high:
        zone = "🟢 EXTREME LOW ZONE - LONG signals available"
        zone_color = "#1a3a2a"
        valid_signal = "LONG"
    elif above_range_top and not near_high:
        zone = "🔴 RANGE TOP ZONE - SHORT signals available"
        zone_color = "#3a1a1a"
        valid_signal = "SHORT"
    elif below_range_bottom and not near_low:
        zone = "🟢 RANGE BOTTOM ZONE - LONG signals available"
        zone_color = "#1a3a2a"
        valid_signal = "LONG"
    else:
        zone = "⚪ MIDDLE OF RANGE - NO SIGNAL. Wait for edges."
        zone_color = "#1c2129"
        valid_signal = "NONE"
    
    # ============ DISPLAY ZONE ============
    st.markdown(f"""
    <div style='background-color: {zone_color}; padding: 15px; border-radius: 8px; border: 1px solid #facc15; margin-bottom: 20px;'>
        <h4 style='color: #facc15;'>📍 Current Zone: {zone}</h4>
        <ul style='color: #e8ecf1;'>
            <li><b>Price:</b> {current_price:.2f}</li>
            <li><b>Range Top:</b> {range_top:.2f}</li>
            <li><b>Range Bottom:</b> {range_bottom:.2f}</li>
            <li><b>Valid Signals:</b> {valid_signal}</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # ============ SIGNAL 1: FADE EXTREMES ============
    st.markdown("### 📉 Signal 1: Fade Extremes")
    st.caption("When price reaches the extreme of the NY range, fade it back toward the middle.")
    
    col_s1, col_s2 = st.columns(2)
    
    with col_s1:
        st.markdown("#### 🟢 Fade High (SHORT)")
        if near_high and not near_low:
            short_entry = current_price
            short_stop = ny_high + 5
            short_target = current_price - (ny_range * 0.5)
            
            risk = short_stop - short_entry
            reward = short_entry - short_target
            rr_ratio = reward / risk if risk > 0 else 0
            
            st.error(f"✅ **SHORT SIGNAL ACTIVE**")
            st.markdown(f"""
            <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                <b>Entry:</b> {short_entry:.2f}<br>
                <b>Stop Loss:</b> {short_stop:.2f}<br>
                <b>Target:</b> {short_target:.2f}<br>
                <b>Risk/Reward:</b> 1:{rr_ratio:.1f}
                <br><b>Risk Amount:</b> {risk:.2f} pts
            </div>
            """, unsafe_allow_html=True)
            if rr_ratio < 1:
                st.warning(f"⚠️ Risk/Reward is {rr_ratio:.1f}:1 - Consider if this trade is worth it!")
            st.caption("📌 Fading the NY high - expecting pullback toward mid-range")
        else:
            dist_to_high = ny_high - current_price
            st.info(f"⏳ Price at {current_price:.2f}. Need to be within 10 points of NY High ({ny_high:.2f}) for SHORT signal.")
            st.caption(f"📌 Distance to NY High: {dist_to_high:.2f} pts")
    
    with col_s2:
        st.markdown("#### 🔴 Fade Low (LONG)")
        if near_low and not near_high:
            long_entry = current_price
            
            if current_price < ny_low:
                long_stop = current_price - 5
                stop_reason = "⚠️ Price below NY Low - stop below entry"
            else:
                long_stop = ny_low - 5
                stop_reason = "✅ Price at range bottom - stop below NY Low"
            
            long_target = current_price + (ny_range * 0.5)
            
            risk = long_entry - long_stop
            reward = long_target - long_entry
            rr_ratio = reward / risk if risk > 0 else 0
            
            st.success(f"✅ **LONG SIGNAL ACTIVE**")
            st.markdown(f"""
            <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                <b>Entry:</b> {long_entry:.2f}<br>
                <b>Stop Loss:</b> {long_stop:.2f}<br>
                <b>Target:</b> {long_target:.2f}<br>
                <b>Risk/Reward:</b> 1:{rr_ratio:.1f}
                <br><b>Risk Amount:</b> {risk:.2f} pts
                <br><b>Stop Reason:</b> {stop_reason}
            </div>
            """, unsafe_allow_html=True)
            
            if rr_ratio < 1:
                st.warning(f"⚠️ Risk/Reward is {rr_ratio:.1f}:1 - Consider if this trade is worth it!")
            
            st.caption("📌 Fading the NY low - expecting bounce toward mid-range")
        else:
            dist_to_low = current_price - ny_low
            st.info(f"⏳ Price at {current_price:.2f}. Need to be within 10 points of NY Low ({ny_low:.2f}) for LONG signal.")
            st.caption(f"📌 Distance to NY Low: {dist_to_low:.2f} pts")
    
    # ============ SIGNAL 2: RANGE TRADING ============
    st.markdown("---")
    st.markdown("### 📊 Signal 2: Range Trading")
    st.caption("Trade the edges of the NY range with tighter stops and targets.")
    
    col_r1, col_r2 = st.columns(2)
    
    with col_r1:
        st.markdown("#### 📈 Range Top (SHORT)")
        if above_range_top and not near_high:
            r_short_entry = current_price
            r_short_stop = ny_high + 5
            r_short_target = ny_low + 20
            
            risk = r_short_stop - r_short_entry
            reward = r_short_entry - r_short_target
            rr_ratio = reward / risk if risk > 0 else 0
            
            st.error(f"✅ **RANGE SHORT SIGNAL**")
            st.markdown(f"""
            <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                <b>Entry:</b> {r_short_entry:.2f}<br>
                <b>Stop:</b> {r_short_stop:.2f}<br>
                <b>Target:</b> {r_short_target:.2f}<br>
                <b>Risk/Reward:</b> 1:{rr_ratio:.1f}
                <br><b>Risk Amount:</b> {risk:.2f} pts
            </div>
            """, unsafe_allow_html=True)
            
            if rr_ratio < 1:
                st.warning(f"⚠️ Risk/Reward is {rr_ratio:.1f}:1 - Consider if this trade is worth it!")
            
            st.caption(f"📌 Price above range top ({range_top:.2f}). Target range bottom.")
        else:
            if near_high:
                st.info(f"⏳ Price is in EXTREME HIGH zone. Use Fade Extremes strategy instead.")
            else:
                distance_to_range_top = range_top - current_price
                st.info(f"⏳ Price below range top ({range_top:.2f}). Waiting for range edge.")
                st.caption(f"📌 Distance to range top: {distance_to_range_top:.2f} pts")
    
    with col_r2:
        st.markdown("#### 📉 Range Bottom (LONG)")
        if below_range_bottom and not near_low:
            r_long_entry = current_price
            
            if current_price < ny_low:
                r_long_stop = current_price - 5
                stop_reason = "⚠️ Price below NY Low - stop below entry"
            else:
                r_long_stop = ny_low - 5
                stop_reason = "✅ Price at range bottom - stop below NY Low"
            
            r_long_target = ny_high - 20
            
            risk = r_long_entry - r_long_stop
            reward = r_long_target - r_long_entry
            rr_ratio = reward / risk if risk > 0 else 0
            
            st.success(f"✅ **RANGE LONG SIGNAL**")
            st.markdown(f"""
            <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                <b>Entry:</b> {r_long_entry:.2f}<br>
                <b>Stop:</b> {r_long_stop:.2f}<br>
                <b>Target:</b> {r_long_target:.2f}<br>
                <b>Risk/Reward:</b> 1:{rr_ratio:.1f}
                <br><b>Risk Amount:</b> {risk:.2f} pts
                <br><b>Stop Reason:</b> {stop_reason}
            </div>
            """, unsafe_allow_html=True)
            
            if rr_ratio < 1:
                st.warning(f"⚠️ Risk/Reward is {rr_ratio:.1f}:1 - Consider if this trade is worth it!")
            
            st.caption(f"📌 Price below range bottom ({range_bottom:.2f}). Target range top.")
        else:
            if near_low:
                st.info(f"⏳ Price is in EXTREME LOW zone. Use Fade Extremes strategy instead.")
            else:
                distance_to_range_bottom = current_price - range_bottom
                st.info(f"⏳ Price above range bottom ({range_bottom:.2f}). Waiting for range edge.")
                st.caption(f"📌 Distance to range bottom: {distance_to_range_bottom:.2f} pts")
    
    # ============ SIGNAL CLEARING RULE ============
    st.markdown("---")
    st.markdown("### ⚠️ Signal Confirmation Rules")
    
    st.markdown("""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px; border-left: 4px solid #facc15;'>
        <h4 style='color: #facc15;'>📋 Only ONE Signal is Valid at a Time</h4>
        <ul style='color: #e8ecf1;'>
            <li>✅ <b>Fade Extremes</b> and <b>Range Trading</b> are DIFFERENT strategies</li>
            <li>✅ They should NOT give signals at the same time</li>
            <li>✅ If price is in the middle of the range → NO SIGNAL</li>
            <li>✅ If price is near both extremes → NO SIGNAL (wait)</li>
            <li>✅ <b>Range Bottom LONG</b> OR <b>Fade Low LONG</b> - NOT both</li>
            <li>✅ <b>Range Top SHORT</b> OR <b>Fade High SHORT</b> - NOT both</li>
            <li>✅ Stop Loss must ALWAYS be on the OPPOSITE side of entry</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # ============ CURRENT VALID SIGNAL SUMMARY ============
    st.markdown("---")
    st.markdown("### 📊 Valid Signal Summary")
    
    if valid_signal == "SHORT":
        summary_stop = ny_high + 5
        risk = summary_stop - current_price
        reward = current_price - (current_price - (ny_range * 0.5))
        rr = reward / risk if risk > 0 else 0
        
        st.markdown(f"""
        <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border: 2px solid #f87171;'>
            <h3 style='color: #f87171;'>📉 SHORT SIGNAL AVAILABLE</h3>
            <ul style='color: #e8ecf1;'>
                <li><b>Strategy:</b> {'Fade Extremes' if near_high else 'Range Trading'}</li>
                <li><b>Entry:</b> {current_price:.2f}</li>
                <li><b>Stop:</b> {summary_stop:.2f} (Above entry)</li>
                <li><b>Target:</b> {current_price - (ny_range * 0.5):.2f}</li>
                <li><b>Risk/Reward:</b> 1:{rr:.1f}</li>
                <li><b>Position Size:</b> 25% of normal</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    elif valid_signal == "LONG":
        if current_price < ny_low:
            summary_stop = current_price - 5
        else:
            summary_stop = ny_low - 5
        
        risk = current_price - summary_stop
        reward = (current_price + (ny_range * 0.5)) - current_price
        rr = reward / risk if risk > 0 else 0
        
        st.markdown(f"""
        <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border: 2px solid #4ade80;'>
            <h3 style='color: #4ade80;'>📈 LONG SIGNAL AVAILABLE</h3>
            <ul style='color: #e8ecf1;'>
                <li><b>Strategy:</b> {'Fade Extremes' if near_low else 'Range Trading'}</li>
                <li><b>Entry:</b> {current_price:.2f}</li>
                <li><b>Stop:</b> {summary_stop:.2f} (Below entry)</li>
                <li><b>Target:</b> {current_price + (ny_range * 0.5):.2f}</li>
                <li><b>Risk/Reward:</b> 1:{rr:.1f}</li>
                <li><b>Position Size:</b> 25% of normal</li>
                <li><b>Stop Reason:</b> {"Below entry (price below NY Low)" if current_price < ny_low else "Below NY Low"}</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='background-color: #1c2129; padding: 15px; border-radius: 8px; border: 2px solid #60a5fa;'>
            <h3 style='color: #60a5fa;'>⏳ NO SIGNAL AVAILABLE</h3>
            <ul style='color: #e8ecf1;'>
                <li><b>Price is in the middle of the range</b></li>
                <li><b>Wait for price to reach an edge</b></li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    # ============ EXECUTION RULES ============
    st.markdown("---")
    st.markdown("### 🎯 Execution Rules")
    
    col_e1, col_e2, col_e3 = st.columns(3)
    
    with col_e1:
        st.markdown("""
        <div style='background-color: #1c2129; padding: 15px; border-radius: 8px;'>
            <h4>⏰ Time</h4>
            <ul style='color: #e8ecf1;'>
                <li>✅ <b>3:30 PM - 4:30 PM UK</b></li>
                <li>✅ Best window</li>
                <li>❌ Avoid 2:30-3:00 PM</li>
                <li>❌ Avoid after 4:30 PM</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col_e2:
        st.markdown("""
        <div style='background-color: #1c2129; padding: 15px; border-radius: 8px;'>
            <h4>📊 Position Size</h4>
            <ul style='color: #e8ecf1;'>
                <li>✅ <b>25% of normal</b></li>
                <li>✅ 1 contract only</li>
                <li>❌ No scaling in</li>
                <li>❌ No averaging</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col_e3:
        st.markdown("""
        <div style='background-color: #1c2129; padding: 15px; border-radius: 8px;'>
            <h4>🎯 Targets</h4>
            <ul style='color: #e8ecf1;'>
                <li>✅ <b>50% of range</b></li>
                <li>✅ Quick in/out</li>
                <li>❌ No holding overnight</li>
                <li>❌ No trailing stops</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    # ============ RISK WARNING ============
    st.markdown("---")
    st.warning("""
    ⚠️ **HIGH YIELD PROTOCOL WARNING:**
    - This is a **CONTRARIAN** strategy (trading against extremes)
    - It works BEST in **sideways/high yield markets**
    - It FAILS in **strong trending markets**
    - USE **25% POSITION SIZE** maximum
    - TAKE PROFITS **QUICKLY** (don't get greedy)
    - **EXIT BY 4:30 PM UK** - No overnight holds
    If the market trends strongly, this strategy will lose money.
    Use the VWAP & EMA strategy instead in trending markets.
    """)
    
    # ============ STRATEGY COMPARISON ============
    st.markdown("### 📊 When to Use Which Strategy")
    
    st.markdown("""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px;'>
        <table style='width: 100%; color: #e8ecf1; border-collapse: collapse;'>
            <tr style='background-color: #2a2a2a;'>
                <th style='padding: 8px; border: 1px solid #3a3a3a;'>Condition</th>
                <th style='padding: 8px; border: 1px solid #3a3a3a;'>Strategy</th>
                <th style='padding: 8px; border: 1px solid #3a3a3a;'>Action</th>
            </tr>
            <tr>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>US10Y < 4.3%<br>VIX 15-25<br>Clear Trend</td>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>🟢 VWAP & EMA</td>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>✅ Trade normally</td>
            </tr>
            <tr>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>US10Y 4.3-4.5%<br>VIX 20-25<br>No Clear Trend</td>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>🟡 VWAP with Caution</td>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>⚠️ 50% size, wider stops</td>
            </tr>
            <tr style='background-color: #2a1a1a;'>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>US10Y > 4.5%<br>VIX 20-30<br>Ranging Market</td>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>🔴 High Yield Protocol</td>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>✅ 25% size, fade extremes</td>
            </tr>
            <tr>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>VIX > 30</td>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>❌ NO STRATEGY</td>
                <td style='padding: 8px; border: 1px solid #3a3a3a;'>⛔ Sit out completely</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

# ============ NY AFTERNOON SNIPER ============
def run_ny_afternoon_sniper():
    """
    Late NY Session Sniper (3:30 PM - 4:30 PM UK Time)
    Better price action after initial NY chaos settles.
    Supports MNQ, MGC, and MES
    """
    st.subheader("🇺🇸 NY Afternoon Sniper (3:30 PM - 4:30 PM UK)")
    st.caption("Better price action after initial NY chaos settles. More reliable entries with fewer fakeouts.")
    
    # Check if it's afternoon session (UK time)
    now_utc = datetime.now(timezone.utc)
    uk_time = now_utc.astimezone(timezone(timedelta(hours=1)))
    current_hour = uk_time.hour
    current_minute = uk_time.minute
    
    # Only show if between 3:30 PM and 4:30 PM UK time
    is_afternoon_session = (current_hour == 15 and current_minute >= 30) or (current_hour == 16 and current_minute <= 30)
    
    if not is_afternoon_session:
        st.info("⏳ NY Afternoon Session runs from 3:30 PM - 4:30 PM UK time. Check back then for better entries!")
        return
    
    # ============ ASSET SELECTION ============
    asset_choice = st.selectbox(
        "Select Asset",
        ["MNQ (Micro Nasdaq)", "MGC (Micro Gold)", "MES (Micro S&P 500)"],
        index=0,
        key="ny_afternoon_asset_select"
    )
    
    # Map selection to ticker
    asset_map = {
        "MNQ (Micro Nasdaq)": "MNQ=F",
        "MGC (Micro Gold)": "MGC=F",
        "MES (Micro S&P 500)": "MES=F"
    }
    ticker = asset_map[asset_choice]
    asset_name = asset_choice.split(" (")[0]
    
    with st.spinner(f"Fetching NY Afternoon data for {asset_name}..."):
        data = yf.Ticker(ticker).history(period="2d", interval="5m")
    
    if data.empty:
        st.warning(f"No data available for {asset_name}.")
        return
    
    today = datetime.now().date()
    macro = get_macro_data()
    vix = macro['vix']
    tnx = macro['yield_10y']
    
    # Get NY Pre-Market Range
    data_today = data[data.index.date == today]
    ny_data = data_today.between_time('08:00', '09:29')
    
    if ny_data.empty:
        st.warning(f"NY Pre-Market data not available for {asset_name}.")
        return
    
    ny_high = ny_data['High'].max()
    ny_low = ny_data['Low'].min()
    ny_range = ny_high - ny_low
    
    # Current price (3:30 PM)
    afternoon_data = data_today.between_time('08:00', '16:30')
    if afternoon_data.empty:
        st.warning("Afternoon data not available.")
        return
    
    current_price = afternoon_data['Close'].iloc[-1]
    
    # Calculate VWAP for the day
    vwap = (afternoon_data['Close'] * afternoon_data['Volume']).cumsum() / afternoon_data['Volume'].cumsum()
    current_vwap = vwap.iloc[-1]
    
    # Calculate 9 EMA
    ema9 = afternoon_data['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
    
    # Display current state
    st.markdown(f"""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px; margin-bottom: 20px;'>
        <h4>📊 Current State (3:30 PM UK) - {asset_name}</h4>
        <b>Price:</b> {current_price:.2f}<br>
        <b>NY Range:</b> {ny_high:.2f} - {ny_low:.2f} (Range: {ny_range:.2f})<br>
        <b>VWAP:</b> {current_vwap:.2f}<br>
        <b>9 EMA:</b> {ema9:.2f}<br>
        <b>VIX:</b> {vix:.2f} | <b>10Y:</b> {tnx:.2f}%
    </div>
    """, unsafe_allow_html=True)
    
    # ============ ENTRY SIGNAL 1: BREAKOUT CONFIRMATION ============
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🚀 Breakout Confirmation")
        
        # Check breakout
        above_ny_high = current_price > ny_high + 15
        below_ny_low = current_price < ny_low - 15
        above_vwap = current_price > current_vwap
        below_vwap = current_price < current_vwap
        
        if above_ny_high and above_vwap:
            long_entry = current_price
            long_sl = ny_high - 15
            long_tp = long_entry + (ny_range * 2)
            
            st.success(f"✅ **LONG SIGNAL**")
            st.markdown(f"""
            <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                <b>Entry:</b> > {long_entry:.2f}<br>
                <b>SL:</b> {long_sl:.2f}<br>
                <b>TP:</b> {long_tp:.2f}<br>
                <b>Risk/Reward:</b> 1:{(long_tp - long_entry) / (long_entry - long_sl):.1f}
            </div>
            """, unsafe_allow_html=True)
            
        elif below_ny_low and below_vwap:
            short_entry = current_price
            short_sl = ny_low + 15
            short_tp = short_entry - (ny_range * 2)
            
            st.error(f"✅ **SHORT SIGNAL**")
            st.markdown(f"""
            <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                <b>Entry:</b> < {short_entry:.2f}<br>
                <b>SL:</b> {short_sl:.2f}<br>
                <b>TP:</b> {short_tp:.2f}<br>
                <b>Risk/Reward:</b> 1:{(short_entry - short_tp) / (short_sl - short_entry):.1f}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("⏳ No breakout yet. Price still inside/around NY Range.")
    
    with col2:
        st.markdown("### 🔄 Pullback to 9 EMA")
        
        # Check pullback entry
        at_ema9 = abs(current_price - ema9) / current_price < 0.002
        price_above_ny_high = current_price > ny_high
        
        if at_ema9 and price_above_ny_high:
            pullback_entry = current_price
            pullback_sl = ny_high - 10
            pullback_tp = pullback_entry + (ny_range * 1.5)
            
            st.success(f"✅ **PULLBACK LONG SIGNAL**")
            st.markdown(f"""
            <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                <b>Entry:</b> {pullback_entry:.2f}<br>
                <b>SL:</b> {pullback_sl:.2f}<br>
                <b>TP:</b> {pullback_tp:.2f}<br>
                <b>Risk/Reward:</b> 1:{(pullback_tp - pullback_entry) / (pullback_entry - pullback_sl):.1f}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("⏳ Waiting for pullback to 9 EMA after breakout.")
    
    # ============ VOLATILITY ADJUSTMENT ============
    st.markdown("---")
    st.markdown("### 📊 Volatility Adjustment")
    
    # Adjust stops based on VIX
    if vix > 30:
        st.warning(f"⚠️ **EXTREME VOLATILITY** (VIX: {vix:.2f})")
        st.caption("Increase stops by 50%, reduce position size to 25%")
    elif vix > 25:
        st.warning(f"⚠️ **HIGH VOLATILITY** (VIX: {vix:.2f})")
        st.caption("Increase stops by 30%, reduce position size to 50%")
    elif vix > 20:
        st.info(f"⚡ **ELEVATED VOLATILITY** (VIX: {vix:.2f})")
        st.caption("Normal stops, reduce position size to 75%")
    else:
        st.success(f"✅ **NORMAL VOLATILITY** (VIX: {vix:.2f})")
        st.caption("Normal stops, full position size")
    
    # ============ EXECUTION RULES ============
    st.markdown("---")
    st.markdown("### 🎯 Execution Rules")
    
    st.markdown("""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px;'>
        <h4>📋 Entry Checklist (3:30 PM - 4:30 PM)</h4>
        <ul>
            <li>✅ <b>Time:</b> 3:30 PM - 4:30 PM UK time</li>
            <li>✅ <b>Breakout:</b> Price above NY High + 15 OR below NY Low - 15</li>
            <li>✅ <b>VWAP:</b> Price on same side as VWAP (above for long, below for short)</li>
            <li>✅ <b>Volume:</b> Volume > average (confirmation)</li>
            <li>✅ <b>VIX:</b> Below 30 for normal sizing</li>
            <li>✅ <b>Better Entry:</b> Pullback to 9 EMA after breakout</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # ============ TRADE MANAGEMENT ============
    st.markdown("---")
    st.markdown("### 📈 Trade Management")
    
    st.markdown("""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px;'>
        <h4>📊 Managing Your Trade</h4>
        <ul>
            <li>✅ <b>Move to breakeven:</b> When price moves 50% of target</li>
            <li>✅ <b>Take partial profits:</b> 50% at 1:1 risk/reward</li>
            <li>✅ <b>Hold remainder:</b> For full target (2x range)</li>
            <li>✅ <b>Exit by 4:30 PM:</b> Unless trend is very strong</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

# ============ SMART MONEY LEVELS ============
def run_smart_money_levels():
    """
    Smart Money Concepts Levels for EdgeFinder
    Displays key SMC levels to use with VWAP/EMA strategy
    Supports MNQ, MGC, and MES
    """
    st.subheader("🎯 Smart Money Levels")
    st.caption("Key SMC levels - Order Blocks, Fair Value Gaps, and Structure to use with your VWAP/EMA strategy")
    
    # Get data
    macro = get_macro_data()
    tnx = macro['yield_10y']
    vix = macro['vix']
    
    # Show market context
    if tnx > 4.5:
        st.warning(f"⚠️ HIGH YIELD MODE ({tnx:.2f}%) - SMC levels still valid, use with High Yield Protocol")
    elif tnx > 4.3:
        st.info(f"⚡ ELEVATED YIELDS ({tnx:.2f}%) - SMC levels provide extra confirmation")
    else:
        st.success(f"✅ NORMAL YIELDS ({tnx:.2f}%) - SMC levels work best")
    
    # ============ ASSET SELECTION ============
    asset_choice = st.selectbox(
        "Select Asset",
        ["MNQ (Micro Nasdaq)", "MGC (Micro Gold)", "MES (Micro S&P 500)"],
        index=0,
        key="smart_money_asset_select"
    )
    
    # Map selection to ticker
    asset_map = {
        "MNQ (Micro Nasdaq)": "MNQ=F",
        "MGC (Micro Gold)": "MGC=F",
        "MES (Micro S&P 500)": "MES=F"
    }
    ticker = asset_map[asset_choice]
    asset_name = asset_choice.split(" (")[0]
    
    with st.spinner(f"Fetching Smart Money levels for {asset_name}..."):
        data = yf.Ticker(ticker).history(period="5d", interval="5m")
    
    if data.empty:
        st.warning(f"No data available for {asset_name}.")
        return
    
    # Current data
    today = datetime.now().date()
    data_today = data[data.index.date == today]
    current_price = data_today['Close'].iloc[-1] if not data_today.empty else data['Close'].iloc[-1]
    
    # ============================================
    # 1. IDENTIFY KEY LEVELS
    # ============================================
    
    # Get yesterday's data for levels
    yesterday = today - timedelta(days=1)
    data_yesterday = data[data.index.date == yesterday]
    
    # Find previous day high/low
    prev_high = data_yesterday['High'].max() if not data_yesterday.empty else 0
    prev_low = data_yesterday['Low'].min() if not data_yesterday.empty else 0
    
    # Find recent swing highs and lows (lookback 50 bars)
    lookback = min(50, len(data))
    recent_high = data['High'].iloc[-lookback:].max()
    recent_low = data['Low'].iloc[-lookback:].min()
    
    # Detect swing highs (price higher than 5 bars on each side)
    highs = data['High'].values
    lows = data['Low'].values
    
    swing_highs = []
    swing_lows = []
    
    for i in range(5, len(data) - 5):
        if highs[i] > max(highs[i-5:i]) and highs[i] > max(highs[i+1:i+6]):
            swing_highs.append((data.index[i], highs[i]))
        if lows[i] < min(lows[i-5:i]) and lows[i] < min(lows[i+1:i+6]):
            swing_lows.append((data.index[i], lows[i]))
    
    # Take last 5 swing points
    last_5_highs = swing_highs[-5:] if len(swing_highs) >= 5 else swing_highs
    last_5_lows = swing_lows[-5:] if len(swing_lows) >= 5 else swing_lows
    
    # Determine current structure
    is_bullish = False
    is_bearish = False
    
    if len(last_5_highs) >= 2 and len(last_5_lows) >= 2:
        hh = last_5_highs[-1][1] > last_5_highs[-2][1]
        hl = last_5_lows[-1][1] > last_5_lows[-2][1]
        lh = last_5_highs[-1][1] < last_5_highs[-2][1]
        ll = last_5_lows[-1][1] < last_5_lows[-2][1]
        
        if hh and hl:
            is_bullish = True
            structure = "🟢 BULLISH (HH + HL)"
            structure_color = "#4ade80"
        elif lh and ll:
            is_bearish = True
            structure = "🔴 BEARISH (LH + LL)"
            structure_color = "#f87171"
        else:
            structure = "⚪ NEUTRAL (Mixed signals)"
            structure_color = "#facc15"
    else:
        structure = "⚪ INSUFFICIENT DATA"
        structure_color = "#a0aec0"
    
    # ============================================
    # 2. DISPLAY LEVELS
    # ============================================
    
    st.markdown(f"### 📊 Current SMC Levels - {asset_name}")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Current Price", f"{current_price:.2f}")
        st.metric("Structure", structure, delta_color="normal")
    
    with col2:
        st.metric("Previous Day High", f"{prev_high:.2f}" if prev_high else "N/A")
        st.metric("Previous Day Low", f"{prev_low:.2f}" if prev_low else "N/A")
    
    with col3:
        st.metric("Recent Swing High", f"{recent_high:.2f}")
        st.metric("Recent Swing Low", f"{recent_low:.2f}")
    
    # ============================================
    # 3. ORDER BLOCKS
    # ============================================
    
    st.markdown("---")
    st.markdown("### 📦 Order Blocks")
    st.caption("Key levels where institutional orders are placed")
    
    # Find last significant swing high and low
    last_swing_high = last_5_highs[-1][1] if last_5_highs else recent_high
    last_swing_low = last_5_lows[-1][1] if last_5_lows else recent_low
    
    bullish_ob = last_swing_low - 5 if last_swing_low else prev_low
    bearish_ob = last_swing_high + 5 if last_swing_high else prev_high
    
    col_ob1, col_ob2 = st.columns(2)
    
    with col_ob1:
        st.markdown(f"""
        <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
            <h4 style='color: #4ade80;'>🟢 Bullish Order Block</h4>
            <b>Level:</b> {bullish_ob:.2f}<br>
            <b>Meaning:</b> Support zone where buyers are expected<br>
            <b>Use:</b> Watch for price to approach this level<br>
            <b>Entry:</b> Price bounce + VWAP/EMA confirmation
        </div>
        """, unsafe_allow_html=True)
    
    with col_ob2:
        st.markdown(f"""
        <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
            <h4 style='color: #f87171;'>🔴 Bearish Order Block</h4>
            <b>Level:</b> {bearish_ob:.2f}<br>
            <b>Meaning:</b> Resistance zone where sellers are expected<br>
            <b>Use:</b> Watch for price to approach this level<br>
            <b>Entry:</b> Price rejection + VWAP/EMA confirmation
        </div>
        """, unsafe_allow_html=True)
    
    # ============================================
    # 4. FAIR VALUE GAPS (Simplified)
    # ============================================
    
    st.markdown("---")
    st.markdown("### 🔲 Fair Value Gaps")
    st.caption("Price imbalances that often get filled (price returns to these levels)")
    
    fvgs_found = False
    
    if len(data) > 5:
        for i in range(2, len(data) - 1):
            if data['Low'].iloc[i] > data['High'].iloc[i-2]:
                bullish_fvg_top = data['Low'].iloc[i]
                bullish_fvg_bottom = data['High'].iloc[i-2]
                
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 10px; border-radius: 8px; border-left: 4px solid #4ade80; margin-bottom: 10px;'>
                    <h4 style='color: #4ade80;'>🟢 Bullish FVG</h4>
                    <b>Level:</b> {bullish_fvg_bottom:.2f} - {bullish_fvg_top:.2f}<br>
                    <b>Status:</b> {'✅ Filled' if current_price > bullish_fvg_top else '⏳ Pending (price may return)'}<br>
                    <b>Use:</b> {'Support zone' if current_price > bullish_fvg_top else 'Potential target area'}
                </div>
                """, unsafe_allow_html=True)
                fvgs_found = True
                break
        
        if not fvgs_found:
            for i in range(2, len(data) - 1):
                if data['High'].iloc[i] < data['Low'].iloc[i-2]:
                    bearish_fvg_top = data['Low'].iloc[i-2]
                    bearish_fvg_bottom = data['High'].iloc[i]
                    
                    st.markdown(f"""
                    <div style='background-color: #3a1a1a; padding: 10px; border-radius: 8px; border-left: 4px solid #f87171; margin-bottom: 10px;'>
                        <h4 style='color: #f87171;'>🔴 Bearish FVG</h4>
                        <b>Level:</b> {bearish_fvg_bottom:.2f} - {bearish_fvg_top:.2f}<br>
                        <b>Status:</b> {'✅ Filled' if current_price < bearish_fvg_bottom else '⏳ Pending (price may return)'}<br>
                        <b>Use:</b> {'Resistance zone' if current_price < bearish_fvg_bottom else 'Potential target area'}
                    </div>
                    """, unsafe_allow_html=True)
                    fvgs_found = True
                    break
    
    if not fvgs_found:
        st.info("⏳ No recent Fair Value Gaps detected. Market is balanced.")
    
    # ============================================
    # 5. PREMIUM/DISCOUNT ZONES
    # ============================================
    
    st.markdown("---")
    st.markdown("### 📊 Premium & Discount Zones")
    st.caption("Price ranges based on the recent swing range")
    
    range_high = recent_high if recent_high else current_price + 100
    range_low = recent_low if recent_low else current_price - 100
    range_mid = (range_high + range_low) / 2
    
    premium_zone_bottom = range_mid + (range_high - range_mid) * 0.382
    discount_zone_top = range_mid - (range_mid - range_low) * 0.382
    
    if current_price > premium_zone_bottom:
        zone = "🔴 PREMIUM ZONE (Overbought)"
        zone_color = "#f87171"
        action = "⚠️ Avoid buying, consider shorting at rejection"
    elif current_price < discount_zone_top:
        zone = "🟢 DISCOUNT ZONE (Oversold)"
        zone_color = "#4ade80"
        action = "✅ Good area to look for longs"
    else:
        zone = "⚪ EQUILIBRIUM ZONE (Fair Value)"
        zone_color = "#facc15"
        action = "⚖️ Wait for pullback to discount or premium"
    
    col_z1, col_z2, col_z3 = st.columns(3)
    
    with col_z1:
        st.metric("Premium Zone", f"{premium_zone_bottom:.2f} - {range_high:.2f}")
    with col_z2:
        st.metric("Equilibrium", f"{range_mid:.2f}")
    with col_z3:
        st.metric("Discount Zone", f"{range_low:.2f} - {discount_zone_top:.2f}")
    
    st.markdown(f"""
    <div style='background-color: #1c2129; padding: 15px; border-radius: 8px; margin-top: 10px;'>
        <h4 style='color: {zone_color};'>📍 Current Zone: {zone}</h4>
        <p style='color: #e8ecf1;'><b>Action:</b> {action}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # ============================================
    # 6. STRUCTURE SUMMARY
    # ============================================
    
    st.markdown("---")
    st.markdown("### 📈 Structure Summary")
    
    col_s1, col_s2 = st.columns(2)
    
    with col_s1:
        st.markdown("#### Recent Swing Points")
        
        if last_5_highs:
            st.markdown("**Recent Highs:**")
            for i, (time_val, price) in enumerate(last_5_highs[-3:]):
                if len(last_5_highs) > 3 and i == 0:
                    label = "HH" if price > last_5_highs[-4][1] else "LH"
                else:
                    label = "H"
                st.caption(f"{label}: {price:.2f}")
        
        if last_5_lows:
            st.markdown("**Recent Lows:**")
            for i, (time_val, price) in enumerate(last_5_lows[-3:]):
                if len(last_5_lows) > 3 and i == 0:
                    label = "HL" if price > last_5_lows[-4][1] else "LL"
                else:
                    label = "L"
                st.caption(f"{label}: {price:.2f}")
    
    with col_s2:
        st.markdown("#### Trend Analysis")
        
        data_15m = yf.Ticker(ticker).history(period="5d", interval="15m")
        if not data_15m.empty:
            ema9 = data_15m['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
            ema20 = data_15m['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
            ema50 = data_15m['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
            
            trend_score = 0
            if current_price > ema9: trend_score += 1
            if current_price > ema20: trend_score += 1
            if current_price > ema50: trend_score += 1
            if ema9 > ema20: trend_score += 1
            if ema20 > ema50: trend_score += 1
            
            if trend_score >= 4:
                trend = "🟢 STRONG BULLISH"
                trend_color = "#4ade80"
            elif trend_score >= 3:
                trend = "🟡 BULLISH"
                trend_color = "#facc15"
            elif trend_score >= 2:
                trend = "🟠 BEARISH"
                trend_color = "#facc15"
            else:
                trend = "🔴 STRONG BEARISH"
                trend_color = "#f87171"
            
            st.markdown(f"**Trend:** <span style='color: {trend_color};'>{trend}</span>", unsafe_allow_html=True)
            st.caption(f"9 EMA: {ema9:.2f} | 20 EMA: {ema20:.2f} | 50 EMA: {ema50:.2f}")
    
    # ============================================
    # 7. TRADE SETUP SUGGESTIONS
    # ============================================
    
    st.markdown("---")
    st.markdown("### 🎯 Trade Setup Suggestions")
    
    suggestions = []
    
    intraday = get_intraday_data(ticker)
    if "error" not in intraday:
        vwap = intraday['vwap']
        
        if current_price < discount_zone_top and current_price > vwap:
            suggestions.append("✅ Price in DISCOUNT zone AND above VWAP - Strong LONG setup")
        elif current_price < discount_zone_top and current_price < vwap:
            suggestions.append("⚠️ Price in DISCOUNT zone but below VWAP - Wait for VWAP reclaim")
        elif current_price > premium_zone_bottom and current_price < vwap:
            suggestions.append("✅ Price in PREMIUM zone AND below VWAP - Strong SHORT setup")
        elif current_price > premium_zone_bottom and current_price > vwap:
            suggestions.append("⚠️ Price in PREMIUM zone but above VWAP - Wait for VWAP break")
        
        if bullish_ob and current_price < bullish_ob + 10 and current_price > vwap:
            suggestions.append("✅ Price near Bullish Order Block + above VWAP - Watch for bounce")
        if bearish_ob and current_price > bearish_ob - 10 and current_price < vwap:
            suggestions.append("✅ Price near Bearish Order Block + below VWAP - Watch for rejection")
        
        if is_bullish and current_price > vwap:
            suggestions.append("✅ BULLISH structure + Price above VWAP - Trend continuation likely")
        if is_bearish and current_price < vwap:
            suggestions.append("✅ BEARISH structure + Price below VWAP - Trend continuation likely")
    
    if suggestions:
        for suggestion in suggestions:
            if "✅" in suggestion:
                st.markdown(f"<div style='background-color: #1a3a2a; padding: 8px; border-radius: 4px; margin-bottom: 5px; color: #4ade80;'>{suggestion}</div>", unsafe_allow_html=True)
            elif "⚠️" in suggestion:
                st.markdown(f"<div style='background-color: #3a2a1a; padding: 8px; border-radius: 4px; margin-bottom: 5px; color: #facc15;'>{suggestion}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='background-color: #1c2129; padding: 8px; border-radius: 4px; margin-bottom: 5px; color: #e8ecf1;'>{suggestion}</div>", unsafe_allow_html=True)
    else:
        st.info("⏳ No clear setups at the moment. Wait for price to reach key levels.")
    
    # ============================================
    # 8. SUMMARY CARD
    # ============================================
    
    st.markdown("---")
    st.markdown("### 📝 Quick Summary")
    
    col_sum1, col_sum2 = st.columns(2)
    
    with col_sum1:
        st.markdown(f"""
        <div style='background-color: #1c2129; padding: 15px; border-radius: 8px;'>
            <h4 style='color: #60a5fa;'>📈 Structure</h4>
            <p style='color: #e8ecf1;'>{structure}<br>
            HH/HL = Bullish | LH/LL = Bearish</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col_sum2:
        key_level = ""
        if current_price < discount_zone_top:
            key_level = f"🟢 DISCOUNT ({current_price:.2f})"
        elif current_price > premium_zone_bottom:
            key_level = f"🔴 PREMIUM ({current_price:.2f})"
        else:
            key_level = f"⚪ EQUILIBRIUM ({current_price:.2f})"
        
        st.markdown(f"""
        <div style='background-color: #1c2129; padding: 15px; border-radius: 8px;'>
            <h4 style='color: #60a5fa;'>📍 Position</h4>
            <p style='color: #e8ecf1;'>{key_level}<br>
            Use with VWAP for confirmation</p>
        </div>
        """, unsafe_allow_html=True)

# ============ LEVEL MARKER ============
def run_level_marker():
    st.subheader("🎯 Global Session Sniper Triggers")
    
    with st.spinner("AI scanning global session data..."):
        mnq_data = yf.Ticker("MNQ=F").history(period="2d", interval="1m")
        mgc_data = yf.Ticker("MGC=F").history(period="2d", interval="1m")
        sil_data = yf.Ticker("SIL=F").history(period="2d", interval="1m")
        mes_data = yf.Ticker("MES=F").history(period="2d", interval="1m")
    
    if mnq_data.empty or mgc_data.empty or sil_data.empty or mes_data.empty:
        st.warning("No session data available. Market may be closed.")
        return
    
    today = datetime.now().date()
    macro = get_macro_data()
    tnx_val = macro['yield_10y']
    
    tab_london, tab_ny, tab_yesterday = st.tabs(["🇬🇧 London Open Sniper", "🇺🇸 NY Open Sniper", "📅 Yesterday's Full Map"])
    
    with tab_london:
        st.markdown("### 🇬🇧 London Open (2:00 AM EST) Sniper Sheet")
        st.caption("London trades the breakout of the Asia Session High/Low. Use these exact numbers for MNQ, MGC, SIL, and MES.")
        
        mnq_today = mnq_data[mnq_data.index.date == today]
        mnq_prev = mnq_data[mnq_data.index.date == (today - timedelta(days=1))]
        mgc_today = mgc_data[mgc_data.index.date == today]
        mgc_prev = mgc_data[mgc_data.index.date == (today - timedelta(days=1))]
        sil_today = sil_data[sil_data.index.date == today]
        sil_prev = sil_data[sil_data.index.date == (today - timedelta(days=1))]
        mes_today = mes_data[mes_data.index.date == today]
        mes_prev = mes_data[mes_data.index.date == (today - timedelta(days=1))]
        
        buffer = 15
        fakeout_buffer = 5
        
        col_mnq_london, col_mgc_london, col_sil_london, col_mes_london = st.columns(4)
        
        with col_mnq_london:
            st.markdown("#### 📈 MNQ London Triggers")
            asia_mnq = mnq_prev.between_time('17:00', '23:59')
            if not asia_mnq.empty:
                asia_high = asia_mnq['High'].max()
                asia_low = asia_mnq['Low'].min()
                asia_range = asia_high - asia_low
            else:
                asia_high = asia_low = asia_range = 0
            
            current_price = 0
            ny_mnq = mnq_today.between_time('08:00', '09:29')
            if not ny_mnq.empty:
                current_price = ny_mnq['Close'].iloc[-1]
            
            if asia_high > 0 and asia_low > 0:
                if current_price > 0:
                    if current_price > asia_low and current_price < asia_high:
                        st.warning("⛔ **WAIT ZONE:** Price trapped inside Asia Range.")
                    if asia_high - current_price < fakeout_buffer and asia_high - current_price > 0:
                        st.error("⚠️ **FAKEOUT:** Near Asia High.")
                    if current_price - asia_low < fakeout_buffer and current_price - asia_low > 0:
                        st.error("⚠️ **FAKEOUT:** Near Asia Low.")
                
                london_long_entry = asia_high + buffer
                london_long_sl = asia_high - 10
                london_long_tp = london_long_entry + (asia_range * 1.5)
                london_short_entry = asia_low - buffer
                london_short_sl = asia_low + 10
                london_short_tp = london_short_entry - (asia_range * 1.5)
                
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                    <h4 style='color: #4ade80;'>🚀 LONG</h4>
                    <b>Trigger:</b> > {london_long_entry}<br>
                    <b>SL:</b> {london_long_sl}<br>
                    <b>TP:</b> {london_long_tp}
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                    <h4 style='color: #f87171;'>📉 SHORT</h4>
                    <b>Trigger:</b> < {london_short_entry}<br>
                    <b>SL:</b> {london_short_sl}<br>
                    <b>TP:</b> {london_short_tp}
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"Asia Range: {asia_range:.2f} pts")
            else:
                st.info("No Asia data for MNQ.")

        with col_mgc_london:
            st.markdown("#### 🥇 MGC London Triggers")
            asia_mgc = mgc_prev.between_time('17:00', '23:59')
            if not asia_mgc.empty:
                asia_high = asia_mgc['High'].max()
                asia_low = asia_mgc['Low'].min()
                asia_range = asia_high - asia_low
            else:
                asia_high = asia_low = asia_range = 0
            
            current_price = 0
            ny_mgc = mgc_today.between_time('08:00', '09:29')
            if not ny_mgc.empty:
                current_price = ny_mgc['Close'].iloc[-1]
            
            if tnx_val > 4.3:
                st.error("⛔ **HARD STOP:** 10Y Yield > 4.3%. Avoid Gold.")
            elif asia_high > 0 and asia_low > 0:
                if current_price > 0:
                    if current_price > asia_low and current_price < asia_high:
                        st.warning("⛔ **WAIT ZONE:** Price trapped inside Asia Range.")
                    if asia_high - current_price < fakeout_buffer and asia_high - current_price > 0:
                        st.error("⚠️ **FAKEOUT:** Near Asia High.")
                    if current_price - asia_low < fakeout_buffer and current_price - asia_low > 0:
                        st.error("⚠️ **FAKEOUT:** Near Asia Low.")
                
                london_long_entry = asia_high + buffer
                london_long_sl = asia_high - 10
                london_long_tp = london_long_entry + (asia_range * 1.5)
                london_short_entry = asia_low - buffer
                london_short_sl = asia_low + 10
                london_short_tp = london_short_entry - (asia_range * 1.5)
                
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                    <h4 style='color: #4ade80;'>🚀 LONG</h4>
                    <b>Trigger:</b> > {london_long_entry}<br>
                    <b>SL:</b> {london_long_sl}<br>
                    <b>TP:</b> {london_long_tp}
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                    <h4 style='color: #f87171;'>📉 SHORT</h4>
                    <b>Trigger:</b> < {london_short_entry}<br>
                    <b>SL:</b> {london_short_sl}<br>
                    <b>TP:</b> {london_short_tp}
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"Asia Range: {asia_range:.2f} pts")
            else:
                st.info("No Asia data for MGC.")

        with col_sil_london:
            st.markdown("#### 🥈 SIL London Triggers")
            asia_sil = sil_prev.between_time('17:00', '23:59')
            if not asia_sil.empty:
                asia_high = asia_sil['High'].max()
                asia_low = asia_sil['Low'].min()
                asia_range = asia_high - asia_low
            else:
                asia_high = asia_low = asia_range = 0
            
            current_price = 0
            ny_sil = sil_today.between_time('08:00', '09:29')
            if not ny_sil.empty:
                current_price = ny_sil['Close'].iloc[-1]
            
            if tnx_val > 4.3:
                st.error("⛔ **HARD STOP:** 10Y Yield > 4.3%. Avoid Silver.")
            elif asia_high > 0 and asia_low > 0:
                if current_price > 0:
                    if current_price > asia_low and current_price < asia_high:
                        st.warning("⛔ **WAIT ZONE:** Price trapped inside Asia Range.")
                    if asia_high - current_price < fakeout_buffer and asia_high - current_price > 0:
                        st.error("⚠️ **FAKEOUT:** Near Asia High.")
                    if current_price - asia_low < fakeout_buffer and current_price - asia_low > 0:
                        st.error("⚠️ **FAKEOUT:** Near Asia Low.")
                
                london_long_entry = asia_high + buffer
                london_long_sl = asia_high - 10
                london_long_tp = london_long_entry + (asia_range * 1.5)
                london_short_entry = asia_low - buffer
                london_short_sl = asia_low + 10
                london_short_tp = london_short_entry - (asia_range * 1.5)
                
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                    <h4 style='color: #4ade80;'>🚀 LONG</h4>
                    <b>Trigger:</b> > {london_long_entry}<br>
                    <b>SL:</b> {london_long_sl}<br>
                    <b>TP:</b> {london_long_tp}
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                    <h4 style='color: #f87171;'>📉 SHORT</h4>
                    <b>Trigger:</b> < {london_short_entry}<br>
                    <b>SL:</b> {london_short_sl}<br>
                    <b>TP:</b> {london_short_tp}
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"Asia Range: {asia_range:.2f} pts")
            else:
                st.info("No Asia data for SIL.")

        with col_mes_london:
            st.markdown("#### 📈 MES London Triggers")
            asia_mes = mes_prev.between_time('17:00', '23:59')
            if not asia_mes.empty:
                asia_high = asia_mes['High'].max()
                asia_low = asia_mes['Low'].min()
                asia_range = asia_high - asia_low
            else:
                asia_high = asia_low = asia_range = 0
            
            current_price = 0
            ny_mes = mes_today.between_time('08:00', '09:29')
            if not ny_mes.empty:
                current_price = ny_mes['Close'].iloc[-1]
            
            if asia_high > 0 and asia_low > 0:
                if current_price > 0:
                    if current_price > asia_low and current_price < asia_high:
                        st.warning("⛔ **WAIT ZONE:** Price trapped inside Asia Range.")
                    if asia_high - current_price < fakeout_buffer and asia_high - current_price > 0:
                        st.error("⚠️ **FAKEOUT:** Near Asia High.")
                    if current_price - asia_low < fakeout_buffer and current_price - asia_low > 0:
                        st.error("⚠️ **FAKEOUT:** Near Asia Low.")
                
                london_long_entry = asia_high + buffer
                london_long_sl = asia_high - 10
                london_long_tp = london_long_entry + (asia_range * 1.5)
                london_short_entry = asia_low - buffer
                london_short_sl = asia_low + 10
                london_short_tp = london_short_entry - (asia_range * 1.5)
                
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                    <h4 style='color: #4ade80;'>🚀 LONG</h4>
                    <b>Trigger:</b> > {london_long_entry}<br>
                    <b>SL:</b> {london_long_sl}<br>
                    <b>TP:</b> {london_long_tp}
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                    <h4 style='color: #f87171;'>📉 SHORT</h4>
                    <b>Trigger:</b> < {london_short_entry}<br>
                    <b>SL:</b> {london_short_sl}<br>
                    <b>TP:</b> {london_short_tp}
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"Asia Range: {asia_range:.2f} pts")
            else:
                st.info("No Asia data for MES.")

        st.markdown("---")
        st.info("💡 **London Strategy:** London tends to reverse the Asia move. If Asia went up, watch for London to fail at the Asia High and reverse.")

    with tab_ny:
        st.markdown("### 🇺🇸 NY Open (9:30 AM EST) Sniper Sheet")
        st.caption("NY trades the breakout of the NY Pre-Market High/Low. Use these exact numbers.")
        
        mnq_today = mnq_data[mnq_data.index.date == today]
        mnq_prev = mnq_data[mnq_data.index.date == (today - timedelta(days=1))]
        mgc_today = mgc_data[mgc_data.index.date == today]
        mgc_prev = mgc_data[mgc_data.index.date == (today - timedelta(days=1))]
        sil_today = sil_data[sil_data.index.date == today]
        sil_prev = sil_data[sil_data.index.date == (today - timedelta(days=1))]
        mes_today = mes_data[mes_data.index.date == today]
        mes_prev = mes_data[mes_data.index.date == (today - timedelta(days=1))]
        
        buffer = 15
        fakeout_buffer = 5
        
        col_mnq_ny, col_mgc_ny, col_sil_ny, col_mes_ny = st.columns(4)
        
        with col_mnq_ny:
            st.markdown("#### 📈 MNQ NY Triggers")
            ny_mnq = mnq_today.between_time('08:00', '09:29')
            
            if not ny_mnq.empty:
                ny_high = ny_mnq['High'].max()
                ny_low = ny_mnq['Low'].min()
                ny_range = ny_high - ny_low
                current_price = ny_mnq['Close'].iloc[-1]
                st.success(f"✅ NY Pre-Market Range: {ny_high:.2f} - {ny_low:.2f} (Range: {ny_range:.2f} pts)")
            else:
                ny_high = ny_low = ny_range = current_price = 0
                st.info("⏳ NY Pre-Market (8:00-9:29 AM EST) data not yet available. Check back after 1:00 PM UK time.")
            
            if ny_high > 0 and ny_low > 0:
                if current_price > ny_low and current_price < ny_high:
                    st.warning("⛔ **WAIT ZONE:** Price trapped inside NY Range.")
                if ny_high - current_price < fakeout_buffer and ny_high - current_price > 0:
                    st.error("⚠️ **FAKEOUT:** Near NY High.")
                if current_price - ny_low < fakeout_buffer and current_price - ny_low > 0:
                    st.error("⚠️ **FAKEOUT:** Near NY Low.")
                
                ny_long_entry = ny_high + buffer
                ny_long_sl = ny_high - 10
                ny_long_tp = ny_long_entry + (ny_range * 1.5)
                ny_short_entry = ny_low - buffer
                ny_short_sl = ny_low + 10
                ny_short_tp = ny_short_entry - (ny_range * 1.5)
                
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                    <h4 style='color: #4ade80;'>🚀 LONG</h4>
                    <b>Trigger:</b> > {ny_long_entry}<br>
                    <b>SL:</b> {ny_long_sl}<br>
                    <b>TP:</b> {ny_long_tp}
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                    <h4 style='color: #f87171;'>📉 SHORT</h4>
                    <b>Trigger:</b> < {ny_short_entry}<br>
                    <b>SL:</b> {ny_short_sl}<br>
                    <b>TP:</b> {ny_short_tp}
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"NY Range: {ny_range:.2f} pts")

        with col_mgc_ny:
            st.markdown("#### 🥇 MGC NY Triggers")
            ny_mgc = mgc_today.between_time('08:00', '09:29')
            
            if not ny_mgc.empty:
                ny_high = ny_mgc['High'].max()
                ny_low = ny_mgc['Low'].min()
                ny_range = ny_high - ny_low
                current_price = ny_mgc['Close'].iloc[-1]
                st.success(f"✅ NY Pre-Market Range: {ny_high:.2f} - {ny_low:.2f} (Range: {ny_range:.2f} pts)")
            else:
                ny_high = ny_low = ny_range = current_price = 0
                st.info("⏳ NY Pre-Market data not yet available.")
            
            if tnx_val > 4.3:
                st.error("⛔ **HARD STOP:** 10Y Yield > 4.3%. Avoid Gold.")
            elif ny_high > 0 and ny_low > 0:
                if current_price > ny_low and current_price < ny_high:
                    st.warning("⛔ **WAIT ZONE:** Price trapped inside NY Range.")
                if ny_high - current_price < fakeout_buffer and ny_high - current_price > 0:
                    st.error("⚠️ **FAKEOUT:** Near NY High.")
                if current_price - ny_low < fakeout_buffer and current_price - ny_low > 0:
                    st.error("⚠️ **FAKEOUT:** Near NY Low.")
                
                ny_long_entry = ny_high + buffer
                ny_long_sl = ny_high - 10
                ny_long_tp = ny_long_entry + (ny_range * 1.5)
                ny_short_entry = ny_low - buffer
                ny_short_sl = ny_low + 10
                ny_short_tp = ny_short_entry - (ny_range * 1.5)
                
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                    <h4 style='color: #4ade80;'>🚀 LONG</h4>
                    <b>Trigger:</b> > {ny_long_entry}<br>
                    <b>SL:</b> {ny_long_sl}<br>
                    <b>TP:</b> {ny_long_tp}
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                    <h4 style='color: #f87171;'>📉 SHORT</h4>
                    <b>Trigger:</b> < {ny_short_entry}<br>
                    <b>SL:</b> {ny_short_sl}<br>
                    <b>TP:</b> {ny_short_tp}
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"NY Range: {ny_range:.2f} pts")

        with col_sil_ny:
            st.markdown("#### 🥈 SIL NY Triggers")
            ny_sil = sil_today.between_time('08:00', '09:29')
            
            if not ny_sil.empty:
                ny_high = ny_sil['High'].max()
                ny_low = ny_sil['Low'].min()
                ny_range = ny_high - ny_low
                current_price = ny_sil['Close'].iloc[-1]
                st.success(f"✅ NY Pre-Market Range: {ny_high:.2f} - {ny_low:.2f}")
            else:
                ny_high = ny_low = ny_range = current_price = 0
                st.info("⏳ NY Pre-Market data not yet available.")
            
            if tnx_val > 4.3:
                st.error("⛔ **HARD STOP:** 10Y Yield > 4.3%. Avoid Silver.")
            elif ny_high > 0 and ny_low > 0:
                if current_price > ny_low and current_price < ny_high:
                    st.warning("⛔ **WAIT ZONE:** Price trapped inside NY Range.")
                if ny_high - current_price < fakeout_buffer and ny_high - current_price > 0:
                    st.error("⚠️ **FAKEOUT:** Near NY High.")
                if current_price - ny_low < fakeout_buffer and current_price - ny_low > 0:
                    st.error("⚠️ **FAKEOUT:** Near NY Low.")
                
                ny_long_entry = ny_high + buffer
                ny_long_sl = ny_high - 10
                ny_long_tp = ny_long_entry + (ny_range * 1.5)
                ny_short_entry = ny_low - buffer
                ny_short_sl = ny_low + 10
                ny_short_tp = ny_short_entry - (ny_range * 1.5)
                
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                    <h4 style='color: #4ade80;'>🚀 LONG</h4>
                    <b>Trigger:</b> > {ny_long_entry}<br>
                    <b>SL:</b> {ny_long_sl}<br>
                    <b>TP:</b> {ny_long_tp}
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                    <h4 style='color: #f87171;'>📉 SHORT</h4>
                    <b>Trigger:</b> < {ny_short_entry}<br>
                    <b>SL:</b> {ny_short_sl}<br>
                    <b>TP:</b> {ny_short_tp}
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"NY Range: {ny_range:.2f} pts")

        with col_mes_ny:
            st.markdown("#### 📈 MES NY Triggers")
            ny_mes = mes_today.between_time('08:00', '09:29')
            
            if not ny_mes.empty:
                ny_high = ny_mes['High'].max()
                ny_low = ny_mes['Low'].min()
                ny_range = ny_high - ny_low
                current_price = ny_mes['Close'].iloc[-1]
                st.success(f"✅ NY Pre-Market Range: {ny_high:.2f} - {ny_low:.2f}")
            else:
                ny_high = ny_low = ny_range = current_price = 0
                st.info("⏳ NY Pre-Market data not yet available.")
            
            if ny_high > 0 and ny_low > 0:
                if current_price > ny_low and current_price < ny_high:
                    st.warning("⛔ **WAIT ZONE:** Price trapped inside NY Range.")
                if ny_high - current_price < fakeout_buffer and ny_high - current_price > 0:
                    st.error("⚠️ **FAKEOUT:** Near NY High.")
                if current_price - ny_low < fakeout_buffer and current_price - ny_low > 0:
                    st.error("⚠️ **FAKEOUT:** Near NY Low.")
                
                ny_long_entry = ny_high + buffer
                ny_long_sl = ny_high - 10
                ny_long_tp = ny_long_entry + (ny_range * 1.5)
                ny_short_entry = ny_low - buffer
                ny_short_sl = ny_low + 10
                ny_short_tp = ny_short_entry - (ny_range * 1.5)
                
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                    <h4 style='color: #4ade80;'>🚀 LONG</h4>
                    <b>Trigger:</b> > {ny_long_entry}<br>
                    <b>SL:</b> {ny_long_sl}<br>
                    <b>TP:</b> {ny_long_tp}
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                    <h4 style='color: #f87171;'>📉 SHORT</h4>
                    <b>Trigger:</b> < {ny_short_entry}<br>
                    <b>SL:</b> {ny_short_sl}<br>
                    <b>TP:</b> {ny_short_tp}
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"NY Range: {ny_range:.2f} pts")

        st.markdown("---")
        st.info("💡 **NY Strategy:** The NY Pre-Market Range sets the battlefield for the first 30 minutes.")

    with tab_yesterday:
        st.markdown("### 📅 Yesterday's Complete Session Map")
        st.caption("Highs, Lows, Ranges, and 50% Reversal Zones for Asia, London, and NY.")
        
        mnq_prev = mnq_data[mnq_data.index.date == (today - timedelta(days=1))]
        mgc_prev = mgc_data[mgc_data.index.date == (today - timedelta(days=1))]
        sil_prev = sil_data[sil_data.index.date == (today - timedelta(days=1))]
        mes_prev = mes_data[mes_data.index.date == (today - timedelta(days=1))]

        st.subheader("📈 MNQ (Micro Nasdaq) - Yesterday")
        if not mnq_prev.empty:
            asia_y_mnq = mnq_prev.between_time('17:00', '23:59')
            if not asia_y_mnq.empty:
                asia_y_high = asia_y_mnq['High'].max()
                asia_y_low = asia_y_mnq['Low'].min()
                asia_y_range = asia_y_high - asia_y_low
                asia_y_sell_zone = asia_y_high + (asia_y_range * 0.5)
                asia_y_buy_zone = asia_y_low - (asia_y_range * 0.5)
            else:
                asia_y_high = asia_y_low = asia_y_sell_zone = asia_y_buy_zone = 0
            
            st.markdown("#### 🌏 Asia Session")
            c_a1, c_a2, c_a3, c_a4 = st.columns(4)
            with c_a1: st.metric("High", f"{asia_y_high:.2f}" if asia_y_high else "N/A")
            with c_a2: st.metric("Low", f"{asia_y_low:.2f}" if asia_y_low else "N/A")
            with c_a3: st.metric("Sell Zone", f"{asia_y_sell_zone:.2f}" if asia_y_sell_zone else "N/A")
            with c_a4: st.metric("Buy Zone", f"{asia_y_buy_zone:.2f}" if asia_y_buy_zone else "N/A")

            london_y_mnq = mnq_prev.between_time('02:00', '09:29')
            st.markdown("---")
            st.markdown("#### 🌍 London Session")
            c_l1, c_l2, c_l3, c_l4 = st.columns(4)
            with c_l1: st.metric("High", f"{london_y_mnq['High'].max():.2f}" if not london_y_mnq.empty else "N/A")
            with c_l2: st.metric("Low", f"{london_y_mnq['Low'].min():.2f}" if not london_y_mnq.empty else "N/A")
            with c_l3: st.metric("Range", f"{london_y_mnq['High'].max() - london_y_mnq['Low'].min():.2f}" if not london_y_mnq.empty else "N/A")
            with c_l4: st.caption("Use 50% extension of NY")
            
            ny_y_mnq = mnq_prev.between_time('08:00', '09:29')
            st.markdown("---")
            st.markdown("#### 🇺🇸 NY Pre-Market")
            c_n1, c_n2, c_n3, c_n4 = st.columns(4)
            with c_n1: st.metric("High", f"{ny_y_mnq['High'].max():.2f}" if not ny_y_mnq.empty else "N/A")
            with c_n2: st.metric("Low", f"{ny_y_mnq['Low'].min():.2f}" if not ny_y_mnq.empty else "N/A")
            with c_n3: st.metric("Range", f"{ny_y_mnq['High'].max() - ny_y_mnq['Low'].min():.2f}" if not ny_y_mnq.empty else "N/A")
            with c_n4: st.caption("Today's NY Sniper is built on this")
        else:
            st.info("No previous day data available for MNQ.")

        st.markdown("---")
        
        st.subheader("🥇 MGC (Micro Gold) - Yesterday")
        if not mgc_prev.empty:
            asia_y_mgc = mgc_prev.between_time('17:00', '23:59')
            if not asia_y_mgc.empty:
                asia_y_high = asia_y_mgc['High'].max()
                asia_y_low = asia_y_mgc['Low'].min()
                asia_y_range = asia_y_high - asia_y_low
                asia_y_sell_zone = asia_y_high + (asia_y_range * 0.5)
                asia_y_buy_zone = asia_y_low - (asia_y_range * 0.5)
            else:
                asia_y_high = asia_y_low = asia_y_sell_zone = asia_y_buy_zone = 0
            
            st.markdown("#### 🌏 Asia Session")
            c_a1, c_a2, c_a3, c_a4 = st.columns(4)
            with c_a1: st.metric("High", f"{asia_y_high:.2f}" if asia_y_high else "N/A")
            with c_a2: st.metric("Low", f"{asia_y_low:.2f}" if asia_y_low else "N/A")
            with c_a3: st.metric("Sell Zone", f"{asia_y_sell_zone:.2f}" if asia_y_sell_zone else "N/A")
            with c_a4: st.metric("Buy Zone", f"{asia_y_buy_zone:.2f}" if asia_y_buy_zone else "N/A")

            london_y_mgc = mgc_prev.between_time('02:00', '09:29')
            st.markdown("---")
            st.markdown("#### 🌍 London Session")
            c_l1, c_l2, c_l3, c_l4 = st.columns(4)
            with c_l1: st.metric("High", f"{london_y_mgc['High'].max():.2f}" if not london_y_mgc.empty else "N/A")
            with c_l2: st.metric("Low", f"{london_y_mgc['Low'].min():.2f}" if not london_y_mgc.empty else "N/A")
            with c_l3: st.metric("Range", f"{london_y_mgc['High'].max() - london_y_mgc['Low'].min():.2f}" if not london_y_mgc.empty else "N/A")
            with c_l4: st.caption("Use 50% extension of NY")
            
            ny_y_mgc = mgc_prev.between_time('08:00', '09:29')
            st.markdown("---")
            st.markdown("#### 🇺🇸 NY Pre-Market")
            c_n1, c_n2, c_n3, c_n4 = st.columns(4)
            with c_n1: st.metric("High", f"{ny_y_mgc['High'].max():.2f}" if not ny_y_mgc.empty else "N/A")
            with c_n2: st.metric("Low", f"{ny_y_mgc['Low'].min():.2f}" if not ny_y_mgc.empty else "N/A")
            with c_n3: st.metric("Range", f"{ny_y_mgc['High'].max() - ny_y_mgc['Low'].min():.2f}" if not ny_y_mgc.empty else "N/A")
            with c_n4: st.caption("Today's NY Sniper is built on this")
        else:
            st.info("No previous day data available for MGC.")

        st.markdown("---")
        
        st.subheader("🥈 SIL (Micro Silver) - Yesterday")
        if not sil_prev.empty:
            asia_y_sil = sil_prev.between_time('17:00', '23:59')
            if not asia_y_sil.empty:
                asia_y_high = asia_y_sil['High'].max()
                asia_y_low = asia_y_sil['Low'].min()
                asia_y_range = asia_y_high - asia_y_low
                asia_y_sell_zone = asia_y_high + (asia_y_range * 0.5)
                asia_y_buy_zone = asia_y_low - (asia_y_range * 0.5)
            else:
                asia_y_high = asia_y_low = asia_y_sell_zone = asia_y_buy_zone = 0
            
            st.markdown("#### 🌏 Asia Session")
            c_a1, c_a2, c_a3, c_a4 = st.columns(4)
            with c_a1: st.metric("High", f"{asia_y_high:.2f}" if asia_y_high else "N/A")
            with c_a2: st.metric("Low", f"{asia_y_low:.2f}" if asia_y_low else "N/A")
            with c_a3: st.metric("Sell Zone", f"{asia_y_sell_zone:.2f}" if asia_y_sell_zone else "N/A")
            with c_a4: st.metric("Buy Zone", f"{asia_y_buy_zone:.2f}" if asia_y_buy_zone else "N/A")

            london_y_sil = sil_prev.between_time('02:00', '09:29')
            st.markdown("---")
            st.markdown("#### 🌍 London Session")
            c_l1, c_l2, c_l3, c_l4 = st.columns(4)
            with c_l1: st.metric("High", f"{london_y_sil['High'].max():.2f}" if not london_y_sil.empty else "N/A")
            with c_l2: st.metric("Low", f"{london_y_sil['Low'].min():.2f}" if not london_y_sil.empty else "N/A")
            with c_l3: st.metric("Range", f"{london_y_sil['High'].max() - london_y_sil['Low'].min():.2f}" if not london_y_sil.empty else "N/A")
            with c_l4: st.caption("Use 50% extension of NY")
            
            ny_y_sil = sil_prev.between_time('08:00', '09:29')
            st.markdown("---")
            st.markdown("#### 🇺🇸 NY Pre-Market")
            c_n1, c_n2, c_n3, c_n4 = st.columns(4)
            with c_n1: st.metric("High", f"{ny_y_sil['High'].max():.2f}" if not ny_y_sil.empty else "N/A")
            with c_n2: st.metric("Low", f"{ny_y_sil['Low'].min():.2f}" if not ny_y_sil.empty else "N/A")
            with c_n3: st.metric("Range", f"{ny_y_sil['High'].max() - ny_y_sil['Low'].min():.2f}" if not ny_y_sil.empty else "N/A")
            with c_n4: st.caption("Today's NY Sniper is built on this")
        else:
            st.info("No previous day data available for SIL.")
            
        st.markdown("---")

        st.subheader("📈 MES (Micro S&P 500) - Yesterday")
        if not mes_prev.empty:
            asia_y_mes = mes_prev.between_time('17:00', '23:59')
            if not asia_y_mes.empty:
                asia_y_high = asia_y_mes['High'].max()
                asia_y_low = asia_y_mes['Low'].min()
                asia_y_range = asia_y_high - asia_y_low
                asia_y_sell_zone = asia_y_high + (asia_y_range * 0.5)
                asia_y_buy_zone = asia_y_low - (asia_y_range * 0.5)
            else:
                asia_y_high = asia_y_low = asia_y_sell_zone = asia_y_buy_zone = 0
            
            st.markdown("#### 🌏 Asia Session")
            c_a1, c_a2, c_a3, c_a4 = st.columns(4)
            with c_a1: st.metric("High", f"{asia_y_high:.2f}" if asia_y_high else "N/A")
            with c_a2: st.metric("Low", f"{asia_y_low:.2f}" if asia_y_low else "N/A")
            with c_a3: st.metric("Sell Zone", f"{asia_y_sell_zone:.2f}" if asia_y_sell_zone else "N/A")
            with c_a4: st.metric("Buy Zone", f"{asia_y_buy_zone:.2f}" if asia_y_buy_zone else "N/A")

            london_y_mes = mes_prev.between_time('02:00', '09:29')
            st.markdown("---")
            st.markdown("#### 🌍 London Session")
            c_l1, c_l2, c_l3, c_l4 = st.columns(4)
            with c_l1: st.metric("High", f"{london_y_mes['High'].max():.2f}" if not london_y_mes.empty else "N/A")
            with c_l2: st.metric("Low", f"{london_y_mes['Low'].min():.2f}" if not london_y_mes.empty else "N/A")
            with c_l3: st.metric("Range", f"{london_y_mes['High'].max() - london_y_mes['Low'].min():.2f}" if not london_y_mes.empty else "N/A")
            with c_l4: st.caption("Use 50% extension of NY")
            
            ny_y_mes = mes_prev.between_time('08:00', '09:29')
            st.markdown("---")
            st.markdown("#### 🇺🇸 NY Pre-Market")
            c_n1, c_n2, c_n3, c_n4 = st.columns(4)
            with c_n1: st.metric("High", f"{ny_y_mes['High'].max():.2f}" if not ny_y_mes.empty else "N/A")
            with c_n2: st.metric("Low", f"{ny_y_mes['Low'].min():.2f}" if not ny_y_mes.empty else "N/A")
            with c_n3: st.metric("Range", f"{ny_y_mes['High'].max() - ny_y_mes['Low'].min():.2f}" if not ny_y_mes.empty else "N/A")
            with c_n4: st.caption("Today's NY Sniper is built on this")
        else:
            st.info("No previous day data available for MES.")
            
        st.markdown("---")
        st.info("💡 **Veteran Tip:** Today's London Sniper trades off the *Asia Range*. Today's NY Sniper trades off the *NY Pre-Market Range*. Use the correct sniper for each session.")

# ============ ASIA SNIPER ENGINE ============
def run_asia_sniper():
    st.subheader("🌏 Asia Session Sniper Triggers")
    st.caption("Sniper triggers for the Nikkei (N225) and KOSPI. Uses today's range if available, otherwise falls back to yesterday's range. Works 24/7.")
    
    with st.spinner("Fetching Asian market data..."):
        n225 = yf.Ticker("EWJ").history(period="5d", interval="5m")
        nk_futures = yf.Ticker("NKD=F").history(period="5d", interval="5m")
        if not nk_futures.empty:
            n225 = nk_futures
            st.info("📊 Using Nikkei Futures (NKD=F) for data")
        elif not n225.empty:
            st.info("📊 Using EWJ (Japan ETF) as proxy for Nikkei 225")
        
        qk1 = yf.Ticker("^KS11").history(period="5d", interval="5m")
        if qk1.empty:
            samsung = yf.Ticker("005930.KS").history(period="5d", interval="5m")
            if not samsung.empty:
                qk1 = samsung
                st.info("📊 Using Samsung (005930.KS) as proxy for KOSPI")
    
    if n225.empty:
        st.warning("Nikkei data unavailable. Please check your internet connection.")
        return
        
    if qk1.empty:
        st.warning("KOSPI data unavailable. Please check your internet connection.")
        return
    
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    if today.weekday() == 0:
        friday = today - timedelta(days=3)
        if not n225[n225.index.date == friday].empty:
            yesterday = friday
            st.info("📅 Monday - Using Friday's data as yesterday's range")
    
    buffer = 15
    fakeout_buffer = 5
    
    now_utc = datetime.now(timezone.utc)
    uk_time = now_utc.astimezone(timezone(timedelta(hours=1)))
    current_hour = uk_time.hour
    asian_market_open = 1 <= current_hour <= 7
    
    col_nikkei, col_kospi = st.columns(2)
    
    with col_nikkei:
        st.markdown("### 📈 Nikkei 225 (Proxy)")
        n225_today = n225[n225.index.date == today]
        n225_yesterday = n225[n225.index.date == yesterday]
        
        if not n225_today.empty and asian_market_open:
            day_high = n225_today['High'].max()
            day_low = n225_today['Low'].min()
            current_price = n225_today['Close'].iloc[-1]
            daily_range = day_high - day_low
            prev_close = n225_yesterday['Close'].iloc[-1] if not n225_yesterday.empty else 0
            data_source = "Today's Live Data"
            st.success(f"✅ **Live Data** - Current: {current_price:.2f} | Range: {day_high:.2f} - {day_low:.2f}")
            
        elif not n225_yesterday.empty:
            day_high = n225_yesterday['High'].max()
            day_low = n225_yesterday['Low'].min()
            daily_range = day_high - day_low
            current_price = n225_yesterday['Close'].iloc[-1]
            prev_close = current_price
            data_source = "Yesterday's Range (Markets Closed)"
            st.info(f"📅 **Using Yesterday's Range** - Close: {current_price:.2f} | Range: {day_high:.2f} - {day_low:.2f}")
            st.caption("Asian markets are currently closed. Triggers based on yesterday's range for US session trading.")
        else:
            day_high = day_low = daily_range = current_price = prev_close = 0
            data_source = "No Data"
            st.warning("No data available for Nikkei.")
        
        if day_high > 0 and day_low > 0 and daily_range > 0:
            st.caption(f"📊 Data Source: {data_source}")
            
            if current_price > 0:
                if current_price > day_low and current_price < day_high:
                    st.warning("⛔ **WAIT ZONE:** Price trapped inside the range.")
                if day_high - current_price < fakeout_buffer and day_high - current_price > 0:
                    st.error("⚠️ **FAKEOUT:** Near Range High.")
                if current_price - day_low < fakeout_buffer and current_price - day_low > 0:
                    st.error("⚠️ **FAKEOUT:** Near Range Low.")
            
            long_entry = day_high + buffer
            long_sl = day_high - 10
            long_tp = long_entry + (daily_range * 1.5)
            short_entry = day_low - buffer
            short_sl = day_low + 10
            short_tp = short_entry - (daily_range * 1.5)
            
            if not asian_market_open:
                st.info("💡 **US Session Trading:** These levels are based on yesterday's Asian range. Use as support/resistance for US session breakouts.")
            
            st.markdown(f"""
            <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                <h4 style='color: #4ade80;'>🚀 LONG BREAKOUT</h4>
                <b>Trigger:</b> > {long_entry}<br>
                <b>SL:</b> {long_sl}<br>
                <b>TP:</b> {long_tp}
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f"""
            <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                <h4 style='color: #f87171;'>📉 SHORT BREAKOUT</h4>
                <b>Trigger:</b> < {short_entry}<br>
                <b>SL:</b> {short_sl}<br>
                <b>TP:</b> {short_tp}
            </div>
            """, unsafe_allow_html=True)
            
            if not asian_market_open:
                st.caption(f"📐 Range: {daily_range:.2f} pts | Yesterday's Close: {prev_close:.2f}")
                st.caption("💡 These levels are valid for the entire US session until Asian markets reopen.")
            else:
                st.caption(f"📐 Daily Range: {daily_range:.2f} pts | Prev Close: {prev_close:.2f}")
        else:
            st.info("No range data available. Check back when markets are open.")

    with col_kospi:
        st.markdown("### 📉 KOSPI (^KS11)")
        qk1_today = qk1[qk1.index.date == today]
        qk1_yesterday = qk1[qk1.index.date == yesterday]
        
        if not qk1_today.empty and asian_market_open:
            day_high = qk1_today['High'].max()
            day_low = qk1_today['Low'].min()
            current_price = qk1_today['Close'].iloc[-1]
            daily_range = day_high - day_low
            prev_close = qk1_yesterday['Close'].iloc[-1] if not qk1_yesterday.empty else 0
            data_source = "Today's Live Data"
            st.success(f"✅ **Live Data** - Current: {current_price:.2f} | Range: {day_high:.2f} - {day_low:.2f}")
            
        elif not qk1_yesterday.empty:
            day_high = qk1_yesterday['High'].max()
            day_low = qk1_yesterday['Low'].min()
            daily_range = day_high - day_low
            current_price = qk1_yesterday['Close'].iloc[-1]
            prev_close = current_price
            data_source = "Yesterday's Range (Markets Closed)"
            st.info(f"📅 **Using Yesterday's Range** - Close: {current_price:.2f} | Range: {day_high:.2f} - {day_low:.2f}")
            st.caption("Asian markets are currently closed. Triggers based on yesterday's range for US session trading.")
        else:
            day_high = day_low = daily_range = current_price = prev_close = 0
            data_source = "No Data"
            st.warning("No data available for KOSPI.")
        
        if day_high > 0 and day_low > 0 and daily_range > 0:
            st.caption(f"📊 Data Source: {data_source}")
            
            if current_price > 0:
                if current_price > day_low and current_price < day_high:
                    st.warning("⛔ **WAIT ZONE:** Price trapped inside the range.")
                if day_high - current_price < fakeout_buffer and day_high - current_price > 0:
                    st.error("⚠️ **FAKEOUT:** Near Range High.")
                if current_price - day_low < fakeout_buffer and current_price - day_low > 0:
                    st.error("⚠️ **FAKEOUT:** Near Range Low.")
            
            long_entry = day_high + buffer
            long_sl = day_high - 10
            long_tp = long_entry + (daily_range * 1.5)
            short_entry = day_low - buffer
            short_sl = day_low + 10
            short_tp = short_entry - (daily_range * 1.5)
            
            if not asian_market_open:
                st.info("💡 **US Session Trading:** These levels are based on yesterday's Asian range. Use as support/resistance for US session breakouts.")
            
            st.markdown(f"""
            <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                <h4 style='color: #4ade80;'>🚀 LONG BREAKOUT</h4>
                <b>Trigger:</b> > {long_entry}<br>
                <b>SL:</b> {long_sl}<br>
                <b>TP:</b> {long_tp}
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f"""
            <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                <h4 style='color: #f87171;'>📉 SHORT BREAKOUT</h4>
                <b>Trigger:</b> < {short_entry}<br>
                <b>SL:</b> {short_sl}<br>
                <b>TP:</b> {short_tp}
            </div>
            """, unsafe_allow_html=True)
            
            if not asian_market_open:
                st.caption(f"📐 Range: {daily_range:.2f} pts | Yesterday's Close: {prev_close:.2f}")
                st.caption("💡 These levels are valid for the entire US session until Asian markets reopen.")
            else:
                st.caption(f"📐 Daily Range: {daily_range:.2f} pts | Prev Close: {prev_close:.2f}")
        else:
            st.info("No range data available. Check back when markets are open.")
    
    st.markdown("---")
    st.info("""
    💡 **US Session Trading Strategy:**
    - When Asian markets are closed, the sniper uses **yesterday's Asian range**
    - These levels act as **Support/Resistance** for the US session
    - Look for breakouts above yesterday's High or below yesterday's Low
    - The 15-point buffer helps filter out false breakouts
    - These levels remain valid until Asian markets reopen the next day
    """)

# ============ TRADING JOURNAL ============
DB_JOURNAL_PATH = Path("trading_journal.db")
def init_journal_db():
    conn = sqlite3.connect(DB_JOURNAL_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_utc TEXT NOT NULL,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        entry_price REAL NOT NULL,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        exit_price REAL,
        pnl REAL,
        outcome TEXT,
        macro_snapshot TEXT,
        notes TEXT
    )
    """)
    conn.commit()
    conn.close()

def save_trade(symbol, direction, entry, sl, tp, macro_data, notes):
    conn = sqlite3.connect(DB_JOURNAL_PATH)
    macro_json = json.dumps(macro_data)
    conn.execute("""
    INSERT INTO trades (ts_utc, symbol, direction, entry_price, stop_loss, take_profit, macro_snapshot, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now(timezone.utc).isoformat(), symbol, direction, entry, sl, tp, macro_json, notes))
    conn.commit()
    conn.close()

def get_recent_trades(limit=20):
    conn = sqlite3.connect(DB_JOURNAL_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
    SELECT id, ts_utc, symbol, direction, entry_price, stop_loss, take_profit, exit_price, outcome, pnl, macro_snapshot, notes 
    FROM trades ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def run_journal_tab():
    st.subheader("📝 Private Discretionary Trading Journal")
    st.caption("Log your macro context, entries, and 'gut feelings' to build your ultimate rulebook.")
    
    macro = get_macro_data()
    
    with st.expander("➕ Log New Trade Entry", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            j_symbol = st.selectbox("Symbol", ["MNQ", "MGC", "MES", "NVDA", "SMH"])
            j_direction = st.selectbox("Direction", ["Long (Buy)", "Short (Sell)"])
        with c2:
            j_entry = st.number_input("Entry Price", step=0.25)
            j_stop = st.number_input("Stop Loss", step=0.25)
        with c3:
            j_target = st.number_input("Take Profit", step=0.25)
        
        st.markdown("#### 🧠 Entry Rationale & Gut Check")
        j_notes = st.text_area("Why did you take this trade? Did the price action feel right, or wrong?", height=100)
        
        if st.button("📌 Log This Trade", type="primary"):
            macro_snap = {
                "dxy": macro['dxy'],
                "yield_10y": macro['yield_10y'],
                "yield_30y": macro['yield_30y'],
                "vix": macro['vix']
            }
            save_trade(j_symbol, j_direction, j_entry, j_stop, j_target, macro_snap, j_notes)
            st.success("Trade logged successfully!")
            st.rerun()
    
    st.markdown("---")
    st.subheader("📊 Recent Trade History")
    trades = get_recent_trades(20)
    
    if trades:
        df = pd.DataFrame(trades)
        df['ts_utc'] = pd.to_datetime(df['ts_utc']).dt.strftime('%Y-%m-%d %H:%M')
        
        st.dataframe(df[['ts_utc', 'symbol', 'direction', 'entry_price', 'stop_loss', 'take_profit', 'outcome']], width='stretch', hide_index=True)
        
        st.markdown("#### 📖 Expand to Read Entry Notes")
        for trade in trades[:3]:
            with st.expander(f"View {trade['symbol']} Trade on {trade['ts_utc']}"):
                st.markdown(f"**Direction:** {trade['direction']} | **Entry:** {trade['entry_price']} | **SL:** {trade['stop_loss']} | **TP:** {trade['take_profit']}")
                
                if trade['exit_price']:
                    st.markdown(f"**Exited at:** {trade['exit_price']} | **Outcome:** {trade['outcome']}")
                
                st.markdown("**Macro at Entry:**")
                macro_data = json.loads(trade['macro_snapshot'])
                st.caption(f"DXY: {macro_data['dxy']:.2f} | 10Y Yield: {macro_data['yield_10y']:.2f}% | 30Y Yield: {macro_data['yield_30y']:.2f}% | VIX: {macro_data['vix']:.2f}")
                
                if trade['notes']:
                    st.markdown("**🧠 Trader's Notes:**")
                    st.info(trade['notes'])
    else:
        st.info("No trades logged yet. Start your trading journal today!")

# ============ RUN APP ============
def run_app():
    load_dotenv()
    init_db()
    init_journal_db()
    st.set_page_config(page_title="EdgeFinder Pro - Terminal", layout="wide")
    st.markdown("<style>.stApp { background-color: #0f1116; color: #e8ecf1; } .eco-card { background: #1c2129; padding: 15px; border-radius: 10px; border-left: 4px solid #4c6fff; }</style>", unsafe_allow_html=True)
    st.title("⚡ EdgeFinder Pro - Market Terminal")
    
    main_tab1, main_tab2, main_tab3, main_tab4, main_tab5, main_tab6, main_tab7, main_tab8, main_tab9, main_tab10, main_tab11, main_tab12, main_tab13, main_tab14 = st.tabs([
        "🏠 Dashboard", 
        "📈 Charts", 
        "📅 Regime Report", 
        "🤖 AI Bubble Watch", 
        "💵 DXY Dashboard",
        "📋 Cheat Sheet",
        "🎯 Market Levels",
        "📝 Journal",
        "🌏 Asia Sniper",
        "🇺🇸 NY Afternoon",
        "📈 VWAP & 9 EMA Strategy",
        "⚡ High Yield Protocol",
        "🎯 Smart Money Levels",
        "📋 SMC Cheat Sheet"
    ])
    
    view_mode = st.sidebar.radio("View Mode", ["📈 Individual Assets", "💵 DXY Dashboard"])
    refresh = st.sidebar.button("🔄 Refresh Data")
    auto_save = st.sidebar.checkbox("Save Swing Snapshot", value=True)
    selected = st.sidebar.multiselect("Assets", options=list(ASSETS.keys()), default=["MGC","MNQ","MES","US10Y"])
    alert_price = st.sidebar.number_input("⚠️ Alert Price (Trigger)", value=0.0, step=1.0)
    alert_asset = st.sidebar.selectbox("Alert Asset", options=list(ASSETS.keys()), index=0)
    
    def fetch_asset_data(asset_key):
        cfg=ASSETS[asset_key]; intraday=get_intraday_data(cfg["ticker"]); macro=get_macro_data(); news=get_news_data(cfg["name"],cfg["news_queries"]); snapshot=build_swing_snapshot(cfg,macro,news); return snapshot,intraday,macro,news

    with main_tab1:
        try:
            mt=get_macro_data(); od=get_options_sentiment("SPY"); fg=calc_fear_greed(mt['vix'],od['ratio'],mt['dxy']); ev=get_economic_calendar(); c1,c2,c3,c4=st.columns(4)
            with c1: st.markdown(f"<div class='eco-card'><h4>🧠 Fear & Greed</h4><h2>{fg['label']}</h2><small>Score: {fg['score']}/100</small></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='eco-card'><h4>📊 Options Flow (SPY)</h4><h3>PCR: {od['ratio']}</h3><small>{od['sentiment']}</small><br><small>Puts: {od['puts']} | Calls: {od['calls']}</small></div>", unsafe_allow_html=True)
            with c3:
                txt=""
                for e in ev: txt += f"**{e['name']}**\n⏳ {e['countdown']}\n\n"
                st.markdown(f"<div class='eco-card'><h4>🕒 Economic Countdown</h4>{txt}</div>", unsafe_allow_html=True)
            with c4:
                spread_10_2 = mt['yield_10y'] - 4.85
                status_10_2 = "⚠️ Inverted (Recession Risk)" if spread_10_2 < 0 else "✅ Normal"
                spread_30_10 = mt['yield_30y'] - mt['yield_10y']
                status_30_10 = "⚠️ Inverted" if spread_30_10 < 0 else "✅ Normal"
                crisis_signal = "🔴 CRISIS" if mt['yield_30y'] > 5.0 else "🟢 Stable"
                
                st.markdown(f"""
                <div class='eco-card'>
                    <h4>Bond Yields</h4>
                    <b>10Y Yield:</b> {mt['yield_10y']:.2f}%<br>
                    <b>30Y Yield:</b> {mt['yield_30y']:.2f}%<br>
                    <b>10Y-2Y Curve:</b> {spread_10_2:.2f}%<br>
                    <small>{status_10_2}</small><br>
                    <b>30Y-10Y Spread:</b> {spread_30_10:.2f}%<br>
                    <small>{status_30_10} | {crisis_signal}</small>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("---")
        except: pass

        st.markdown("### 🔮 Macro Confluence & Action Radar")
        st.caption("If the Macro Direction and Price Direction disagree, the market is indecisive. Do not force a trade.")
        try:
            mnq_pre=yf.Ticker("MNQ=F").history(period="1d",interval="5m"); 
            mgc_pre=yf.Ticker("MGC=F").history(period="1d",interval="5m"); 
            dxy=yf.Ticker("DX-Y.NYB").history(period="1d",interval="5m"); 
            tnx=yf.Ticker("^TNX").history(period="1d",interval="5m");
            tyx=yf.Ticker("^TYX").history(period="1d",interval="5m");
            vxn=yf.Ticker("^VXN").history(period="1d",interval="5m")
            
            if not mnq_pre.empty and not mgc_pre.empty:
                mnq_change=((mnq_pre['Close'].iloc[-1]-mnq_pre['Close'].iloc[0])/mnq_pre['Close'].iloc[0])*100
                mgc_change=((mgc_pre['Close'].iloc[-1]-mgc_pre['Close'].iloc[0])/mgc_pre['Close'].iloc[0])*100
                dxy_val=dxy['Close'].iloc[-1]
                tnx_val=tnx['Close'].iloc[-1]
                tyx_val=tyx['Close'].iloc[-1] if not tyx.empty else 4.50
                vxn_val=vxn['Close'].iloc[-1] if not vxn.empty else 20.0
                
                macro_score_nq = 0
                if tnx_val < 4.2: macro_score_nq += 5
                elif tnx_val < 4.3: macro_score_nq += 2
                else: macro_score_nq -= 2
                
                if dxy_val < 103: macro_score_nq += 5
                elif dxy_val < 104: macro_score_nq += 3
                else: macro_score_nq -= 3
                
                if tyx_val - tnx_val > 0.5:
                    macro_score_nq += 2
                elif tyx_val - tnx_val < 0:
                    macro_score_nq -= 3
                
                if vxn_val < 20: macro_score_nq += 3
                elif vxn_val < 25: macro_score_nq += 0
                elif vxn_val < 30: macro_score_nq -= 2
                else: macro_score_nq -= 5
                
                macro_score_gc = 0
                if tnx_val > 4.3:
                    macro_score_gc = -5
                elif tnx_val < 4.0:
                    macro_score_gc = 6
                else:
                    macro_score_gc = 2
                
                if tyx_val > 5.0:
                    macro_score_gc += 3
                elif tyx_val < 4.0:
                    macro_score_gc -= 2
                
                nq_action = "⚖️ CONFLICT: Sit Tight"
                if macro_score_nq > 0 and mnq_change > 0.2:
                    nq_action = "✅ CONFLUENCE: Watch for Long entry"
                elif macro_score_nq < 0 and mnq_change < -0.2:
                    nq_action = "✅ CONFLUENCE: Watch for Short entry"
                
                gc_action = "⛔ AVOID: High Yields (4.3%+)"
                if macro_score_gc > 0 and mgc_change > 0:
                    gc_action = "✅ CONFLUENCE: Watch for Long"
                
                nq_bias = "Bullish" if macro_score_nq > 5 else "Bearish" if macro_score_nq < -2 else "Neutral"
                gold_bias = "Bullish" if macro_score_gc > 4 else "Bearish" if macro_score_gc < -2 else "Neutral"
                
                sc1,sc2=st.columns(2)
                with sc1: 
                    st.markdown(f"""
                    <div class='eco-card'>
                        <h4>📈 NQ (Nasdaq) Outlook</h4>
                        <b>Pre-Market Change (MNQ):</b> {'🟢' if mnq_change>0 else '🔴'} {mnq_change:.2f}%<br>
                        <b>DXY:</b> {dxy_val:.2f} | <b>10Y:</b> {tnx_val:.2f}% | <b>30Y:</b> {tyx_val:.2f}%<br>
                        <b>VXN (Tech Fear):</b> {vxn_val:.2f}<br>
                        <b>Macro Score:</b> {macro_score_nq}/10<br>
                        <b>Directional Bias:</b> <span style='color: {"#4ade80" if "Bullish" in nq_bias else "#f87171" if "Bearish" in nq_bias else "#facc15"}; font-weight: bold;'>{nq_bias}</span><br>
                        <b>Decision:</b> <span style='color: {"#facc15" if "Sit" in nq_action else "#4ade80" if "Long" in nq_action else "#f87171"}; font-weight: bold;'>{nq_action}</span>
                    </div>
                    """, unsafe_allow_html=True)
                with sc2: 
                    st.markdown(f"""
                    <div class='eco-card'>
                        <h4>🥇 Gold (MGC) Outlook</h4>
                        <b>Pre-Market Change (MGC):</b> {'🟢' if mgc_change>0 else '🔴'} {mgc_change:.2f}%<br>
                        <b>10Y Yield:</b> {tnx_val:.2f}% | <b>30Y Yield:</b> {tyx_val:.2f}%<br>
                        <b>Macro Score:</b> {macro_score_gc}/10<br>
                        <b>Directional Bias:</b> <span style='color: {"#4ade80" if "Bullish" in gold_bias else "#f87171" if "Bearish" in gold_bias else "#facc15"}; font-weight: bold;'>{gold_bias}</span><br>
                        <b>Decision:</b> <span style='color: {"#f87171" if tnx_val>4.3 else "#4ade80"}; font-weight: bold;'>{gc_action}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else: st.info("Pre-market data loading... (Markets may be closed)")
        except Exception as e: 
            st.info(f"Overnight futures data unavailable at this time.")

    with main_tab2:
        if view_mode == "💵 DXY Dashboard":
            render_dxy_dashboard()
        else:
            for asset_key in selected:
                render_asset(asset_key, auto_save)

    with main_tab3:
        st.subheader("📅 12-Month Regime Report")
        st.caption("Monthly averages of your EdgeFinder scores. Shows the long-term structural trend of each asset.")
        for asset_key in selected:
            monthly = get_monthly_regime_report(asset_key)
            if monthly is not None:
                st.subheader(f"📈 {ASSETS[asset_key]['symbol']} Monthly Regime")
                cols = st.columns(len(monthly) + 1)
                cols[0].markdown("**Month**")
                def get_bias_color(bias):
                    if "Bullish" in bias: return "#4ade80"
                    elif "Bearish" in bias: return "#f87171"
                    else: return "#e8ecf1"
                for i, row in monthly.iterrows():
                    cols[i+1].markdown(f"<div style='text-align: center; background-color: {get_bias_color(row['overall_bias'])}; padding: 10px; border-radius: 8px; color: #0f1116; font-weight: bold;'>{row['month_str']}<br>{row['overall_score']:.1f}/10<br><small>{row['overall_bias']}</small></div>", unsafe_allow_html=True)
                st.markdown("---")
            else:
                st.info(f"No historical data for {ASSETS[asset_key]['symbol']} yet. Start saving snapshots to build your report.")

    with main_tab4:
        st.subheader("🤖 AI & Semiconductor Bubble Watch")
        st.caption("Real-time risk radar for NVDA and SMH. 0-100 Risk Score based on technicals, macro, and pre-market sentiment.")
        try:
            nvda = yf.Ticker("NVDA").history(period="6mo")
            smh = yf.Ticker("SMH").history(period="6mo")
            mnq = yf.Ticker("MNQ=F").history(period="1d", interval="5m")
            dxy = yf.Ticker("DX-Y.NYB").history(period="1d", interval="5m")
            tnx = yf.Ticker("^TNX").history(period="1d", interval="5m")
            
            if nvda.empty: 
                nvda_price = 0.0; nvda_200 = 0.0
            else: 
                nvda_price = nvda['Close'].iloc[-1]
                nvda_200 = sma(nvda['Close'].tolist(), 200)
                
            if smh.empty: 
                smh_price = 0.0; smh_200 = 0.0
            else:
                smh_price = smh['Close'].iloc[-1]
                smh_200 = sma(smh['Close'].tolist(), 200)
                
            if mnq.empty or dxy.empty or tnx.empty:
                dxy_val = 0.0; tnx_val = 0.0; mnq_change = 0.0
            else:
                dxy_val = dxy['Close'].iloc[-1]
                tnx_val = tnx['Close'].iloc[-1]
                mnq_change = ((mnq['Close'].iloc[-1] - mnq['Close'].iloc[0]) / mnq['Close'].iloc[0]) * 100

            risk_score = 0
            warnings = []
            
            if nvda_price > 0 and nvda_200 > 0:
                if nvda_price > nvda_200: risk_score += 0
                elif nvda_price > nvda_200 * 0.95: risk_score += 15; warnings.append("⚠️ NVDA approaching 200-DMA")
                else: risk_score += 30; warnings.append("🔴 NVDA BROKEN 200-DMA")
            
            if smh_price > 0 and smh_200 > 0:
                if smh_price > smh_200: risk_score += 0
                elif smh_price > smh_200 * 0.95: risk_score += 15; warnings.append("⚠️ SMH approaching 200-DMA")
                else: risk_score += 30; warnings.append("🔴 SMH BROKEN 200-DMA")
            
            if dxy_val > 105 or tnx_val > 4.8: risk_score += 20; warnings.append("🔴 High Macro Pressure (DXY > 105 / Yields > 4.8%)")
            elif dxy_val > 103 or tnx_val > 4.5: risk_score += 10; warnings.append("⚠️ Moderate Macro Pressure")
            
            if mnq_change < -1.5: risk_score += 20; warnings.append("🔴 MNQ Pre-Market Down > 1.5%")
            elif mnq_change < -0.5: risk_score += 10; warnings.append("⚠️ MNQ Pre-Market Weak")
            
            nvda_price_str = f"${nvda_price:.2f}" if nvda_price > 0 else "Loading..."
            nvda_200_str = f"${nvda_200:.2f}" if nvda_200 > 0 else "Loading..."
            smh_price_str = f"${smh_price:.2f}" if smh_price > 0 else "Loading..."
            smh_200_str = f"${smh_200:.2f}" if smh_200 > 0 else "Loading..."
            
            if risk_score >= 70: alert_color="#f87171"; alert_icon="🔴"; alert_text="HIGH RISK: AI BUBBLE ALERT"
            elif risk_score >= 40: alert_color="#facc15"; alert_icon="🟡"; alert_text="MODERATE RISK: Caution Advised"
            else: alert_color="#4ade80"; alert_icon="🟢"; alert_text="LOW RISK: All Clear"
            
            col_b1, col_b2 = st.columns([1, 2])
            with col_b1: 
                st.markdown(f"<div class='eco-card'><h3 style='color: {alert_color};'>{alert_icon} {alert_text}</h3><h1 style='color: {alert_color}; font-size: 48px;'>{risk_score}/100</h1><small>Risk Score</small></div>", unsafe_allow_html=True)
            with col_b2: 
                st.markdown(f"<div class='eco-card'><h4>📊 Key Metrics</h4><b>NVDA:</b> {nvda_price_str} (200-DMA: {nvda_200_str})<br><b>SMH:</b> {smh_price_str} (200-DMA: {smh_200_str})<br><b>DXY:</b> {dxy_val:.2f} | <b>10Y Yield:</b> {tnx_val:.2f}%<br><b>MNQ Pre-Market:</b> {'🟢' if mnq_change>0 else '🔴'} {mnq_change:.2f}%</div>", unsafe_allow_html=True)
            
            if warnings: st.warning("**⚠️ Bubble Watch Alerts:** " + " | ".join(warnings))
            
        except Exception as e:
            st.warning(f"🤖 AI Bubble Watch is temporarily offline (Yahoo API delay). Data will load shortly.")

    with main_tab5:
        render_dxy_dashboard()

    with main_tab6:
        run_cheat_sheet()

    with main_tab7:
        run_level_marker()

    with main_tab8:
        run_journal_tab()

    with main_tab9:
        run_asia_sniper()

    with main_tab10:
        run_ny_afternoon_sniper()

    with main_tab11:
        run_vwap_ema_strategy()

    with main_tab12:
        run_high_yield_protocol()

    with main_tab13:
        run_smart_money_levels()

    with main_tab14:
        render_smc_cheat_sheet()

if __name__ == "__main__":
    run_app()