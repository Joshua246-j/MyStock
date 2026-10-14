from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import UserSettings
from datetime import datetime, timezone

router = APIRouter(prefix="/settings", tags=["Settings"])

DEFAULT_SETTINGS = {
    "ai_model": "qwen2.5:1.5b",
    "temperature": 0.2,
    "context_size": 4096,
    "max_output_tokens": 2048,
    "response_detail": "balanced",
    "default_chat_mode": "auto",
    "citation_visibility": True,
    "max_retrieved_documents": 5,
    "web_research_enabled": True,
    "automatic_news_retrieval": True,
    "automatic_technical_analysis": True,
    "automatic_fundamental_analysis": True,
    "default_market_exchange": "IN",
    "default_chart_period": "1mo",
    "default_chart_interval": "1d",
    "theme": "light",
    "ui_density": "comfortable",
    "show_advanced_metrics": True,
    "show_data_sources": True,
    "cache_ttl": 300,
    "request_timeout": 120,
    "top_p": 0.9,
    "top_k": 40,
    "repeat_penalty": 1.1,
    "seed": 0,
    "streaming": False
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
    numeric_ranges = {"temperature": (0, 2), "context_size": (256, 131072), "max_output_tokens": (64, 16384), "max_retrieved_documents": (1, 20), "cache_ttl": (0, 86400), "request_timeout": (1, 180), "top_p": (0.0, 1.0), "top_k": (0, 1000), "repeat_penalty": (0.0, 5.0), "seed": (0, 2147483647)}
    for key, (minimum, maximum) in numeric_ranges.items():
        if key in new_settings:
            value = new_settings[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
                raise HTTPException(status_code=422, detail=f"{key} must be between {minimum} and {maximum}")
    for key in ("web_research_enabled", "automatic_news_retrieval", "automatic_technical_analysis", "automatic_fundamental_analysis", "citation_visibility", "show_advanced_metrics", "show_data_sources", "streaming"):
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
    settings_record.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    return current

@router.delete("")
def reset_settings(db: Session = Depends(get_db)):
    """Reset all settings to their defaults."""
    settings_record = db.query(UserSettings).first()
    if settings_record:
        settings_record.settings = dict(DEFAULT_SETTINGS)
        settings_record.updated_at = datetime.now(timezone.utc)
        db.commit()
    return dict(DEFAULT_SETTINGS)

SETTINGS_SCHEMA = {
    "ai_model": {"type": "string", "label": "AI Model", "group": "basic", "description": "The Ollama model used for chat generation. Must be installed locally."},
    "temperature": {"type": "number", "min": 0, "max": 2, "step": 0.1, "label": "Temperature", "group": "basic", "description": "Controls randomness. Lower values give more focused answers; higher values increase creativity but may reduce accuracy. Does NOT guarantee factual correctness at any value."},
    "max_output_tokens": {"type": "integer", "min": 64, "max": 16384, "step": 64, "label": "Max Output Tokens", "group": "basic", "description": "Maximum number of tokens the model can generate per response. Higher values allow longer answers but increase latency."},
    "context_size": {"type": "integer", "min": 256, "max": 131072, "step": 256, "label": "Context Window", "group": "advanced", "description": "Number of tokens available for the entire conversation context (prompt + history + evidence + response). Larger values use more memory."},
    "top_p": {"type": "number", "min": 0.0, "max": 1.0, "step": 0.05, "label": "Top-P (Nucleus Sampling)", "group": "advanced", "description": "Limits token selection to the most probable tokens whose cumulative probability reaches this threshold. Lower values make output more deterministic."},
    "top_k": {"type": "integer", "min": 0, "max": 1000, "step": 1, "label": "Top-K", "group": "advanced", "description": "Limits token selection to the top K most probable tokens. 0 disables the limit. Lower values reduce variability."},
    "repeat_penalty": {"type": "number", "min": 0.0, "max": 5.0, "step": 0.1, "label": "Repeat Penalty", "group": "advanced", "description": "Penalizes repeated tokens. Values above 1.0 discourage repetition; 1.0 disables the penalty."},
    "seed": {"type": "integer", "min": 0, "max": 2147483647, "step": 1, "label": "Seed", "group": "advanced", "description": "Fixed seed for reproducible generation. 0 means random seed each time."},
    "response_detail": {"type": "select", "options": ["concise", "balanced", "detailed"], "label": "Response Detail", "group": "basic", "description": "Controls how verbose and structured the AI responses are."},
    "streaming": {"type": "boolean", "label": "Streaming", "group": "basic", "description": "When enabled, the UI receives tokens as they are generated instead of waiting for the full response."},
    "request_timeout": {"type": "integer", "min": 1, "max": 180, "step": 1, "label": "Request Timeout (seconds)", "group": "advanced", "description": "Maximum time in seconds to wait for model generation and data retrieval."},
    "default_chat_mode": {"type": "select", "options": ["auto", "market", "documents", "general"], "label": "Default Chat Mode", "group": "basic", "description": "Controls which data sources the AI consults. Auto detects intent; Market forces stock data; Documents forces RAG; General skips external retrieval."},
    "web_research_enabled": {"type": "boolean", "label": "Web Research", "group": "basic", "description": "Allow the AI to search financial news and crawl allowed publisher websites."},
    "automatic_news_retrieval": {"type": "boolean", "label": "Auto News Retrieval", "group": "basic", "description": "Automatically fetch recent news headlines when a stock-related question is detected."},
    "automatic_technical_analysis": {"type": "boolean", "label": "Auto Technical Analysis", "group": "basic", "description": "Automatically compute technical indicators when chart or trend questions are detected."},
    "automatic_fundamental_analysis": {"type": "boolean", "label": "Auto Fundamental Analysis", "group": "basic", "description": "Automatically retrieve financial metrics for fundamental analysis questions."},
    "max_retrieved_documents": {"type": "integer", "min": 1, "max": 20, "step": 1, "label": "Max Retrieved Passages", "group": "advanced", "description": "Maximum number of document passages to retrieve for RAG context."},
    "cache_ttl": {"type": "integer", "min": 0, "max": 86400, "step": 60, "label": "Cache TTL (seconds)", "group": "advanced", "description": "How long market data and other cached results remain valid. 0 disables caching."},
    "theme": {"type": "select", "options": ["light", "dark"], "label": "Theme", "group": "ui", "description": "Application color theme."},
    "ui_density": {"type": "select", "options": ["comfortable", "compact"], "label": "UI Density", "group": "ui", "description": "Controls spacing and sizing of interface elements."},
    "citation_visibility": {"type": "boolean", "label": "Show Citations", "group": "ui", "description": "Display source citations below AI responses."},
    "show_advanced_metrics": {"type": "boolean", "label": "Show Advanced Metrics", "group": "ui", "description": "Display detailed technical metrics and data provenance information."},
    "show_data_sources": {"type": "boolean", "label": "Show Data Sources", "group": "ui", "description": "Display which data providers were used for each response."},
    "default_market_exchange": {"type": "select", "options": ["US", "IN", "UK", "CA", "AU"], "label": "Default Exchange", "group": "basic", "description": "Default stock exchange for symbol resolution."},
    "default_chart_period": {"type": "select", "options": ["1mo", "3mo", "6mo", "1y", "2y", "5y"], "label": "Default Chart Period", "group": "ui", "description": "Default time range for market charts."},
    "default_chart_interval": {"type": "select", "options": ["1d", "1wk", "1mo"], "label": "Default Chart Interval", "group": "ui", "description": "Default bar interval for market charts."},
}

@router.get("/schema")
def get_settings_schema():
    """Return parameter metadata (types, ranges, descriptions) for UI rendering."""
    return {"defaults": DEFAULT_SETTINGS, "schema": SETTINGS_SCHEMA}
