"""
database.py — PostgreSQL connection + all table models
"""

from sqlalchemy import (
    create_engine, Column, String, Text, Integer,
    Boolean, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")  # SQLite fallback for dev

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─── Dependency for FastAPI routes ───────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Models ──────────────────────────────────────────────────────────────────

class Business(Base):
    """
    One row per client business using your platform.
    e.g. "Ravi Tiles Hyderabad", "Sri Sai Coaching Center"
    """
    __tablename__ = "businesses"

    id              = Column(String, primary_key=True)          # UUID
    name            = Column(String, nullable=False)            # "Ravi Tiles"
    whatsapp_number = Column(String, unique=True, nullable=False)  # "+919876543210"
    business_type   = Column(String)                            # "tiles", "coaching", "clinic"
    owner_name      = Column(String)
    owner_phone     = Column(String)                            # For human handoff alerts
    is_active       = Column(Boolean, default=True)
    plan            = Column(String, default="starter")         # starter / growth / pro
    created_at      = Column(DateTime, default=func.now())

    # Bot configuration — this becomes Claude's system prompt context
    bot_config      = Column(JSON, default={})
    """
    bot_config shape:
    {
      "business_description": "We sell floor, wall, and bathroom tiles...",
      "services": ["Floor tiles", "Wall tiles", "Bathroom fittings"],
      "price_range": "₹28–₹150 per sq ft depending on type",
      "working_hours": "Mon–Sat, 9am–7pm",
      "location": "Kukatpally, Hyderabad",
      "delivery": "We deliver across Hyderabad within 3–5 days",
      "faqs": [
        {"q": "Do you give samples?", "a": "Yes, free samples for orders above 100 sqft"},
      ],
      "escalation_keywords": ["complaint", "refund", "speak to owner", "manager"],
      "language_preference": "auto"   # auto / english / telugu / hindi
    }
    """

    contacts    = relationship("Contact", back_populates="business")
    messages    = relationship("Message", back_populates="business")


class Contact(Base):
    """
    Every unique person who has WhatsApp messaged any business on your platform.
    """
    __tablename__ = "contacts"

    id              = Column(String, primary_key=True)          # UUID
    business_id     = Column(String, ForeignKey("businesses.id"), nullable=False)
    phone           = Column(String, nullable=False)            # "+919876543210"
    name            = Column(String)                            # Filled if they introduce themselves
    tags            = Column(JSON, default=[])                  # ["lead", "customer", "vip"]
    lead_status     = Column(String, default="new")             # new / warm / converted / lost
    first_seen      = Column(DateTime, default=func.now())
    last_seen       = Column(DateTime, default=func.now())
    total_messages  = Column(Integer, default=0)
    notes           = Column(Text)                              # Business owner's manual notes

    business    = relationship("Business", back_populates="contacts")
    messages    = relationship("Message", back_populates="contact")


class Message(Base):
    """
    Every single WhatsApp message — incoming from customer or outgoing from bot/human.
    """
    __tablename__ = "messages"

    id              = Column(String, primary_key=True)          # UUID
    business_id     = Column(String, ForeignKey("businesses.id"), nullable=False)
    contact_id      = Column(String, ForeignKey("contacts.id"), nullable=False)
    direction       = Column(String, nullable=False)            # "inbound" / "outbound"
    content         = Column(Text, nullable=False)
    sender          = Column(String)                            # "bot" / "human" / customer phone
    was_ai          = Column(Boolean, default=False)            # True if Claude generated it
    timestamp       = Column(DateTime, default=func.now())
    read            = Column(Boolean, default=False)

    business    = relationship("Business", back_populates="messages")
    contact     = relationship("Contact", back_populates="messages")


class BotSession(Base):
    """
    Tracks active conversation context per contact.
    Stores last N messages for Claude's memory window.
    """
    __tablename__ = "bot_sessions"

    id              = Column(String, primary_key=True)          # UUID
    business_id     = Column(String, ForeignKey("businesses.id"), nullable=False)
    contact_phone   = Column(String, nullable=False)
    history         = Column(JSON, default=[])                  # Last 10 messages for Claude
    is_human_mode   = Column(Boolean, default=False)            # True = bot paused, human took over
    last_activity   = Column(DateTime, default=func.now())


def create_tables():
    Base.metadata.create_all(bind=engine)
    print("✅ All database tables created.")