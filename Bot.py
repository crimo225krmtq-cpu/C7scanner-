import asyncio
import logging
import MetaTrader5 as mt5
from telegram import Bot
from datetime import datetime
import pandas as pd
import pytz
import numpy as np

# === CONFIG TON BOT ===
BOT_TOKEN = "8370688019:AAH5ZqN...ton token ici..."
CHAT_ID = 8682366225 # TON ID DÉFINITIF

# PAIRES QUE TU AS DEMANDÉ
SYMBOLS = ["XAUUSD", "EURUSD", "BTCUSD", "NAS100", "VOLATILE_10"]
TIMEZONE = pytz.timezone("Africa/Abidjan")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bot = Bot(token=BOT_TOKEN)

# === FONCTIONS SCANNER C7 ===

def get_data(symbol, timeframe, bars=500):
    tf_map = {"H4": mt5.TIMEFRAME_H4, "H1": mt5.TIMEFRAME_H1, "M15": mt5.TIMEFRAME_M15}
    rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, bars)
    if rates is None: return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def check_trend(df_h4, df_h1):
    # Tendance = EMA50 > EMA200 sur H4 ET H1
    ema50_h4 = df_h4['close'].ewm(span=50).mean().iloc[-1]
    ema200_h4 = df_h4['close'].ewm(span=200).mean().iloc[-1]
    ema50_h1 = df_h1['close'].ewm(span=50).mean().iloc[-1]
    ema200_h1 = df_h1['close'].ewm(span=200).mean().iloc[-1]
    trend_bull = ema50_h4 > ema200_h4 and ema50_h1 > ema200_h1
    trend_bear = ema50_h4 < ema200_h4 and ema50_h1 < ema200_h1
    return trend_bull, trend_bear

def find_fvg(df, i):
    # FVG Bull: bougie i-2 low > bougie i high
    if df['low'].iloc[i-2] > df['high'].iloc[i]:
        return True, df['low'].iloc[i-2], df['high'].iloc[i]
    # FVG Bear: bougie i-2 high < bougie i low
    if df['high'].iloc[i-2] < df['low'].iloc[i]:
        return True, df['high'].iloc[i-2], df['low'].iloc[i]
    return False, 0, 0

def find_ob(df, i, trend_bull):
    # OB Bull = dernière bougie baissière avant impulsion haussière
    if trend_bull and df['close'].iloc[i-1] < df['open'].iloc[i-1]:
        return True, df['high'].iloc[i-1], df['low'].iloc[i-1]
    # OB Bear = dernière bougie haussière avant impulsion baissière
    if not trend_bull and df['close'].iloc[i-1] > df['open'].iloc[i-1]:
        return True, df['high'].iloc[i-1], df['low'].iloc[i-1]
    return False, 0, 0

def check_fibo_zone(price, ob_high, ob_low):
    fibo_61 = ob_low + (ob_high - ob_low) * 0.618
    fibo_78 = ob_low + (ob_high - ob_low) * 0.786
    if fibo_61 <= price <= fibo_78:
        return True, fibo_61, fibo_78
    return False, 0, 0

def get_sl_tp(entry, trend_bull, atr):
    if trend_bull:
        sl = entry - atr * 1.5
        tp = entry + atr * 3
    else:
        sl = entry + atr * 1.5
        tp = entry - atr * 3
    return round(sl, 5), round(tp, 5)

async def scan_pair(symbol):
    try:
        if not mt5.initialize(): return

        df_h4 = get_data(symbol, "H4")
        df_h1 = get_data(symbol, "H1")
        df_m15 = get_data(symbol, "M15")
        if df_h4 is None or df_h1 is None or df_m15 is None: return

        trend_bull, trend_bear = check_trend(df_h4, df_h1)
        if not trend_bull and not trend_bear: return

        # Scan les 3 dernières bougies M15
        for i in range(-3, 0):
            price = df_m15['close'].iloc[i]

            # 1. FVG
            fvg, fvg_top, fvg_bottom = find_fvg(df_m15, i)
            if not fvg: continue

            # 2. OB
            ob, ob_high, ob_low = find_ob(df_m15, i, trend_bull)
            if not ob: continue

            # 3. Prix dans FVG + dans OB + dans FIBO 61.8-78.6
            fibo_ok, fibo_61, fibo_78 = check_fibo_zone(price, ob_high, ob_low)

            if fvg_bottom <= price <= fvg_top and ob_low <= price <= ob_high and fibo_ok:
                atr = df_m15['high'].iloc[i] - df_m15['low'].iloc[i]
                sl, tp = get_sl_tp(price, trend_bull, atr)
                direction = "BUY 🔥" if trend_bull else "SELL ❄️"

                msg = f"""🔔 **SIGNAL C7 - {symbol}**

**Direction**: {direction}
**TF**: M15 | **Heure**: {datetime.now(TIMEZONE).strftime('%H:%M')}
**Entry**: `{price}`
**SL**: `{sl}` | **TP**: `{tp}`
**Zone**: FVG dans OB + Fibo 61.8-78.6
**Validé**: H4 + H1 tendance OK

Pas de News. Attendre confirmation bougie."""
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
                return # Envoie 1 signal max par scan

    except Exception as e:
        logging.error(f"Erreur {symbol}: {e}")

async def main():
    await bot.send_message(chat_id=CHAT_ID, text="✅ C7Scanner225Rimka ACTIF!\nScan Auto toutes les 15min lancé")

    while True:
        now = datetime.now(TIMEZONE)
        if now.minute % 15 == 0:
            logging.info(f"--- SCAN DEBUT {now} ---")
            tasks = [scan_pair(s) for s in SYMBOLS]
            await asyncio.gather(*tasks)
            await asyncio.sleep(60) # evite double scan
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
