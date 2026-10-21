"""Every API route and the WebSocket need the per-launch token (see jarvis/server.py)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from jarvis import server

# no `with`: lifespan (collectors, whisper, token file) is not started
client = TestClient(server.app)


def test_health_is_open():
    assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("method,path", [("get", "/api/snapshot"), ("get", "/api/alerts"), ("post", "/api/refresh"),
                                         ("post", "/api/ask"), ("post", "/api/tts"), ("post", "/api/brain/reset")])
def test_api_rejects_missing_or_wrong_token(method, path):
    assert getattr(client, method)(path).status_code == 403
    assert getattr(client, method)(path, headers={"X-Jarvis-Token": "guess"}).status_code == 403


def test_api_accepts_the_token():
    r = client.get("/api/snapshot", headers={"X-Jarvis-Token": server.TOKEN})
    assert r.status_code == 200 and "alerts" in r.json()


def test_preflight_is_not_blocked_by_the_token_check():
    r = client.options("/api/ask", headers={"Origin": "null", "Access-Control-Request-Method": "POST",
                                            "Access-Control-Request-Headers": "x-jarvis-token,content-type"})
    assert r.status_code == 200


def test_websocket_requires_the_token():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/events"):
            pass
    with client.websocket_connect(f"/ws/events?token={server.TOKEN}") as ws:
        assert "alerts" in ws.receive_json()


def test_token_file_location_and_contents(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_TOKEN_FILE", str(tmp_path / "t" / "session.token"))
    p = server.token_path()
    assert p == tmp_path / "t" / "session.token"
    server.write_token(p, "abc")
    server.write_token(p, "def")          # truncates, never appends
    assert p.read_text(encoding="utf-8") == "def"
    monkeypatch.delenv("JARVIS_TOKEN_FILE")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert server.token_path() == tmp_path / "jarvis" / "session.token"
