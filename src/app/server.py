"""
api_server.py
=============
HTTP API for frontend chat integration.
Run with: uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.console_utils import normalize_user_text
from core.intent_contract import infer_intent
from core.pipeline_router import resolve_execution_mode
from llm.ollama_client import ensure_ollama_model_ready
from phase3.agent import run_phase3
from phase4.agent import run_phase4
from phase5.agent import run_phase5
from routing.semantic_routing import classic_semantic_analytics_eligible
from core.feedback_store import append_answer_feedback
from core.settings import SQLITE_MOCK_DB_PATH, USE_SQLITE_MOCK


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = Field(default="auto")
    real_planner: bool = Field(default=True)


class ChatResponse(BaseModel):
    ok: bool
    mode: str
    answer: str
    intent: str | None = None
    confidence: str | None = None


class WarmupRequest(BaseModel):
    pull_if_missing: bool = Field(default=True)


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    user_query: str = Field(default="")
    assistant_answer: str = Field(min_length=1)
    mode: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    chart_type: str | None = None
    real_planner: bool | None = None


app = FastAPI(title="Divalto Agent API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "sqlite_mock": str(bool(USE_SQLITE_MOCK)).lower(),
        "sqlite_db_path": SQLITE_MOCK_DB_PATH or "",
    }


def _infer_mode_from_query(query: str) -> str:
    """Infer execution mode from user intent when mode='auto'."""
    return resolve_execution_mode(query)


@app.post("/api/chat")
def chat(payload: ChatRequest):
    query = normalize_user_text(payload.query)
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    use_mock_planner = not payload.real_planner
    requested_mode = payload.mode.lower().strip()
    mode = _infer_mode_from_query(query) if requested_mode in {"", "auto"} else requested_mode
    intent_decision = infer_intent(query)

    try:
        # Mock planner: no Ollama for classic/phase5 (fast). Phase4 still needs the analytics LLM.
        needs_ollama = (mode == "phase4") or (
            payload.real_planner
            and (
                mode == "phase5"
                or (mode == "classic" and classic_semantic_analytics_eligible(query))
            )
        )
        if needs_ollama:
            warmup = ensure_ollama_model_ready(pull_if_missing=True)
            if not warmup.get("ok"):
                raise HTTPException(status_code=503, detail=warmup.get("message", "Ollama model unavailable."))

        if mode == "phase4":
            result = run_phase4(query)
            answer = result.get("answer") if isinstance(result, dict) else str(result)
            return {
                "ok": True,
                "mode": mode,
                "answer": answer if isinstance(answer, str) else str(result),
                "result": result,
                "intent": intent_decision.intent,
                "confidence": intent_decision.confidence,
            }
        if mode == "phase5":
            answer = run_phase5(query, use_mock_planner=use_mock_planner)
            return ChatResponse(
                ok=True,
                mode=mode,
                answer=answer,
                intent=intent_decision.intent,
                confidence=intent_decision.confidence,
            ).model_dump()
        if mode == "langgraph":
            from agents.langgraph_agent import run_phase3_langgraph

            answer = run_phase3_langgraph(query, use_mock_planner=use_mock_planner)
            return ChatResponse(
                ok=True,
                mode=mode,
                answer=answer,
                intent=intent_decision.intent,
                confidence=intent_decision.confidence,
            ).model_dump()

        answer = run_phase3(query, use_mock_planner=use_mock_planner)
        return ChatResponse(
            ok=True,
            mode="classic",
            answer=answer,
            intent=intent_decision.intent,
            confidence=intent_decision.confidence,
        ).model_dump()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/feedback")
def submit_feedback(payload: FeedbackRequest):
    try:
        return append_answer_feedback(
            rating=payload.rating,  # type: ignore[arg-type]
            user_query=payload.user_query,
            assistant_answer=payload.assistant_answer,
            mode=payload.mode,
            conversation_id=payload.conversation_id,
            message_id=payload.message_id,
            chart_type=payload.chart_type,
            real_planner=payload.real_planner,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write feedback: {exc}") from exc


@app.post("/api/planner/warmup")
def planner_warmup(payload: WarmupRequest):
    try:
        result = ensure_ollama_model_ready(pull_if_missing=payload.pull_if_missing)
        if not result.get("ok"):
            raise HTTPException(status_code=503, detail=result.get("message", "Ollama model unavailable."))
        return {"ok": True, **result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ollama warmup failed: {exc}") from exc
