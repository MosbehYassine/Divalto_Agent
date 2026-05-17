"""
api_server.py
=============
HTTP API for frontend chat integration.
Run with: uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from intent_contract import decompose_query, infer_intent
from ollama_client import ensure_ollama_model_ready
from phase3_agent import run_phase3
from phase3_planner import _is_client_count_query
from phase4_agent import run_phase4
from phase5_agent import run_phase5
from semantic_routing import classic_semantic_analytics_eligible
from settings import SQLITE_MOCK_DB_PATH, USE_SQLITE_MOCK


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
    normalized = query.lower()
    # Master-data counts must stay in Phase 3 (WS + consulter_clients), never Phase 5 time-series.
    if _is_client_count_query(query):
        return "classic"
    decomposition = decompose_query(query)
    intent = infer_intent(query)
    phase4_hints = (
        "dataset",
        "csv",
        "excel",
        "export",
        "table",
        "sql",
        "query builder",
        "mdx",
        "olap",
        "cube",
        "dimension",
        "hierarchy",
        "measure",
    )
    phase5_hints = (
        "forecast",
        "prediction",
        "predictive",
        "projection",
    )
    langgraph_hints = ("workflow", "agent graph", "langgraph")

    if decomposition.wants_mdx or any(hint in normalized for hint in phase4_hints):
        return "phase4"
    if decomposition.wants_forecast or any(hint in normalized for hint in phase5_hints):
        return "phase5"
    if decomposition.wants_time_series or decomposition.wants_comparison or intent.intent == "kpi_analysis":
        return "phase5"
    if any(hint in normalized for hint in langgraph_hints):
        return "langgraph"
    return "classic"


@app.post("/api/chat")
def chat(payload: ChatRequest):
    query = payload.query.strip()
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
            from langgraph_agent import run_phase3_langgraph

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
