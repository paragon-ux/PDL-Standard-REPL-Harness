"""Model and Provider Classification Taxonomy (Track M2).

Prevents cross-tier and cross-provider false equivalences in adversarial evaluation.
Explicitly distinguishes between:
  1. Capability Tier (Frontier Flagship vs. Mid-Tier Balanced vs. Lightweight Fast)
  2. Provider Hosting Class (Direct Dedicated vs. Aggregator BYOK vs. Aggregator Shared Pool)
  3. Reasoning Architecture (Disabled vs. Native Thinking Traces)

Under this taxonomy, comparing a Mid-Tier Balanced model (e.g. GLM-4.7) to a
Frontier Flagship model (e.g. DeepSeek-V4-Pro, Claude 3.5 Sonnet, GPT-4o) without
controlling for capability tier constitutes a methodological false equivalence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class CapabilityTier(str, Enum):
    FRONTIER_FLAGSHIP = "FRONTIER_FLAGSHIP"  # Tier 1: DeepSeek-V4-Pro, GPT-4o, Claude 3.5 Sonnet, GLM-5.3
    MID_BALANCED = "MID_BALANCED"            # Tier 2: GLM-4.7, DeepSeek-Flash, Qwen-2.5-72B, Llama-3.3-70B
    LIGHT_FAST = "LIGHT_FAST"                # Tier 3: GLM-4.7-Flash, Gemini-2.0-Flash, Claude-3.5-Haiku


class ProviderHostingClass(str, Enum):
    DIRECT_FIRST_PARTY = "DIRECT_FIRST_PARTY"  # Direct vendor API with dedicated account quota (e.g. api.deepseek.com)
    AGGREGATOR_BYOK = "AGGREGATOR_BYOK"        # Aggregator proxy with user's own upstream account key
    AGGREGATOR_SHARED = "AGGREGATOR_SHARED"    # Aggregator shared public rate-limit pool (e.g. OpenRouter free/shared)


@dataclass(frozen=True)
class ModelClassification:
    model_id: str
    display_name: str
    family: str
    capability_tier: CapabilityTier
    tier_rank: int  # 1 = Frontier, 2 = Mid, 3 = Light
    provider_class: ProviderHostingClass
    upstream_provider: str
    reasoning_mode: str
    recommended_inter_call_delay_s: float
    comparative_peers: list[str]
    methodological_notes: str

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["capability_tier"] = self.capability_tier.value
        d["provider_class"] = self.provider_class.value
        return d


# Known model taxonomy registry
_TAXONOMY: dict[str, dict[str, Any]] = {
    "z-ai/glm-4.7": {
        "display_name": "GLM-4.7",
        "family": "Zhipu GLM",
        "capability_tier": CapabilityTier.MID_BALANCED,
        "tier_rank": 2,
        "upstream_provider": "Google Vertex (via OpenRouter)",
        "recommended_inter_call_delay_s": 3.0,
        "comparative_peers": ["deepseek-flash", "qwen/qwen-2.5-72b-instruct", "meta-llama/llama-3.3-70b-instruct"],
        "methodological_notes": (
            "GLM-4.7 is a Mid-Tier Balanced workhorse. Comparing it to Frontier Flagships "
            "(e.g. DeepSeek-V4-Pro, Claude-3.5-Sonnet) represents a cross-tier false equivalence. "
            "Valid comparative baselines must be drawn from Tier 2 peers or paired with GLM-5.3 if available."
        ),
    },
    "z-ai/glm-4.7-flash": {
        "display_name": "GLM-4.7-Flash",
        "family": "Zhipu GLM",
        "capability_tier": CapabilityTier.LIGHT_FAST,
        "tier_rank": 3,
        "upstream_provider": "DeepInfra (via OpenRouter)",
        "recommended_inter_call_delay_s": 1.5,
        "comparative_peers": ["google/gemini-2.0-flash-001", "anthropic/claude-3.5-haiku"],
        "methodological_notes": "High-speed Tier 3 lightweight model.",
    },
    "deepseek-flash": {
        "display_name": "DeepSeek-V4.1-Flash",
        "family": "DeepSeek",
        "capability_tier": CapabilityTier.MID_BALANCED,
        "tier_rank": 2,
        "upstream_provider": "DeepSeek First-Party API",
        "recommended_inter_call_delay_s": 1.0,
        "comparative_peers": ["z-ai/glm-4.7", "qwen/qwen-2.5-72b-instruct"],
        "methodological_notes": "Direct competitor to GLM-4.7 within Tier 2 (Mid-Tier Balanced).",
    },
    "deepseek-v4-pro": {
        "display_name": "DeepSeek-V4-Pro",
        "family": "DeepSeek",
        "capability_tier": CapabilityTier.FRONTIER_FLAGSHIP,
        "tier_rank": 1,
        "upstream_provider": "DeepSeek First-Party API",
        "recommended_inter_call_delay_s": 2.0,
        "comparative_peers": ["claude-3-5-sonnet", "gpt-4o", "z-ai/glm-5.3"],
        "methodological_notes": "Frontier Flagship (Tier 1). Symmetrically comparable only to other Frontier models.",
    },
    "google/gemini-2.0-flash-001": {
        "display_name": "Gemini 2.0 Flash",
        "family": "Google Gemini",
        "capability_tier": CapabilityTier.LIGHT_FAST,
        "tier_rank": 3,
        "upstream_provider": "Google (via OpenRouter)",
        "recommended_inter_call_delay_s": 1.0,
        "comparative_peers": ["z-ai/glm-4.7-flash", "anthropic/claude-3.5-haiku"],
        "methodological_notes": "Tier 3 Lightweight fast instruction-follower.",
    },
    "google/gemini-2.5-flash": {
        "display_name": "Gemini 2.5 Flash",
        "family": "Google Gemini",
        "capability_tier": CapabilityTier.MID_BALANCED,
        "tier_rank": 2,
        "upstream_provider": "Google Vertex (via OpenRouter)",
        "recommended_inter_call_delay_s": 0.5,
        "comparative_peers": ["z-ai/glm-4.7", "deepseek-flash", "qwen/qwen-2.5-72b-instruct"],
        "methodological_notes": (
            "Google Vertex Tier 2 Mid-Tier Balanced workhorse model with high throughput and native structured outputs. "
            "Directly comparable to GLM-4.7 and DeepSeek-Flash."
        ),
    },
    "qwen/qwen3-coder-30b-a3b-instruct": {
        "display_name": "Qwen3 Coder 30B",
        "family": "Qwen / Alibaba",
        "capability_tier": CapabilityTier.MID_BALANCED,
        "tier_rank": 2,
        "upstream_provider": "Alibaba (via OpenRouter)",
        "recommended_inter_call_delay_s": 1.0,
        "comparative_peers": ["z-ai/glm-4.7", "meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-chat"],
        "methodological_notes": "Tier 2 Mid-Tier Balanced coding MoE with 256k context. Primary open-weights distillation baseline.",
    },
    "meta-llama/llama-3.3-70b-instruct": {
        "display_name": "Llama 3.3 70B Instruct",
        "family": "Meta Llama",
        "capability_tier": CapabilityTier.MID_BALANCED,
        "tier_rank": 2,
        "upstream_provider": "Meta (via OpenRouter)",
        "recommended_inter_call_delay_s": 1.0,
        "comparative_peers": ["z-ai/glm-4.7", "qwen/qwen3-coder-30b-a3b-instruct", "deepseek/deepseek-chat"],
        "methodological_notes": "Tier 2 Mid-Tier Balanced dense 70B standard enterprise baseline.",
    },
    "deepseek/deepseek-chat": {
        "display_name": "DeepSeek-V3",
        "family": "DeepSeek",
        "capability_tier": CapabilityTier.MID_BALANCED,
        "tier_rank": 2,
        "upstream_provider": "DeepSeek (via OpenRouter)",
        "recommended_inter_call_delay_s": 1.0,
        "comparative_peers": ["z-ai/glm-4.7", "qwen/qwen3-coder-30b-a3b-instruct", "meta-llama/llama-3.3-70b-instruct"],
        "methodological_notes": "Tier 2 Mid-Tier Balanced MoE (671B total, 37B active). Direct architectural peer to GLM-4.7's 32B active MoE.",
    },
    "z-ai/glm-5.3-flash": {
        "display_name": "GLM-5.3-Flash",
        "family": "Zhipu GLM",
        "capability_tier": CapabilityTier.LIGHT_FAST,
        "tier_rank": 3,
        "upstream_provider": "Zhipu AI (via OpenRouter)",
        "recommended_inter_call_delay_s": 0.5,
        "comparative_peers": ["openai/gpt-4o-mini", "z-ai/glm-4.7-flash"],
        "methodological_notes": "Tier 3 Lightweight Fast high-throughput MoE (320B total, 18B active) with 1.3M context.",
    },
    "openai/gpt-4o-mini": {
        "display_name": "GPT-4o-mini",
        "family": "OpenAI",
        "capability_tier": CapabilityTier.LIGHT_FAST,
        "tier_rank": 3,
        "upstream_provider": "OpenAI (via OpenRouter)",
        "recommended_inter_call_delay_s": 0.5,
        "comparative_peers": ["z-ai/glm-5.3-flash", "google/gemini-2.0-flash-001"],
        "methodological_notes": "Tier 3 Lightweight Fast commercial baseline.",
    },
    "anthropic/claude-haiku-4.5": {
        "display_name": "Claude Haiku 4.5",
        "family": "Anthropic",
        "capability_tier": CapabilityTier.FRONTIER_FLAGSHIP,
        "tier_rank": 1,
        "upstream_provider": "Anthropic (via OpenRouter)",
        "recommended_inter_call_delay_s": 1.5,
        "comparative_peers": ["deepseek-v4-pro", "openai/gpt-4o"],
        "methodological_notes": "Tier 1 Frontier Flagship lightweight anchor. Frontier upper-bound audit model.",
    },
}


def classify_model(
    model_id: str,
    base_url: str = "https://openrouter.ai/api/v1",
    reasoning_effort: str = "none",
) -> ModelClassification:
    """Classify model capability tier, provider class, and peers."""
    if "api.deepseek.com" in base_url:
        provider_class = ProviderHostingClass.DIRECT_FIRST_PARTY
    elif "openrouter.ai" in base_url:
        provider_class = ProviderHostingClass.AGGREGATOR_SHARED
    else:
        provider_class = ProviderHostingClass.DIRECT_FIRST_PARTY

    reasoning_mode = "disabled" if reasoning_effort in ("none", "", None) else f"enabled({reasoning_effort})"

    meta = _TAXONOMY.get(model_id)
    if meta:
        return ModelClassification(
            model_id=model_id,
            display_name=meta["display_name"],
            family=meta["family"],
            capability_tier=meta["capability_tier"],
            tier_rank=meta["tier_rank"],
            provider_class=provider_class,
            upstream_provider=meta["upstream_provider"],
            reasoning_mode=reasoning_mode,
            recommended_inter_call_delay_s=meta["recommended_inter_call_delay_s"],
            comparative_peers=list(meta["comparative_peers"]),
            methodological_notes=meta["methodological_notes"],
        )

    return ModelClassification(
        model_id=model_id,
        display_name=model_id,
        family="Unknown",
        capability_tier=CapabilityTier.MID_BALANCED,
        tier_rank=2,
        provider_class=provider_class,
        upstream_provider="Generic / Aggregator",
        reasoning_mode=reasoning_mode,
        recommended_inter_call_delay_s=3.0,
        comparative_peers=[],
        methodological_notes="Uncataloged model evaluated as generic Tier 2.",
    )


def get_proportional_reasoning_mapping(model_id: str) -> dict[str, str]:
    """Return the normative operational reasoning mapping per model class (ADR-0006).

    Operational intent:
      - BOOTSTRAP_ANALYSIS: Defensive reasoning (untangle injections from tasks)
      - DRAFT_PROMPT / REVISE_PROMPT: Bounded pre-execution reasoning (entity preservation)
      - DRAFT_PLAN / REVISE_PLAN / EXECUTE: Zero reasoning (mechanical translation)
    """
    mid = model_id.lower()
    if "glm-4.7" in mid:
        # Class A: Native effort tiers (Zhipu GLM-4.7)
        return {
            "BOOTSTRAP_ANALYSIS": "high",
            "DRAFT_PROMPT": "low",
            "REVISE_PROMPT": "low",
            "DRAFT_PLAN": "none",
            "REVISE_PLAN": "none",
            "EXECUTE": "none",
        }
    elif "thinking" in mid or "r1" in mid or "o1" in mid or "o3" in mid or "o4" in mid:
        # Class C / Native thinking open-weights / reasoning
        return {
            "BOOTSTRAP_ANALYSIS": "high",
            "DRAFT_PROMPT": "low",
            "REVISE_PROMPT": "low",
            "DRAFT_PLAN": "none",
            "REVISE_PLAN": "none",
            "EXECUTE": "none",
        }
    else:
        # Class D: Pure instruct / quantized models (Llama 3.3, Qwen Instruct, GPT-4o-mini)
        # Native API reasoning disabled; deliberative compute provided in-band via schema.
        return {
            "BOOTSTRAP_ANALYSIS": "none",
            "DRAFT_PROMPT": "none",
            "REVISE_PROMPT": "none",
            "DRAFT_PLAN": "none",
            "REVISE_PLAN": "none",
            "EXECUTE": "none",
        }

