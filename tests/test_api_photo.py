from fastapi.testclient import TestClient

from resume_agent.api.app import create_app

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_photo_upload_preview_get_delete(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        up = client.put(
            f"/fact-bases/{base['id']}/photo",
            files={"photo": ("me.png", PNG_BYTES, "image/png")},
        )
        assert up.status_code == 200
        assert up.json()["profile"]["photo"].endswith(".png")

        photo = client.get(f"/fact-bases/{base['id']}/photo")
        assert photo.status_code == 200
        assert photo.content == PNG_BYTES
        assert photo.headers["content-type"] == "image/png"

        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh"},
        ).json()
        preview = client.get(f"/versions/{version['id']}/preview").json()
        assert "data:image/png;base64" in preview["html"]
        assert 'class="photo"' in preview["html"]
        assert "data:image/png;base64" in preview["markdown"]

        removed = client.delete(f"/fact-bases/{base['id']}/photo")
        assert removed.status_code == 200
        assert removed.json()["profile"]["photo"] == ""
        assert client.get(f"/fact-bases/{base['id']}/photo").status_code == 404


def test_photo_rejects_bad_type_and_missing_file(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post("/fact-bases", json={}).json()
        bad = client.put(
            f"/fact-bases/{base['id']}/photo",
            files={"photo": ("me.txt", b"xx", "text/plain")},
        )
        assert bad.status_code == 415
        missing = client.get(f"/fact-bases/{base['id']}/photo")
        assert missing.status_code == 404


def test_preview_orders_educations_desc_and_shows_details(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post("/fact-bases", json={}).json()
        client.post(
            f"/fact-bases/{base['id']}/educations",
            json={"school": "某大学", "major": "统计学", "degree": "本科",
                  "start": "2020-09", "end": "2024-06", "gpa": "3.6/4.0"},
        )
        client.post(
            f"/fact-bases/{base['id']}/educations",
            json={"school": "华中科技大学", "major": "计算机科学与技术",
                  "degree": "硕士", "start": "2024-09",
                  "research_direction": "数据挖掘", "thesis": "推荐系统研究"},
        )
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh"},
        ).json()
        preview = client.get(f"/versions/{version['id']}/preview").json()
        html = preview["html"]
        master_index = html.index("华中科技大学")
        bachelor_index = html.index("某大学")
        assert master_index < bachelor_index
        assert "GPA：3.6/4.0" in html
        assert "研究方向：数据挖掘" in html
        assert "毕业论文：推荐系统研究" in html


TEMPLATE_HTML = """<!DOCTYPE html><html><head><style>body{font-family:serif}</style></head><body>
<h1>我的学校模板</h1>
{{header}}
{{education}}
{{experience_work}}
{{experience_projects}}
{{skills}}
{{summary}}
</body></html>"""


def test_template_upload_fills_placeholders_and_can_remove(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post("/fact-bases", json={"target": {"role": "产品经理"}}).json()
        client.post(
            f"/fact-bases/{base['id']}/educations",
            json={"school": "同济大学", "major": "软件工程",
                  "degree": "本科", "start": "2020-09"},
        )
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh"},
        ).json()

        up = client.put(
            f"/fact-bases/{base['id']}/template",
            files={"template": ("school.html", TEMPLATE_HTML.encode("utf-8"), "text/html")},
        )
        assert up.status_code == 200
        assert up.json()["profile"]["template"].endswith(".html")

        preview = client.get(f"/versions/{version['id']}/preview").json()
        assert "我的学校模板" in preview["html"]
        assert "同济大学" in preview["html"]
        assert "{{header}}" not in preview["html"]

        removed = client.delete(f"/fact-bases/{base['id']}/template")
        assert removed.status_code == 200
        preview2 = client.get(f"/versions/{version['id']}/preview").json()
        assert "我的学校模板" not in preview2["html"]
        assert "同济大学" in preview2["html"]


def test_template_without_placeholder_falls_back_to_system_layout(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post("/fact-bases", json={"target": {"role": "产品经理"}}).json()
        client.post(
            f"/fact-bases/{base['id']}/educations",
            json={"school": "同济大学", "major": "软件工程",
                  "degree": "本科", "start": "2020-09"},
        )
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh"},
        ).json()
        up = client.put(
            f"/fact-bases/{base['id']}/template",
            files={"template": ("plain.html", b"<html><body>no placeholder</body></html>", "text/html")},
        )
        assert up.status_code == 200
        preview = client.get(f"/versions/{version['id']}/preview").json()
        assert "no placeholder" not in preview["html"]
        assert "同济大学" in preview["html"]


def test_template_rejects_non_html(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post("/fact-bases", json={}).json()
        up = client.put(
            f"/fact-bases/{base['id']}/template",
            files={"template": ("note.txt", b"just text", "text/plain")},
        )
        assert up.status_code == 415
