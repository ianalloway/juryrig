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
from .atlas import (
    ContrarianRate,
    DisagreementAtlas,
    ItemDisagreement,
    SplitCluster,
    disagreement_atlas,
    disagreement_atlas_from_report,
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

__version__ = "0.3.0"

__all__ = [
    "AgreementMatrixReport",
    "AgreementThresholds",
    "AuditSuiteReport",
    "ConsistencyReport",
    "ContrarianRate",
    "DEFAULT_AGREEMENT_THRESHOLDS",
    "DEFAULT_THRESHOLDS",
    "DisagreementAtlas",
    "ItemDisagreement",
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
    "SplitCluster",
    "Thresholds",
    "VerbosityBiasReport",
    "agreement_matrix",
    "audit_suite",
    "brier_score",
    "cohen_kappa",
    "disagreement_atlas",
    "disagreement_atlas_from_report",
    "expected_calibration_error",
    "position_bias",
    "prompt_injection_bias",
    "reliability_table",
    "self_consistency",
    "verbosity_bias",
]
