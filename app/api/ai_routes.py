from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/ai")


@router.get("/models")
async def list_models() -> dict:
    """Danh sách model OpenRouter được hỗ trợ (curated whitelist) cho frontend."""
    models = settings.ai_model_choice_list
    return {
        "enabled": settings.ai_enabled,
        "provider": "openrouter",
        "base_url": settings.ai_base_url,
        "default_model": settings.ai_model if settings.ai_model_is_choice else None,
        "models": models,
    }
