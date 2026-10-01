import os
from typing import Dict, List, Tuple
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_PROTECTED_ENVIRONMENTS = ["prod", "production", "live", "critical"]
DEFAULT_PROTECTED_TAG_KEYS = [
    "CostOptimizerOptOut",
    "DoNotStop",
    "Protected",
    "Production",
]


def get_protected_environments() -> List[str]:
    """Retrieves protected environment names from environment variable."""
    env_str = os.environ.get("PROTECTED_ENVIRONMENTS", "")
    if env_str:
        return [e.strip().lower() for e in env_str.split(",") if e.strip()]
    return DEFAULT_PROTECTED_ENVIRONMENTS


def is_resource_protected(tags: Dict[str, str]) -> Tuple[bool, str]:
    """
    Evaluates whether a cloud resource is protected from automated remediation.
    Returns (is_protected, reason).
    """
    # 1. Check direct opt-out tags
    for key in DEFAULT_PROTECTED_TAG_KEYS:
        val = str(tags.get(key, "")).lower()
        if val in ["true", "yes", "1"]:
            return True, f"Direct opt-out tag active: {key}={val}"

    # 2. Check environment safety guardrails
    prod_flag = os.environ.get("ALLOW_PRODUCTION_REMEDIATION", "false")
    allow_prod = prod_flag.lower() == "true"
    if not allow_prod:
        env_tag = (
            tags.get("Environment")
            or tags.get("env")
            or tags.get("environment")
            or ""
        ).lower()

        protected_envs = get_protected_environments()
        if env_tag in protected_envs:
            return True, (
                f"Resource is in protected environment '{env_tag}'. "
                "Production remediation guardrail active."
            )

    return False, "Not protected"


def filter_actionable_resources(
    resources: List[Dict]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Separates detected resources into actionable and protected groups.
    """
    actionable: List[Dict] = []
    protected: List[Dict] = []

    for res in resources:
        tags = res.get("tags") or res.get("details", {}).get("tags", {})
        is_prot, reason = is_resource_protected(tags)

        if is_prot:
            res_id = res.get("resource_id", "unknown")
            logger.info(
                f"Governance Guardrail: Skipping {res_id} - {reason}"
            )
            res["protection_reason"] = reason
            protected.append(res)
        else:
            actionable.append(res)

    return actionable, protected
