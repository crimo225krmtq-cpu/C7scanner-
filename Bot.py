import asyncio
import logging
import MetaTrader5 as mt5
from telegram import Bot
from datetime import datetime
import pandas as pd
import pytz
import numpy as np

# === CONFIG TOI ===
BOT_TOKEN = "8874286424:AAEiYnHXmSeU9kJsIpUF76pwnKXwsNtr91E" # NOUVEAU TOKEN
CHAT_ID = 8682366225 # TON ID

SYMBOLS = ["XAUUSD", "EURUSD", "BTCUSD", "NAS100", "VOLATILE_10"]
TZ = pytz.timezone("Africa/Abidjan")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)

def get_data(symbol, timeframe, bars=500):
    tf_map = {"H4": mt5.TIMEFRAME_H4, "H1": mt5.TIMEFRAME_H1, "M15": mt5.TIMEFRAME_M15}
    rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, bars)
    if rates is None: return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def check_trend(df_h4, df_h1):
    ema50_h4 = df_h4['close'].ewm(span=50).mean().iloc[-1]
    ema200_h4 = df_h4['close'].ewm(span=200).mean().iloc[-1]
    ema50_h1 = df_h1['close'].ewm(span=50).mean().iloc[-1]
    ema200_h1 = df_h1['close'].ewm(span=200).mean().iloc[-1]
    trend_bull = ema50_h4 > ema200_h4 and ema50_h1 > ema200_h1
    trend_bear = ema50_h4 < ema200_h4 and ema50_h1 < ema200_h1
    return trend_bull, trend_bear

def find_fvg(df, i):
    if df['low'].iloc[i-2] > df['high'].iloc[i]: # FVG Bull
        return True, df['low'].iloc[i-2], df['high'].iloc[i]
    if df['high'].iloc[i-2] < df['low'].iloc[i]: # FVG Bear
        return True, df['high'].iloc[i-2], df['low'].iloc[i]
    return False, 0, 0

def find_ob(df, i, trend_bull):
    if trend_bull and df['close'].iloc[i-1] < df['open'].iloc[i-1]:
        return True, df['high'].iloc[i-1], df['low'].iloc[i-1]
    if not trend_bull and df['close'].iloc[i-1] > df['open'].iloc[i-1]:
        return True, df['high'].iloc[i-1], df['low'].iloc[i-1]
    return False, 0, 0

def check_fibo_zone(price, ob_high, ob_low):
    fibo_61 = ob_low + (ob_high - ob_low) * 0.618
    fibo_78 = ob_low + (ob_high - ob_low) * 0.786
    if fibo_61 <= price <= fibo_78: return True, fibo_61, fibo_78
    return False, 0, 0

def get_sl_tp(entry, trend_bull, atr):
    if trend_bull: sl = entry - atr * 1.5; tp = entry + atr * 3
    else: sl = entry + atr * 1.5; tp = entry - atr * 3
    return round(sl, 5), round(tp, 5)

async def scan_pair(symbol):
    try:
        if not mt5.initialize(): return
        df_h4 = get_data(symbol, "H4")
        df_h1 = get_data(symbol, "H1")
        df_m15 = get_data(symbol, "M15")
        if df_h4 is None: return

        trend_bull, trend_bear = check_trend(df_h4, df_h1)
        if not trend_bull and not trend_bear: return

        for i in range(-3, 0):
            price = df_m15['close'].iloc[i]
            fvg, fvg_top, fvg_bottom = find_fvg(df_m15, i)
            ob, ob_high, ob_low = find_ob(df_m15, i, trend_bull)
            fibo_ok, fibo_61, fibo_78 = check_fibo_zone(price, ob_high, ob_low)

            if fvg and ob and fibo_ok and fvg_bottom <= price <= fvg_top and ob_low <= price <= ob_high:
                atr = df_m15['high'].iloc[i] - df_m15['low'].iloc[i]
                sl, tp = get_sl_tp(price, trend_bull, atr)
                direction = "BUY 🔥" if trend_bull else "SELL ❄️"
                msg = f"""🔔 **SIGNAL C7 - {symbol}**
**Direction**: {direction}
**TF**: M15 | **Heure**: {datetime.now(TZ).strftime('%H:%M')}
**Entry**: `{price}`
**SL**: `{sl}` | **TP**: `{tp}`
**Zone**: FVG dans OB + Fibo 61.8-78.6
**Validé**: H4 + H1 tendance OK"""
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
                return
    except Exception as e: logging.error(f"Erreur {symbol}: {e}")

async def main():
    await bot.send_message(chat_id=CHAT_ID
