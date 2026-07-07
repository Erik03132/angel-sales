from agent.component_generator import generate_component, COMPONENT_TYPES
from agent.brand_system import INCUBIRD_DEFAULT

def test_component_types():
    assert "button" in COMPONENT_TYPES
    assert "card" in COMPONENT_TYPES
    assert "hero" in COMPONENT_TYPES
    assert "nav" in COMPONENT_TYPES
    assert len(COMPONENT_TYPES) >= 10

def test_generate_component_no_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    result = generate_component("button", "Primary CTA button", INCUBIRD_DEFAULT)
    assert result is not None
    assert "button" in result.lower()

def test_generate_component_returns_html():
    result = generate_component("card", "Feature card with icon, title, description", INCUBIRD_DEFAULT)
    assert result is not None
    assert isinstance(result, str)
