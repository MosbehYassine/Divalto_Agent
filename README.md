# Divalto Agent Project

## Structure
- `src/`: core agent code (phase 2 + phase 3 + phase 4)
- `tests/`: mock test suites
- `docs/`: documentation and project status
- `datasets/`: training-ready structured datasets (Phase 4)

## Configuration
1. Copy `.env.example` to `.env`
2. Fill real Divalto values:
   - `DIVALTO_BASE_URL` / `DIVALTO_AUTH_URL` / `DIVALTO_WS_URL`
   - `DIVALTO_USER` / `DIVALTO_PASSWORD` / `DIVALTO_ENV`
   - `DIVALTO_DOSSIER_CODE`

## Run tests
- Phase 2 mock tests:
  - `python tests/divalto_agent_mock_test.py`
- Phase 3 mock tests:
  - `python src/phase3_agent.py`
- LangGraph smoke test:
  - `python tests/langgraph_smoke_test.py`
- Phase 4 tests:
  - `python -m pytest tests/phase4_query_builder_test.py`

## Unified CLI
- Classic mode:
  - `python src/main.py --mode classic --query "Quel est le stock de l'article ALB0001 ?"`
- LangGraph mode:
  - `python src/main.py --mode langgraph --query "Quel est le stock de l'article ALB0001 ?"`
- With mock responses:
  - `python src/main.py --mode classic --query "..." --mock-responses-json "{\"step_0\": {\"quantity\": 42}}"`
- Phase 4 query builder + dataset export:
  - `python src/main.py --mode phase4 --query "Donne la facturation du client CLI-001" --dataset-output-dir datasets`

## LangGraph
- Install dependency:
  - `pip install -r requirements.txt`
- LangGraph pipeline file:
  - `src/langgraph_agent.py`
- Entry point:
  - `run_phase3_langgraph(...)`
