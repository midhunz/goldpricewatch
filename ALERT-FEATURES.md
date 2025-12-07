# Multi-Channel Gold Price Alert System

## Goal
Notify users about daily gold prices or specific price targets via their preferred communication channel (WhatsApp, Telegram, Email).

## Channel Analysis

### 1. Telegram (Recommended for MVP) 🚀
**Pros:**
- **Free:** No cost for sending messages via Bot API.
- **Easy:** Very simple API.
- **Privacy:** Users just chat with a bot, no need to verify phone numbers via SMS.
- **Rich Media:** Can send charts/images easily.

**How it works:**
1. User clicks "Subscribe on Telegram" button on website.
2. Opens Telegram app -> `@GoldRateBot`.
3. User clicks `Start`.
4. Bot asks: "Which region?" (Buttons: India, UAE, etc.).
5. Backend saves `chat_id` and `region`.
6. Daily job sends price update to `chat_id`.

### 2. WhatsApp
**Pros:**
- **High Reach:** Everyone uses WhatsApp.
- **High Open Rate:** Messages are almost always read.

**Cons:**
- **Cost:** WhatsApp Business API charges per conversation (approx $0.05 - $0.10).
- **Complexity:** Requires business verification (Meta) or Twilio wrapper.
- **Strict Rules:** Promotional messages can get banned.

**Implementation:**
- Use **Twilio API** for easiest integration.
- User sends "Join" to sandbox number.

### 3. Email
**Pros:**
- **Professional:** Good for weekly summaries or detailed reports.
- **Cheap:** AWS SES or SendGrid free tiers.

**Cons:**
- **Low Urgency:** Not good for "Price Drop Alert" (might be seen hours later).
- **Spam:** Emails often go to spam/promotions tab.

---

## Proposed Architecture

### Database Schema
```sql
CREATE TABLE alert_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100), -- Email or Phone or Telegram Chat ID
    channel VARCHAR(20),  -- 'TELEGRAM', 'WHATSAPP', 'EMAIL'
    region VARCHAR(50),
    purity VARCHAR(20),
    alert_type VARCHAR(20), -- 'DAILY', 'THRESHOLD'
    target_price FLOAT,     -- Only for THRESHOLD
    condition VARCHAR(10),  -- 'ABOVE', 'BELOW'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Backend Logic (Python/FastAPI)

#### 1. Telegram Bot Service (Polling or Webhook)
- Listens for `/start`
- Listens for `/subscribe <region>`
- Updates database.

#### 2. Notification Scheduler
- Runs daily at 9:00 AM.
- Queries `alert_subscriptions` where `alert_type = 'DAILY'`.
- Sends messages via respective APIs.

#### 3. Threshold Monitor
- Runs after every scraper execution.
- Checks `THRESHOLD` alerts.
- Triggers message if condition met.

---

## Recommendation
**Start with Telegram.** It's free, instant, and developer-friendly. We can build a fully functional prototype in < 2 hours.
