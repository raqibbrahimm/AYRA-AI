from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import os
import re
import asyncio
import httpx

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.5-flash-lite"

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)

app = FastAPI(title="AYRA AI")


@app.on_event("startup")
async def startup_http_client():
    app.state.http_client = httpx.AsyncClient(timeout=20)


@app.on_event("shutdown")
async def shutdown_http_client():
    await app.state.http_client.aclose()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)
    user_name: str = ""


def normalize(text):
    text = text.lower().strip()
    text = re.sub(r"[?!.,]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def simple_response(message):
    msg = normalize(message)

    current_time_patterns = [
        r"\b(abhi|filhal|is waqt)\b.*\b(time|tym|waqt)\b",
        r"\b(time|tym|waqt)\b.*\b(kya|kitna|kitne baje)\b",
        r"\b(what time is it|current time|tell me the time)\b",
        r"\b(kitne baje hain|abhi kitna baja hai)\b",
        r"\b(time|tym|waqt)\b",
    ]

    past_future_words = [
        "kal", "yesterday", "tomorrow",
        "parso", "last week", "next week"
    ]

    if (
        any(re.search(p, msg) for p in current_time_patterns)
        and not any(word in msg for word in past_future_words)
    ):
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        return "Abhi " + now.strftime("%I:%M %p") + " ho rahe hain."

    if any(x in msg for x in [
        "tumhara naam kya", "aapka naam kya",
        "what is your name", "your name"
    ]):
        return "Mera naam AYRA hai. Main tumhari AI assistant hoon."

    greetings = {
        "hi": "Hii! Aap kaise hain?",
        "hii": "Hii! Aap kaise hain?",
        "hello": "Hello! Bataiye, kya help chahiye?",
        "hey": "Hey! Main sun rahi hoon.",
        "hlw": "Hello! Main yahin hoon.",
        "good morning": "Good morning! Aapka din achha rahe.",
        "good evening": "Good evening! Kaise hain aap?",
        "good night": "Good night! Aaram se soyiye.",
    }

    if msg in greetings:
        return greetings[msg]

    if msg in ["tum kaise hoo", "tum kaisi ho", "aap kaise hain",
               "how are you", "how are you ayra"]:
        return "Mai achii huu, aap batayeyai?"

    if msg in ["thank you", "thanks", "shukriya", "sukriya", "thx"]:
        return "Aapka welcome! Aur kuch help chahiye?"

    if msg in ["bye", "goodbye", "allah hafiz", "khuda hafiz"]:
        return "Allah hafiz! Phir baat hogi."

    if msg in ["ok", "okay", "theek hai", "thik hai"]:
        return "Theek hai!"

    return None
SYSTEM_PROMPT = """
You are AYRA, a friendly female AI assistant.

PERSONALITY:
- Friendly, intelligent, cheerful and respectful.
- Speak naturally, like a helpful conversational assistant.
- Your name is always AYRA.
- Never pretend to be human.

LANGUAGE AND SCRIPT — VERY IMPORTANT:
- Understand Hindi, Urdu, English, Hinglish and Roman Urdu.
- Understand informal typing and short forms:
  tym, kr, rha, rhy, nhi, mtlb, kyu, btao, hoo.
- Reply in the same language AND writing script as the user's latest message.
- If the user writes Hindi or Urdu using English letters,
  reply in natural Roman Hindi/Urdu using English letters.
- Never switch Roman Hindi into Devanagari.
- Do not explain or translate the language.
- If the user writes English, reply in English.

STYLE:
- Example:
  User: Tum kaise hoo?
  AYRA: Mai achii huu, aap batayeyai?
- Keep casual replies short and natural.
- Give proper explanations when asked.
- Answer the actual question.
- Avoid repetitive replies and unnecessary introductions.
- Use emojis naturally, not excessively.
"""


@app.get("/")
def home():
    return {"status": "AYRA Gemini AI online"}


@app.post("/chat")
async def chat(data: ChatRequest):
    message = data.message.strip()

    if not message:
        return {"reply": "Kuch bolo, main sun rahi hoon."}

    if data.user_name and re.search(
        r"\\b(what is my name|mera naam kya hai|mera naam batao|do you remember my name)\\b",
        normalize(message)
    ):
        return {"reply": "Aapka naam " + data.user_name + " hai."}

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key missing. Check your .env file."
        )

    quick_reply = simple_response(message)
    if quick_reply:
        return {"reply": quick_reply}

    contents = []

    for item in data.history[-8:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content", "")

        if role not in ["user", "assistant"] or not isinstance(content, str):
            continue

        content = content.strip()
        if not content:
            continue

        gemini_role = "user" if role == "user" else "model"

        contents.append({
            "role": gemini_role,
            "parts": [{"text": content[:1200]}]
        })

    contents.append({
        "role": "user",
        "parts": [{"text": message[:2000]}]
    })

    payload = {
        "system_instruction": {
            "parts": [{
                "text": SYSTEM_PROMPT + (
                    "\\nThe user's saved name is " + data.user_name +
                    ". Address the user by this name naturally when appropriate."
                    if data.user_name else ""
                )
            }]
        },
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 160
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    try:
        response = None

        for attempt in range(3):
            try:
                response = await app.state.http_client.post(
                    GEMINI_URL,
                    headers=headers,
                    json=payload
                )

                if response.status_code in (502, 503, 504) and attempt < 2:
                    print(
                        f"AYRA GEMINI RETRY: HTTP {response.status_code}, "
                        f"attempt {attempt + 2}/3",
                        flush=True
                    )
                    await asyncio.sleep(attempt + 1)
                    continue

                response.raise_for_status()
                break

            except httpx.RequestError as retry_error:
                if attempt >= 2:
                    raise

                print(
                    f"AYRA GEMINI RETRY: "
                    f"{type(retry_error).__name__}, "
                    f"attempt {attempt + 2}/3",
                    flush=True
                )
                await asyncio.sleep(attempt + 1)
        result = response.json()

        candidates = result.get("candidates", [])
        if not candidates:
            raise HTTPException(
                status_code=502,
                detail="Gemini returned no response."
            )

        parts = candidates[0].get("content", {}).get("parts", [])
        answer = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict)
        ).strip()

        if not answer:
            answer = "Ek baar phir bataiye, main samajhne ki koshish karti hoon."

        return {"reply": answer}

    except httpx.HTTPStatusError as error:
        status = error.response.status_code

        if status == 429:
            detail = "Gemini free usage limit reached. Please try later."
        elif status in (401, 403):
            detail = "Gemini API key or access problem. Check API settings."
        else:
            detail = "Gemini API error: " + error.response.text[:400]

        raise HTTPException(status_code=status, detail=detail)

    except httpx.RequestError as error:
        print(
            "AYRA GEMINI CONNECTION ERROR:",
            type(error).__name__,
            str(error),
            flush=True
        )
        raise HTTPException(
            status_code=503,
            detail="Gemini se connection nahi ho raha. Internet check karo."
        )
