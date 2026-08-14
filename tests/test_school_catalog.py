from fastapi.testclient import TestClient

from resume_agent.api.app import create_app
from resume_agent.domain.school_catalog import search_schools


def test_search_by_name_fragment():
    names = [item["name"] for item in search_schools("华中")]
    assert "华中科技大学" in names


def test_search_by_full_pinyin():
    names = [item["name"] for item in search_schools("huazhong")]
    assert "华中科技大学" in names


def test_search_by_initials():
    names = [item["name"] for item in search_schools("hz")]
    assert "华中科技大学" in names
    assert "杭州电子科技大学" in names


def test_search_empty_query_returns_nothing():
    assert search_schools("") == []
    assert search_schools("   ") == []


def test_search_limit():
    assert len(search_schools("大学", limit=5)) == 5


def test_search_unknown_returns_nothing():
    assert search_schools("不存在的大学xyz") == []


def test_schools_search_endpoint(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        response = client.get("/schools/search", params={"q": "华中"})
        assert response.status_code == 200
        names = [item["name"] for item in response.json()]
        assert "华中科技大学" in names
