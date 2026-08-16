"""读取 GitHub 公开仓库信息（无需鉴权，仅公开数据）。"""

import json
import re
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional

GITHUB_API = "https://api.github.com"

_REPO_URL_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s?#]+)")
_PROFILE_URL_RE = re.compile(r"github\.com/([^/\s?#]+)/?$")


class GithubError(RuntimeError):
    """GitHub 读取失败，消息为可直接展示给用户的中文说明。"""


def parse_repo_url(url: str) -> Optional[tuple]:
    match = _REPO_URL_RE.search(url or "")
    if not match:
        return None
    owner, repo = match.group(1), re.sub(r"\.git$", "", match.group(2))
    return owner, repo


def parse_profile_url(url: str) -> Optional[str]:
    match = _PROFILE_URL_RE.search((url or "").strip())
    if not match:
        return None
    user = match.group(1)
    if user in ("", "login"):
        return None
    return user


def _default_get_json(request_url: str) -> object:
    request = urllib.request.Request(
        request_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ResumeAgent",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _repo_item(data: dict) -> Dict[str, str]:
    return {
        "name": data.get("name", ""),
        "full_name": data.get("full_name", ""),
        "description": (data.get("description") or "")[:80],
        "language": data.get("language") or "",
        "stars": data.get("stargazers_count", 0) or 0,
        "html_url": data.get("html_url", ""),
    }


def fetch_repos(
    url: str,
    get_json: Callable[[str], object] = _default_get_json,
) -> List[Dict[str, str]]:
    """根据 GitHub 主页或仓库链接返回候选项目（最多 6 个，按最近更新排序）。"""
    url = (url or "").strip()
    if not url:
        raise GithubError("请粘贴 GitHub 主页或仓库链接")

    repo = parse_repo_url(url)
    if repo is not None:
        owner, name = repo
        try:
            data = get_json(f"{GITHUB_API}/repos/{owner}/{name}")
        except urllib.error.HTTPError as error:
            raise GithubError(_http_error_message(error)) from error
        except Exception as error:
            raise GithubError("无法连接 GitHub，请检查网络后重试") from error
        item = _repo_item(data)
        return [item] if item["full_name"] else []

    user = parse_profile_url(url)
    if not user:
        raise GithubError(
            "链接格式不对，请粘贴 https://github.com/用户名 或某个仓库的地址"
        )
    try:
        data = get_json(
            f"{GITHUB_API}/users/{user}/repos?sort=updated&per_page=10"
        )
    except urllib.error.HTTPError as error:
        raise GithubError(_http_error_message(error)) from error
    except Exception as error:
        raise GithubError("无法连接 GitHub，请检查网络后重试") from error

    repos = [
        _repo_item(item)
        for item in data
        if item.get("full_name") and not item.get("archived")
    ]
    return repos[:6]


def _http_error_message(error: urllib.error.HTTPError) -> str:
    if error.code == 404:
        return "没有找到这个 GitHub 用户或仓库，请检查链接"
    if error.code in (403, 429):
        return "GitHub 接口访问受限（可能触发限流），请稍后再试或直接填写项目名"
    return f"GitHub 读取失败（{error.code}）"
