"""
claude_handler.py — The AI brain of the platform (now using free Ollama/LLaMA 2).

Uses open-source LLaMA 2 model running locally or on a remote Ollama server.
Zero API costs, full control, locally hosted.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# Ollama server settings
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama2")  # Free open-source model

MAX_HISTORY = 10        # Messages to keep in memory per session
MAX_TOKENS  = 400       # Keep replies concise for WhatsApp


# ─── System Prompt Builder ────────────────────────────────────────────────────

def build_system_prompt(business: dict, config: dict) -> str:
    """
    Builds LLaMA 2's system prompt dynamically from the business's config.
    This is what makes each bot feel custom-built for that business.
    """

    faqs_text = ""
    if config.get("faqs"):
        faqs_text = "\n\nFrequently Asked Questions:\n"
        for faq in config["faqs"]:
            faqs_text += f"Q: {faq['q']}\nA: {faq['a']}\n\n"

    services_text = ""
    if config.get("services"):
        services_text = f"\nServices/Products offered: {', '.join(config['services'])}"

    prompt = f"""You are a helpful WhatsApp assistant for {business['name']}, a {business.get('business_type', 'business')} based in Hyderabad, India.

ABOUT THIS BUSINESS:
{config.get('business_description', f"We are {business['name']}.")}
{services_text}

IMPORTANT DETAILS TO SHARE WHEN ASKED:
- Price range: {config.get('price_range', 'Please contact us for pricing')}
- Working hours: {config.get('working_hours', 'Please contact us for timings')}
- Location: {config.get('location', 'Hyderabad, India')}
- Delivery/Service area: {config.get('delivery', 'Please contact us for details')}
{faqs_text}

YOUR BEHAVIOUR RULES:
1. Be friendly, warm, and helpful — like a knowledgeable staff member
2. Keep replies SHORT and conversational — this is WhatsApp, not an email
3. NEVER make up information. If you don't know something, say "Let me check with our team and get back to you!"
4. Detect the language the customer is using (Telugu, Hindi, or English) and reply in the SAME language
5. If the customer seems ready to buy or place an order, ask for their requirements and note them
6. If you detect frustration, complaint, or requests to speak to a human — respond with: "ESCALATE_TO_HUMAN"
7. Do not discuss competitors or make negative comparisons
8. Sign off occasionally with "{business['name']}" to reinforce the brand

ESCALATION TRIGGERS (reply with ESCALATE_TO_HUMAN if customer says any of these):
{', '.join(config.get('escalation_keywords', ['complaint', 'refund', 'speak to owner', 'manager', 'problem', 'issue']))}

Remember: You represent {business['name']}. Every reply builds or breaks their reputation."""

    return prompt


# ─── Main AI Response Function ────────────────────────────────────────────────

def get_ai_response(
    business: dict,
    config: dict,
    conversation_history: list,
    incoming_message: str
) -> dict:
    """
    Takes the business context + full conversation history + new message.
    Calls Ollama (LLaMA 2) for a response.
    
    Returns:
        {
            "reply": str,           # The message to send back
            "escalate": bool,       # True = pause bot, alert human
            "detected_language": str
        }
    """

    system_prompt = build_system_prompt(business, config)

    # Build message history for Ollama (keep last MAX_HISTORY messages)
    messages = conversation_history[-MAX_HISTORY:] if len(conversation_history) > MAX_HISTORY else conversation_history

    # Format conversation for Ollama (simple text format)
    context = system_prompt + "\n\n"
    for msg in messages:
        role = msg["role"].upper()
        context += f"{role}: {msg['content']}\n"
    
    context += f"ASSISTANT: "

    try:
        # Call Ollama API
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": context,
                "stream": False,
                "temperature": 0.7
            },
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ Ollama API error: {response.status_code}")
            return {
                "reply": f"Sorry, we're experiencing a brief issue. Please try again in a moment or call us directly! — {business['name']}",
                "escalate": False,
                "detected_language": "english"
            }
        
        reply_text = response.json()["response"].strip()

        # Check if LLaMA decided to escalate
        if "ESCALATE_TO_HUMAN" in reply_text:
            return {
                "reply": f"Let me connect you with our team right away! Someone from {business['name']} will get back to you shortly. 🙏",
                "escalate": True,
                "detected_language": detect_language(incoming_message)
            }

        return {
            "reply": reply_text,
            "escalate": False,
            "detected_language": detect_language(incoming_message)
        }

    except requests.exceptions.Timeout:
        print("❌ Ollama API timeout - server may be slow")
        return {
            "reply": f"Sorry, we're a bit slow right now. Please try again! — {business['name']}",
            "escalate": False,
            "detected_language": "english"
        }
    except Exception as e:
        print(f"❌ Ollama error: {e}")
        return {
            "reply": f"Sorry, we're experiencing a brief issue. Please try again in a moment or call us directly! — {business['name']}",
            "escalate": False,
            "detected_language": "english"
        }


# ─── Language Detection ───────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """
    Simple heuristic language detection.
    Claude handles the actual multilingual replies — this is just for logging.
    """
    telugu_chars = set("అఆఇఈఉఊఋఌఎఏఐఒఓఔకఖగఘఙచఛజఝఞటఠడఢణతథదధనపఫబభమయరలవశషసహళక్షజ్ఞ")
    hindi_chars  = set("अआइईउऊएऐओऔकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह")

    for char in text:
        if char in telugu_chars:
            return "telugu"
        if char in hindi_chars:
            return "hindi"

    return "english"


# ─── Broadcast Message Drafting ───────────────────────────────────────────────

def draft_broadcast_message(business: dict, campaign_goal: str, tone: str = "friendly") -> str:
    """
    Uses Claude to draft a WhatsApp broadcast message for the business.
    Business owner just types the goal — Claude writes the message.

    e.g. campaign_goal = "Announce 20% off on all floor tiles this weekend"
    """
    prompt = f"""Write a WhatsApp broadcast message for {business['name']}.

Goal: {campaign_goal}
Tone: {tone}

Requirements:
- Max 3–4 lines (WhatsApp readers scan, not read)
- Include a clear call to action at the end
- Feel personal and warm, not like a generic ad
- End with the business name
- Use relevant emoji sparingly (1–2 max)
- Write in English unless specified otherwise

Return ONLY the message text. No explanation."""

    try:
        # Using Ollama instead of Claude
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json()["response"].strip()
        return ""
    except Exception as e:
        print(f"❌ Broadcast draft error: {e}")
        return ""


# ─── FAQ Auto-Generator ───────────────────────────────────────────────────────

def generate_faqs_from_description(business_description: str, business_type: str) -> list:
    """
    Given a business description, Claude generates likely FAQs automatically.
    Used during business onboarding to help owners set up their bot faster.
    """
    prompt = f"""A {business_type} business has this description:
"{business_description}"

Generate 8 realistic FAQs that customers commonly ask this type of business on WhatsApp.
Return as a JSON array only, no explanation:
[
  {{"q": "question here", "a": "answer here"}},
  ...
]"""

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=30
        )
        if response.status_code == 200:
            text = response.json()["response"].strip()
            # Strip markdown fences if present
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        return []
    except Exception as e:
        print(f"❌ FAQ generation error: {e}")
        return []
