from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Dict, Any

class Source(BaseModel):
    """
    Represents a citation or a reference to a data source used by an agent
    to substantiate its findings.
    """
    document_name: str = Field(
        ..., 
        description="The name of the source document, dataset, or file."
    )
    section: Optional[str] = Field(
        None, 
        description="The specific section, clause, paragraph, or page in the document."
    )
    snippet: Optional[str] = Field(
        None, 
        description="The exact text snippet or data retrieved from the source."
    )
    uri: Optional[str] = Field(
        None, 
        description="A URI, link, or reference pointing directly to the source."
    )

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True
    )


class Confidence(BaseModel):
    """
    Represents a numeric confidence score (0.0 to 1.0) for a given claim
    along with its qualitative reasoning.
    """
    score: float = Field(
        ..., 
        description="The numeric confidence score, strictly between 0.0 (no confidence) and 1.0 (absolute confidence)."
    )
    rationale: str = Field(
        ..., 
        description="The reasoning or justification supporting the confidence score."
    )

    model_config = ConfigDict(
        str_strip_whitespace=True
    )

    @field_validator("score")
    @classmethod
    def validate_score_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence score must be strictly between 0.0 and 1.0 inclusive.")
        return v


class AgentError(BaseModel):
    """
    Represents a structured error encountered during agent execution,
    used to distinguish execution failures from valid low-confidence findings.
    """
    agent_name: str = Field(
        ..., 
        description="The name of the agent that encountered the execution error."
    )
    error_code: str = Field(
        ..., 
        description="A machine-readable unique code identifying the error type (e.g., 'API_TIMEOUT', 'PARSING_ERROR')."
    )
    message: str = Field(
        ..., 
        description="A detailed human-readable message describing what went wrong."
    )
    details: Optional[Dict[str, Any]] = Field(
        None, 
        description="Optional dictionary containing extra structured troubleshooting metadata."
    )

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True
    )


class AgentInput(BaseModel):
    """
    Base Pydantic model for all agent inputs within the GridPilot swarm.
    Forces strict spelling discipline by forbidding extra fields.
    """
    project_id: str = Field(
        ..., 
        description="The unique UUID string representing the Renewable Interconnection project."
    )
    study_id: str = Field(
        ..., 
        description="The unique UUID string representing the active study run."
    )

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True
    )


class AgentOutput(BaseModel):
    """
    Base Pydantic model for all agent outputs within the GridPilot swarm.
    Ensures every agent output carries confidence scores, data sources,
    and a raw audit trail.
    """
    confidence: float = Field(
        ..., 
        description="The agent's confidence score (0.0 to 1.0) for its findings."
    )
    sources: List[Source] = Field(
        default_factory=list, 
        description="A list of references or citations to data sources substantiating the findings."
    )
    assumptions: List[str] = Field(
        default_factory=list, 
        description="A list of explicit assumptions made by the agent during the run."
    )
    raw_model_output: str = Field(
        ..., 
        description="The raw LLM completion string stored for immutable auditing and debugging."
    )

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence score must be strictly between 0.0 and 1.0 inclusive.")
        return v
