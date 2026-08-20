from app.ai_provider import list_provider_models
import app.ai_provider as ap

def test_gemini_model_list(monkeypatch):
    def fake(url, headers=None, timeout=30):
        assert url.endswith("/models")
        assert headers["x-goog-api-key"] == "secret"
        return {"models":[
            {"name":"models/gemini-test","displayName":"Gemini Test","supportedGenerationMethods":["generateContent"],"inputTokenLimit":123},
            {"name":"models/embed-test","supportedGenerationMethods":["embedContent"]}
        ]}
    monkeypatch.setattr(ap, "_get_json", fake)
    rows=list_provider_models({"ai_provider":"gemini","ai_api_key":"secret","ai_base_url":""})
    assert rows == [{"id":"gemini-test","name":"Gemini Test","context_length":123}]

def test_gemini_analysis(monkeypatch):
    def fake(url, payload, headers=None, timeout=90):
        assert "models/gemini-test:generateContent" in url
        assert headers["x-goog-api-key"] == "secret"
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        return {"candidates":[{"content":{"parts":[{"text":'{"total_cost":123.45,"findings":["ok"]}'}]}}]}
    monkeypatch.setattr(ap, "_request", fake)
    out=ap.analyze_with_provider("Test", {"ai_provider":"gemini","ai_api_key":"secret","ai_model":"gemini-test","ai_base_url":""})
    assert out["total_cost"] == 123.45
    assert out["ai_provider"] == "gemini"
