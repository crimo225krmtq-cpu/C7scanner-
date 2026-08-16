import time
import yfinance as yf
import pandas as pd
import numpy as np
from telegram import Bot
import asyncio
import os

# ========== CONFIG ==========
TOKEN = os.environ.get("TOKEN", "8874286424:AAEiYnHXmSeU9kJsIpUF76pwnKXwsNtr91E")
CHAT_ID = os.environ.get("CHAT_ID", "52504489")
bot = Bot(token=TOKEN)

# Les 5 marchés que tu m’as donné
MARKETS = {
    "GOLD": "GC=F", # Gold
    "EURUSD": "EURUSD=X", # Euro USD
    "NASDAQ": "^IXIC", # Nasdaq
    "VIX": "^VIX", # Index Volatilité
    "BTCUSD": "BTC-USD" # BTC USD
}

# ========== FONCTIONS C7 ==========

def get_data(symbol, timeframe):
    """Récupère les données H4, H1, M15"""
    periods = {"H4": "60d", "H1": "30d", "M15": "7d"}
    intervals = {"H4": "4h", "H1": "1h", "M15": "15m"}

    try:
        df = yf.download(symbol, period=periods[timeframe], interval=intervals[timeframe], progress=False)
        return df
    except:
        return None

def get_trend(df_h4, df_h1):
    """Tendance H4 + H1. Les 2 doivent être d'accord"""
    if df_h4 is None or df_h1 is None or len(df_h4) < 50 or len(df_h1) < 50:
        return "NONE"

    ema50_h4 = df_h4['Close'].ewm(span=50).mean().iloc[-1]
    ema200_h4 = df_h4['Close'].ewm(span=200).mean().iloc[-1]
    ema50_h1 = df_h1['Close'].ewm(span=50).mean().iloc[-1]
    ema200_h1 = df_h1['Close'].ewm(span=200).mean().iloc[-1]

    trend_h4 = "UP" if ema50_h4 > ema200_h4 else "DOWN"
    trend_h1 = "UP" if ema50_h1 > ema200_h1 else "DOWN"

    if trend_h4 == trend_h1:
        return trend_h4
    return "NONE" # On ne trade pas si pas aligné

def get_fibonacci_zone(df):
    """Zone Fibo 61.8 à 78.6"""
    if len(df) < 20: return None, None
    high = df['High'].iloc[-20:].max()
    low = df['Low'].iloc[-20:].min()
    diff = high - low

    zone_618 = high - diff * 0.618
    zone_786 = high - diff * 0.786

    if zone_618 > zone_786: # Pour DOWN
        return zone_786, zone_618
    else: # Pour UP
        return zone_618, zone_786

def check_rvg_ob(df_m15):
    """Simule RVG + OB sur M15. Prix dans une zone de demande/offre"""
    if len(df_m15) < 10: return False
    last_candle = df_m15.iloc[-1]
    prev_candle = df_m15.iloc[-2]

    # RVG = FVG: gap entre bougies
    # OB = Order Block: grosse bougie impulsive
    body = abs(last_candle['Close'] - last_candle['Open'])
    range_candle = last_candle['High'] - last_candle['Low']

    is_ob = body > range_candle * 0.6 # Bougie forte
    is_rvg = abs(last_candle['Close'] - prev_candle['Close']) > range_candle * 0.3 # Mouvement

    return is_ob or is_rvg

def analyze_market(name, symbol):
    """Analyse complète C7"""
    df_h4 = get_data(symbol, "H4")
    df_h1 = get_data(symbol, "H1")
    df_m15 = get_data(symbol, "M15")

    # 1. TENDANCE H4 + H1
    trend = get_trend(df_h4, df_h1)
    if trend == "NONE": return None

    # 2. ZONE FIBO 61.8 - 78.6
    fibo_low, fibo_high = get_fibonacci_zone(df_h4 if trend=="UP" else df_h1)
    if fibo_low is None: return None

    current_price = df_m15['Close'].iloc[-1]

    # Prix doit être dans la zone 61.8 - 78.6
    in_fibo_zone = fibo_low <= current_price <= fibo_high

    # 3. RVG + OB sur M15
    has_rvg_ob = check_rvg_ob(df_m15)

    # 4. SIGNAL
    if in_fibo_zone and has_rvg_ob:
        signal_type = "BUY" if trend == "UP" else "SELL"
        tp = fibo_high if trend == "UP" else fibo_low
        sl = fibo_low if trend == "UP" else fibo_high

        return {
            "market": name,
            "type": signal_type,
            "entry": round(current_price, 4),
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "timeframe": "M15"
        }
    return None

async def send_signal(signal):
    """Envoie le signal sur Telegram"""
    msg = f"""🚨 **C7 SIGNAL M15** 🚨

**Marché:** {signal['market']}
**Position:** {signal['type']}
**Entry:** {signal['entry']}
**SL:** {signal['sl']}
**TP:** {signal['tp']}

Zone: RVG + OB + Fibo 61.8-78.6
Tendance: H4/H1 Confirmée
"""
    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')

async def main():
    """Boucle toutes les 15 minutes"""
    await bot.send_message(chat_id=CHAT_ID, text="✅ **C7Scanner225Rimka ACTIF!**\nAnalyse toutes les 15min: GOLD, EURUSD, NASDAQ, VIX, BTCUSD")

    while True:
        for name, symbol in MARKETS.items():
            signal = analyze_market(name, symbol)
            if signal:
                await send_signal(signal)

        # Attendre 15 minutes = 900 secondes
        await asyncio.sleep(900)

if __name__ == "__main__":
    asyncio.run(main())
