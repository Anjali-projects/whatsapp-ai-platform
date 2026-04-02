"""
main.py — FastAPI application entry point.

Run with: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

from database import get_db, create_tables, Business, Contact, Message, BotSession
from webhook import router as webhook_router
from claude_handler import generate_faqs_from_description, draft_broadcast_message

app = FastAPI(
    title="WhatsApp AI Platform",
    description="Claude-powered WhatsApp automation for Indian small businesses",
    version="1.0.0"
)

# ── CORS (allow React frontend to call this API) ──────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include routers ───────────────────────────────────────────────────────────
app.include_router(webhook_router, tags=["WhatsApp Webhook"])


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    create_tables()
    print("🚀 WhatsApp AI Platform started")


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "running", "platform": "WhatsApp AI Platform v1.0"}


# ═══════════════════════════════════════════════════════════════════════════════
# BUSINESS MANAGEMENT APIS
# These will be called by your React dashboard
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/businesses")
def create_business(payload: dict, db: Session = Depends(get_db)):
    """
    Register a new client business on the platform.
    Called when a new client signs up.
    """
    business = Business(
        id=str(uuid.uuid4()),
        name=payload["name"],
        whatsapp_number=payload["whatsapp_number"],
        business_type=payload.get("business_type", "general"),
        owner_name=payload.get("owner_name"),
        owner_phone=payload.get("owner_phone"),
        plan=payload.get("plan", "starter"),
        bot_config=payload.get("bot_config", {})
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    return {"status": "created", "business_id": business.id}


@app.get("/api/businesses/{business_id}")
def get_business(business_id: str, db: Session = Depends(get_db)):
    """Get a single business's full profile."""
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return {"error": "Business not found"}
    return {
        "id": business.id,
        "name": business.name,
        "whatsapp_number": business.whatsapp_number,
        "business_type": business.business_type,
        "plan": business.plan,
        "is_active": business.is_active,
        "bot_config": business.bot_config
    }


@app.put("/api/businesses/{business_id}/config")
def update_bot_config(business_id: str, config: dict, db: Session = Depends(get_db)):
    """
    Update a business's bot configuration.
    Called when owner fills in the Settings form in the dashboard.
    """
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return {"error": "Not found"}
    business.bot_config = config
    db.commit()
    return {"status": "updated"}


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATION & INBOX APIS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/businesses/{business_id}/conversations")
def get_conversations(business_id: str, db: Session = Depends(get_db)):
    """
    Returns all contacts with their latest message.
    Powers the Inbox view in the dashboard.
    """
    contacts = db.query(Contact).filter(
        Contact.business_id == business_id
    ).order_by(Contact.last_seen.desc()).all()

    result = []
    for contact in contacts:
        last_msg = db.query(Message).filter(
            Message.contact_id == contact.id
        ).order_by(Message.timestamp.desc()).first()

        result.append({
            "contact_id": contact.id,
            "phone": contact.phone,
            "name": contact.name,
            "lead_status": contact.lead_status,
            "tags": contact.tags,
            "last_message": last_msg.content[:80] if last_msg else "",
            "last_seen": contact.last_seen.isoformat() if contact.last_seen else None,
            "total_messages": contact.total_messages
        })

    return result


@app.get("/api/businesses/{business_id}/contacts/{contact_id}/messages")
def get_chat_history(business_id: str, contact_id: str, db: Session = Depends(get_db)):
    """
    Returns full chat history for one contact.
    Powers the chat detail view in the dashboard.
    """
    messages = db.query(Message).filter(
        Message.business_id == business_id,
        Message.contact_id == contact_id
    ).order_by(Message.timestamp.asc()).all()

    return [{
        "id": m.id,
        "direction": m.direction,
        "content": m.content,
        "sender": m.sender,
        "was_ai": m.was_ai,
        "timestamp": m.timestamp.isoformat()
    } for m in messages]


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS APIS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/businesses/{business_id}/analytics")
def get_analytics(business_id: str, db: Session = Depends(get_db)):
    """
    Key metrics for the analytics dashboard.
    """
    total_contacts  = db.query(Contact).filter(Contact.business_id == business_id).count()
    total_messages  = db.query(Message).filter(Message.business_id == business_id).count()
    ai_messages     = db.query(Message).filter(
        Message.business_id == business_id,
        Message.was_ai == True
    ).count()
    inbound         = db.query(Message).filter(
        Message.business_id == business_id,
        Message.direction == "inbound"
    ).count()
    new_leads       = db.query(Contact).filter(
        Contact.business_id == business_id,
        Contact.lead_status == "new"
    ).count()
    converted       = db.query(Contact).filter(
        Contact.business_id == business_id,
        Contact.lead_status == "converted"
    ).count()

    bot_rate = round((ai_messages / total_messages * 100), 1) if total_messages > 0 else 0

    return {
        "total_contacts":       total_contacts,
        "total_messages":       total_messages,
        "inbound_messages":     inbound,
        "ai_handled":           ai_messages,
        "bot_response_rate":    f"{bot_rate}%",
        "new_leads":            new_leads,
        "converted_leads":      converted,
        "human_hours_saved":    round(ai_messages * 0.02, 1)  # ~1.2 mins per msg saved
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AI HELPER APIS (Claude-powered features for the dashboard)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/ai/generate-faqs")
def generate_faqs(payload: dict, db: Session = Depends(get_db)):
    """
    Auto-generate FAQs for a business during onboarding.
    Business owner just types their description — Claude does the rest.
    """
    faqs = generate_faqs_from_description(
        business_description=payload["description"],
        business_type=payload.get("business_type", "business")
    )
    return {"faqs": faqs}


@app.post("/api/ai/draft-broadcast")
def draft_broadcast(payload: dict, db: Session = Depends(get_db)):
    """
    Claude drafts a WhatsApp broadcast message from a simple goal.
    e.g. "announce 20% off on floor tiles this weekend"
    """
    business = db.query(Business).filter(Business.id == payload["business_id"]).first()
    if not business:
        return {"error": "Business not found"}

    draft = draft_broadcast_message(
        business={"name": business.name},
        campaign_goal=payload["goal"],
        tone=payload.get("tone", "friendly")
    )
    return {"draft": draft}