from fastapi.testclient import TestClient

from resume_agent.api.app import create_app


def test_generate_summary_options_offline(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh", "selected_experience_ids": []},
        ).json()
        response = client.post(f"/versions/{version['id']}/summary-options/generate")
        assert response.status_code == 200
        options = response.json()["options"]
        assert len(options) >= 3
        picked = options[0]
        put = client.put(
            f"/versions/{version['id']}/summary", json={"text": picked}
        )
        assert put.status_code == 200
        assert put.json()["selected_summary"] == picked


def test_questionnaire_summary_pick_writes_version_summary(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh", "selected_experience_ids": []},
        ).json()
        options = client.post(
            f"/versions/{version['id']}/summary-options/generate"
        ).json()["options"]
        answer = client.post(
            f"/fact-bases/{base['id']}/questionnaire/answer",
            json={"step_id": "summary:pick", "values": [options[0]]},
        )
        assert answer.status_code == 200
        fetched = client.get(f"/versions/{version['id']}")
        assert fetched.json()["selected_summary"] == options[0]
