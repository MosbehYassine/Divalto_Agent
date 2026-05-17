"""
phase5_analytics.py
===================
Transforms multi-step ERP payloads into synthesized French answers:

- Top‑N classement rows with optional CA total reconciliation
- Contiguous window comparisons drawn from sequential ``consulter_ventes`` calls
- Lightweight ASCII visualizations for analytic indicator buckets
"""

from __future__ import annotations

from typing import Any

from phase5_dates import describe_window_fr

Row = dict[str, Any]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace(",", ".").replace("€", "").strip())
    except (ValueError, TypeError):
        return None


def _step_ok(raw_step: Row) -> bool:
    return bool(raw_step.get("ok")) and raw_step.get("action")


def render_ranking_table(items: list[Row]) -> str:
    rows = [["#", "Article", "Qté", "CA (€)"]]
    def _rank_key(record: Row) -> int:
        candidate = record.get("rank", record.get("#", 999))
        try:
            return int(candidate)
        except (TypeError, ValueError):
            return 999

    top = sorted(items, key=_rank_key)
    for row in top:
        rank = row.get("rank", "?")
        ref = row.get("reference", "?")
        qty = row.get("quantite", "?")
        ca = row.get("ca", "?")
        rows.append([str(rank), str(ref), str(qty), str(ca)])

    widths = [max(len(str(r[idx])) for r in rows) for idx in range(4)]

    def line(cells: list[str]) -> str:
        padded = []
        for cell, width in zip(cells, widths, strict=False):
            padded.append(str(cell).ljust(width))
        return " │ ".join(padded)

    sep = "-+-".join("-" * w for w in widths)
    out = [line(rows[0]), sep]
    for body in rows[1:]:
        out.append(line(body))
    return "\n".join(out)


def render_ascii_chart(points: list[tuple[str, float]], max_width: int = 34) -> str:
    labels = [p[0] for p in points]
    values = [p[1] for p in points]
    vmax = max(values) if values else 1.0
    if vmax == 0:
        vmax = 1.0
    lines_out: list[str] = []
    for label, value in zip(labels, values, strict=False):
        frac = max(0.0, min(1.0, value / vmax))
        bars = max(1, int(frac * max_width)) if value > 0 else 0
        bar = "#" * bars if bars > 0 else "·"
        lines_out.append(f"{label[:12]:>12} │{bar:<{max_width}} {value:g}")
    return "\n".join(lines_out)


