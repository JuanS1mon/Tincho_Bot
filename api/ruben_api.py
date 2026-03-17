"""
API endpoints for Ruben offline analysis agent.
Provides REST interface for generating insights, selecting profiles, and applying recommendations.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import json

from offline_agents.ruben_tool_calling_wrapper import RubenToolCallingWrapper
from config.settings import settings

router = APIRouter(prefix="/api/ruben", tags=["ruben"])


# ────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ────────────────────────────────────────────────────────────────────────────


class GenerateInsightsRequest(BaseModel):
    hours: int = Field(24, ge=1, le=720, description="Hours to analyze")
    symbols: Optional[str] = Field(
        None, description="Comma-separated symbols (e.g., BTCUSDT,ETHUSDT)"
    )
    analysis_type: str = Field(
        "simple", 
        description="Analysis type: 'simple' (layer 1) or 'two_layer' (with LLM)"
    )


class SelectProfileRequest(BaseModel):
    profile: str = Field(..., description="Profile to select: 'conservative' or 'aggressive'")
    reasoning: str = Field(..., description="Why this profile was selected")


class ApplyRecommendationsRequest(BaseModel):
    apply_profile: str = Field("no", description="'yes' to apply, 'no' to skip")
    confidence_threshold: float = Field(
        0.0, ge=0.0, le=1.0, description="Min confidence to apply"
    )


class SkipAnalysisRequest(BaseModel):
    reason: str = Field(..., description="Reason for skipping analysis")


class RubenStatusResponse(BaseModel):
    status: str
    message: str
    tool_calling_enabled: bool
    last_analysis_available: bool


# ────────────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────────────


@router.get("/status")
async def get_ruben_status() -> RubenStatusResponse:
    """
    Get Ruben offline analysis status.
    """
    wrapper = RubenToolCallingWrapper()
    
    return RubenStatusResponse(
        status="ok",
        message="Ruben offline analysis agent is ready",
        tool_calling_enabled=settings.tool_calling_ruben,
        last_analysis_available=wrapper._last_analysis is not None,
    )


@router.post("/generate-insights")
async def generate_insights(request: GenerateInsightsRequest):
    """
    Generate insights report by analyzing historical trading data.
    
    Args:
        hours: Window of hours to analyze (1-720)
        symbols: Comma-separated CSV symbols (optional, auto-detect if omitted)
        analysis_type: 'simple' for layer 1 only, 'two_layer' for LLM analysis
    
    Returns:
        Insights report with per-symbol statistics and parameter suggestions
    """
    try:
        wrapper = RubenToolCallingWrapper()
        result = wrapper.generate_insights_report(
            hours=request.hours,
            symbols=request.symbols,
            analysis_type=request.analysis_type,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating insights: {str(e)}",
        )


@router.post("/select-profile")
async def select_profile(request: SelectProfileRequest):
    """
    Select a profile (conservative or aggressive) from analysis results.
    
    Args:
        profile: 'conservative' (risk preservation) or 'aggressive' (fast gains)
        reasoning: Explanation for the profile selection
    
    Returns:
        Selected profile with recommended adjustments
    """
    try:
        wrapper = RubenToolCallingWrapper()
        result = wrapper.select_profile(
            profile=request.profile,
            reasoning=request.reasoning,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error selecting profile: {str(e)}",
        )


@router.post("/apply-recommendations")
async def apply_recommendations(request: ApplyRecommendationsRequest):
    """
    Apply selected profile recommendations to Tincho1 parameters.
    
    Args:
        apply_profile: 'yes' to apply, 'no' to skip
        confidence_threshold: Min confidence (0.0-1.0) required to apply
    
    Returns:
        Application status and applied adjustments
    """
    try:
        wrapper = RubenToolCallingWrapper()
        result = wrapper.apply_recommendations(
            apply_profile=request.apply_profile,
            confidence_threshold=request.confidence_threshold,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error applying recommendations: {str(e)}",
        )


@router.post("/skip-analysis")
async def skip_analysis(request: SkipAnalysisRequest):
    """
    Skip analysis for this cycle with a reason.
    
    Args:
        reason: Why analysis is being skipped
    
    Returns:
        Skip confirmation
    """
    try:
        wrapper = RubenToolCallingWrapper()
        result = wrapper.skip_analysis(reason=request.reason)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error skipping analysis: {str(e)}",
        )


@router.post("/run-with-tool-calling")
async def run_with_tool_calling(system_prompt: Optional[str] = None):
    """
    Run Ruben with LLM-driven tool calling.
    LLM decides which tools to call and in what order.
    
    Args:
        system_prompt: Optional custom system prompt for the LLM
    
    Returns:
        Tool calling results and final analysis
    """
    if not settings.tool_calling_ruben:
        raise HTTPException(
            status_code=403,
            detail="Tool calling for Ruben is disabled (tool_calling_ruben=False)",
        )
    
    try:
        wrapper = RubenToolCallingWrapper()
        result = wrapper.run_with_tool_calling(system_prompt=system_prompt)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error running Ruben with tool calling: {str(e)}",
        )


# ────────────────────────────────────────────────────────────────────────────
# Complete Flow Endpoint (Experimental)
# ────────────────────────────────────────────────────────────────────────────


class RubenCompleteFlowRequest(BaseModel):
    hours: int = Field(24, ge=1, le=720, description="Hours to analyze")
    symbols: Optional[str] = Field(None, description="Comma-separated symbols")
    preferred_profile: str = Field("conservative", description="Preferred profile")
    auto_apply: bool = Field(False, description="Auto-apply if confident")


@router.post("/complete-flow")
async def complete_flow(request: RubenCompleteFlowRequest):
    """
    Complete flow: Generate insights → Select profile → Apply recommendations.
    This is a convenience endpoint that chains the main Ruben operations.
    
    Args:
        hours: Window of hours to analyze
        symbols: Comma-separated CSV symbols
        preferred_profile: 'conservative' or 'aggressive'
        auto_apply: Whether to automatically apply if confident
    
    Returns:
        Complete flow results (insights, selected profile, application status)
    """
    try:
        wrapper = RubenToolCallingWrapper()
        
        # Step 1: Generate insights with two-layer analysis
        insights_result = wrapper.generate_insights_report(
            hours=request.hours,
            symbols=request.symbols,
            analysis_type="two_layer",
        )
        
        if insights_result.get("status") != "success":
            return {
                "status": "failed_at_insights",
                "insights": insights_result,
            }
        
        # Step 2: Select profile
        select_result = wrapper.select_profile(
            profile=request.preferred_profile,
            reasoning=f"Executing complete flow with preferred profile: {request.preferred_profile}",
        )
        
        if select_result.get("status") != "success":
            return {
                "status": "failed_at_profile_selection",
                "insights": insights_result,
                "profile_selection": select_result,
            }
        
        # Step 3: Apply recommendations (if auto_apply is true)
        apply_result = {
            "status": "skipped",
            "message": "Auto-apply disabled",
        }
        
        if request.auto_apply:
            apply_result = wrapper.apply_recommendations(
                apply_profile="yes",
                confidence_threshold=0.5,
            )
        
        return {
            "status": "success",
            "flow": "complete",
            "insights": insights_result,
            "profile_selection": select_result,
            "application": apply_result,
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error in complete flow: {str(e)}",
        )
