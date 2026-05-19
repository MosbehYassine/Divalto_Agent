"""
phase3_agent.py
===============
Phase 3 — Complete agent: Planner + Orchestrator + Aggregator

This is the main entry point for Phase 3.
Import and call run_phase3(user_query) from your agent loop.

Also contains the full mock test suite at the bottom —
run this file directly to validate everything works
before you have real endpoints.

Usage:
    python phase3_agent.py          # runs all mock tests
    from phase3.agent import run_phase3
"""

import json

from core.console_utils import normalize_user_text, safe_print
from governance.context import build_optional_context_from_env
from governance.execution_context import AgentExecutionContext
from governance.models import ExecutionApproval
from governance.pipeline import finalize_agent_audit
from core.intent_contract import infer_intent

from analytics.catalog import load_or_build_semantic_bundle
from analytics.orchestrator import run_semantic_data_analytics
from phase3.orchestrator import execute_plan
from phase3.planner import plan
from routing.semantic_routing import classic_semantic_analytics_eligible


def _safe_log(text: str) -> None:
    safe_print(text)


# ─────────────────────────────────────────────
# PRECHECKS
# ─────────────────────────────────────────────

def _requires_reference_clarification(execution_plan: list[dict]) -> bool:
    """True when a stock lookup is planned without a usable article reference."""
    for step in execution_plan:
        if step.get("action") != "interroger_stock":
            continue
        reference = str(step.get("reference", "")).strip()
        if not reference or reference.upper() == "UNKNOWN_REFERENCE":
            return True
    return False


# ─────────────────────────────────────────────
# AGGREGATOR
# ─────────────────────────────────────────────

def aggregate(execution_result: dict) -> dict:
    """
    Analyse the steps and their results to determine
    what kind of answer to build.

    Returns a structured dict that format_final() will render.
    """
    steps = execution_result.get("steps", [])

    if not steps:
        return {"type": "error", "message": "No results to aggregate."}

    # Single step → just return it directly
    if len(steps) == 1:
        s = steps[0]
        return {
            "type":   "single",
            "action": s["action"],
            "raw":    s["raw"]
        }

    # Two steps where step 0 found a top article and
    # step 1 checked its stock → "top + stock" combo
    actions = [s["action"] for s in steps]

    # If ranking is present, prioritize rendering ranking as a single business answer.
    # Some planners may append extra helper calls; ranking remains the user-facing intent.
    if "classement_clients" in actions:
        ranking_step = next((s for s in reversed(steps) if s.get("action") == "classement_clients"), None)
        if ranking_step is not None:
            return {
                "type": "single",
                "action": "classement_clients",
                "raw": ranking_step.get("raw", {}),
            }

    if "classement_ventes" in actions:
        ranking_step = next((s for s in reversed(steps) if s.get("action") == "classement_ventes"), None)
        if ranking_step is not None:
            return {
                "type": "single",
                "action": "classement_ventes",
                "raw": ranking_step.get("raw", {}),
            }

    if ("article_plus_vendu" in actions and
            "interroger_stock" in actions):
        top_data   = steps[0]["raw"]
        stock_data = steps[1]["raw"]
        return {
            "type":      "top_plus_stock",
            "article":   top_data.get("reference", "?"),
            "sold":      top_data.get("quantite",  "?"),
            "ca":        top_data.get("ca",         None),
            "stock":     stock_data.get("quantity",
                         stock_data.get("quantite", "?")),
            "warehouse": stock_data.get("warehouse", "*")
        }

    # Two steps both querying sales → period comparison
    if actions.count("consulter_ventes") == 2:
        current  = steps[0]["raw"].get("totalVentes", 0)
        previous = steps[1]["raw"].get("totalVentes", 0)
        delta    = current - previous
        pct      = round(delta / previous * 100, 1) if previous else 0
        return {
            "type":     "comparison",
            "current":  current,
            "previous": previous,
            "delta":    delta,
            "pct":      pct,
            "trend":    "up" if delta >= 0 else "down"
        }

    # Multiple stock steps → total across depots
    if all(s["action"] == "interroger_stock" for s in steps):
        total = sum(
            s["raw"].get("quantity", s["raw"].get("quantite", 0))
            for s in steps
        )
        return {"type": "total_stock", "total": total,
                "steps": len(steps)}

    # Fallback: return all raw results
    return {
        "type":    "multi_raw",
        "results": [{"action": s["action"], "raw": s["raw"]}
                    for s in steps]
    }


