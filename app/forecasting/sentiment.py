"""Point-in-time financial sentiment analysis using a lightweight financial lexicon.

Designed for CPU-only execution with zero multi-gigabyte neural weight downloads,
low memory (<5 MB), and deterministic, leak-free timestamp alignment.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

# Curated financial domain keywords based on Loughran-McDonald & corporate news patterns
POSITIVE_FINANCIAL_WORDS = {
    "surge", "surges", "surged", "surging", "soar", "soars", "soared", "soaring",
    "rally", "rallies", "rallied", "rallying", "gain", "gains", "gained", "gaining",
    "jump", "jumps", "jumped", "jumping", "rise", "rises", "rose", "rising",
    "beat", "beats", "beating", "outperform", "outperforms", "outperformed",
    "profit", "profits", "profitable", "profitability", "growth", "grow", "grows", "grew",
    "dividend", "dividends", "buyback", "buybacks", "upgrade", "upgrades", "upgraded",
    "bullish", "expansion", "expands", "expanded", "record", "peak", "milestone",
    "order", "orders", "contract", "contracts", "acquisition", "deal", "breakthrough",
    "ebitda", "margin", "margins", "pat", "turnaround", "uptrend", "resilient", "recovery"
}

NEGATIVE_FINANCIAL_WORDS = {
    "plunge", "plunges", "plunged", "plunging", "slump", "slumps", "slumped", "slumping",
    "drop", "drops", "dropped", "dropping", "fall", "falls", "fell", "falling",
    "decline", "declines", "declined", "declining", "crash", "crashes", "crashed",
    "tumble", "tumbles", "tumbled", "tumbling", "miss", "misses", "missed", "missing",
    "underperform", "loss", "losses", "deficit", "debt", "debts", "downgrade", "downgrades",
    "downgraded", "bearish", "recession", "inflation", "cut", "cuts", "cutting",
    "layoff", "layoffs", "investigation", "probe", "fraud", "penalty", "fine", "sanction",
    "default", "bankruptcy", "insolvent", "lawsuit", "dispute", "npa", "warning", "caution",
    "headwind", "headwinds", "selloff", "sell-off", "volatility", "turmoil", "stumble"
}

UNCERTAINTY_WORDS = {
    "may", "might", "could", "perhaps", "uncertain", "uncertainty", "speculate",
    "speculation", "volatile", "risk", "risks", "pending", "unclear", "contingent",
    "possibility", "unconfirmed", "rumor", "rumors"
}


def analyze_text_sentiment(text: str) -> dict[str, Any]:
    """Calculate polarity, subjectivity, and tone counts for financial text."""
    if not text or not text.strip():
        return {
            "score": 0.0,
            "uncertainty": 0.0,
            "positive_count": 0,
            "negative_count": 0,
            "total_words": 0,
            "label": "neutral",
        }

    tokens = re.findall(r"[a-z]+", text.casefold())
    total_words = len(tokens)
    if total_words == 0:
        return {
            "score": 0.0,
            "uncertainty": 0.0,
            "positive_count": 0,
            "negative_count": 0,
            "total_words": 0,
            "label": "neutral",
        }

    pos_count = sum(1 for w in tokens if w in POSITIVE_FINANCIAL_WORDS)
    neg_count = sum(1 for w in tokens if w in NEGATIVE_FINANCIAL_WORDS)
    unc_count = sum(1 for w in tokens if w in UNCERTAINTY_WORDS)

    # Bounded polarity between -1.0 and +1.0
    denom = max(1, pos_count + neg_count)
    score = (pos_count - neg_count) / denom

    uncertainty = unc_count / max(1, total_words)

    if score > 0.15:
        label = "positive"
    elif score < -0.15:
        label = "negative"
    else:
        label = "neutral"

    return {
        "score": round(float(score), 4),
        "uncertainty": round(float(uncertainty), 4),
        "positive_count": pos_count,
        "negative_count": neg_count,
        "total_words": total_words,
        "label": label,
    }


def aggregate_point_in_time_sentiment(
    cutoff_time: datetime,
    news_items: Iterable[dict[str, Any]],
    lookback_days: int = 7,
) -> dict[str, Any]:
    """Compute aggregated sentiment strictly using news published at or before cutoff_time.

    Guarantees zero future-leakage by discarding any news with published_at > cutoff_time.
    """
    if cutoff_time.tzinfo is None:
        cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

    eligible_scores: list[float] = []
    eligible_articles: list[dict[str, Any]] = []

    for item in news_items:
        pub_str = item.get("published_at")
        if not pub_str:
            continue
        try:
            pub_dt = datetime.fromisoformat(str(pub_str).replace("Z", "+00:00"))
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            else:
                pub_dt = pub_dt.astimezone(timezone.utc)
        except Exception:
            continue

        # Point-in-time cutoff check: must be strictly <= cutoff_time
        if pub_dt > cutoff_time:
            continue

        # Lookback horizon check
        delta_days = (cutoff_time - pub_dt).total_seconds() / 86400.0
        if delta_days < 0 or delta_days > lookback_days:
            continue

        text = f"{item.get('title', '')} {item.get('summary', '')}"
        sent = analyze_text_sentiment(text)

        # Exponential recency decay weight: half-life of 2 days
        decay_weight = 0.5 ** (delta_days / 2.0)
        eligible_scores.append(sent["score"] * decay_weight)
        eligible_articles.append({
            "title": item.get("title"),
            "publisher": item.get("publisher"),
            "published_at": pub_str,
            "score": sent["score"],
            "weight": round(decay_weight, 3),
        })

    if not eligible_scores:
        return {
            "sentiment_score": 0.0,
            "news_count": 0,
            "recent_articles": [],
        }

    mean_sentiment = sum(eligible_scores) / len(eligible_scores)
    return {
        "sentiment_score": round(float(mean_sentiment), 4),
        "news_count": len(eligible_scores),
        "recent_articles": eligible_articles[:5],
    }
