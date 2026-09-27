from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)


class WireError(RuntimeError):
    """Raised when a model response violates wire syntax or schema contract.

    Attributes:
        reason: Legacy or semantic error token (e.g. 'artifact_review_kind', 'task_entities').
        operator_feedback: Formatted, field-localized description for retry correction.
        validation_error: Underlying Pydantic ValidationError if applicable.
    """

    def __init__(
        self,
        reason: str,
        *,
        operator_feedback: str | None = None,
        validation_error: ValidationError | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.operator_feedback = operator_feedback
        self.validation_error = validation_error


class ActivationRoute(str, Enum):
    APPLY_PROTOCOL = "APPLY_PROTOCOL"
    PROTOCOL_DISCUSSION = "PROTOCOL_DISCUSSION"
    BYPASS = "BYPASS"
    BLOCKED_BY_HIGHER_PRIORITY = "BLOCKED_BY_HIGHER_PRIORITY"


class ActivationDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: ActivationRoute
    response: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_route_constraints(self) -> ActivationDecisionPayload:
        if self.route == ActivationRoute.BLOCKED_BY_HIGHER_PRIORITY:
            if not self.response or not self.response.strip():
                raise ValueError("blocked_response: response must be non-empty when route is BLOCKED_BY_HIGHER_PRIORITY")
        else:
            if self.response is not None:
                raise ValueError("extra_fields: response is not permitted unless route is BLOCKED_BY_HIGHER_PRIORITY")
        return self


class BootstrapAnalysisData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ANALYSIS"] = "ANALYSIS"
    task_summary: str
    approach_notes: str
    risk_notes: str
    task_entities: list[str]

    @model_validator(mode="after")
    def validate_non_empty(self) -> BootstrapAnalysisData:
        if not self.task_summary.strip():
            raise ValueError("bootstrap_task_summary: task_summary must not be empty")
        return self


class BootstrapBlockedData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["BLOCKED_BY_HIGHER_PRIORITY"] = "BLOCKED_BY_HIGHER_PRIORITY"
    response: str

    @model_validator(mode="after")
    def validate_non_empty(self) -> BootstrapBlockedData:
        if not self.response.strip():
            raise ValueError("blocked_response: response must not be empty")
        return self


BootstrapAnalysisPayload = Annotated[
    Union[BootstrapAnalysisData, BootstrapBlockedData],
    Field(discriminator="kind"),
]


_PDL05_FIELDED_SCHEMA_PATTERN = re.compile(
    r"(?:^\s*(?:TASK|OUTPUT|INCLUDE|INPUT|CONSTRAINTS?|REQUIREMENTS?|ACTION|RESULT|STATUS|GOAL|OBJECTIVE)\s*:|(?<=\S)\s+(?:OUTPUT|INCLUDE|INPUT|ACTION|RESULT|STATUS)\s*:)",
    re.IGNORECASE | re.MULTILINE,
)

_PDL08_META_RULE_PATTERN = re.compile(
    r"(?i)\b(?:(?:do not|never)\s+(?:perform|execute|calculate|compute|solve|partition|do)\s+(?:any\s+|the\s+)?(?:computation|work|calculation|partitioning|task)|(?:only\s+describe|describe\s+only)\s+(?:the\s+)?(?:required\s+)?(?:task|result|output|deliverable)|without\s+performing\s+any\s+(?:computation|work|calculation|selection|partitioning)|no\s+(?:actual|algorithmic|substantive)\s+(?:computation|work|calculation)|defer\s+(?:all\s+)?computation\s+to\s+(?:the\s+)?execution\s+stage)\b"
)

_PLAN_PLACEHOLDER_PATTERN = re.compile(
    r"(?i)(?:INSERT\s+placeholders?\s+for\s+(?:the\s+)?substantive\s+results?|placeholders?\s+without\s+performing\s+any\s+computation|\b(?:do not|never)\s+(?:perform|execute|calculate|compute|solve)\s+(?:any\s+)?(?:computation|work|calculation)\b|without\s+performing\s+any\s+(?:computation|work|calculation))"
)


def validate_prompt_pdl_conformance(body: str) -> str:
    """Validate prompt_body conforms to PDL-01..08, PROMPT-01..05."""
    if not body or not body.strip():
        raise ValueError("prompt_body: prompt_body must not be empty")

    fielded_match = _PDL05_FIELDED_SCHEMA_PATTERN.search(body)
    if fielded_match:
        matched_str = fielded_match.group(0).strip()
        raise ValueError(
            f"prompt_body violates PDL-05 by inventing fielded schema prefix '{matched_str}'. "
            "Express steps directly in Structured English with uppercase action verbs (e.g. 'PARTITION the string...', 'RETURN the result')."
        )

    meta_match = _PDL08_META_RULE_PATTERN.search(body)
    if meta_match:
        matched_str = meta_match.group(0).strip()
        raise ValueError(
            f"prompt_body violates PDL-08 / PROMPT-01 by containing drafting meta-rule or execution prohibition '{matched_str}'. "
            "Prompt Pseudocode defines what execution must deliver, never negative execution constraints."
        )
    return body


def validate_plan_pdl_conformance(body: str) -> str:
    """Validate neutral_plan_body conforms to PDL-01..08, PLAN-01..10."""
    if not body or not body.strip():
        raise ValueError("neutral_plan_body: neutral_plan_body must not be empty")

    placeholder_match = _PLAN_PLACEHOLDER_PATTERN.search(body)
    if placeholder_match:
        matched_str = placeholder_match.group(0).strip()
        raise ValueError(
            f"neutral_plan_body violates PLAN-04 / PLAN-10 by containing placeholder step or meta-prohibition '{matched_str}'. "
            "Plan the high-level steps to solve and deliver the result upon execution."
        )
    return body


class PromptDraftData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["PROMPT"] = "PROMPT"
    prompt_body: str
    approach_handoff: Literal["NONE", "CARRY_SOURCE_TO_PLAN"] = "NONE"
    task_entities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_body(self) -> PromptDraftData:
        validate_prompt_pdl_conformance(self.prompt_body)
        return self


class PromptDraftBlockedData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["TASK_BLOCKED_BY_HIGHER_PRIORITY"] = "TASK_BLOCKED_BY_HIGHER_PRIORITY"
    blocking_basis: Literal["PROVIDER_PLATFORM_SAFETY_PRIVACY_PERMISSION_OR_TOOL"]
    response: str

    @model_validator(mode="after")
    def validate_response(self) -> PromptDraftBlockedData:
        if not self.response.strip():
            raise ValueError("blocked_response: response must not be empty")
        return self


PromptDraftPayload = Annotated[
    Union[PromptDraftData, PromptDraftBlockedData],
    Field(discriminator="kind"),
]


class PromptBodyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_body: str

    @model_validator(mode="after")
    def validate_body(self) -> PromptBodyPayload:
        validate_prompt_pdl_conformance(self.prompt_body)
        return self


class NeutralPlanBodyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    neutral_plan_body: str

    @model_validator(mode="after")
    def validate_body(self) -> NeutralPlanBodyPayload:
        validate_plan_pdl_conformance(self.neutral_plan_body)
        return self


class ProtocolDiscussionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str

    @model_validator(mode="after")
    def validate_body(self) -> ProtocolDiscussionPayload:
        if not self.body.strip():
            raise ValueError("protocol_body: body must not be empty")
        return self


class TaskChangeDimension(str, Enum):
    ACTION_SUBJECT_OR_OBJECT = "ACTION_SUBJECT_OR_OBJECT"
    SCOPE_CONSTRAINT_EXCLUSION_OR_PRIORITY = "SCOPE_CONSTRAINT_EXCLUSION_OR_PRIORITY"
    TIME_FRESHNESS_QUANTITY_OR_CONDITION = "TIME_FRESHNESS_QUANTITY_OR_CONDITION"
    COMPARISON_CRITERION_DEFINITION_OR_RELATIONSHIP = "COMPARISON_CRITERION_DEFINITION_OR_RELATIONSHIP"
    AUDIENCE_OR_OUTPUT_CHARACTERISTIC = "AUDIENCE_OR_OUTPUT_CHARACTERISTIC"
    REQUIRED_CONCLUSION = "REQUIRED_CONCLUSION"
    OTHER_TASK_OR_RESULT = "OTHER_TASK_OR_RESULT"


class ApproachChangeDimension(str, Enum):
    RESEARCH_OR_EVIDENCE_SELECTION_METHOD = "RESEARCH_OR_EVIDENCE_SELECTION_METHOD"
    COMPARISON_RANKING_OR_SCORING_METHOD = "COMPARISON_RANKING_OR_SCORING_METHOD"
    ANALYSIS_ORDER = "ANALYSIS_ORDER"
    JUSTIFICATION_PROCEDURE = "JUSTIFICATION_PROCEDURE"
    OTHER_RESPONSE_PROCEDURE = "OTHER_RESPONSE_PROCEDURE"


SYSTEM1_CONFIDENCE_FLOOR: float = 0.85


class ReviewFactsData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["REVIEW_FACTS"] = "REVIEW_FACTS"
    task_change_dimensions: list[TaskChangeDimension]
    approach_change_dimensions: list[ApproachChangeDimension]
    progression_requested: bool
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_deduplication(self) -> ReviewFactsData:
        if len(self.task_change_dimensions) != len(set(self.task_change_dimensions)):
            raise ValueError("task_change_dimensions: duplicates not allowed")
        if len(self.approach_change_dimensions) != len(set(self.approach_change_dimensions)):
            raise ValueError("approach_change_dimensions: duplicates not allowed")
        return self


class ReviewSpecialData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "NEW_TASK",
        "CANCEL",
        "PROTOCOL_DISCUSSION",
        "SUBSTANTIVE_DISCUSSION",
        "UNRESOLVED",
    ]
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


