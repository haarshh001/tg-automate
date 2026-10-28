# 🚀 Render Cloud 24/7 Deployment & Multi-Account Guide

Everything in this system (Telegram credentials, StringSession, channel routes, history, and stats) is **stored 100% inside your MongoDB Atlas cloud database**. 

### Why this is a game changer:
- **Zero local storage needed on Render**: Render is 100% disposable and stateless.
- **Switch Render accounts in 30 seconds**: If your Render free tier exhausts, simply connect this same repository to a new Render account. It connects to MongoDB and boots up authorized with all your settings preserved instantly!

---

## 1. How to Allow Access from Any IP in MongoDB Atlas (Crucial for Render)

Render uses dynamic IP addresses that change constantly. To ensure Render can always connect to your MongoDB cluster, you must allow `0.0.0.0/0`:

1. Log into your [MongoDB Atlas Dashboard](https://cloud.mongodb.com).
2. In the left navigation sidebar, look under the **Security** section and click **Network Access**.
3. Click the green **+ Add IP Address** button on the right.
4. In the modal that appears, click the button named **"Allow Access from Anywhere"** (this automatically enters `0.0.0.0/0` into the IP address field).
5. (Optional) Set the comment to `Render Cloud Access`.
6. Click **Confirm**.
7. Wait ~30 seconds until the status badge turns green (`Active`).

Your database is now accessible by Render servers worldwide!

---

## 2. Deploying to Render

1. Push this repository to GitHub.
2. In [Render Dashboard](https://dashboard.render.com), click **New +** ➔ **Web Service**.
3. Select your repository (`tg-automate`).
4. Set:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
5. In the **Environment Variables** tab, add your single database connection string:
   - `DATABASE_URL` = `mongodb+srv://<username>:<password>@cluster0.isa7w5b.mongodb.net/?retryWrites=true&w=majority`
   - `DASHBOARD_PASSWORD` = `your_secure_password`
   - `PORT` = `10000`
6. Click **Create Web Service**.

Render will deploy the service in ~60 seconds.

---

## 3. How to Edit Telegram Credentials & Channels from the Web Dashboard

Once deployed, open your Render web address: `https://your-app.onrender.com`.

Log in with:
- **Username**: *(leave blank or anything)*
- **Password**: `DASHBOARD_PASSWORD`

### Inside the Dashboard:
1. **Telegram Account & Credentials Tab**:
   - View and edit your Telegram API ID, API Hash, StringSession, and Admin ID.
   - Click **Save Credentials to MongoDB** — updates are saved to the cloud instantly without redeploying.
2. **Channel Mappings Tab**:
   - Add new source ➔ target channel routes.
   - Toggle routes ON / OFF with switches.
3. **Live Database History Tab**:
   - Watch incoming posts and link conversions in real time.
4. **Export DB**:
   - Download a full JSON backup with 1 click anytime.

---

## 4. 24/7 Keep-Alive (Prevent Free Tier Sleep)
1. Copy your Render health check URL: `https://your-app.onrender.com/health`.
2. Go to [UptimeRobot.com](https://uptimerobot.com) (free) or [Cron-job.org](https://cron-job.org).
3. Create an HTTP monitor pinging that URL every 5 or 10 minutes.
4. Render will stay awake and active 24 hours a day, 7 days a week!
