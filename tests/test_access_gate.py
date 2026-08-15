from fastapi.testclient import TestClient

from resume_agent.api.app import create_app


def test_access_code_gates_app(tmp_path):
    app = create_app(tmp_path / "app.db", access_code="secret")
    with TestClient(app) as client:
        blocked = client.get("/")
        assert blocked.status_code == 401
        assert "访问口令" in blocked.text

        wrong = client.post("/login", data={"code": "wrong"})
        assert wrong.status_code == 401
        assert "口令不正确" in wrong.text

        ok = client.post("/login", data={"code": "secret"}, follow_redirects=False)
        assert ok.status_code == 303
        assert ok.cookies.get("resumeagent_access") == "secret"

        client.cookies.set("resumeagent_access", "secret")
        assert client.get("/").status_code == 200

        # 健康检查放行
        assert client.get("/health").status_code == 200


def test_access_gate_open_by_default(tmp_path):
    app = create_app(tmp_path / "app.db", access_code="")
    with TestClient(app) as client:
        assert client.get("/").status_code == 200


def test_access_gate_query_param(tmp_path):
    app = create_app(tmp_path / "app.db", access_code="secret")
    with TestClient(app) as client:
        assert client.get("/?code=secret").status_code == 200
