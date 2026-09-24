from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import UserSettings
from pydantic import BaseModel
import datetime

router = APIRouter(prefix="/settings", tags=["Settings"])

DEFAULT_SETTINGS = {
    "ai_model": "gemma3:4b",
    "temperature": 0.2,
    "context_size": 4096,
    "response_detail": "balanced",
    "default_chat_mode": "auto",
    "citation_visibility": True,
    "max_retrieved_documents": 5,
    "web_research_enabled": True,
    "automatic_news_retrieval": True,
    "automatic_technical_analysis": True,
    "automatic_fundamental_analysis": True,
    "default_market_exchange": "US",
    "default_chart_period": "1mo",
    "default_chart_interval": "1d",
    "theme": "dark",
    "ui_density": "comfortable",
    "show_advanced_metrics": False,
    "show_data_sources": True,
    "cache_ttl": 300,
    "request_timeout": 30
}

@router.get("")
def get_settings(db: Session = Depends(get_db)):
    settings_record = db.query(UserSettings).first()
    if not settings_record:
        # Create default
        settings_record = UserSettings(settings=DEFAULT_SETTINGS)
        db.add(settings_record)
        db.commit()
        db.refresh(settings_record)
    
    return {**DEFAULT_SETTINGS, **(settings_record.settings or {})}

@router.put("")
def update_settings(new_settings: dict, db: Session = Depends(get_db)):
    unknown = set(new_settings) - set(DEFAULT_SETTINGS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown setting(s): {', '.join(sorted(unknown))}")
    numeric_ranges = {"temperature": (0, 2), "context_size": (256, 131072), "max_retrieved_documents": (1, 20), "cache_ttl": (0, 86400), "request_timeout": (1, 180)}
    for key, (minimum, maximum) in numeric_ranges.items():
        if key in new_settings:
            value = new_settings[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
                raise HTTPException(status_code=422, detail=f"{key} must be between {minimum} and {maximum}")
    for key in ("web_research_enabled", "automatic_news_retrieval", "automatic_technical_analysis", "automatic_fundamental_analysis", "citation_visibility", "show_advanced_metrics", "show_data_sources"):
        if key in new_settings and not isinstance(new_settings[key], bool):
            raise HTTPException(status_code=422, detail=f"{key} must be a boolean")
    allowed_values = {
        "theme": {"light", "dark"}, "ui_density": {"comfortable", "compact"},
        "response_detail": {"concise", "balanced", "detailed"}, "default_chat_mode": {"auto", "market", "documents", "general"},
        "default_market_exchange": {"US", "IN", "UK", "CA", "AU"},
        "default_chart_period": {"1mo", "3mo", "6mo", "1y", "2y", "5y"},
        "default_chart_interval": {"1d", "1wk", "1mo"},
    }
    for key, values in allowed_values.items():
        if key in new_settings and new_settings[key] not in values:
            raise HTTPException(status_code=422, detail=f"Invalid value for {key}")
    if "ai_model" in new_settings and (not isinstance(new_settings["ai_model"], str) or not new_settings["ai_model"].strip() or len(new_settings["ai_model"]) > 120):
        raise HTTPException(status_code=422, detail="ai_model must be a non-empty model name up to 120 characters")
    settings_record = db.query(UserSettings).first()
    if not settings_record:
        settings_record = UserSettings(settings=DEFAULT_SETTINGS)
        db.add(settings_record)
    
    # Merge updates
    current = {**DEFAULT_SETTINGS, **(settings_record.settings or {})}
    current.update(new_settings)
    settings_record.settings = current
    settings_record.updated_at = datetime.datetime.utcnow()
    
    db.commit()
    return current
