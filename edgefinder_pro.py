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
    
    # --- BOND YIELDS ---
    "US02Y": {"symbol":"US02Y","name":"2-Year Treasury Yield","ticker":"^IRX","tv_ticker":"TVC:US02Y","news_queries":["2Y","IRX","treasury"],"inverse_dxy":False,"safe_haven":False,"type":"Yield","favors":"High Rates"},
    "US10Y": {"symbol":"US10Y","name":"10-Year Treasury Yield","ticker":"^TNX","tv_ticker":"TVC:US10Y","news_queries":["10Y","TNX","treasury"],"inverse_dxy":False,"safe_haven":False,"type":"Yield","favors":"High Rates"},
    "US30Y": {"symbol":"US30Y","name":"30-Year Treasury Yield","ticker":"^TYX","tv_ticker":"TVC:US30Y","news_queries":["30Y","TYX","treasury"],"inverse_dxy":False,"safe_haven":False,"type":"Yield","favors":"High Rates"},

    # --- INDICES ---
    "DXY": {"symbol":"DXY","name":"US Dollar Index","ticker":"DX-Y.NYB","tv_ticker":"TVC:DXY","news_queries":["DXY","dollar index"],"inverse_dxy":False,"safe_haven":False,"type":"Currency","favors":"High Yields"},
    "VIX": {"symbol":"VIX","name":"Volatility Index","ticker":"^VIX","tv_ticker":"TVC:VIX","news_queries":["VIX","volatility"],"inverse_dxy":False,"safe_haven":False,"type":"Index","favors":"Panic"},

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
        
    return {"dxy": dxy, "vix": vix, "real_yield_10y": ry, "yield_10y": tnx, "yield_30y": tyx}

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

def render_asset(asset_key,auto_save):
 cfg=ASSETS[asset_key]; intraday=get_intraday_data(cfg["ticker"]); macro=get_macro_data(); news=get_news_data(cfg["name"],cfg["news_queries"]); snapshot=build_swing_snapshot(cfg,macro,news)
 if auto_save: save_snapshot(snapshot)
 st.subheader(f"{snapshot.name} ({snapshot.symbol})")
 c1,c2,c3,c4=st.columns(4); c1.metric("Swing Price",f"{snapshot.price:,.2f}"); c2.metric("Overall",f"{snapshot.overall_score}/10",snapshot.overall_bias.value); c3.metric("Technical",f"{snapshot.technical_score}/10"); c4.metric("Macro / News",f"{snapshot.macro_score}/10 / {snapshot.news_score}/10")
 if "error" in intraday: st.warning(f"Intraday data unavailable: {intraday['error']}")
 else:
  st.info("📊 Intraday Setup: VWAP (Blue), 9-EMA (Orange), 20-EMA (Yellow), 50-EMA (Purple)")
  c_i1,c_i2,c_i3,c_i4,c_i5=st.columns(5); c_i1.metric("Price",f"{intraday['current_price']:.2f}"); c_i2.metric("VWAP",f"{intraday['vwap']:.2f}"); c_i3.metric("9 EMA",f"{intraday['ema9']:.2f}"); c_i4.metric("20 EMA",f"{intraday['ema20']:.2f}"); c_i5.metric("50 EMA",f"{intraday['ema50']:.2f}")
  
  # --- FIX: Switch to Finviz for unrestricted free chart embedding ---
  finviz_ticker = cfg['ticker']
  if finviz_ticker.endswith("=F"):
      finviz_ticker = finviz_ticker.replace("=F", "")
  elif finviz_ticker.startswith("^"):
      finviz_ticker = finviz_ticker.replace("^", "")
      
  if cfg['symbol'] == "US10Y":
      finviz_ticker = "US10Y"
  elif cfg['symbol'] == "US30Y":
      finviz_ticker = "US30Y"
  elif cfg['symbol'] == "US02Y":
      finviz_ticker = "US02Y"
  elif cfg['symbol'] == "DXY":
      finviz_ticker = "DXY"

  st.components.v1.html(f"""
  <iframe src="https://finviz.com/chart.ashx?t={finviz_ticker}&ty=c&ta=1&p=d&s=l" 
          width="100%" height="500" frameborder="0" scrolling="no">
  </iframe>
  """, height=500)
 t1,t2,t3,t4=st.tabs(["Technical Scores","Macro Scores","Historical Trend","📊 Macro Drivers"])
 with t1:
  df=pd.DataFrame([{"Indicator":x.name,"Value":round(x.value,4),"Score":x.score,"Bias":x.bias.value} for x in snapshot.technical_details])
  daily=yf.Ticker(cfg["ticker"]).history(period="6mo"); closes=daily['Close'].tolist(); p=closes[-1]; m50=sma(closes,50); m200=sma(closes,200)
  ldf=pd.DataFrame([{"Indicator":"Daily 50 SMA","Value":round(m50,4),"Score":"-","Bias":"Bullish" if p>m50 else "Bearish"},{"Indicator":"Daily 200 SMA","Value":round(m200,4),"Score":"-","Bias":"Bullish" if p>m200 else "Bearish"}])
  st.dataframe(pd.concat([df,ldf]), width='stretch', hide_index=True)
 with t2: st.dataframe(pd.DataFrame([{"Indicator":x.name,"Value":round(x.value,4),"Score":x.score,"Bias":x.bias.value} for x in snapshot.macro_details]), width='stretch', hide_index=True)
 with t3:
  recent=load_recent(snapshot.symbol)
  if recent:
   hist=pd.DataFrame(recent); line=go.Figure(); line.add_scatter(x=hist["ts_utc"],y=hist["overall_score"],mode="lines+markers",name="Overall"); line.update_layout(height=200,paper_bgcolor="#0f1116",plot_bgcolor="#0f1116",font={"color":"#e8ecf1"}); st.plotly_chart(line, width='stretch')
  else: st.info("No history yet.")
 with t4: drivers=get_macro_drivers(asset_key); render_macro_drivers(drivers)

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

