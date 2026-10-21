"""Persistent user memory service for preferences, constraints, and long-term context."""
from __future__ import annotations

import re
import logging
from typing import Any
from sqlalchemy.orm import Session
from app.db.models import UserMemory

logger = logging.getLogger("stockrag.memory")


class MemoryService:
    def __init__(self, db: Session):
        self.db = db

    def list_memories(self, user_id: str = "default_user", category: str | None = None) -> list[dict[str, Any]]:
        query = self.db.query(UserMemory).filter(UserMemory.user_id == user_id)
        if category:
            query = query.filter(UserMemory.category == category)
        records = query.order_by(UserMemory.updated_at.desc(), UserMemory.id.desc()).all()
        return [
            {
                "id": record.id,
                "user_id": record.user_id,
                "key": record.key,
                "value": record.value,
                "category": record.category,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                "metadata": record.metadata_json or {},
            }
            for record in records
        ]

    def set_memory(
        self,
        key: str,
        value: str,
        category: str = "preference",
        user_id: str = "default_user",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_key = " ".join(str(key).strip().split())[:100]
        clean_val = str(value).strip()[:2000]
        clean_cat = str(category).strip().lower()[:50] or "preference"

        if not clean_key or not clean_val:
            raise ValueError("Memory key and value cannot be empty.")

        existing = (
            self.db.query(UserMemory)
            .filter(UserMemory.user_id == user_id, UserMemory.key == clean_key)
            .first()
        )
        if existing:
            existing.value = clean_val
            existing.category = clean_cat
            existing.metadata_json = metadata or existing.metadata_json or {}
            self.db.commit()
            self.db.refresh(existing)
            record = existing
        else:
            record = UserMemory(
                user_id=user_id,
                key=clean_key,
                value=clean_val,
                category=clean_cat,
                metadata_json=metadata or {},
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)

        return {
            "id": record.id,
            "user_id": record.user_id,
            "key": record.key,
            "value": record.value,
            "category": record.category,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "metadata": record.metadata_json or {},
        }

    def delete_memory(self, memory_id: int, user_id: str = "default_user") -> bool:
        record = (
            self.db.query(UserMemory)
            .filter(UserMemory.id == memory_id, UserMemory.user_id == user_id)
            .first()
        )
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True

    def delete_memory_by_key(self, key: str, user_id: str = "default_user") -> bool:
        clean_key = " ".join(str(key).strip().split())
        record = (
            self.db.query(UserMemory)
            .filter(UserMemory.user_id == user_id, UserMemory.key.ilike(clean_key))
            .first()
        )
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True

    def get_relevant_memories(
        self,
        query: str,
        user_id: str = "default_user",
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        all_memories = self.list_memories(user_id=user_id)
        if not all_memories:
            return []

        q_terms = set(re.findall(r"\w+", query.casefold()))
        scored = []
        for mem in all_memories:
            score = 0.5  # Base score so general preferences always remain active
            m_terms = set(re.findall(r"\w+", f"{mem['key']} {mem['value']} {mem['category']}".casefold()))
            overlap = len(q_terms & m_terms)
            score += overlap * 1.5
            scored.append((score, mem))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [mem for _, mem in scored[:limit]]

    def get_memories(self, user_id: str = "default_user", category: str | None = None) -> list[dict[str, Any]]:
        return self.list_memories(user_id=user_id, category=category)

    def clear_memories(self, user_id: str = "default_user") -> int:
        count = self.db.query(UserMemory).filter(UserMemory.user_id == user_id).delete()
        self.db.commit()
        return count

    @staticmethod
    def extract_memory_directive(message: str) -> dict[str, str] | None:
        return extract_memory_directive(message)


def extract_memory_directive(message: str) -> dict[str, str] | None:
    """Parse explicit user commands like 'remember that I prefer Indian stocks' or 'forget my watchlist'."""
    text = message.strip()
    lowered = text.casefold()

    if any(p in lowered for p in ("what do you remember", "what do you know about me", "show all my saved memories", "show my memories", "show memories", "list memories")):
        return {"action": "list"}

    if any(p in lowered for p in ("forget everything", "clear memories", "delete all memories", "clear all memories", "forget all memories")):
        return {"action": "clear", "target": "all"}

    # Forget directive
    forget_match = re.match(
        r"^(?:forget|delete|remove)\s+(?:that\s+|my\s+|the\s+)?(.+)",
        text,
        re.IGNORECASE,
    )
    if forget_match and not any(k in lowered for k in ("what", "how", "why", "when")):
        target = forget_match.group(1).rstrip(".!?;")
        low_t = target.casefold()
        if "risk" in low_t:
            key = "risk_tolerance"
        elif "horizon" in low_t:
            key = "investment_horizon"
        else:
            key = "_".join(re.sub(r"[^\w]", "", w.lower()) for w in target.split()[:4] if w) or target
        return {"action": "delete", "target": target, "key": key}

    # Remember directive
    remember_match = re.match(
        r"^(?:please\s+)?(?:remember|save|note|keep in mind)\s+(?:that\s+|this:\s*)?(.+)",
        text,
        re.IGNORECASE,
    )
    if remember_match and not any(k in lowered for k in ("what do you remember", "can you remember", "do you remember")):
        content = remember_match.group(1).rstrip(".!?;")
        # Determine category and key
        cat = "preference"
        low_c = content.casefold()
        if any(w in low_c for w in ("risk", "conservative", "aggressive", "moderate")):
            key = "risk_tolerance"
            cat = "constraint"
        elif any(w in low_c for w in ("horizon", "short term", "long term", "years", "months")):
            key = "investment_horizon"
            cat = "constraint"
        elif any(w in low_c for w in ("watchlist", "stocks i like", "favorite")):
            key = "watchlist"
            cat = "watchlist"
        elif any(w in low_c for w in ("market", "exchange", "india", "nse", "bse", "us", "nyse", "nasdaq")):
            key = "preferred_market"
            cat = "preference"
        elif any(w in low_c for w in ("format", "bullet", "concise", "detail", "table")):
            key = "output_format"
            cat = "preference"
        else:
            # First 3-4 words as key
            words = content.split()[:4]
            key = "_".join(re.sub(r"[^\w]", "", w.lower()) for w in words if w) or "user_note"

        return {"action": "set", "key": key, "value": content, "category": cat}

    return None
