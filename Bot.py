import asyncio
import logging
import yfinance as yf
from telegram import Bot
from datetime import datetime
import pandas as pd
import pytz

# === CONFIG TOI ===
BOT_TOKEN = "8874286424:AAEiYnHXmSeU9kJsIpUF76pwnKXwsNtr91E"
CHAT_ID = 8682366225

# Map pour yfinance : Forex et Indices
SYMBOLS_MAP = {
    "XAUUSD": "XAUUSD=X",
    "EURUSD": "EURUSD=X",
    "BTCUSD": "BTC-USD",
    "NAS100": "^NDX",
    "VOLATILE_10": "VOLATILE_10" # Ça on skip car pas dispo sur yfinance
}
TZ = pytz.timezone("Africa/Abidjan")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
bot = Bot(token=BOT_TOKEN)

def get_data(symbol_yf, timeframe, bars=500):
    period_map = {"H4": "60d", "H1": "7d", "M15": "2d"}
    interval_map = {"H4": "1h", "H1": "1h", "M15": "15m"}

    try:
        ticker = yf.Ticker(symbol_yf)
        df = ticker.history(period=period_map[timeframe], interval=interval_map[timeframe])
        if df.empty: return None
        df = df.reset_index()
        df['time'] = pd.to_datetime(df['Date'])
        df = df.tail(bars)
        return df
    except: return None

def check_trend(df_h4, df_h1):
    ema50_h4 = df_h4['Close'].ewm(span=50).mean().iloc[-1]
    ema200_h4 = df_h4['Close'].ewm(span=200).mean().iloc[-1]
    ema50_h1 = df_h1['Close'].ewm(span=50).mean().iloc[-1]
    ema200_h1 = df_h1['Close'].ewm(span=200).mean().iloc[-1]
    trend_bull = ema50_h4 > ema200_h4 and ema50_h1 > ema200_h1
    trend_bear = ema50_h4 < ema200_h4 and ema50_h1 < ema200_h1
    return trend_bull, trend_bear

def find_fvg(df, i):
    if i < 2: return False, 0, 0
    if df['Low'].iloc[i-2] > df['High'].iloc[i]: # FVG Bull
        return True, df['Low'].iloc[i-2], df['High'].iloc[i]
    if df['High'].iloc[i-2] < df['Low'].iloc[i]: # FVG Bear
        return True, df['High'].iloc[i-2], df['Low'].iloc[i]
    return False, 0, 0

def find_ob(df, i, trend_bull):
    if i < 1: return False, 0, 0
    if trend_bull and df['Close'].iloc[i-1] < df['Open'].iloc[i-1]:
        return True, df['High'].iloc[i-1], df['Low'].iloc[i-1]
    if not trend_bull and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
        return True, df['High'].iloc[i-1], df['Low'].iloc[i-1]
    return False, 0, 0

def check_fibo_zone(price, ob_high, ob_low):
    if ob_high == 0: return False, 0, 0
    fibo_61 = ob_low + (ob_high - ob_low) * 0.618
    fibo_78 = ob_low + (ob_high - ob_low) * 0.786
    if fibo_61 <= price <= fibo_78: return True, fibo_61, fibo_78
    return False, 0, 0

def get_sl_tp(entry, trend_bull, atr):
    if trend_bull: sl = entry - atr * 1.5; tp = entry + atr * 3
    else: sl = entry + atr * 1.5; tp = entry - atr * 3
    return round(sl, 5), round(tp, 5)

async def scan_pair(symbol_name, symbol_yf):
    try:
        df_h4 = get_data(symbol_yf, "H4")
        df_h1 = get_data(symbol_yf, "H1")
        df_m15 = get_data(symbol_yf, "M15")
        if df_h4 is None or df_h1 is None or df_m15 is None: return

        trend_bull, trend_bear = check_trend(df_h4, df_h1)
        if not trend_bull and not trend_bear: return

        for i in range(-3, 0):
            price = df_m15['Close'].iloc[i]
            fvg, fvg_top, fvg_bottom = find_fvg(df_m15, i)
            ob, ob_high, ob_low = find_ob(df_m15, i, trend_bull)
            fibo_ok, fibo_61, fibo_78 = check_fibo_zone(price, ob_high, ob_low)

            if fvg and ob and fibo_ok and fvg_bottom <= price <= fvg_top and ob_low <= price <= ob_high:
                atr = df_m15['High'].iloc[i] - df_m15['Low'].iloc[i]
                sl, tp = get_sl_tp(price, trend_bull, atr)
                direction = "BUY 🔥" if trend_bull else "SELL ❄️"
                msg = f"""🔔 **SIGNAL C7 - {symbol_name}**
**Direction**: {direction}
**TF**: M15 | **Heure**: {datetime.now(TZ).strftime('%H:%M')}
**Entry**: `{price}`
**SL**: `{sl}` | **TP**: `{tp}`
**Zone**: FVG dans OB + Fibo 61.8-78.6"""
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
                logging.info(f"Signal envoyé pour {symbol_name}")
                return
    except Exception as e: logging.error(f"Erreur {symbol_name}: {e}")

async def main():
    await bot.send_message(chat_id=CHAT_ID, text="✅ C7Scanner YFINANCE ACTIF!\nScan Auto toutes les 15min lancé")
    logging.info("Bot démarré")
    while True:
        logging.info("Lancement du scan...")
        tasks = [scan_pair(name, yf_sym) for name, yf_sym in SYMBOLS_MAP.items()]
        await asyncio.gather(*tasks)
        logging.info("Scan terminé. Attente 15min")
        await asyncio.sleep(900)

if __name__ == "__main__":
    asyncio.run(main())
