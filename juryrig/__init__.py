"""juryrig — audit your LLM judges before you trust them.

Provider-backed judges (AnthropicJudge, OpenAIJudge) and `HttpJudge` are
not exported here; import them explicitly from `juryrig.providers` /
`juryrig.http_judge` when you need a live API.
"""

from .agreement import (
    DEFAULT_AGREEMENT_THRESHOLDS,
    AgreementMatrixReport,
    AgreementThresholds,
    PairAgreement,
    agreement_matrix,
    cohen_kappa,
)
from .audits import (
    DEFAULT_THRESHOLDS,
    ConsistencyReport,
    PositionBiasReport,
    PromptInjectionReport,
    Thresholds,
    VerbosityBiasReport,
    position_bias,
    prompt_injection_bias,
    self_consistency,
    verbosity_bias,
)
from .calibration import brier_score, expected_calibration_error, reliability_table
from .judge import Judge, Judgment, MockJudge, PairwiseJudge
from .panel import Panel, PanelReport, PanelVerdict
from .suite import AuditSuiteReport, audit_suite

__version__ = "0.2.2"

__all__ = [
    "AgreementMatrixReport",
    "AgreementThresholds",
    "AuditSuiteReport",
    "ConsistencyReport",
    "DEFAULT_AGREEMENT_THRESHOLDS",
    "DEFAULT_THRESHOLDS",
    "Judge",
    "Judgment",
    "MockJudge",
    "PairAgreement",
    "PairwiseJudge",
    "Panel",
    "PanelReport",
    "PanelVerdict",
    "PositionBiasReport",
    "PromptInjectionReport",
    "Thresholds",
    "VerbosityBiasReport",
    "agreement_matrix",
    "audit_suite",
    "brier_score",
    "cohen_kappa",
    "expected_calibration_error",
    "position_bias",
    "prompt_injection_bias",
    "reliability_table",
    "self_consistency",
    "verbosity_bias",
]
