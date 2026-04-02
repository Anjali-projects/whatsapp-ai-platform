"""
webhook.py — Receives all incoming WhatsApp messages from Twilio.

Flow:
  Customer sends WhatsApp msg
    → Twilio hits this webhook
      → We identify the business
        → Load conversation history
          → Ask Claude for a reply
            → Save everything to DB
              → Send reply back via Twilio
"""

import uuid
from datetime import datetime
from fastapi import APIRouter, Form, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from twilio.rest import Client as TwilioClient
from twilio.request_validator import RequestValidator
import os

from database import get_db, Business, Contact, Message, BotSession
from claude_handler import get_ai_response

router = APIRouter()

twilio_client = TwilioClient(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")


# ─── Main Webhook Endpoint ────────────────────────────────────────────────────

@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    background_tasks: BackgroundTasks,
    From: str = Form(...),       # Customer's WhatsApp number e.g. "whatsapp:+919876543210"
    To: str = Form(...),         # Your business WhatsApp number
    Body: str = Form(...),       # The actual message text
    db: Session = Depends(get_db)
):
    """
    Twilio calls this endpoint every time a customer sends a WhatsApp message.
    We process it in the background so Twilio gets a fast 200 OK response.
    """
    background_tasks.add_task(
        process_incoming_message,
        from_number=From,
        to_number=To,
        message_body=Body.strip(),
        db=db
    )
    # Twilio needs a fast response — processing happens in background
    return {"status": "received"}


# ─── Core Message Processing Logic ────────────────────────────────────────────

def process_incoming_message(
    from_number: str,
    to_number: str,
    message_body: str,
    db: Session
):
    """
    The full pipeline for handling one incoming WhatsApp message.
    """
    # Clean phone numbers (remove "whatsapp:" prefix from Twilio format)
    customer_phone  = from_number.replace("whatsapp:", "")
    business_phone  = to_number.replace("whatsapp:", "")

    print(f"\n📩 New message from {customer_phone} → {business_phone}")
    print(f"   Message: {message_body[:80]}...")

    # ── Step 1: Find the business this number belongs to ─────────────────────
    business = db.query(Business).filter(
        Business.whatsapp_number == business_phone,
        Business.is_active == True
    ).first()

    if not business:
        print(f"⚠️  No active business found for number {business_phone}")
        return  # Silently ignore — number not registered on platform

    # ── Step 2: Find or create the contact ───────────────────────────────────
    contact = db.query(Contact).filter(
        Contact.business_id == business.id,
        Contact.phone == customer_phone
    ).first()

    if not contact:
        contact = Contact(
            id=str(uuid.uuid4()),
            business_id=business.id,
            phone=customer_phone,
            lead_status="new",
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            total_messages=1
        )
        db.add(contact)
        print(f"   ✨ New contact created: {customer_phone}")
    else:
        contact.last_seen = datetime.utcnow()
        contact.total_messages += 1

    # ── Step 3: Save the incoming message to DB ───────────────────────────────
    inbound_msg = Message(
        id=str(uuid.uuid4()),
        business_id=business.id,
        contact_id=contact.id,
        direction="inbound",
        content=message_body,
        sender=customer_phone,
        was_ai=False,
        timestamp=datetime.utcnow()
    )
    db.add(inbound_msg)
    db.commit()

    # ── Step 4: Check if human mode is ON (bot paused for this contact) ──────
    session = db.query(BotSession).filter(
        BotSession.business_id == business.id,
        BotSession.contact_phone == customer_phone
    ).first()

    if not session:
        session = BotSession(
            id=str(uuid.uuid4()),
            business_id=business.id,
            contact_phone=customer_phone,
            history=[],
            is_human_mode=False,
            last_activity=datetime.utcnow()
        )
        db.add(session)
        db.commit()

    if session.is_human_mode:
        print(f"   👤 Human mode ON for {customer_phone} — bot skipping reply")
        return  # Human is handling this — bot stays silent

    # ── Step 5: Get Claude's AI response ─────────────────────────────────────
    ai_result = get_ai_response(
        business={
            "id": business.id,
            "name": business.name,
            "business_type": business.business_type
        },
        config=business.bot_config or {},
        conversation_history=session.history,
        incoming_message=message_body
    )

    reply_text = ai_result["reply"]
    should_escalate = ai_result["escalate"]

    print(f"   🤖 Claude reply: {reply_text[:80]}...")

    # ── Step 6: Handle escalation (human handoff) ─────────────────────────────
    if should_escalate:
        session.is_human_mode = True
        print(f"   🚨 ESCALATION triggered for {customer_phone}")
        # Alert the business owner
        alert_business_owner(business, customer_phone, message_body)

    # ── Step 7: Update conversation history for Claude's memory ───────────────
    updated_history = session.history + [
        {"role": "user",        "content": message_body},
        {"role": "assistant",   "content": reply_text}
    ]
    # Keep only last 10 exchanges (20 messages) to manage token costs
    session.history = updated_history[-20:]
    session.last_activity = datetime.utcnow()

    # ── Step 8: Save the outbound reply to DB ─────────────────────────────────
    outbound_msg = Message(
        id=str(uuid.uuid4()),
        business_id=business.id,
        contact_id=contact.id,
        direction="outbound",
        content=reply_text,
        sender="bot",
        was_ai=True,
        timestamp=datetime.utcnow()
    )
    db.add(outbound_msg)
    db.commit()

    # ── Step 9: Send the reply via Twilio WhatsApp ────────────────────────────
    send_whatsapp_reply(
        to=from_number,         # Send back to the customer
        body=reply_text
    )

    print(f"   ✅ Reply sent to {customer_phone}")


# ─── Twilio Message Sender ────────────────────────────────────────────────────

def send_whatsapp_reply(to: str, body: str):
    """
    Sends a WhatsApp message via Twilio.
    'to' should be in format "whatsapp:+919876543210"
    """
    try:
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"

        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to,
            body=body
        )
        print(f"   📤 Twilio sent: {message.sid}")
    except Exception as e:
        print(f"   ❌ Twilio send error: {e}")


# ─── Business Owner Alert ─────────────────────────────────────────────────────

def alert_business_owner(business, customer_phone: str, last_message: str):
    """
    When escalation is triggered, notify the business owner via WhatsApp.
    """
    if not business.owner_phone:
        return

    alert_message = (
        f"🚨 *Action needed — {business.name}*\n\n"
        f"Customer {customer_phone} needs human support.\n"
        f"Their last message: \"{last_message[:100]}\"\n\n"
        f"The bot has paused for this contact.\n"
        f"Reply to them directly on WhatsApp."
    )

    send_whatsapp_reply(
        to=f"whatsapp:{business.owner_phone}",
        body=alert_message
    )
    print(f"   🔔 Owner alerted: {business.owner_phone}")


# ─── Resume Bot Endpoint (owner can turn bot back on) ────────────────────────

@router.post("/webhook/resume-bot/{business_id}/{contact_phone}")
def resume_bot(business_id: str, contact_phone: str, db: Session = Depends(get_db)):
    """
    Business owner can call this to resume the bot after handling a conversation.
    Will be connected to a button in the dashboard UI.
    """
    session = db.query(BotSession).filter(
        BotSession.business_id == business_id,
        BotSession.contact_phone == contact_phone
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_human_mode = False
    db.commit()

    return {"status": "bot_resumed", "contact": contact_phone}