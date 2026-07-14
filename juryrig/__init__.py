"""juryrig — audit your LLM judges before you trust them.

Provider-backed judges (AnthropicJudge, OpenAIJudge) are not exported here;
import them explicitly from `juryrig.providers` when you need a live API.
"""

from .audits import (
    ConsistencyReport,
    PositionBiasReport,
    PromptInjectionReport,
    VerbosityBiasReport,
    position_bias,
    prompt_injection_bias,
    self_consistency,
    verbosity_bias,
)
from .calibration import brier_score, expected_calibration_error, reliability_table
from .judge import Judge, Judgment, MockJudge, PairwiseJudge
from .panel import Panel, PanelReport

__version__ = "0.1.0"

__all__ = [
    "ConsistencyReport",
    "Judge",
    "Judgment",
    "MockJudge",
    "PairwiseJudge",
    "Panel",
    "PanelReport",
    "PositionBiasReport",
    "PromptInjectionReport",
    "VerbosityBiasReport",
    "brier_score",
    "expected_calibration_error",
    "position_bias",
    "prompt_injection_bias",
    "reliability_table",
    "self_consistency",
    "verbosity_bias",
]
