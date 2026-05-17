"""
phase4_dataset.py
=================
Phase 4 dataset builder: Plan -> WS Query payload training examples.

Creates a structured dataset for specialized training/inference adaptation.
"""

import json
from pathlib import Path
from typing import Any


def get_seed_examples() -> list[dict[str, Any]]:
    """
    Canonical examples for the specialized "Plan -> Requete WS" dataset.
    """
    return [
        {
            "user_request": "Donne la facturation de ce trimestre pour le client CLI-001.",
            "logical_plan": [
                "Identifier periode (trimestre courant).",
                "Selectionner outil facturation.",
                "Construire payload avec customer + dates + status.",
            ],
            "required_webservices": ["consulter_facturation"],
            "final_payload": {
                "action": "consulter_facturation",
                "customer": "CLI-001",
                "startDate": "20260101",
                "endDate": "20260331",
                "status": "all",
            },
        },
        {
            "user_request": "Quels sont les articles de la famille OUTILLAGE ?",
            "logical_plan": [
                "Selectionner outil articles.",
                "Appliquer filtre famille.",
                "Limiter taille de retour.",
            ],
            "required_webservices": ["consulter_articles"],
            "final_payload": {
                "action": "consulter_articles",
                "family": "OUTILLAGE",
                "limit": 50,
            },
        },
        {
            "user_request": "Affiche les clients de la region NORD.",
            "logical_plan": [
                "Selectionner outil clients.",
                "Appliquer region.",
                "Fixer limite de pagination.",
            ],
            "required_webservices": ["consulter_clients"],
            "final_payload": {
                "action": "consulter_clients",
                "region": "NORD",
                "limit": 50,
            },
        },
        {
            "user_request": "Consulte le stock global de la reference ALB0001.",
            "logical_plan": [
                "Selectionner outil stocks.",
                "Injecter reference.",
                "Utiliser entrepot wildcard pour global.",
            ],
            "required_webservices": ["consulter_stocks"],
            "final_payload": {
                "action": "consulter_stocks",
                "reference": "ALB0001",
                "warehouse": "*",
                "limit": 100,
            },
        },
        {
            "user_request": "Donne les indicateurs de ventes par mois sur 2025.",
            "logical_plan": [
                "Selectionner outil analytiques.",
                "Choisir metric sales.",
                "Configurer fenetre temporelle + groupBy.",
            ],
            "required_webservices": ["consulter_indicateurs_analytiques"],
            "final_payload": {
                "action": "consulter_indicateurs_analytiques",
                "metric": "sales",
                "startDate": "20250101",
                "endDate": "20251231",
                "groupBy": "month",
            },
        },
    ]


def export_dataset_jsonl(output_path: str) -> str:
    """
    Export seed examples into JSONL format.
    """
    examples = get_seed_examples()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding="utf-8") as fh:
        for item in examples:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return str(target)
