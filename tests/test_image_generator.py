from agent.image_generator import leonardo_generate, download_image

def test_leonardo_generate_no_key(monkeypatch):
    monkeypatch.setenv("LEONARDO_API_KEY", "")
    result = leonardo_generate("test prompt")
    assert result is None
