import hashlib
import os
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import Session
from app.database import get_db, Base

router = APIRouter(prefix="/api/translate", tags=["translate"])

ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://modelservice.jdcloud.com/anthropic")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_TRANSLATE_MODEL", "claude-sonnet-5-hq")


class TranslationCache(Base):
    __tablename__ = "translation_cache"
    id = Column(Integer, primary_key=True, index=True)
    text_hash = Column(String(64), unique=True, nullable=False, index=True)
    original = Column(Text, nullable=False)
    translated = Column(Text, nullable=False)


SYSTEM_PROMPT = """你是一个视频生成prompt的翻译助手。用户会给你一段视频生成指令（可能是英文、中文、或中英混合），请按以下规则处理：

1. 英文描述性内容 → 翻译为中文
2. 中文内容 → 保持原样
3. 刻意的英文台词、歌词、对白（通常在引号内或明确标注为dialogue/speech/subtitle） → 保留英文原文，用「」括起来
4. 专有名词、人名、品牌名 → 保留原文
5. 技术参数（分辨率、帧率、镜头术语等） → 保留原文

输出只包含翻译结果，不要解释、不要前缀。保持原文的段落结构。"""


@router.post("/")
async def translate_prompt(data: dict, db: Session = Depends(get_db)):
    text = data.get("text", "").strip()
    if not text:
        return {"translated": "", "cached": False}

    text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]

    cached = db.query(TranslationCache).filter(TranslationCache.text_hash == text_hash).first()
    if cached:
        return {"translated": cached.translated, "cached": True}

    if not ANTHROPIC_AUTH_TOKEN:
        return {"translated": "[翻译服务未配置API Key]", "cached": False}

    try:
        translated = await _call_claude(text)
    except Exception as e:
        return {"translated": f"[翻译失败: {str(e)[:100]}]", "cached": False}

    entry = TranslationCache(text_hash=text_hash, original=text, translated=translated)
    db.add(entry)
    db.commit()

    return {"translated": translated, "cached": False}


async def _call_claude(text: str) -> str:
    url = f"{ANTHROPIC_BASE_URL}/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_AUTH_TOKEN,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": text}],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        return result["content"][0]["text"]
