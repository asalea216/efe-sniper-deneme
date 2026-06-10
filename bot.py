import ccxt
import pandas as pd
import numpy as np
import time
import requests
import logging
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- AYARLAR ---
TOKEN          = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID", "")
SYMBOL         = os.getenv("SYMBOL", "PAXG/USDT")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "10"))

TZ_TR = timezone(timedelta(hours=3))

exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'timeout': 30000,
})


# ─────────────────────────────────────────────
# YARDIMCI
# ─────────────────────────────────────────────

def now_tr():
    return datetime.now(TZ_TR)

def is_trading_hour():
    return 8 <= now_tr().hour <= 23

def send_telegram_msg(text: str) -> bool:
    if not TOKEN or not CHAT_ID:
        logger.warning("⚠️ TELEGRAM_TOKEN veya TELEGRAM_CHAT_ID eksik!")
        return False
    for attempt in range(3):
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            r = requests.post(url, data={
                'chat_id': CHAT_ID,
                'text': text,
                'parse_mode': 'HTML'
            }, timeout=10)
            if r.status_code == 200:
                logger.info("✅ Telegram mesajı gönderildi.")
                return True
            logger.warning(f"Telegram HTTP {r.status_code}: {r.text}")
        except Exception as e:
            logger.error(f"❌ Mesaj Hatası (Deneme {attempt+1}/3): {e}")
            time.sleep(2)
    return False


# ─────────────────────────────────────────────
# RSI (manuel — pandas_ta yok)
# ─────────────────────────────────────────────

def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ─────────────────────────────────────────────
# OHLCV ÇEK
# ─────────────────────────────────────────────

def get_ohlcv(timeframe: str, limit: int = 150) -> pd.DataFrame:
    raw = exchange.fetch_ohlcv(SYMBOL, timeframe, limit=limit)
    df  = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df


# ─────────────────────────────────────────────
# VWAP (KuCoin 5m — gün başından itibaren)
# ─────────────────────────────────────────────

def get_vwap_and_price() -> tuple:
    df = get_ohlcv('5m', limit=200)

    # Bugünün UTC 00:00 timestamp'i (ms)
    today_ms = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp() * 1000

    today_df = df[df['timestamp'] >= today_ms].copy()
    if len(today_df) < 5:
        today_df = df.tail(80).copy()   # fallback

    today_df['tp']  = (today_df['high'] + today_df['low'] + today_df['close']) / 3
    today_df['tpv'] = today_df['tp'] * today_df['volume']

    cum_vol = today_df['volume'].cumsum()
    cum_tpv = today_df['tpv'].cumsum()
    vwap    = (cum_tpv / cum_vol.replace(0, np.nan)).iloc[-1]

    price = today_df['close'].iloc[-1]
    return round(float(vwap), 2), round(float(price), 2)


# ─────────────────────────────────────────────
# SİNYAL HESABI
# ─────────────────────────────────────────────

def get_signals() -> dict:
    df_5m  = get_ohlcv('5m',  limit=100)
    df_15m = get_ohlcv('15m', limit=100)

    df_5m['rsi']  = calc_rsi(df_5m['close'],  14)
    df_15m['rsi'] = calc_rsi(df_15m['close'], 14)

    rsi_5m  = round(float(df_5m['rsi'].iloc[-1]),  2)
    rsi_15m = round(float(df_15m['rsi'].iloc[-1]), 2)

    vwap, price = get_vwap_and_price()

    return {
        'rsi_5m':      rsi_5m,
        'rsi_15m':     rsi_15m,
        'vwap':        vwap,
        'price':       price,
        'below_vwap':  price < vwap,
        'above_vwap':  price > vwap,
    }


# ─────────────────────────────────────────────
# ANA DÖNGÜ
# ─────────────────────────────────────────────

