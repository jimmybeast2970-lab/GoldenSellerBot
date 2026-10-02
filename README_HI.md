# Golden Seller Telegram Bot

यह Bot Seller registration, order entry, Telegram Stars payment, automatic order confirmation और seller/month reports के लिए है।

## जरूरी सुरक्षा
Bot token को कभी chat, screenshot या public code में न डालें। आपने पुराना token साझा किया था, इसलिए BotFather से नया token इस्तेमाल करें।

## Setup
1. इस ZIP को किसी Python 3.11+ server/computer पर extract करें।
2. `pip install -r requirements.txt`
3. `.env.example` की copy बनाकर `.env` करें।
4. `.env` में:
   - `BOT_TOKEN` = BotFather का नया token
   - `ADMIN_ID` = आपका Telegram numeric user ID
   - `PAYMENT_STARS` = order confirmation के लिए Stars की संख्या
5. `python bot.py`

## Admin ID
Bot चलने के बाद आप `/start` या `/admin` से Admin panel तभी पाएँगे जब `.env` का `ADMIN_ID` आपके Telegram numeric ID से match करे।

## Payment
Telegram Stars invoices `XTR` currency में होते हैं। Payment successful होने के बाद ही order `CONFIRMED` होता है। Telegram के official flow में `pre_checkout_query` और फिर `successful_payment` को handle करना जरूरी है।

**महत्वपूर्ण:** `PAYMENT_STARS=100` का अर्थ 100 Telegram Stars है, ₹100 नहीं। यदि आपको लगभग ₹100 का confirmation fee रखना है तो Stars की संख्या अलग से तय करनी होगी क्योंकि Star price/fees और INR value बदल सकती है। इसे production में लगाने से पहले test payment करें।

## Current features
- Seller registration
- Bank/UPI details
- New order
- Stars payment
- Automatic confirmation
- Admin notification
- Today report
- Current month report
- Seller list
- CSV export
- SQLite database

## Production में आगे
- Webhook/HTTPS hosting
- Automatic database backups
- Admin seller add/block/edit
- Date/month selector
- Excel `.xlsx` report
- Refund/support commands
- Terms and support pages
- Payment amount configuration
