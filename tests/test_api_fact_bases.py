from fastapi.testclient import TestClient

from resume_agent.api.app import create_app


def make_client(tmp_path):
    return TestClient(create_app(tmp_path / "resume-agent.db"))


def test_health_endpoint(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_fetch_fact_base(tmp_path):
    with make_client(tmp_path) as client:
        created = client.post(
            "/fact-bases",
            json={
                "target": {
                    "role": "Data Analyst",
                    "country": "Japan",
                    "languages": ["ja", "en"],
                }
            },
        )
        fetched = client.get(f"/fact-bases/{created.json()['id']}")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json()["target"]["role"] == "Data Analyst"


def test_add_experience_increments_revision_and_persists(tmp_path):
    with make_client(tmp_path) as client:
        base = client.post("/fact-bases", json={}).json()
        response = client.post(
            f"/fact-bases/{base['id']}/experiences",
            json={"organization": "Yunshu", "role": "Data Analyst"},
        )
        fetched = client.get(f"/fact-bases/{base['id']}")

    assert response.status_code == 201
    assert response.json()["revision"] == 1
    assert response.json()["experiences"][0]["organization"] == "Yunshu"
    assert fetched.json()["revision"] == 1


def test_unknown_fact_base_returns_404(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get(
            "/fact-bases/00000000-0000-0000-0000-000000000000"
        )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_update_education_and_certifications(tmp_path):
    with make_client(tmp_path) as client:
        base = client.post("/fact-bases", json={}).json()

        response = client.put(
            f"/fact-bases/{base['id']}/education",
            json={"education": [
                {"school": "復旦大学", "major": "経済学", "start": "2020-09", "end": "2024-06"}
            ]},
        )
        assert response.status_code == 200
        assert response.json()["education"][0]["school"] == "復旦大学"
        assert response.json()["revision"] == 1

        response = client.put(
            f"/fact-bases/{base['id']}/certifications",
            json={"certifications": [
                {"name_ja": "日本語能力試験 N2", "date": "2023-12"}
            ]},
        )
        assert response.status_code == 200
        assert response.json()["certifications"][0]["name_ja"] == "日本語能力試験 N2"
        assert response.json()["revision"] == 2


def test_update_japan_extra(tmp_path):
    with make_client(tmp_path) as client:
        base = client.post("/fact-bases", json={}).json()

        response = client.put(
            f"/fact-bases/{base['id']}/japan-extra",
            json={
                "motivation": "データ分析で貢献したい。",
                "self_pr": "一気通貫で実行できる。",
                "desired_position": "データアナリスト",
            },
        )

    assert response.status_code == 200
    assert response.json()["japan_extra"]["motivation"] == "データ分析で貢献したい。"
    assert response.json()["japan_extra"]["desired_position"] == "データアナリスト"


def test_update_education_rejects_invalid_payload(tmp_path):
    with make_client(tmp_path) as client:
        base = client.post("/fact-bases", json={}).json()
        response = client.put(
            f"/fact-bases/{base['id']}/education",
            json={"education": [{"school": 123}]},
        )

    assert response.status_code == 422
