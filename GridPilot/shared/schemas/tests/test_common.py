import pytest
from pydantic import ValidationError
from shared.schemas.common import Source, Confidence, AgentError, AgentInput, AgentOutput

def test_source_model_valid():
    """Verify that a valid Source instance initializes correctly."""
    source = Source(
        document_name="FERC Order 2023",
        section="Section II.A.1",
        snippet="interconnection cluster study process...",
        uri="https://www.ferc.gov/order-2023"
    )
    assert source.document_name == "FERC Order 2023"
    assert source.section == "Section II.A.1"
    assert source.snippet == "interconnection cluster study process..."
    assert source.uri == "https://www.ferc.gov/order-2023"

def test_source_model_optional_fields():
    """Verify that Source works with only required fields and strips whitespace."""
    source = Source(document_name="  NWI Wetlands Map  ")
    assert source.document_name == "NWI Wetlands Map"
    assert source.section is None
    assert source.snippet is None
    assert source.uri is None

def test_source_model_missing_required():
    """Verify that Source raises validation error if document_name is missing."""
    with pytest.raises(ValidationError):
        Source()

def test_confidence_model_valid():
    """Verify that valid Confidence instances initialize correctly."""
    conf1 = Confidence(score=0.0, rationale="No data available")
    conf2 = Confidence(score=1.0, rationale="Direct match found")
    conf3 = Confidence(score=0.75, rationale="Calculated probability")
    
    assert conf1.score == 0.0
    assert conf2.score == 1.0
    assert conf3.score == 0.75

def test_confidence_model_invalid_range():
    """Verify that Confidence rejects scores outside [0.0, 1.0] range."""
    # Under limit
    with pytest.raises(ValidationError) as exc_info:
        Confidence(score=-0.1, rationale="Negative confidence")
    assert "strictly between 0.0 and 1.0 inclusive" in str(exc_info.value)

    # Over limit
    with pytest.raises(ValidationError) as exc_info:
        Confidence(score=1.01, rationale="Too high confidence")
    assert "strictly between 0.0 and 1.0 inclusive" in str(exc_info.value)

def test_agent_error_model_valid():
    """Verify that AgentError initializes properly."""
    err = AgentError(
        agent_name="RegulatoryAgent",
        error_code="API_TIMEOUT",
        message="Failed to contact DashScope API after 3 attempts.",
        details={"attempt_count": 3}
    )
    assert err.agent_name == "RegulatoryAgent"
    assert err.error_code == "API_TIMEOUT"
    assert err.details == {"attempt_count": 3}

def test_agent_input_model_valid():
    """Verify that AgentInput enforces required fields."""
    inp = AgentInput(project_id="proj-123", study_id="study-456")
    assert inp.project_id == "proj-123"
    assert inp.study_id == "study-456"

def test_agent_input_model_forbids_extra():
    """Verify that AgentInput forbids extra parameters to prevent spelling errors."""
    with pytest.raises(ValidationError) as exc_info:
        AgentInput(
            project_id="proj-123", 
            study_id="study-456", 
            extra_field="spelling_error"
        )
    assert "Extra inputs are not permitted" in str(exc_info.value)

def test_agent_output_model_valid():
    """Verify that AgentOutput accepts valid configurations."""
    out = AgentOutput(
        confidence=0.9,
        sources=[Source(document_name="NWI")],
        assumptions=["Wetland buffer is 100ft"],
        raw_model_output="LLM raw text"
    )
    assert out.confidence == 0.9
    assert len(out.sources) == 1
    assert out.assumptions == ["Wetland buffer is 100ft"]
    assert out.raw_model_output == "LLM raw text"

def test_agent_output_model_invalid_confidence():
    """Verify that AgentOutput enforces confidence bounds."""
    with pytest.raises(ValidationError):
        AgentOutput(
            confidence=1.5,
            sources=[],
            assumptions=[],
            raw_model_output="test"
        )

def test_agent_output_model_ignores_extra():
    """Verify that AgentOutput allows downstream models to add fields safely (ignores extra)."""
    out = AgentOutput(
        confidence=0.8,
        raw_model_output="LLM raw text",
        downstream_extra_field="ignored"
    )
    assert out.confidence == 0.8
