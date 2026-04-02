# 🚀 WhatsApp AI Platform — Free Setup Guide

## Overview
This guide sets up a fully **free** WhatsApp AI chatbot using:
- **WhatsApp**: Twilio Sandbox (free)
- **LLM**: Ollama + LLaMA 2 (free, open-source)
- **Hosting**: Railway or Render (free tier)
- **Database**: PostgreSQL (free tier on Railway/Render)

---

## Step 1: Local Development with Ollama

### 1.1 Install Ollama
Download from: https://ollama.ai

### 1.2 Pull LLaMA 2 Model
```bash
ollama pull llama2
ollama serve
```
This runs Ollama on `http://localhost:11434` (keep it running)

### 1.3 Set Up Backend Locally
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux

pip install -r requirements.txt
cp .env.example .env
```

### 1.4 Update `.env` for Local Development
```
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=llama2
DATABASE_URL=sqlite:///./dev.db
```

### 1.5 Run Locally
```bash
uvicorn main:app --reload --port 8000
```

Visit: http://localhost:8000/docs (Swagger UI)

---

## Step 2: Deploy on Railway (Recommended for Free)

### 2.1 Create Railway Account
- Go to https://railway.app
- Sign up with GitHub
- Create new project

### 2.2 Add PostgreSQL Database
1. Click "Advanced" → "PostgreSQL"
2. Railway creates DB automatically
3. Copy the `DATABASE_URL` to your `.env`

### 2.3 Deploy Backend
1. Connect your GitHub repo
2. Select the `backend/` folder
3. Railway auto-detects `Procfile` or `Dockerfile`
4. Add environment variables from `.env`:
   ```
   TWILIO_ACCOUNT_SID
   TWILIO_AUTH_TOKEN
   TWILIO_WHATSAPP_NUMBER
   OLLAMA_API_URL
   OLLAMA_MODEL
   DATABASE_URL
   ```

### 2.4 Set OLLAMA_API_URL for Production
**Option A: Keep Local Ollama**
- Only works if your machine stays on
- Not recommended for production
- URL: `http://localhost:11434/api/generate`

**Option B: Run Ollama on Railway (requires Docker)**
```bash
# Add another service in Railway for Ollama
# Use: ollama/ollama Docker image
# Port: 11434
```

**Option C: Use Free Ollama Cloud (Easiest)**
- Sign up: https://www.ollama.ai/cloud
- Get public API endpoint
- Use in `OLLAMA_API_URL`

### 2.5 Get Your Backend URL
Railway gives you a domain like: `https://your-app-xyz.railway.app`

---

## Step 3: Configure Twilio Webhook

1. Go to https://console.twilio.com
2. Navigate to WhatsApp Sandbox
3. Set Webhook URL: `https://your-app-xyz.railway.app/webhook/whatsapp`
4. Test webhook works in Twilio Console

---

## Step 4: Test End-to-End
1. Send WhatsApp message to Twilio's sandbox number
2. Message hits your webhook → Ollama generates reply → Twilio sends back
3. Check logs: Railway dashboard → Logs

---

## Cost Breakdown (Monthly)
| Service | Cost | Notes |
|---------|------|-------|
| Twilio Sandbox | $0 | ~3000 free messages |
| Railway | Free tier | 500 hours + 100GB bandwidth/month |
| Ollama | $0 | Open source |
| **Total** | **$0** | 100% Free! |

---

## Alternative: Deploy on Render

### Similar to Railway:
1. Go to https://render.com
2. Connect GitHub repo
3. Create Web Service + PostgreSQL
4. Deploy

---

## Troubleshooting

### "Ollama connection refused"
- Is Ollama running? (`ollama serve`)
- Wrong URL? Should be `http://localhost:11434/api/generate`
- Using remote Ollama? Check firewall rules

### "Twilio webhook not connecting"
- Railway URL correct? (Include `/webhook/whatsapp`)
- Twilio Auth Token correct?
- Database migrations ran? Check Railway logs

### "Database connection error"
- In Railway: Check PostgreSQL service is running
- `DATABASE_URL` correct? (Railway provides it)
- Run migrations: `python -c "from database import create_tables; create_tables()"`

---

## Next Steps
1. Add more businesses to your `businesses` table
2. Customize system prompts in `claude_handler.py` (now `llm_handler.py`)
3. Add escalation logic for human handoff
4. Scale to paid Ollama API or Claude when needed

---

**Questions?** Check Railway/Render docs or ask in their communities!
