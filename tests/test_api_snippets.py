from fastapi.testclient import TestClient

from resume_agent.api.app import create_app
from tests.fakes import StubAuditAgent, StubQuestionWriter


class FakeSnippetAgent:
    def write(self, experience, facts_text):
        return ["搭建并维护了用户留存看板"]


def build_base_with_confirmed_fact(client):
    base = client.post(
        "/fact-bases", json={"target": {"role": "数据分析师"}}
    ).json()
    base = client.post(
        f"/fact-bases/{base['id']}/experiences",
        json={"organization": "星河科技", "role": "实习生"},
    ).json()
    experience = base["experiences"][0]
    session = client.post(
        "/sessions",
        json={"fact_base_id": base["id"], "active_experience_id": experience["id"]},
    ).json()
    proposal = client.post(
        f"/sessions/{session['id']}/answers", json={"message": "搭建看板"}
    ).json()["proposal"]
    client.post(f"/sessions/{session['id']}/proposals/{proposal['id']}/confirm")
    return base, experience


def test_generate_snippets_offline_returns_fact_cards(tmp_path):
    app = create_app(
        tmp_path / "resume-agent.db",
        fact_audit_agent=StubAuditAgent(),
        question_writer=StubQuestionWriter(),
    )
    with TestClient(app) as client:
        base, experience = build_base_with_confirmed_fact(client)
        response = client.post(
            f"/fact-bases/{base['id']}/experiences/{experience['id']}/snippets/generate"
        )
    assert response.status_code == 200
    snippets = response.json()["snippets"]
    assert [item["text"] for item in snippets] == ["搭建看板"]
    assert snippets[0]["source_fact_ids"]


def test_generate_snippets_with_agent_rewrites(tmp_path):
    app = create_app(
        tmp_path / "resume-agent.db",
        fact_audit_agent=StubAuditAgent(),
        question_writer=StubQuestionWriter(),
        snippet_agent=FakeSnippetAgent(),
    )
    with TestClient(app) as client:
        base, experience = build_base_with_confirmed_fact(client)
        response = client.post(
            f"/fact-bases/{base['id']}/experiences/{experience['id']}/snippets/generate"
        )
    assert response.status_code == 200
    assert [item["text"] for item in response.json()["snippets"]] == [
        "搭建并维护了用户留存看板"
    ]


def test_generate_snippets_without_facts_is_empty(tmp_path):
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
        response = client.post(
            f"/fact-bases/{base['id']}/experiences/{experience['id']}/snippets/generate"
        )
    assert response.status_code == 200
    assert response.json()["snippets"] == []


def test_add_and_remove_version_snippet(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh", "selected_experience_ids": []},
        ).json()
        added = client.post(
            f"/versions/{version['id']}/snippets",
            json={"experience_id": None, "text": "一段自由补充内容", "source_fact_ids": []},
        )
        assert added.status_code == 200
        snippet = added.json()["custom_sections"][0]
        assert snippet["text"] == "一段自由补充内容"
        duplicate = client.post(
            f"/versions/{version['id']}/snippets",
            json={"experience_id": None, "text": "一段自由补充内容", "source_fact_ids": []},
        )
        assert duplicate.status_code == 422
        removed = client.delete(
            f"/versions/{version['id']}/snippets/{snippet['id']}"
        )
        assert removed.status_code == 200
        assert removed.json()["custom_sections"] == []
