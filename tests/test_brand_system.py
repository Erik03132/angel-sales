import json, tempfile, os
from agent.brand_system import BrandSystem, DesignToken, load_brand, INCUBIRD_DEFAULT

def test_brand_system_creation():
    brand = BrandSystem(
        name="Test",
        theme="dark",
        colors=[DesignToken(name="Void", value="#08090a", token="--color-void", role="Canvas")],
        typography={"font": "Inter"},
        spacing={"base": 4},
        components={"button": {"radius": 6}},
        guidelines=["Do use Inter"],
    )
    assert brand.name == "Test"
    assert brand.theme == "dark"
    assert brand.colors[0].name == "Void"

def test_incubird_default_exists():
    assert INCUBIRD_DEFAULT is not None
    assert INCUBIRD_DEFAULT.name == "IncuBird"

def test_load_brand():
    data = {
        "name": "Custom",
        "theme": "light",
        "colors": [],
        "typography": {},
        "spacing": {},
        "components": {},
        "guidelines": [],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        brand = load_brand(path)
        assert brand.name == "Custom"
    finally:
        os.unlink(path)

def test_brand_to_dict():
    brand = BrandSystem(name="Test", theme="light", colors=[], typography={}, spacing={}, components={}, guidelines=[])
    d = brand.to_dict()
    assert d["name"] == "Test"