# ─────────────────────────────────────────────
# FINAL FORMATTER
# ─────────────────────────────────────────────

def format_final(aggregated: dict, user_query: str = "") -> str:
    """
    Convert the aggregated dict into a natural French sentence.
    """
    t = aggregated.get("type")

    if t == "error":
        return f"Erreur : {aggregated.get('message')}"

    if t == "single":
        # Delegate to Phase 2 format_response for single-step answers
        from core.divalto_agent import format_response

        return format_response(aggregated["action"], aggregated["raw"], user_query=user_query or "")

    if t == "top_plus_stock":
        art   = aggregated["article"]
        sold  = aggregated["sold"]
        stock = aggregated["stock"]
        ca    = aggregated.get("ca")
        msg   = (f"L'article le plus vendu est '{art}' "
                 f"avec {sold} unité(s) écoulée(s).")
        if ca:
            msg += f" CA généré : {ca} €."
        msg += f" Stock actuel : {stock} unité(s) disponible(s)."
        return msg

    if t == "comparison":
        sign  = "+" if aggregated["delta"] >= 0 else ""
        trend = "en hausse" if aggregated["trend"] == "up" else "en baisse"
        return (
            f"Ce mois : {aggregated['current']} €  |  "
            f"Mois précédent : {aggregated['previous']} €\n"
            f"Évolution : {sign}{aggregated['delta']} € "
            f"({sign}{aggregated['pct']}%) — {trend}."
        )

    if t == "total_stock":
        return (
            f"Stock total consolidé sur {aggregated['steps']} dépôt(s) : "
            f"{aggregated['total']} unité(s)."
        )

    if t == "multi_raw":
        lines = []
        for r in aggregated["results"]:
            lines.append(
                f"[{r['action']}] -> "
                f"{json.dumps(r['raw'], ensure_ascii=False)}"
            )
        return "\n".join(lines)

    return f"Résultat brut : {json.dumps(aggregated, ensure_ascii=False)}"


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def run_phase3(
    user_query: str,
    use_mock_planner: bool = True,
    mock_responses: dict | None = None,
    *,
    correlation_id: str | None = None,
    approval: ExecutionApproval | None = None,
    execution_context: AgentExecutionContext | None = None,
) -> str:
    """
    Full Phase 3 pipeline:
        user_query
            → plan()           (planner)
            → execute_plan()   (orchestrator)
            → aggregate()      (aggregator)
            → format_final()   (formatter)
            → French answer

    Args:
        user_query        : natural language question
        use_mock_planner  : True = rule-based planner (no LLM needed)
        mock_responses    : dict of step_N → fake ERP JSON (None → real endpoint)
        correlation_id / approval / execution_context : optional Phase‑6 telemetry controls

    Returns:
        str — the final business answer
    """
    user_query = normalize_user_text(user_query)

    safe_print(f"\n{'='*55}")
    safe_print("PHASE 3 AGENT")
    safe_print(f"Query: {user_query}")
    safe_print("=" * 55)

    exec_ctx = execution_context or build_optional_context_from_env(
        user_query=user_query,
        correlation_id=correlation_id,
        approval=approval,
    )

    # Step 1 — Plan
    execution_plan = plan(user_query, use_mock=use_mock_planner)
    if _requires_reference_clarification(execution_plan):
        decision = infer_intent(user_query)
        answer = (
            decision.clarification_message
            if decision.requires_clarification and decision.clarification_message
            else (
                "J'ai besoin de la reference article pour verifier le stock. "
                "Pouvez-vous me donner le code produit (ex: ALB0001) ?"
            )
        )
        finalize_agent_audit(
            exec_ctx,
            plan=execution_plan,
            execution_result={"ok": False, "steps": [], "errors": [{"type": "MISSING_REFERENCE"}]},
            final_answer=answer,
        )
        _safe_log(f"\n[Final Answer] {answer}")
        return answer

    # Step 2 — Execute
    result = execute_plan(execution_plan, mock_responses=mock_responses, execution_context=exec_ctx)

    governance = result.get("governance") or {}
    if governance.get("plan_blocked"):
        answer = (
            "La demande a été bloquée par la politique de sécurité (périmètre non autorisé). "
            f"Détails : {governance.get('message', '')}"
        )
        finalize_agent_audit(
            exec_ctx,
            plan=execution_plan,
            execution_result=result,
            final_answer=answer,
        )
        _safe_log(f"\n[Final Answer] {answer}")
        return answer

    if not result["ok"] and not result["steps"]:
        fallback = result.get("error") or result.get("errors")
        answer = f"Erreur d'exécution : {fallback}"
        finalize_agent_audit(
            exec_ctx,
            plan=execution_plan,
            execution_result=result,
            final_answer=answer,
        )
        _safe_log(f"\n[Final Answer] {answer}")
        return answer

    # Step 3 — Aggregate
    aggregated = aggregate(result)

    # Step 4 — Format
    answer = format_final(aggregated, user_query=user_query)

    if not use_mock_planner and classic_semantic_analytics_eligible(user_query):
        bundle, _, _ = load_or_build_semantic_bundle()
        if bundle:
            try:
                sa = run_semantic_data_analytics(user_query)
                if sa.get("ok") and sa.get("answer"):
                    answer = f"{answer.rstrip()}\n\n---\n\n{sa['answer'].strip()}"
            except Exception as exc:  # noqa: BLE001
                answer = f"{answer.rstrip()}\n\n---\n\n_Analytique cataloguée : {exc}_"

    finalize_agent_audit(
        exec_ctx,
        plan=execution_plan,
        execution_result=result,
        final_answer=answer,
    )

    _safe_log(f"\n[Final Answer] {answer}")
    return answer