# ============ SAFE SWING SNAPSHOT (PREVENTS EMPTY DATA CRASH) ============
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

# ============ MONTHLY REGIME REPORT (From SQLite) ============
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

# ============ MULTI-TIMEFRAME ORDER FLOW SCANNER ============
def run_order_flow_scanner():
    st.subheader("🌀 Multi-Timeframe Order Flow Scanner")
    st.caption("Detects institutional Order Blocks and Liquidity Sweeps across 4H, 1H, and 15m timeframes for MNQ and MGC.")
    
    with st.spinner("Scanning multiple timeframes for Order Blocks and Liquidity Sweeps..."):
        mnq_4h = yf.Ticker("MNQ=F").history(period="5d", interval="1h")  
        mnq_1h = yf.Ticker("MNQ=F").history(period="5d", interval="1h")
        mnq_15m = yf.Ticker("MNQ=F").history(period="2d", interval="15m")
        
        mgc_4h = yf.Ticker("MGC=F").history(period="5d", interval="1h")
        mgc_1h = yf.Ticker("MGC=F").history(period="5d", interval="1h")
        mgc_15m = yf.Ticker("MGC=F").history(period="2d", interval="15m")
    
    if mnq_4h.empty or mnq_1h.empty or mnq_15m.empty:
        st.warning("No data available for one or more timeframes. Market may be closed.")
        return
    
    def detect_order_blocks(data, timeframe_name):
        ob = []
        for i in range(1, len(data)-1):
            candle = data.iloc[i]
            body = abs(candle['Close'] - candle['Open'])
            total_range = candle['High'] - candle['Low']
            
            if total_range == 0: continue
            
            if candle['Close'] > candle['Open'] and (body / total_range) > 0.60:
                ob.append({
                    'Timeframe': timeframe_name,
                    'Time': data.index[i].strftime('%Y-%m-%d %H:%M'),
                    'Type': 'Bullish OB',
                    'Level': round(candle['Low'], 2),
                    'Body%': f"{round((body/total_range)*100, 0)}%"
                })
            elif candle['Close'] < candle['Open'] and (body / total_range) > 0.60:
                ob.append({
                    'Timeframe': timeframe_name,
                    'Time': data.index[i].strftime('%Y-%m-%d %H:%M'),
                    'Type': 'Bearish OB',
                    'Level': round(candle['High'], 2),
                    'Body%': f"{round((body/total_range)*100, 0)}%"
                })
        return ob
    
    def detect_liquidity_sweeps(data, lookback=20, timeframe_name="15m"):
        sweeps = []
        high_20 = data['High'].rolling(lookback).max()
        low_20 = data['Low'].rolling(lookback).min()
        
        for i in range(lookback, len(data)-1):
            candle = data.iloc[i]
            if candle['High'] > high_20.iloc[i-1] and candle['Close'] < candle['Open']:
                sweeps.append({
                    'Timeframe': timeframe_name,
                    'Time': data.index[i].strftime('%Y-%m-%d %H:%M'),
                    'Type': 'Bearish Sweep',
                    'Sweep Level': round(candle['High'], 2),
                    'Close': round(candle['Close'], 2)
                })
            elif candle['Low'] < low_20.iloc[i-1] and candle['Close'] > candle['Open']:
                sweeps.append({
                    'Timeframe': timeframe_name,
                    'Time': data.index[i].strftime('%Y-%m-%d %H:%M'),
                    'Type': 'Bullish Sweep',
                    'Sweep Level': round(candle['Low'], 2),
                    'Close': round(candle['Close'], 2)
                })
        return sweeps
    
    st.markdown("### 📈 MNQ (Micro Nasdaq) Multi-Timeframe Order Flow")
    
    ob_4h_mnq = detect_order_blocks(mnq_4h, "4H")
    ob_1h_mnq = detect_order_blocks(mnq_1h, "1H")
    ob_15m_mnq = detect_order_blocks(mnq_15m, "15m")
    
    sweeps_4h_mnq = detect_liquidity_sweeps(mnq_4h, 20, "4H")
    sweeps_1h_mnq = detect_liquidity_sweeps(mnq_1h, 20, "1H")
    sweeps_15m_mnq = detect_liquidity_sweeps(mnq_15m, 20, "15m")
    
    def clean_df_for_render(df):
        if df.empty: return df
        if 'Score' not in df.columns:
            df['Score'] = 0
        else:
            df['Score'] = pd.to_numeric(df['Score'], errors='coerce').fillna(0).astype(int)
        return df

    col_ob1, col_ob2, col_ob3 = st.columns(3)
    with col_ob1:
        st.markdown("#### ⏳ 4H Order Blocks")
        if ob_4h_mnq:
            st.dataframe(clean_df_for_render(pd.DataFrame(ob_4h_mnq)), width='stretch', hide_index=True)
        else: st.info("No 4H blocks yet.")
    
    with col_ob2:
        st.markdown("#### ⏳ 1H Order Blocks")
        if ob_1h_mnq:
            st.dataframe(clean_df_for_render(pd.DataFrame(ob_1h_mnq)), width='stretch', hide_index=True)
        else: st.info("No 1H blocks yet.")
    
    with col_ob3:
        st.markdown("#### ⏳ 15m Order Blocks")
        if ob_15m_mnq:
            st.dataframe(clean_df_for_render(pd.DataFrame(ob_15m_mnq)), width='stretch', hide_index=True)
        else: st.info("No 15m blocks yet.")
    
    st.markdown("---")
    col_sw1, col_sw2, col_sw3 = st.columns(3)
    with col_sw1:
        st.markdown("#### 💨 4H Liquidity Sweeps")
        if sweeps_4h_mnq:
            st.dataframe(clean_df_for_render(pd.DataFrame(sweeps_4h_mnq)), width='stretch', hide_index=True)
        else: st.info("No 4H sweeps yet.")
    
    with col_sw2:
        st.markdown("#### 💨 1H Liquidity Sweeps")
        if sweeps_1h_mnq:
            st.dataframe(clean_df_for_render(pd.DataFrame(sweeps_1h_mnq)), width='stretch', hide_index=True)
        else: st.info("No 1H sweeps yet.")
    
    with col_sw3:
        st.markdown("#### 💨 15m Liquidity Sweeps")
        if sweeps_15m_mnq:
            st.dataframe(clean_df_for_render(pd.DataFrame(sweeps_15m_mnq)), width='stretch', hide_index=True)
        else: st.info("No 15m sweeps yet.")
    
    st.markdown("---")
    st.markdown("🥇 MGC (Micro Gold) Multi-Timeframe Order Flow")
    
    ob_4h_mgc = detect_order_blocks(mgc_4h, "4H")
    ob_1h_mgc = detect_order_blocks(mgc_1h, "1H")
    ob_15m_mgc = detect_order_blocks(mgc_15m, "15m")
    
    sweeps_4h_mgc = detect_liquidity_sweeps(mgc_4h, 20, "4H")
    sweeps_1h_mgc = detect_liquidity_sweeps(mgc_1h, 20, "1H")
    sweeps_15m_mgc = detect_liquidity_sweeps(mgc_15m, 20, "15m")
    
    col_ob1, col_ob2, col_ob3 = st.columns(3)
    with col_ob1:
        st.markdown("#### ⏳ 4H Order Blocks")
        if ob_4h_mgc:
            st.dataframe(clean_df_for_render(pd.DataFrame(ob_4h_mgc)), width='stretch', hide_index=True)
        else: st.info("No 4H blocks yet.")
    
    with col_ob2:
        st.markdown("#### ⏳ 1H Order Blocks")
        if ob_1h_mgc:
            st.dataframe(clean_df_for_render(pd.DataFrame(ob_1h_mgc)), width='stretch', hide_index=True)
        else: st.info("No 1H blocks yet.")
    
    with col_ob3:
        st.markdown("#### ⏳ 15m Order Blocks")
        if ob_15m_mgc:
            st.dataframe(clean_df_for_render(pd.DataFrame(ob_15m_mgc)), width='stretch', hide_index=True)
        else: st.info("No 15m blocks yet.")
    
    st.markdown("---")
    col_sw1, col_sw2, col_sw3 = st.columns(3)
    with col_sw1:
        st.markdown("#### 💨 4H Liquidity Sweeps")
        if sweeps_4h_mgc:
            st.dataframe(clean_df_for_render(pd.DataFrame(sweeps_4h_mgc)), width='stretch', hide_index=True)
        else: st.info("No 4H sweeps yet.")
    
    with col_sw2:
        st.markdown("#### 💨 1H Liquidity Sweeps")
        if sweeps_1h_mgc:
            st.dataframe(clean_df_for_render(pd.DataFrame(sweeps_1h_mgc)), width='stretch', hide_index=True)
        else: st.info("No 1H sweeps yet.")
    
    with col_sw3:
        st.markdown("#### 💨 15m Liquidity Sweeps")
        if sweeps_15m_mgc:
            st.dataframe(clean_df_for_render(pd.DataFrame(sweeps_15m_mgc)), width='stretch', hide_index=True)
        else: st.info("No 15m sweeps yet.")

