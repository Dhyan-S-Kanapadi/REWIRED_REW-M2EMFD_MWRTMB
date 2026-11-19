from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_both_frontends_are_served():
    for path, title in [("/chat/", "ChitMirror Chat"), ("/dashboard/", "ChitMirror Dashboard")]:
        response = client.get(path)
        assert response.status_code == 200
        assert title in response.text
        for asset in ["config.js", "app.js", "style.css"]:
            assert client.get(path + asset).status_code == 200
        if path == "/chat/":
            assert client.get(path + "api.js").status_code == 200
