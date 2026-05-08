from fastapi import APIRouter

from app.modules.meta_ads.tools import meta_get_campaigns, meta_get_account_insights, meta_analyze_and_recommend

router = APIRouter()


@router.get("/campaigns")
async def get_campaigns():
    return await meta_get_campaigns()


@router.get("/insights")
async def get_insights(date_preset: str = "today"):
    return await meta_get_account_insights(date_preset=date_preset)


@router.get("/recommendations")
async def get_recommendations():
    return await meta_analyze_and_recommend()