ArtifactReviewPayload = Annotated[
    Union[ReviewFactsData, ReviewSpecialData],
    Field(discriminator="kind"),
]


class ExecutionInputReviseData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["REVISE_TASK"] = "REVISE_TASK"
    also_changes_approach: bool
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ExecutionInputSpecialData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["SUPPLY_EXECUTION_INPUT", "NEW_TASK", "CANCEL", "UNRESOLVED"]
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


ExecutionInputPayload = Annotated[
    Union[ExecutionInputReviseData, ExecutionInputSpecialData],
    Field(discriminator="kind"),
]


class ExecutionDraftBlockedData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["BLOCKED_BY_HIGHER_PRIORITY"] = "BLOCKED_BY_HIGHER_PRIORITY"
    brief_body: str

    @model_validator(mode="after")
    def validate_body(self) -> ExecutionDraftBlockedData:
        if not self.brief_body.strip():
            raise ValueError("execution_draft_body: brief_body must not be empty")
        return self


class ExecutionDraftResultData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["RESULT"] = "RESULT"
    brief_body: str
    execution_entities: list[Union[dict[str, Any], str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_body(self) -> ExecutionDraftResultData:
        if not self.brief_body.strip():
            raise ValueError("execution_draft_body: brief_body must not be empty")
        return self


ExecutionDraftPayload = Annotated[
    Union[ExecutionDraftBlockedData, ExecutionDraftResultData],
    Field(discriminator="kind"),
]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: str
    section: Optional[str] = None
    observed: Optional[str] = None


class PositiveWitness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polarity: Literal["positive"] = "positive"
    evidence: Evidence = Field(default_factory=lambda: Evidence(path="execution://witness"))
    data: dict[str, Any]


class NegativeWitness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polarity: Literal["negative"] = "negative"
    evidence: Evidence = Field(default_factory=lambda: Evidence(path="execution://witness"))
    search_exhausted: bool
    nodes_explored: int
    method: str


WitnessPayload = Union[PositiveWitness, NegativeWitness]


class FileItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    filename: str
    satisfies: list[str] = Field(default_factory=list)
    evidence: Evidence


class ReconciliationItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    requirement: str
    status: Literal["satisfied", "partial", "open"]
    evidence: Evidence


class DefectItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    description: str
    evidence: Evidence


class ResultIRData(BaseModel):
    model_config = ConfigDict(extra="allow")
    files: list[FileItem] = Field(default_factory=list)
    reconciliation: list[ReconciliationItem] = Field(default_factory=list)
    open_defects: list[DefectItem] = Field(default_factory=list)
    witness: Optional[Union[PositiveWitness, NegativeWitness]] = None


class ResultIRRepairPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_ir: ResultIRData


class ExecutionRequestInputData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["REQUEST_INPUT"] = "REQUEST_INPUT"
    body: str
    expected_type: str
    description: str

    @model_validator(mode="after")
    def validate_fields(self) -> ExecutionRequestInputData:
        if not self.body.strip():
            raise ValueError("execution_body: body must not be empty")
        if not self.expected_type.strip():
            raise ValueError("execution_expected_type: expected_type must not be empty")
        if not self.description.strip():
            raise ValueError("execution_description: description must not be empty")
        return self


class ExecutionResultData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["RESULT", "BLOCKED_BY_HIGHER_PRIORITY"]
    body: str
    result_ir: Optional[ResultIRData] = None

    @model_validator(mode="after")
    def validate_fields(self) -> ExecutionResultData:
        if not self.body.strip():
            raise ValueError("execution_body: body must not be empty")
        return self


ExecutionOutcomePayload = Annotated[
    Union[ExecutionRequestInputData, ExecutionResultData],
    Field(discriminator="kind"),
]


OPERATION_PAYLOAD_MODELS: dict[str, Any] = {
    "INTERPRET_ACTIVATION": ActivationDecisionPayload,
    "BOOTSTRAP_ANALYSIS": BootstrapAnalysisPayload,
    "DRAFT_PROMPT": PromptDraftPayload,
    "DRAFT_PLAN": NeutralPlanBodyPayload,
    "REVISE_PROMPT": PromptBodyPayload,
    "REVISE_PLAN": NeutralPlanBodyPayload,
    "INTERPRET_PROMPT_REVIEW": ArtifactReviewPayload,
    "INTERPRET_PLAN_REVIEW": ArtifactReviewPayload,
    "INTERPRET_EXECUTION_INPUT": ExecutionInputPayload,
    "ANSWER_PROTOCOL_DISCUSSION": ProtocolDiscussionPayload,
    "DRAFT_EXECUTION": ExecutionDraftPayload,
    "EMIT_RESULT_IR": ResultIRRepairPayload,
    "EXECUTE": ExecutionOutcomePayload,
}


def get_operation_pydantic_schema(operation: str) -> dict[str, Any] | None:
    """Derive strict JSON Schema for an operation from its Pydantic payload model."""
    model_or_adapter = OPERATION_PAYLOAD_MODELS.get(operation)
    if model_or_adapter is None:
        return None
    adapter = TypeAdapter(model_or_adapter)
    return adapter.json_schema()


def format_validation_feedback(val_err: ValidationError) -> str:
    """Format Pydantic ValidationError into precise operator feedback."""
    parts: list[str] = []
    strip_tags = {
        "ANALYSIS",
        "PROMPT",
        "BLOCKED_BY_HIGHER_PRIORITY",
        "TASK_BLOCKED_BY_HIGHER_PRIORITY",
        "REVIEW_FACTS",
        "REVISE_TASK",
        "RESULT",
        "REQUEST_INPUT",
    }
    for err in val_err.errors():
        clean_loc = [str(p) for p in err.get("loc", ()) if str(p) not in strip_tags]
        loc = ".".join(clean_loc) or "root"
        msg = err.get("msg", "invalid")
        # Strip internal Pydantic prefixes if present
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        parts.append(f"field '{loc}': {msg}")
    return "Validation failed on " + "; ".join(parts)


def map_validation_error_to_wire_reason(
    operation: str,
    val_err: ValidationError,
    raw_dict: dict[str, Any] | None = None,
) -> str:
    """Map Pydantic ValidationError to a canonical WireError reason token."""
    errors = val_err.errors()
    if not errors:
        return "schema_violation"

    # Prioritize union tag / discriminator failures
    for e in errors:
        loc = tuple(str(x) for x in e.get("loc", ()))
        err_type = e.get("type", "")
        msg = e.get("msg", "")

        if "union_tag_invalid" in err_type or (loc and loc[-1] == "kind") or "discriminator" in msg:
            if operation in {"INTERPRET_PROMPT_REVIEW", "INTERPRET_PLAN_REVIEW"}:
                return "artifact_review_kind"
            if operation == "BOOTSTRAP_ANALYSIS":
                return "bootstrap_kind"
            if operation == "DRAFT_PROMPT":
                return "prompt_draft_kind"
            if operation == "INTERPRET_EXECUTION_INPUT":
                return "execution_input_kind"
            if operation == "DRAFT_EXECUTION":
                return "execution_draft_kind"
            if operation == "EXECUTE":
                return "execution_kind"

        if err_type == "extra_forbidden" or "extra_fields" in msg:
            return "extra_fields"

    # Next check if any error is missing_fields
    for e in errors:
        if e.get("type") == "missing":
            return "missing_fields"

    # Inspect first error details
    first = errors[0]
    loc = tuple(str(x) for x in first.get("loc", ()))
    msg = first.get("msg", "")

    if "task_change_dimensions" in loc or "task_change_dimensions" in msg:
        return "task_change_dimensions"
    if "approach_change_dimensions" in loc or "approach_change_dimensions" in msg:
        return "approach_change_dimensions"
    if "progression_requested" in loc or "progression_requested" in msg:
        return "progression_requested"
    if "task_entities" in loc or "task_entities" in msg:
        return "bootstrap_task_entities" if operation == "BOOTSTRAP_ANALYSIS" else "task_entities"
    if "task_summary" in loc or "task_summary" in msg:
        return "bootstrap_task_summary"
    if "approach_notes" in loc or "approach_notes" in msg:
        return "bootstrap_approach_notes"
    if "risk_notes" in loc or "risk_notes" in msg:
        return "bootstrap_risk_notes"
    if "route" in loc:
        return "activation_route"
    if "response" in loc or "blocked_response" in msg:
        return "blocked_response"
    if "prompt_body" in loc or "prompt_body" in msg:
        if "PDL-05" in msg or "fielded" in msg:
            return "prompt_pdl_field_schema_prohibited"
        if "PDL-08" in msg or "PROMPT-01" in msg or "meta-rule" in msg or "prohibition" in msg:
            return "prompt_pdl_meta_rule_bleed"
        return "prompt_body"
    if "neutral_plan_body" in loc or "neutral_plan_body" in msg:
        if "PLAN-04" in msg or "PLAN-10" in msg or "placeholder" in msg or "prohibition" in msg:
            return "plan_pdl_placeholder_bleed"
        return "neutral_plan_body"
    if "body" in loc or "body" in msg:
        return "protocol_body" if operation == "ANSWER_PROTOCOL_DISCUSSION" else "execution_body"
    if "approach_handoff" in loc or "approach_handoff" in msg:
        return "approach_handoff"
    if "blocking_basis" in loc or "blocking_basis" in msg:
        return "blocking_basis"
    if "also_changes_approach" in loc or "also_changes_approach" in msg:
        return "execution_input_also_changes_approach"
    if "brief_body" in loc or "brief_body" in msg:
        return "execution_draft_body"
    if "execution_entities" in loc or "execution_entities" in msg:
        return "execution_draft_entities"
    if "expected_type" in loc or "expected_type" in msg:
        return "execution_expected_type"
    if "description" in loc or "description" in msg:
        return "execution_description"
    if "result_ir" in loc or "result_ir" in msg:
        for leaf in ("files", "reconciliation", "open_defects", "witness"):
            if leaf in loc or leaf in msg:
                prefix = "result_ir_repair" if operation == "EMIT_RESULT_IR" else "execution_result_ir"
                return f"{prefix}_{leaf}"
        prefix = "result_ir_repair" if operation == "EMIT_RESULT_IR" else "execution_result_ir"
        return f"{prefix}_shape"

    if "extra_fields" in msg:
        return "extra_fields"
    if "missing_fields" in msg:
        return "missing_fields"
    if "blocked_response" in msg:
        return "blocked_response"

    return "schema_violation"