# ============ STRATEGY CHEAT SHEET ============
def run_cheat_sheet():
    st.subheader("📋 Strategy Entry Cheat Sheet")
    st.caption("Quick reference guide for Long and Short entry requirements across all strategies, plus the VIX Volatility Map.")
    
    st.markdown("### 📊 ICT Order Block Strategy")
    col_ict1, col_ict2 = st.columns(2)
    with col_ict1:
        st.markdown("""
        <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
            <h4 style='color: #4ade80;'>🟢 LONG ENTRY</h4>
            <ul style='color: #e8ecf1;'>
                <li>✅ Higher High structure</li>
                <li>✅ Price > 200 EMA (Trend Filter)</li>
                <li>✅ RSI < 30 (Oversold)</li>
                <li>✅ Close > Previous Close (Momentum)</li>
                <li>✅ Price > Order Block</li>
                <li>❌ No existing Long position</li>
            </ul>
            <br>
            <b>Stop Loss:</b> Below Order Block<br>
            <b>Take Profit:</b> 2x Risk
        </div>
        """, unsafe_allow_html=True)
    with col_ict2:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
            <h4 style='color: #f87171;'>🔴 SHORT ENTRY</h4>
            <ul style='color: #e8ecf1;'>
                <li>✅ Lower Low structure</li>
                <li>✅ Price < 200 EMA (Trend Filter)</li>
                <li>✅ RSI > 70 (Overbought)</li>
                <li>✅ Close < Previous Close (Momentum)</li>
                <li>✅ Price < Order Block</li>
                <li>❌ No existing Short position</li>
            </ul>
            <br>
            <b>Stop Loss:</b> Above Order Block<br>
            <b>Take Profit:</b> 2x Risk
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.markdown("### 📈 NY Open VWAP & EMA Strategy")
    col_ny1, col_ny2 = st.columns(2)
    with col_ny1:
        st.markdown("""
        <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
            <h4 style='color: #4ade80;'>🟢 LONG ENTRY</h4>
            <ul style='color: #e8ecf1;'>
                <li>✅ Time: NY Open (9:30 AM)</li>
                <li>✅ Price > VWAP</li>
                <li>✅ Pullback to 9 EMA</li>
                <li>✅ Price > Pre-Market Low</li>
                <li>❌ No existing Long position</li>
            </ul>
            <br>
            <b>Stop Loss:</b> Below Pre-Market Low<br>
            <b>Take Profit:</b> 2x Risk
        </div>
        """, unsafe_allow_html=True)
    with col_ny2:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
            <h4 style='color: #f87171;'>🔴 SHORT ENTRY</h4>
            <ul style='color: #e8ecf1;'>
                <li>✅ Time: NY Open (9:30 AM)</li>
                <li>✅ Price < VWAP</li>
                <li>✅ Pullback to 9 EMA</li>
                <li>✅ Price < Pre-Market High</li>
                <li>❌ No existing Short position</li>
            </ul>
            <br>
            <b>Stop Loss:</b> Above Pre-Market High<br>
            <b>Take Profit:</b> 2x Risk
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.markdown("### 📈 CRT Expansion Strategy")
    col_crt1, col_crt2 = st.columns(2)
    with col_crt1:
        st.markdown("""
        <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
            <h4 style='color: #4ade80;'>🟢 LONG ENTRY</h4>
            <ul style='color: #e8ecf1;'>
                <li>✅ Time: NY Open (9:30 AM)</li>
                <li>✅ Price > VWAP</li>
                <li>✅ Price > CRT Upper Expansion Target</li>
                <li>✅ Pullback to 9 EMA</li>
                <li>❌ No existing Long position</li>
            </ul>
            <br>
            <b>Stop Loss:</b> Below Pre-Market High<br>
            <b>Take Profit:</b> 2x Risk
        </div>
        """, unsafe_allow_html=True)
    with col_crt2:
        st.markdown("""
        <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
            <h4 style='color: #f87171;'>🔴 SHORT ENTRY</h4>
            <ul style='color: #e8ecf1;'>
                <li>✅ Time: NY Open (9:30 AM)</li>
                <li>✅ Price < VWAP</li>
                <li>✅ Price < CRT Lower Expansion Target</li>
                <li>✅ Pullback to 9 EMA</li>
                <li>❌ No existing Short position</li>
            </ul>
            <br>
            <b>Stop Loss:</b> Above Pre-Market Low<br>
            <b>Take Profit:</b> 2x Risk
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    # ============ VIX BENCHMARK SECTION ============
    st.markdown("### 🌪️ VIX Volatility Map & Bias Benchmarks")
    st.caption("Use the VIX to gauge market complacency, panic, and the probability of a reversal.")
    
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
    
    # ============ BOND YIELD BENCHMARK SECTION ============
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
    
    # ============ 30-YEAR YIELD BENCHMARK SECTION ============
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

# ============ EXECUTION ENGINE: NY OPEN BREAKOUT SCANNER ============
def run_level_marker():
    st.subheader("🎯 NY Open Execution Engine")
    st.caption("No guesses. No opinions. Just sniper triggers for the NY Open based on Pre-Market levels.")
    
    with st.spinner("AI scanning session data for sniper triggers..."):
        mnq_data = yf.Ticker("MNQ=F").history(period="2d", interval="1m")
        mgc_data = yf.Ticker("MGC=F").history(period="2d", interval="1m")
    
    if mnq_data.empty or mgc_data.empty:
        st.warning("No session data available. Market may be closed.")
        return
    
    today = datetime.now().date()
    
    macro = get_macro_data()
    tnx_val = macro['yield_10y']
    tyx_val = macro['yield_30y']
    dxy_val = macro['dxy']
    
    st.markdown("### 📈 MNQ (Micro Nasdaq) Execution Triggers")
    mnq_today = mnq_data[mnq_data.index.date == today]
    mnq_prev = mnq_data[mnq_data.index.date == (today - timedelta(days=1))]
    
    asia_mnq = mnq_prev.between_time('17:00', '23:59')
    if not asia_mnq.empty:
        asia_high = asia_mnq['High'].max()
        asia_low = asia_mnq['Low'].min()
        asia_range = asia_high - asia_low
        asia_sell = asia_high + (asia_range * 0.5)
        asia_buy = asia_low - (asia_range * 0.5)
    else:
        asia_high = asia_low = asia_sell = asia_buy = 0
    
    london_mnq = mnq_today.between_time('02:00', '09:29')
    if not london_mnq.empty:
        london_high = london_mnq['High'].max()
        london_low = london_mnq['Low'].min()
        london_range = london_high - london_low
        london_sell = london_high + (london_range * 0.5)
        london_buy = london_low - (london_range * 0.5)
    else:
        london_high = london_low = london_sell = london_buy = 0
    
    ny_mnq = mnq_today.between_time('08:00', '09:29')
    if not ny_mnq.empty:
        ny_high = ny_mnq['High'].max()
        ny_low = ny_mnq['Low'].min()
        ny_range = ny_high - ny_low
        ny_sell = ny_high + (ny_range * 0.5)
        ny_buy = ny_low - (ny_range * 0.5)
        current_price = ny_mnq['Close'].iloc[-1]
    else:
        ny_high = ny_low = ny_sell = ny_buy = current_price = 0
    
    buffer = 15
    fakeout_buffer = 5
    
    st.markdown("#### 🎯 NY Open Sniper Triggers")
    
    if current_price > 0:
        if current_price > ny_low and current_price < ny_high:
            st.warning("⛔ **WAIT ZONE:** Price is currently trapped inside the NY Pre-Market Range. DO NOT TRADE. Wait for a break of High or Low.")
        
        if ny_high - current_price < fakeout_buffer and ny_high - current_price > 0:
            st.error("⚠️ **FAKEOUT WARNING:** Price is within 5 points of the NY High. Watch for a brief spike (fakeout) that immediately reverses before entering.")
        if current_price - ny_low < fakeout_buffer and current_price - ny_low > 0:
            st.error("⚠️ **FAKEOUT WARNING:** Price is within 5 points of the NY Low. Watch for a brief dip (fakeout) that immediately reverses before entering.")
        
        long_entry = ny_high + buffer
        long_stop_loss = ny_high - 10
        long_take_profit = long_entry + (ny_range * 1.5)
        
        short_entry = ny_low - buffer
        short_stop_loss = ny_low + 10
        short_take_profit = short_entry - (ny_range * 1.5)
        
        col_trigger1, col_trigger2 = st.columns(2)
        with col_trigger1:
            st.markdown(f"""
            <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                <h4 style='color: #4ade80;'>🚀 LONG BREAKOUT</h4>
                <b>Trigger Price:</b> > {long_entry}<br>
                <b>Stop Loss:</b> {long_stop_loss} (Points: {abs(long_entry - long_stop_loss)})<br>
                <b>Take Profit:</b> {long_take_profit} (1.5x Range)<br>
                <b>Risk/Reward:</b> 1 : 1.5
            </div>
            """, unsafe_allow_html=True)
            
        with col_trigger2:
            st.markdown(f"""
            <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                <h4 style='color: #f87171;'>📉 SHORT BREAKOUT</h4>
                <b>Trigger Price:</b> < {short_entry}<br>
                <b>Stop Loss:</b> {short_stop_loss} (Points: {abs(short_entry - short_stop_loss)})<br>
                <b>Take Profit:</b> {short_take_profit} (1.5x Range)<br>
                <b>Risk/Reward:</b> 1 : 1.5
            </div>
            """, unsafe_allow_html=True)
    else:
        st.error("Unable to calculate NY Pre-Market range.")

    st.markdown("---")
    st.markdown("#### 📊 Session Level Reference")
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Asia High/Low", f"{asia_high:.2f} / {asia_low:.2f}")
    with c2: st.metric("London High/Low", f"{london_high:.2f} / {london_low:.2f}")
    with c3: st.metric("NY Pre-Market High/Low", f"{ny_high:.2f} / {ny_low:.2f}")
    
    st.markdown("---")
    st.markdown("🥇 MGC (Micro Gold) Execution Triggers")
    
    if tnx_val > 4.3:
        st.error("⛔ **HARD STOP:** 10-Year Yield is above 4.3%. Gold is structurally broken in this environment. No trades recommended.")
    else:
        mgc_today = mgc_data[mgc_data.index.date == today]
        mgc_prev = mgc_data[mgc_data.index.date == (today - timedelta(days=1))]
        
        ny_mgc = mgc_today.between_time('08:00', '09:29')
        if not ny_mgc.empty:
            ny_high = ny_mgc['High'].max()
            ny_low = ny_mgc['Low'].min()
            ny_range = ny_high - ny_low
            current_price = ny_mgc['Close'].iloc[-1]
            
            long_entry = ny_high + buffer
            long_stop_loss = ny_high - 10
            long_take_profit = long_entry + (ny_range * 1.5)
            
            short_entry = ny_low - buffer
            short_stop_loss = ny_low + 10
            short_take_profit = short_entry - (ny_range * 1.5)
            
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.markdown(f"""
                <div style='background-color: #1a3a2a; padding: 15px; border-radius: 8px; border-left: 4px solid #4ade80;'>
                    <h4 style='color: #4ade80;'>🚀 LONG BREAKOUT</h4>
                    <b>Trigger Price:</b> > {long_entry}<br>
                    <b>SL:</b> {long_stop_loss}<br>
                    <b>TP:</b> {long_take_profit}
                </div>
                """, unsafe_allow_html=True)
            with col_m2:
                st.markdown(f"""
                <div style='background-color: #3a1a1a; padding: 15px; border-radius: 8px; border-left: 4px solid #f87171;'>
                    <h4 style='color: #f87171;'>📉 SHORT BREAKOUT</h4>
                    <b>Trigger Price:</b> < {short_entry}<br>
                    <b>SL:</b> {short_stop_loss}<br>
                    <b>TP:</b> {short_take_profit}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Gold pre-market data unavailable.")

    st.markdown("---")
    st.info("💡 **Execution Rules:** Do not place a trade unless price triggers the exact Entry Level. If price is currently inside the Pre-Market High/Low, wait. The best entries happen at 9:30 - 10:00 AM EST.")

# ============ CRT (CUMULATIVE RANGE THEORY) STRATEGY ============
def run_crt_strategy():
    st.subheader("📈 CRT Expansion Strategy Backtest")
    st.caption("Uses Cumulative Range Theory (CRT) to calculate dynamic expansion targets above the Pre-Market High/Low.")
    
    st.markdown("### 🎛️ Strategy Parameters")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        ema_lookback = st.number_input("EMA Lookback (Bars)", min_value=5, max_value=20, value=9, step=1, key="crt_ema")
        ny_open_hour = st.number_input("NY Open Hour (EST)", min_value=8, max_value=10, value=9, step=1, key="crt_hour")
    with col_p2:
        rr_ratio = st.number_input("Risk:Reward Ratio", min_value=1.0, max_value=5.0, value=2.0, step=0.5, key="crt_rr")
        crt_multiplier = st.number_input("CRT Range Multiplier", min_value=0.5, max_value=3.0, value=1.5, step=0.5, key="crt_mult")
    with col_p3:
        pre_market_minutes = st.number_input("Pre-Market Lookback (Minutes)", min_value=10, max_value=60, value=30, step=5, key="crt_pre")
    
    run_btn = st.button("🚀 Run CRT Backtest", key="crt_btn")
    
    if not run_btn:
        st.info("Adjust the parameters above and click 'Run CRT Backtest' to see results.")
        return
    
    with st.spinner("Fetching MNQ historical data..."):
        mnq = yf.Ticker("MNQ=F").history(period="6mo", interval="1h")
        if mnq.empty:
            st.warning("No data available. Market may be closed.")
            return
    
    data = mnq.copy()
    data.columns = [col.capitalize() for col in data.columns]
    data = data.dropna()
    
    data['EMA'] = data['Close'].ewm(span=ema_lookback, adjust=False).mean()
    data['VWAP'] = (data['Close'] * data['Volume']).cumsum() / data['Volume'].cumsum()
    data['Date'] = data.index.date
    data['Hour'] = data.index.hour
    data['Minute'] = data.index.minute
    data['Is_NY_Open'] = (data['Hour'] == ny_open_hour) & (data['Minute'] == 30)
    
    class CRTStrategy(Strategy):
        def init(self):
            super().init()
            self.ema = self.data.EMA
            self.vwap = self.data.VWAP
            self.is_ny_open = self.data.Is_NY_Open
        
        def next(self):
            super().next()
            if len(self.data.Close) < 50: return
            
            current_close = self.data.Close[-1]
            current_ema = self.ema[-1]
            current_vwap = self.vwap[-1]
            
            recent_opens = self.is_ny_open[-5:].any()
            if not recent_opens:
                return
                
            today = self.data.index[-1].date()
            today_data = self.data[self.data.index.date == today]
            pre_market_data = today_data[today_data['Hour'] < ny_open_hour]
            
            if len(pre_market_data) < 3:
                return
                
            pre_market_high = pre_market_data['High'].max()
            pre_market_low = pre_market_data['Low'].min()
            pre_market_range = pre_market_high - pre_market_low
            
            if pre_market_high is None or pre_market_low is None or pre_market_range == 0:
                return
            
            upper_expansion = pre_market_high + (pre_market_range * crt_multiplier)
            lower_expansion = pre_market_low - (pre_market_range * crt_multiplier)
            
            if (current_close > current_vwap and 
                current_close > upper_expansion and
                current_close < current_ema * 1.001 and
                not self.position.is_long):
                
                stop_loss = pre_market_high - 5
                risk = current_close - stop_loss
                take_profit = current_close + (risk * rr_ratio)
                self.buy(sl=stop_loss, tp=take_profit)
            
            elif (current_close < current_vwap and 
                  current_close < lower_expansion and
                  current_close > current_ema * 0.999 and
                  not self.position.is_short):
                
                stop_loss = pre_market_low + 5
                risk = stop_loss - current_close
                take_profit = current_close - (risk * rr_ratio)
                self.sell(sl=stop_loss, tp=take_profit)
    
    bt = Backtest(data, CRTStrategy, commission=0.0002, margin=1/50)
    stats = bt.run()
    st.markdown("---")
    st.subheader("📈 MNQ CRT Strategy Results")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Return", f"{stats['Return [%]']:.2f}%")
    c2.metric("Win Rate", f"{stats['Win Rate [%]']:.2f}%")
    c3.metric("Max Drawdown", f"{stats['Max. Drawdown [%]']:.2f}%")
    c4.metric("Total Trades", f"{stats['# Trades']}")
    st.metric("Sharpe Ratio", f"{stats['Sharpe Ratio']:.2f}")
    st.subheader("📊 Equity Curve")
    st.components.v1.html(bt.plot()._repr_html_(), height=400, width='stretch')

# ============ NY OPEN VWAP & EMA STRATEGY ============
def run_ny_open_strategy():
    st.subheader("📈 NY Open VWAP & 9 EMA Strategy Backtest")
    st.caption("Trades the New York Open (9:30 AM) using VWAP, 9 EMA, and Pre-Market High/Low.")
    
    st.markdown("### 🎛️ Strategy Parameters")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        ema_lookback = st.number_input("EMA Lookback (Bars)", min_value=5, max_value=20, value=9, step=1, key="ny_ema")
        ny_open_hour = st.number_input("NY Open Hour (EST)", min_value=8, max_value=10, value=9, step=1, key="ny_hour")
    with col_p2:
        rr_ratio = st.number_input("Risk:Reward Ratio", min_value=1.0, max_value=5.0, value=2.0, step=0.5, key="ny_rr")
        sl_buffer = st.number_input("Stop Loss Buffer (Points)", min_value=1, max_value=20, value=5, step=1, key="ny_sl")
    with col_p3:
        pre_market_minutes = st.number_input("Pre-Market Lookback (Minutes)", min_value=10, max_value=60, value=30, step=5, key="ny_pre")
    
    run_btn = st.button("🚀 Run NY Open Backtest", key="ny_btn")
    
    if not run_btn:
        st.info("Adjust the parameters above and click 'Run NY Open Backtest' to see results.")
        return
    
    with st.spinner("Fetching MNQ historical data..."):
        mnq = yf.Ticker("MNQ=F").history(period="6mo", interval="1h")
        if mnq.empty:
            st.warning("No data available. Market may be closed.")
            return
    
    data = mnq.copy()
    data.columns = [col.capitalize() for col in data.columns]
    data = data.dropna()
    
    data['EMA'] = data['Close'].ewm(span=ema_lookback, adjust=False).mean()
    data['VWAP'] = (data['Close'] * data['Volume']).cumsum() / data['Volume'].cumsum()
    data['Date'] = data.index.date
    data['Hour'] = data.index.hour
    data['Minute'] = data.index.minute
    data['Is_NY_Open'] = (data['Hour'] == ny_open_hour) & (data['Minute'] == 30)
    
    class NYOpenStrategy(Strategy):
        def init(self):
            super().init()
            self.ema = self.data.EMA
            self.vwap = self.data.VWAP
            self.is_ny_open = self.data.Is_NY_Open
        
        def next(self):
            super().next()
            if len(self.data.Close) < 50: return
            
            current_close = self.data.Close[-1]
            current_ema = self.ema[-1]
            current_vwap = self.vwap[-1]
            recent_opens = self.is_ny_open[-5:].any()
            if not recent_opens:
                return
                
            today = self.data.index[-1].date()
            today_data = self.data[self.data.index.date == today]
            pre_market_data = today_data[today_data['Hour'] < ny_open_hour]
            if len(pre_market_data) < 3:
                return
                
            pre_market_high = pre_market_data['High'].max()
            pre_market_low = pre_market_data['Low'].min()
            if pre_market_high is None or pre_market_low is None:
                return
            
            if (current_close > current_vwap and 
                current_close < current_ema * 1.001 and 
                current_close > pre_market_low and
                not self.position.is_long):
                stop_loss = pre_market_low - sl_buffer
                risk = current_close - stop_loss
                take_profit = current_close + (risk * rr_ratio)
                self.buy(sl=stop_loss, tp=take_profit)
            
            elif (current_close < current_vwap and 
                  current_close > current_ema * 0.999 and 
                  current_close < pre_market_high and
                  not self.position.is_short):
                stop_loss = pre_market_high + sl_buffer
                risk = stop_loss - current_close
                take_profit = current_close - (risk * rr_ratio)
                self.sell(sl=stop_loss, tp=take_profit)
    
    bt = Backtest(data, NYOpenStrategy, commission=0.0002, margin=1/50)
    stats = bt.run()
    st.markdown("---")
    st.subheader("📈 MNQ NY Open Strategy Results")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Return", f"{stats['Return [%]']:.2f}%")
    c2.metric("Win Rate", f"{stats['Win Rate [%]']:.2f}%")
    c3.metric("Max Drawdown", f"{stats['Max. Drawdown [%]']:.2f}%")
    c4.metric("Total Trades", f"{stats['# Trades']}")
    st.metric("Sharpe Ratio", f"{stats['Sharpe Ratio']:.2f}")
    st.subheader("📊 Equity Curve")
    st.components.v1.html(bt.plot()._repr_html_(), height=400, width='stretch')

# ============ ICT STRATEGY BACKTEST ENGINE ============
def run_ict_backtest():
    st.subheader("📊 Interactive ICT Order Block Strategy Backtest")
    st.caption("Tune the strategy parameters on the fly and instantly see the 6-month performance for MNQ and MGC.")
    
    st.markdown("### 🎛️ Strategy Parameters")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        liquidity_lookback = st.number_input("Liquidity Lookback (Bars)", min_value=10, max_value=100, value=50, step=5, key="ict_lookback")
    with col_p2:
        rsi_oversold = st.number_input("RSI Oversold (Long)", min_value=10, max_value=50, value=30, step=5, key="ict_rsi_low")
        rsi_overbought = st.number_input("RSI Overbought (Short)", min_value=50, max_value=90, value=70, step=5, key="ict_rsi_high")
    with col_p3:
        rr_ratio = st.number_input("Risk:Reward Ratio", min_value=1.0, max_value=5.0, value=2.0, step=0.5, key="ict_rr")
        sl_buffer = st.number_input("Stop Loss Buffer (Points)", min_value=1, max_value=20, value=5, step=1, key="ict_sl")
    
    run_btn = st.button("🚀 Run ICT Backtest", key="ict_btn")
    
    if not run_btn:
        st.info("Adjust the parameters above and click 'Run Backtest' to see results.")
        return
    
    with st.spinner("Fetching MNQ and MGC historical data..."):
        mnq = yf.Ticker("MNQ=F").history(period="6mo", interval="1h")
        mgc = yf.Ticker("MGC=F").history(period="6mo", interval="1h")
        if mnq.empty or mgc.empty:
            st.warning("No data available. Market may be closed.")
            return
    
    def run_backtest_on_asset(data, asset_name, lookback, rsi_low, rsi_high, rr, buffer):
        data = data.copy()
        data.columns = [col.capitalize() for col in data.columns]
        
        data['High_L'] = data['High'].rolling(lookback).max()
        data['Low_L'] = data['Low'].rolling(lookback).min()
        data['EMA_200'] = data['Close'].ewm(span=200, adjust=False).mean()
        
        delta = data['Close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))
        
        data['Order_Block'] = np.nan
        bull_cond = (data['Close'] > data['Open']) & (data['Close'] - data['Open'] > 0.75 * (data['High'] - data['Low']))
        data.loc[bull_cond, 'Order_Block'] = data.loc[bull_cond, 'Low']
        bear_cond = (data['Close'] < data['Open']) & (data['Open'] - data['Close'] > 0.75 * (data['High'] - data['Low']))
        data.loc[bear_cond, 'Order_Block'] = data.loc[bear_cond, 'High']
        
        data = data.dropna()
        
        class InteractiveICTStrategy(Strategy):
            def init(self):
                super().init()
                self.highs = self.data.High_L
                self.lows = self.data.Low_L
                self.ema_200 = self.data.EMA_200
                self.rsi = self.data.RSI
                self.order_blocks = self.data.Order_Block
            
            def next(self):
                super().next()
                if len(self.data.Close) < lookback: return
                    
                current_high = self.data.High[-1]
                current_low = self.data.Low[-1]
                current_close = self.data.Close[-1]
                prev_close = self.data.Close[-2]
                current_rsi = self.rsi[-1]
                ema_200 = self.ema_200[-1]
                ob = self.order_blocks[-1]
                
                higher_high = current_high > self.highs[-2]
                lower_low = current_low < self.lows[-2]
                
                if (higher_high and not lower_low and current_close > ema_200 and
                    current_rsi < rsi_low and current_close > prev_close and
                    not np.isnan(ob) and ob < current_close and
                    not self.position.is_long):
                    
                    stop_loss = ob - buffer
                    risk = current_close - stop_loss
                    take_profit = current_close + (risk * rr)
                    self.buy(sl=stop_loss, tp=take_profit)
                
                elif (lower_low and not higher_high and current_close < ema_200 and
                      current_rsi > rsi_high and current_close < prev_close and
                      not np.isnan(ob) and ob > current_close and
                      not self.position.is_short):
                    
                    stop_loss = ob + buffer
                    risk = stop_loss - current_close
                    take_profit = current_close - (risk * rr)
                    self.sell(sl=stop_loss, tp=take_profit)
        
        bt = Backtest(data, InteractiveICTStrategy, commission=0.0002, margin=1/50)
        stats = bt.run()
        return stats, bt
    
    st.markdown("---")
    st.subheader("📈 MNQ Micro Nasdaq - ICT Results")
    stats_mnq, bt_mnq = run_backtest_on_asset(mnq, "MNQ", liquidity_lookback, rsi_oversold, rsi_overbought, rr_ratio, sl_buffer)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Return", f"{stats_mnq['Return [%]']:.2f}%")
    c2.metric("Win Rate", f"{stats_mnq['Win Rate [%]']:.2f}%")
    c3.metric("Max Drawdown", f"{stats_mnq['Max. Drawdown [%]']:.2f}%")
    c4.metric("Total Trades", f"{stats_mnq['# Trades']}")
    st.metric("Sharpe Ratio", f"{stats_mnq['Sharpe Ratio']:.2f}")
    st.subheader("📊 MNQ Equity Curve")
    st.components.v1.html(bt_mnq.plot()._repr_html_(), height=400, width='stretch')
    
    st.markdown("---")
    st.subheader("🥇 MGC Micro Gold - ICT Results")
    stats_mgc, bt_mgc = run_backtest_on_asset(mgc, "MGC", liquidity_lookback, rsi_oversold, rsi_overbought, rr_ratio, sl_buffer)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Return", f"{stats_mgc['Return [%]']:.2f}%")
    c2.metric("Win Rate", f"{stats_mgc['Win Rate [%]']:.2f}%")
    c3.metric("Max Drawdown", f"{stats_mgc['Max. Drawdown [%]']:.2f}%")
    c4.metric("Total Trades", f"{stats_mgc['# Trades']}")
    st.metric("Sharpe Ratio", f"{stats_mgc['Sharpe Ratio']:.2f}")
    st.subheader("📊 MGC Equity Curve")
    st.components.v1.html(bt_mgc.plot()._repr_html_(), height=400, width='stretch')

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

def run_app():
    load_dotenv()
    init_db()
    init_journal_db()
    st.set_page_config(page_title="EdgeFinder Pro - Terminal", layout="wide")
    st.markdown("<style>.stApp { background-color: #0f1116; color: #e8ecf1; } .eco-card { background: #1c2129; padding: 15px; border-radius: 10px; border-left: 4px solid #4c6fff; }</style>", unsafe_allow_html=True)
    st.title("⚡ EdgeFinder Pro - Market Terminal")
    
    main_tab1, main_tab2, main_tab3, main_tab4, main_tab5, main_tab6, main_tab7, main_tab8, main_tab9, main_tab10, main_tab11, main_tab12 = st.tabs([
        "🏠 Dashboard", 
        "📈 Charts", 
        "📅 Regime Report", 
        "🤖 AI Bubble Watch", 
        "💵 DXY Dashboard",
        "📊 ICT Backtest",
        "📈 NY Open Strategy",
        "📈 CRT Strategy",
        "📋 Cheat Sheet",
        "🎯 Market Levels",
        "🌀 Order Flow",
        "📝 Journal"
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
            tyx=yf.Ticker("^TYX").history(period="1d",interval="5m")
            
            if not mnq_pre.empty and not mgc_pre.empty:
                mnq_change=((mnq_pre['Close'].iloc[-1]-mnq_pre['Close'].iloc[0])/mnq_pre['Close'].iloc[0])*100
                mgc_change=((mgc_pre['Close'].iloc[-1]-mgc_pre['Close'].iloc[0])/mgc_pre['Close'].iloc[0])*100
                dxy_val=dxy['Close'].iloc[-1]
                tnx_val=tnx['Close'].iloc[-1]
                tyx_val=tyx['Close'].iloc[-1] if not tyx.empty else 4.50
                
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
        run_ict_backtest()

    with main_tab7:
        run_ny_open_strategy()

    with main_tab8:
        run_crt_strategy()

    with main_tab9:
        run_cheat_sheet()

    with main_tab10:
        run_level_marker()

    with main_tab11:
        run_order_flow_scanner()

    with main_tab12:
        run_journal_tab()

if __name__ == "__main__":
    run_app()