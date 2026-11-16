from typing import Dict, List, Tuple
from src.utils.config import get_config
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
    """Retrieves protected environment names from centralized config."""
    cfg = get_config(reload=True)
    return cfg.protected_environments


def is_resource_protected(tags: Dict[str, str]) -> Tuple[bool, str]:
    """
    Evaluates whether a cloud resource is protected from automated remediation.
    Returns (is_protected, reason).
    """
    cfg = get_config(reload=True)

    # 1. Check direct opt-out tags
    for key in cfg.protected_tag_keys:
        val = str(tags.get(key, "")).lower()
        if val in ["true", "yes", "1"]:
            return True, f"Direct opt-out tag active: {key}={val}"

    # 2. Check environment safety guardrails
    if not cfg.allow_production_remediation:
        env_tag = (
            tags.get("Environment")
            or tags.get("env")
            or tags.get("environment")
            or ""
        ).lower()

        protected_envs = cfg.protected_environments
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
    Returns (actionable_resources, protected_resources).
    """
    actionable = []
    protected = []

    for res in resources:
        tags = res.get("tags", {})
        is_prot, reason = is_resource_protected(tags)
        if is_prot:
            res_copy = dict(res)
            res_copy["protection_reason"] = reason
            protected.append(res_copy)
            logger.info(
                f"Resource {res.get('resource_id')} "
                f"({res.get('resource_type')}) protected: {reason}"
            )
        else:
            actionable.append(res)

    return actionable, protected
