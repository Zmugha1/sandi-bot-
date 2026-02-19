"""
Rule-based coaching recommendations from rules.yaml.
Every recommendation includes: action, why, evidence (snippet + page) from the client's facts.
No LLM. Deterministic.
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = REPO_ROOT / "data" / "rules.yaml"


def _load_rules() -> List[Dict[str, Any]]:
    if not RULES_PATH.exists():
        return []
    try:
        import yaml
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return (data or {}).get("rules") or []
    except Exception:
        return []


def _matches_trigger(label: str, triggers: List[str]) -> bool:
    if not label or not triggers:
        return False
    label_lower = label.lower()
    for t in triggers:
        if t and t.lower() in label_lower:
            return True
    return False


def get_recommendations(
    traits: List[Dict[str, Any]],
    drivers: List[Dict[str, Any]],
    risks: List[Dict[str, Any]],
    max_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Returns list of {
      "action": str,
      "why": str,
      "evidence": {"page": int, "snippet": str},
      "triggered_by": str  # which fact triggered
    }
    """
    rules = _load_rules()
    trait_labels = [ (t.get("label") or "", t.get("evidence")) for t in (traits or []) ]
    driver_labels = [ (d.get("label") or "", d.get("evidence")) for d in (drivers or []) ]
    risk_labels = [ (r.get("label") or "", r.get("evidence")) for r in (risks or []) ]

    out = []
    seen_actions = set()

    for rule in rules:
        if len(out) >= max_n:
            break
        triggers_cfg = rule.get("triggers") or {}
        trait_triggers = triggers_cfg.get("trait") or []
        driver_triggers = triggers_cfg.get("driver") or []
        risk_triggers = triggers_cfg.get("risk") or []

        evidence = None
        triggered_by = None

        for label, ev in trait_labels:
            if _matches_trigger(label, trait_triggers):
                evidence = ev or {}
                triggered_by = f"Trait: {label}"
                break
        if not triggered_by:
            for label, ev in driver_labels:
                if _matches_trigger(label, driver_triggers):
                    evidence = ev or {}
                    triggered_by = f"Driver: {label}"
                    break
        if not triggered_by:
            for label, ev in risk_labels:
                if _matches_trigger(label, risk_triggers):
                    evidence = ev or {}
                    triggered_by = f"Risk: {label}"
                    break

        if not triggered_by:
            continue

        action = (rule.get("action") or "").strip()
        why = (rule.get("why") or "").strip()
        if not action or action in seen_actions:
            continue
        seen_actions.add(action)
        out.append({
            "action": action,
            "why": why,
            "evidence": evidence or {},
            "triggered_by": triggered_by,
        })

    return out[:max_n]
