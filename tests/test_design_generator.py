from agent.design_generator import generate_design_md, render_design_md
from agent.brand_system import BrandSystem, DesignToken

def test_render_design_md_minimal():
    brand = BrandSystem(name="Test", theme="dark", colors=[], typography={}, spacing={}, components={}, guidelines=[])
    md = render_design_md(brand)
    assert "# Test" in md
    assert "dark" in md
    assert "## Tokens — Colors" in md

def test_render_design_md_with_colors():
    brand = BrandSystem(
        name="ColorTest", theme="light",
        colors=[DesignToken("Red", "#ff0000", "--color-red", "Primary")],
        typography={}, spacing={}, components={}, guidelines=[],
    )
    md = render_design_md(brand)
    assert "#ff0000" in md
    assert "--color-red" in md

def test_generate_design_md_no_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    result = generate_design_md("modern brand")
    assert result is None
