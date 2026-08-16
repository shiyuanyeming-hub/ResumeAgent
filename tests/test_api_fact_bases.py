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


def test_delete_fact_base_removes_it_and_returns_204(tmp_path):
    with make_client(tmp_path) as client:
        base = client.post("/fact-bases", json={}).json()
        deleted = client.delete(f"/fact-bases/{base['id']}")
        fetched = client.get(f"/fact-bases/{base['id']}")
        listed = client.get("/fact-bases")

    assert deleted.status_code == 204
    assert fetched.status_code == 404
    assert base["id"] not in [item["id"] for item in listed.json()]


def test_delete_unknown_fact_base_returns_404(tmp_path):
    with make_client(tmp_path) as client:
        response = client.delete(
            "/fact-bases/00000000-0000-0000-0000-000000000000"
        )

    assert response.status_code == 404


def test_delete_fact_base_cleans_up_files(tmp_path):
    with make_client(tmp_path) as client:
        base = client.post("/fact-bases", json={}).json()
        base_id = base["id"]
        photo = client.put(
            f"/fact-bases/{base_id}/photo",
            files={"photo": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")},
        )
        assert photo.status_code == 200

        deleted = client.delete(f"/fact-bases/{base_id}")
        photos_dir = tmp_path / "photos"

    assert deleted.status_code == 204
    assert photos_dir.is_dir()
    assert not any(photos_dir.iterdir())
