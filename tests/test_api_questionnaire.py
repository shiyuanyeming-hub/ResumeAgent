from fastapi.testclient import TestClient

from resume_agent.api.app import create_app


def test_questionnaire_returns_sections_and_first_card(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        response = client.get(f"/fact-bases/{base['id']}/questionnaire")
    assert response.status_code == 200
    body = response.json()
    assert [item["section"] for item in body["sections"]] == [
        "profile", "target", "education", "experience", "skills", "summary",
    ]
    assert body["next"]["step_id"] == "profile:name"


def test_questionnaire_answer_advances_card(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        answer = client.post(
            f"/fact-bases/{base['id']}/questionnaire/answer",
            json={"step_id": "profile:name", "value": "王明"},
        )
        assert answer.status_code == 200
        assert answer.json()["next"]["step_id"] == "profile:email"
        fetched = client.get(f"/fact-bases/{base['id']}").json()
        assert fetched["profile"]["name"] == "王明"


def test_questionnaire_answer_validates_email(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        answer = client.post(
            f"/fact-bases/{base['id']}/questionnaire/answer",
            json={"step_id": "profile:email", "value": "not-an-email"},
        )
        assert answer.status_code == 422


def test_questionnaire_skip_advances(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        skip = client.post(
            f"/fact-bases/{base['id']}/questionnaire/skip",
            json={"step_id": "profile:name"},
        )
        assert skip.status_code == 200
        assert skip.json()["next"]["step_id"] == "profile:email"


def test_education_crud(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        created = client.post(
            f"/fact-bases/{base['id']}/educations",
            json={"school": "某大学", "major": "统计", "start": "2020-09"},
        )
        assert created.status_code == 201
        education = created.json()["educations"][0]
        patched = client.patch(
            f"/fact-bases/{base['id']}/educations/{education['id']}",
            json={"school": "某大学", "major": "统计", "start": "2020-09", "degree": "本科"},
        )
        assert patched.status_code == 200
        assert patched.json()["educations"][0]["degree"] == "本科"
        removed = client.delete(
            f"/fact-bases/{base['id']}/educations/{education['id']}"
        )
        assert removed.status_code == 200
        assert removed.json()["educations"] == []


def test_experience_patch_updates_type_and_period(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        base = client.post(
            f"/fact-bases/{base['id']}/experiences",
            json={"organization": "星河科技", "role": "实习生"},
        ).json()
        experience = base["experiences"][0]
        patched = client.patch(
            f"/fact-bases/{base['id']}/experiences/{experience['id']}",
            json={"type": "internship", "start": "2024-06", "end": "2024-09"},
        )
        assert patched.status_code == 200
        updated = patched.json()["experiences"][0]
        assert updated["type"] == "internship"
        assert updated["start"] == "2024-06"
        assert updated["end"] == "2024-09"