def run_bot():
    logger.info("🚀 BOT BAŞLATILDI")
    send_telegram_msg(
        f"🤖 <b>PAXG RSI + VWAP Bot Başlatıldı!</b>\n"
        f"📊 Sembol     : {SYMBOL} (KuCoin)\n"
        f"⏱ Timeframe  : 5m + 15m RSI\n"
        f"📊 VWAP       : Günlük (5m mumlar, KuCoin)\n"
        f"📉 ALIŞ  cond : RSI 5m ≤ 30 &amp; RSI 15m ≤ 35 &amp; Fiyat &lt; VWAP\n"
        f"📈 SATIŞ cond : RSI 5m ≥ 70 &amp; RSI 15m ≥ 65 &amp; Fiyat &gt; VWAP\n"
        f"🕐 Aktif      : 08:00 – 23:59 (Türkiye)\n"
        f"🕐 Şu an      : {now_tr().strftime('%H:%M:%S')}"
    )

    last_alert         = None   # "buy" | "sell" | None
    consecutive_errors = 0
    MAX_ERRORS         = 10

    while True:
        try:
            if is_trading_hour():
                sig     = get_signals()
                tr_time = now_tr().strftime('%H:%M')

                logger.info(
                    f"RSI 5m: {sig['rsi_5m']:>6} | RSI 15m: {sig['rsi_15m']:>6} | "
                    f"Fiyat: {sig['price']:>8} | VWAP: {sig['vwap']:>8} | "
                    f"{'↓ VWAP ALTI' if sig['below_vwap'] else '↑ VWAP ÜSTÜ'}"
                )

                # ── GÜÇLÜ ALIŞ ──────────────────────────────────
                if (sig['rsi_5m']  <= 30
                        and sig['rsi_15m'] <= 35
                        and sig['below_vwap']
                        and last_alert != "buy"):

                    send_telegram_msg(
                        f"🟢🟢 <b>GÜÇLÜ ALIŞ SİNYALİ — PAXG/USDT</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 Fiyat  : <b>{sig['price']}</b>\n"
                        f"📊 VWAP   : {sig['vwap']} ✅ (fiyat altında)\n"
                        f"📉 RSI 5m : <b>{sig['rsi_5m']}</b>\n"
                        f"📉 RSI 15m: <b>{sig['rsi_15m']}</b>\n"
                        f"🕐 {tr_time}"
                    )
                    last_alert = "buy"

                # ── GÜÇLÜ SATIŞ ─────────────────────────────────
                elif (sig['rsi_5m']  >= 70
                        and sig['rsi_15m'] >= 65
                        and sig['above_vwap']
                        and last_alert != "sell"):

                    send_telegram_msg(
                        f"🔴🔴 <b>GÜÇLÜ SATIŞ SİNYALİ — PAXG/USDT</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 Fiyat  : <b>{sig['price']}</b>\n"
                        f"📊 VWAP   : {sig['vwap']} ✅ (fiyat üstünde)\n"
                        f"📈 RSI 5m : <b>{sig['rsi_5m']}</b>\n"
                        f"📈 RSI 15m: <b>{sig['rsi_15m']}</b>\n"
                        f"🕐 {tr_time}"
                    )
                    last_alert = "sell"

                # ── NÖTR → sıfırla ──────────────────────────────
                elif 45 < sig['rsi_5m'] < 55:
                    if last_alert is not None:
                        logger.info("↩️  RSI nötr bölge — sinyal sıfırlandı.")
                    last_alert = None

            else:
                logger.info(f"💤 Trading saati dışı — {now_tr().strftime('%H:%M:%S')}")

            consecutive_errors = 0
            time.sleep(CHECK_INTERVAL)

        except ccxt.NetworkError as e:
            consecutive_errors += 1
            logger.error(f"🌐 Ağ Hatası ({consecutive_errors}/{MAX_ERRORS}): {e}")
            time.sleep(30)

        except ccxt.ExchangeError as e:
            consecutive_errors += 1
            logger.error(f"🏦 Borsa Hatası ({consecutive_errors}/{MAX_ERRORS}): {e}")
            time.sleep(60)

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"⚠️ Genel Hata ({consecutive_errors}/{MAX_ERRORS}): {e}")
            time.sleep(10)

        if consecutive_errors >= MAX_ERRORS:
            send_telegram_msg(
                f"🚨 <b>BOT KRİTİK HATA!</b>\n"
                f"{MAX_ERRORS} ardışık hata — lütfen Railway loglarına bak!"
            )
            consecutive_errors = 0


if __name__ == "__main__":
    run_bot()
