from fastapi import APIRouter, HTTPException
from agent.marquitos_agent import marquitos_agent

router = APIRouter()

@router.get("/marquitos/state", summary="Estado de Marquitos (scalper)")
def get_marquitos_state():
    try:
        return marquitos_agent.get_state_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error: {exc}")
