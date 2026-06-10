# PAXG/USDT RSI + VWAP Sinyal Botu

Altın (XAU) üzerinden PAXG/USDT kullanarak RSI + VWAP sinyal üretir.
Sinyalleri Telegram'a gönderir. KuCoin verisi kullanır.

## Sinyal Koşulları

| Sinyal | RSI 5m | RSI 15m | VWAP |
|--------|--------|---------|------|
| 🟢 ALIŞ  | ≤ 30 | ≤ 35 | Fiyat altında |
| 🔴 SATIŞ | ≥ 70 | ≥ 65 | Fiyat üstünde |

## Railway Kurulum Adımları

### 1. GitHub'a yükle
- Bu klasördeki tüm dosyaları GitHub reposuna yükle
- `.env` dosyasını **ASLA** yükleme (zaten .gitignore'da engellendi)

### 2. Railway'de proje oluştur
1. [railway.app](https://railway.app) → **New Project**
2. **Deploy from GitHub Repo** → repoyu seç
3. Sol menüden **Variables** sekmesine tıkla

### 3. Environment Variables ekle
Railway → Variables sekmesine şunları ekle:

```
TELEGRAM_TOKEN    = BotFather'dan aldığın token
TELEGRAM_CHAT_ID  = Telegram chat ID'n
```

> İsteğe bağlı (değiştirmek istersen):
> ```
> SYMBOL         = PAXG/USDT
> CHECK_INTERVAL = 10
> ```

### 4. Deploy
- Variables kaydedilince Railway otomatik deploy eder
- **Logs** sekmesinden çalışıp çalışmadığını kontrol et

---

## Telegram Bot Token nasıl alınır?
1. Telegram'da `@BotFather` ara
2. `/newbot` yaz → bot adı ver
3. Gelen TOKEN'ı Railway'e ekle

## Telegram Chat ID nasıl bulunur?
1. `@userinfobot` botuna `/start` yaz
2. Gelen `Id:` değerini Railway'e ekle