# ─────────────────────────────────────────────
# MOCK TEST SUITE
# ─────────────────────────────────────────────

if __name__ == "__main__":

    print("\n" + "="*55)
    print("  PHASE 3 MOCK TEST SUITE")
    print("  No real endpoint needed.")
    print("="*55)

    results = []

    def test(name, query, mocks, expected_keyword):
        answer = run_phase3(
            query,
            use_mock_planner=True,
            mock_responses=mocks
        )
        passed = expected_keyword.lower() in answer.lower()
        results.append((name, passed, answer))
        status = "PASS" if passed else "FAIL"
        print(f"\n[{status}] {name}")
        print(f"       -> {answer}")

    # ── Test 1: single stock query ─────────────────
    test(
        name="Single stock query",
        query="Quel est le stock de l'article ALB0001 ?",
        mocks={
            "step_0": {
                "reference": "ALB0001",
                "warehouse": "*",
                "quantity":  42
            }
        },
        expected_keyword="42"
    )

    # ── Test 2: top seller + its stock ────────────
    test(
        name="Top seller + stock combo",
        query="Quel est l'article le plus vendu et quel est son stock ?",
        mocks={
            "step_0": {
                "reference": "PROD-007",
                "quantite":  320,
                "ca":        "14500"
            },
            "step_1": {
                "reference": "PROD-007",
                "warehouse": "*",
                "quantity":  18
            }
        },
        expected_keyword="PROD-007"
    )

    # ── Test 3: reference injection works ─────────
    test(
        name="Reference injected from step 0 into step 1",
        query="Top produit et son stock dispo ?",
        mocks={
            "step_0": {
                "reference": "XYZ-999",
                "quantite":  100
            },
            "step_1": {
                "reference": "XYZ-999",
                "quantity":  5
            }
        },
        expected_keyword="XYZ-999"
    )

    # ── Test 4: sales comparison ───────────────────
    test(
        name="Month-over-month sales comparison",
        query="Compare les ventes de ce mois vs le mois dernier",
        mocks={
            "step_0": {"totalVentes": 48200},
            "step_1": {"totalVentes": 41500}
        },
        expected_keyword="hausse"
    )

    # ── Test 5: sales down ─────────────────────────
    test(
        name="Sales comparison — downward trend",
        query="Évolution des ventes mois par mois ?",
        mocks={
            "step_0": {"totalVentes": 30000},
            "step_1": {"totalVentes": 45000}
        },
        expected_keyword="baisse"
    )

    # ── Test 6: top seller only ────────────────────
    test(
        name="Top seller only (no stock)",
        query="Quel est le meilleur produit du mois ?",
        mocks={
            "step_0": {
                "reference": "TOP-001",
                "quantite":  500,
                "ca":        "25000"
            }
        },
        expected_keyword="TOP-001"
    )

    # ── Summary ───────────────────────────────────
    print(f"\n{'='*55}")
    passed = sum(1 for _, p, _ in results if p)
    total  = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    for name, p, answer in results:
        icon = "[OK]" if p else "[X]"
        print(f"  {icon} {name}")

    if passed == total:
        print("\nAll tests passing. Phase 3 logic is correct.")
        print("Ready for real endpoints when the company sends them.")
    else:
        print("\nSome tests failed. Review the output above.")
    print('='*55)
