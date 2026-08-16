import urllib.error

import pytest

from resume_agent.infrastructure.github_client import (
    GithubError,
    fetch_repos,
    parse_profile_url,
    parse_repo_url,
)


def test_parse_repo_url():
    assert parse_repo_url("https://github.com/wangming/resume-agent") == (
        "wangming", "resume-agent",
    )
    assert parse_repo_url("github.com/foo/bar.git") == ("foo", "bar")
    assert parse_repo_url("https://github.com/wangming") is None


def test_parse_profile_url():
    assert parse_profile_url("https://github.com/wangming") == "wangming"
    assert parse_profile_url("github.com/wangming/") == "wangming"
    assert parse_profile_url("https://github.com/wangming/repo") is None


def test_fetch_repos_from_profile():
    def fake_get_json(request_url):
        assert "/users/wangming/repos" in request_url
        return [
            {"full_name": "wangming/project-a", "description": "A 项目",
             "language": "Python", "stargazers_count": 12,
             "html_url": "https://github.com/wangming/project-a"},
            {"full_name": "wangming/project-b", "description": "",
             "language": "TypeScript", "stargazers_count": 3,
             "html_url": "https://github.com/wangming/project-b"},
        ]

    repos = fetch_repos("https://github.com/wangming", get_json=fake_get_json)
    assert [repo["full_name"] for repo in repos] == [
        "wangming/project-a", "wangming/project-b",
    ]
    assert repos[0]["language"] == "Python"


def test_fetch_repos_from_single_repo():
    def fake_get_json(request_url):
        assert "/repos/wangming/project-a" in request_url
        return {"full_name": "wangming/project-a", "description": "A",
                "language": "Python", "stargazers_count": 5,
                "html_url": "https://github.com/wangming/project-a"}

    repos = fetch_repos("https://github.com/wangming/project-a", get_json=fake_get_json)
    assert [repo["full_name"] for repo in repos] == ["wangming/project-a"]


def test_fetch_repos_user_not_found():
    def fake_get_json(request_url):
        raise urllib.error.HTTPError(request_url, 404, "Not Found", {}, None)

    with pytest.raises(GithubError, match="没有找到"):
        fetch_repos("https://github.com/nobody-xyz-404", get_json=fake_get_json)


def test_fetch_repos_bad_url():
    with pytest.raises(GithubError, match="链接格式不对"):
        fetch_repos("https://example.com/not-github", get_json=lambda url: [])