def synthesize_answer(user_question: str, execution_result: dict[str, Any]) -> str:
    steps = execution_result.get("steps", [])
    usable = [s for s in steps if _step_ok(s)]
    actions = [s["action"] for s in usable]

    if not usable:
        if execution_result.get("errors"):
            return "Impossible de finaliser les calculs métier suite à une erreur d'étape ERP."
        return "Aucun résultat exploitable après exécution orchestrée."

    # Analytic buckets
    if actions.count("consulter_indicateurs_analytiques") >= 1:
        raw = usable[-1]["raw"]
        snapshot = usable[-1].get("payload_snapshot") or {}
        metric = raw.get("metric", "sales")
        group_by = raw.get("groupBy", "bucket")
        series = raw.get("series") or []
        points = []
        for point in series:
            bucket_label = point.get("bucket") or "?"
            value = float(point.get("value") or 0.0)
            points.append((str(bucket_label), value))
        if not points:
            return "Série analytique vide sur la fenêtre sélectionnée."
        viz = render_ascii_chart(points)
        window_label = describe_window_fr(
            str(snapshot.get("startDate", "") or ""),
            str(snapshot.get("endDate", "") or ""),
        )
        headline = (
            f"Répartition {metric.replace('_', ' ')} "
            f"({group_by}) — {window_label} :"
            if metric
            else f"Indicateurs analytiques — {window_label} :"
        )
        return headline + "\n" + viz

    # Comparative totals (assume étape la plus ancienne stockée après la récente)
    if actions.count("consulter_ventes") >= 2 and "classement_ventes" not in actions:
        snap_recent = usable[0].get("payload_snapshot") or {}
        snap_prev = usable[1].get("payload_snapshot") or {}
        window_recent_txt = describe_window_fr(
            str(snap_recent.get("startDate", "")),
            str(snap_recent.get("endDate", "")),
        )
        window_prev_txt = describe_window_fr(
            str(snap_prev.get("startDate", "")),
            str(snap_prev.get("endDate", "")),
        )
        recent_total = float(usable[0]["raw"].get("totalVentes") or 0.0)
        previous_total = float(usable[1]["raw"].get("totalVentes") or 0.0)
        delta = recent_total - previous_total
        pct = round(delta / previous_total * 100, 1) if previous_total else 0.0
        trend_word = "hausse" if delta >= 0 else "baisse"
        return (
            f"Comparaison CA ({window_prev_txt} -> {window_recent_txt}).\n"
            f"Période la plus récente : {recent_total:.2f} € ; "
            f"période de référence : {previous_total:.2f} €.\n"
            f"Variation : {delta:+.2f} € ({pct:+.1f} %), soit une {trend_word} relative."
        )

    classement_rank = None
    for step in usable:
        if step["action"] == "classement_ventes":
            classement_rank = step
            break

    leader_stock = None
    for step in usable:
        if classement_rank and step["action"] == "interroger_stock":
            leader_stock = step
            break

    totals_step = None
    if classement_rank:
        for step in usable:
            if step["action"] == "consulter_ventes" and step["step"] > classement_rank["step"]:
                totals_step = step
                break

    if classement_rank:
        raw_rank = classement_rank["raw"]
        items_raw = raw_rank.get("items") or []
        if not items_raw:
            window_txt = describe_window_fr(str(raw_rank.get("startDate") or ""), str(raw_rank.get("endDate") or ""))
            return f"Aucun classement disponible ({window_txt})."

        ordered_rows = sorted(items_raw, key=lambda row: row.get("rank", 999))
        preview = ordered_rows[: min(5, len(ordered_rows))]
        table = render_ranking_table(preview)
        winner = sorted(items_raw, key=lambda row: row.get("rank", 999))[0]
        qty = winner.get("quantite", "?")
        ca_leader = winner.get("ca")

        headline = infer_headline_sentence(
            winner.get("reference", "?"),
            qty,
            ca_leader,
            describe_window_fr(str(raw_rank.get("startDate") or ""), str(raw_rank.get("endDate") or "")),
        )

        paragraphs = [headline, "Synthèse tableau (extrait):\n" + table]

        if totals_step:
            total_ca = totals_step["raw"].get("totalVentes")
            summed_rows = sum(_safe_float(row.get("ca")) or 0.0 for row in items_raw)
            reconcile = ""
            if total_ca is not None:
                reconcile = (
                    f"\nCA consolidé ERP sur la même fenêtre : {float(total_ca):.2f} € "
                    f"(somme ligne classement approx. {summed_rows:.2f} €)."
                )
            paragraphs.append(reconcile.strip())

        if leader_stock:
            qty_stock = leader_stock["raw"].get(
                "quantity",
                leader_stock["raw"].get("quantite", "?"),
            )
            wh = leader_stock["raw"].get("warehouse", "*")
            paragraphs.append(f"Stock actuel pour le leader '{winner.get('reference')}' ({wh}) : {qty_stock} unité(s).")

        return "\n\n".join(p for p in paragraphs if p)

    # Fallback reuse Phase 3 single-step summaries
    if len(usable) == 1:
        from divalto_agent import format_response

        single = usable[0]
        return format_response(single["action"], single["raw"])

    fallback_lines = []
    for chunk in usable:
        fallback_lines.append(f"[{chunk['action']}]\n```\n{chunk['raw']}\n```")
    return "\n\n".join(fallback_lines)


def infer_headline_sentence(article_ref: Any, qty: Any, ca: Any, window_txt: str) -> str:
    ca_piece = ""
    fv = _safe_float(ca)
    if fv is not None:
        ca_piece = f", pour un CA de {fv:.2f} €"
    elif ca not in (None, "", "?"):
        ca_piece = f", pour un CA de {ca} €"
    return (
        f"Le produit le plus vendu {window_txt} est '{article_ref}' "
        f"avec {qty} unités{ca_piece}."
    )

