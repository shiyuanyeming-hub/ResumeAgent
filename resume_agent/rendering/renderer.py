"""Pure, evidence-only resume rendering."""

from __future__ import annotations

import html
import re
from collections.abc import Iterable

from resume_agent.domain.models import (
    CareerFactBase,
    ConfidenceStatus,
    Experience,
    QualityDimension,
    ResumeVersion,
)
from resume_agent.rendering.models import (
    RenderedExperience,
    RenderedResume,
    RenderWarning,
)
from resume_agent.rendering.styles import default_style, get_theme
from resume_agent.rendering.wareki import to_wareki_date


DIMENSION_ORDER = (
    QualityDimension.ACTION,
    QualityDimension.METHOD,
    QualityDimension.RESULT,
    QualityDimension.RESPONSIBILITY,
    QualityDimension.CONTEXT,
    QualityDimension.EVIDENCE,
)

COPY = {
    "zh": {
        "title": "简历",
        "experience": "工作经历",
        "skills": "技能",
        "summary": "职业概述",
        "target": "求职意向",
        "present": "至今",
    },
    "en": {
        "title": "Resume",
        "experience": "Experience",
        "skills": "Skills",
        "summary": "Summary",
        "target": "Target Role",
        "present": "Present",
    },
    "ja": {
        "title": "職務経歴書",
        "experience": "職務経歴",
        "skills": "活かせるスキル",
        "summary": "職務要約",
        "target": "希望職種",
        "present": "現在",
    },
}


class ResumeRenderer:
    def render(
        self,
        base: CareerFactBase,
        version: ResumeVersion,
    ) -> RenderedResume:
        if base.id != version.fact_base_id:
            raise ValueError("version does not belong to fact base")
        if version.locale not in COPY:
            raise ValueError(f"unsupported locale: {version.locale}")

        style = version.styles.get(version.locale) or default_style(version.locale)
        theme = get_theme(version.locale, style)
        experiences, has_estimates = self._resolve_experiences(base, version)
        skills = self._collect_skills(base, version)
        warnings = self._warnings(base, version, experiences, has_estimates)
        candidate_name = base.profile.name or self._candidate_fallback(version.locale)
        headline = version.target_role or base.target.role or version.name
        contact_line = " · ".join(
            value
            for value in (
                base.profile.email,
                base.profile.phone,
                base.profile.location,
                *base.profile.links,
            )
            if value
        )
        summary = self._summary(version.locale, headline, len(experiences))
        filename_stem = self._filename_stem(version.name, version.locale)
        markdown = self._markdown(
            version.locale,
            candidate_name,
            headline,
            contact_line,
            summary,
            experiences,
            skills,
        )
        rendered_html = self._html(
            version.locale,
            theme,
            candidate_name,
            headline,
            contact_line,
            summary,
            experiences,
            skills,
        )
        secondary_title = secondary_markdown = secondary_html = secondary_stem = ""
        if version.locale == "ja":
            secondary_title = "履歴書"
            secondary_markdown = self._rirekisho_markdown(base, version)
            secondary_html = self._rirekisho_html(base, version, theme)
            secondary_stem = f"{filename_stem}_rirekisho"
        return RenderedResume(
            version_id=version.id,
            base_revision=base.revision,
            version_base_revision=version.base_revision,
            locale=version.locale,
            style=style,
            title=COPY[version.locale]["title"],
            filename_stem=filename_stem,
            candidate_name=candidate_name,
            headline=headline,
            contact_line=contact_line,
            summary=summary,
            experiences=experiences,
            skills=skills,
            markdown=markdown,
            html=rendered_html,
            warnings=warnings,
            secondary_title=secondary_title,
            secondary_markdown=secondary_markdown,
            secondary_html=secondary_html,
            secondary_filename_stem=secondary_stem,
        )

    def _resolve_experiences(
        self,
        base: CareerFactBase,
        version: ResumeVersion,
    ) -> tuple[list[RenderedExperience], bool]:
        by_id = {experience.id: experience for experience in base.experiences}
        unknown = set(version.selected_experience_ids) - set(by_id)
        if unknown:
            raise ValueError(
                "unknown experience references: "
                + ", ".join(sorted(str(item) for item in unknown))
            )
        selected = set(version.selected_experience_ids)
        ordered_ids = [item for item in version.ordering if item in selected]
        ordered_ids.extend(
            item for item in version.selected_experience_ids if item not in ordered_ids
        )
        rendered = []
        has_estimates = False
        for experience_id in ordered_ids:
            experience = by_id[experience_id]
            bullets, experience_has_estimates = self._bullets(experience)
            has_estimates = has_estimates or experience_has_estimates
            rendered.append(
                RenderedExperience(
                    organization=experience.organization,
                    role=experience.role,
                    period=self._period(
                        experience.start,
                        experience.end,
                        version.locale,
                    ),
                    bullets=bullets,
                )
            )
        return rendered, has_estimates

    @staticmethod
    def _bullets(experience: Experience) -> tuple[list[str], bool]:
        bullets: list[str] = []
        seen = set()
        has_estimates = False
        for dimension in DIMENSION_ORDER:
            for value in experience.statements.get(dimension, []):
                if value.confidence is ConfidenceStatus.UNVERIFIED:
                    continue
                has_estimates = (
                    has_estimates or value.confidence is ConfidenceStatus.ESTIMATED
                )
                if value.text not in seen:
                    seen.add(value.text)
                    bullets.append(value.text)
        return bullets, has_estimates

    @staticmethod
    def _collect_skills(
        base: CareerFactBase,
        version: ResumeVersion,
    ) -> list[str]:
        by_id = {experience.id: experience for experience in base.experiences}
        skills: list[str] = []
        seen = set()
        for experience_id in version.selected_experience_ids:
            experience = by_id.get(experience_id)
            if experience is None:
                continue
            for skill in experience.linked_skills:
                normalized = skill.strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    skills.append(normalized)
        return skills

    @staticmethod
    def _warnings(
        base: CareerFactBase,
        version: ResumeVersion,
        experiences: list[RenderedExperience],
        has_estimates: bool,
    ) -> list[RenderWarning]:
        warnings = []
        if not base.profile.name or not base.profile.email or not base.profile.phone:
            warnings.append(
                RenderWarning(
                    code="missing_profile",
                    message="姓名、邮箱或电话尚未补全，导出前建议完善基本信息。",
                )
            )
        if has_estimates:
            warnings.append(
                RenderWarning(
                    code="estimated_evidence",
                    message="简历包含估算信息，请在投递前再次核对。",
                )
            )
        if version.base_revision != base.revision:
            warnings.append(
                RenderWarning(
                    code="stale_version",
                    message="证据档案已有更新，这个投递版本尚未刷新。",
                )
            )
        if not experiences or not any(item.bullets for item in experiences):
            warnings.append(
                RenderWarning(
                    code="empty_evidence",
                    message="当前版本没有可写入简历的已确认经历证据。",
                )
            )
        return warnings

    @staticmethod
    def _summary(locale: str, headline: str, count: int) -> str:
        if locale == "en":
            return f"Target role: {headline}. Evidence selected from {count} experience(s)."
        if locale == "ja":
            return f"希望職種：{headline}。確認済みの職務経験 {count} 件を掲載しています。"
        return f"目标岗位：{headline}。以下内容来自 {count} 段已确认经历。"

    @staticmethod
    def _candidate_fallback(locale: str) -> str:
        return {"zh": "候选人", "en": "Candidate", "ja": "候補者"}[locale]

    @staticmethod
    def _period(start: str, end: str, locale: str) -> str:
        if not start and not end:
            return ""
        if locale == "ja":
            normalized_start = to_wareki_date(start) if start else ""
            normalized_end = to_wareki_date(end) if end else COPY["ja"]["present"]
            return f"{normalized_start} 〜 {normalized_end}".strip()
        normalized_start = start.replace("-", ".") if start else ""
        normalized_end = end.replace("-", ".") if end else COPY[locale]["present"]
        return f"{normalized_start} – {normalized_end}".strip()

    def _rirekisho_events(
        self,
        base: CareerFactBase,
        version: ResumeVersion,
    ) -> list[tuple[str, str]]:
        """Chronological 学歴・職歴 rows for the Japanese rirekisho."""
        events: list[tuple[str, str]] = []
        for edu in base.education:
            school = edu.school_ja or edu.school
            major = edu.major_ja or edu.major
            if edu.start:
                events.append((edu.start, f"{school} {major}学部 入学"))
            if edu.end:
                events.append((edu.end, f"{school} 卒業"))
        by_id = {experience.id: experience for experience in base.experiences}
        for experience_id in version.selected_experience_ids:
            experience = by_id.get(experience_id)
            if experience is None:
                continue
            if experience.start:
                events.append(
                    (experience.start, f"{experience.organization} 入社（{experience.role}）")
                )
            if experience.end:
                events.append((experience.end, f"{experience.organization} 退社"))
        events.sort(key=lambda item: item[0])
        return events

    def _rirekisho_markdown(self, base: CareerFactBase, version: ResumeVersion) -> str:
        profile = base.profile
        birth_jp = to_wareki_date(profile.birth) if profile.birth else "（未記入）"
        lines = [
            "# 履歴書",
            "",
            f"- **氏名**：{self._markdown_escape(profile.name)}"
            f"（{self._markdown_escape(profile.name_kana)}）",
            f"- **生年月日**：{birth_jp}",
        ]
        if profile.phone:
            lines.append(f"- **電話**：{self._markdown_escape(profile.phone)}")
        if profile.email:
            lines.append(f"- **メール**：{self._markdown_escape(profile.email)}")
        if profile.address:
            lines.append(f"- **現住所**：{self._markdown_escape(profile.address)}")
        if profile.nearest_station:
            lines.append(f"- **最寄駅**：{self._markdown_escape(profile.nearest_station)}")
        lines.append("- **写真**：（3×4cm 証明写真貼付欄）")
        lines += ["", "## 学歴・職歴", ""]
        for date, text in self._rirekisho_events(base, version):
            lines.append(f"- {to_wareki_date(date)}　{self._markdown_escape(text)}")
        lines += ["", "## 免許・資格", ""]
        if base.certifications:
            for certification in base.certifications:
                name = certification.name_ja or certification.name
                suffix = f"（{to_wareki_date(certification.date)}）" if certification.date else ""
                lines.append(f"- {self._markdown_escape(name)}{suffix}")
        else:
            lines.append("- 特になし")
        japan_extra = base.japan_extra
        lines += [
            "",
            "## 志望動機",
            "",
            japan_extra.motivation or "（未記入）",
            "",
            "## 本人希望欄",
            "",
            japan_extra.desired_position or "貴社規定に従います。",
            "",
        ]
        return "\n".join(lines)

    def _rirekisho_html(self, base: CareerFactBase, version: ResumeVersion, theme) -> str:
        profile = base.profile
        birth_jp = to_wareki_date(profile.birth) if profile.birth else "（未記入）"
        escape = lambda value: html.escape(value or "", quote=True)
        events_rows = "".join(
            f"<tr><td>{escape(to_wareki_date(date))}</td><td>{escape(text)}</td></tr>"
            for date, text in self._rirekisho_events(base, version)
        )
        certifications = base.certifications
        cert_html = (
            "<ul>"
            + "".join(
                f"<li>{escape(certification.name_ja or certification.name)}"
                + (f"（{escape(to_wareki_date(certification.date))}）" if certification.date else "")
                + "</li>"
                for certification in certifications
            )
            + "</ul>"
        ) if certifications else "<p>特になし</p>"
        japan_extra = base.japan_extra
        css = f"""
        :root {{--accent:{theme.accent};--tint:{theme.tint};}}
        @page {{ size: A4; margin: 12mm; }}
        * {{ box-sizing: border-box; }}
        body {{ font-family: "Hiragino Kaku Gothic ProN","Hiragino Sans GB","Noto Sans CJK JP",sans-serif;
                font-size: 10.5pt; line-height: 1.6; color: #1a1a1a; margin: 0; }}
        .title-band {{ background: var(--accent); color: #fff; text-align: center; font-size: 14pt;
                       font-weight: bold; letter-spacing: 6px; padding: 2mm 0; margin-bottom: 3mm; }}
        .head-row {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 2.5mm; }}
        .person {{ font-size: 13pt; font-weight: bold; }}
        .person .kana {{ font-size: 10pt; color: #555; font-weight: normal; }}
        .photo-box {{ width: 26mm; height: 34mm; border: .8pt solid var(--accent); background: var(--tint);
                      color: #8a9bb0; font-size: 8pt; display: flex; align-items: center;
                      justify-content: center; text-align: center; }}
        table.grid {{ width: 100%; border-collapse: collapse; }}
        table.grid td, table.grid th {{ border: .7pt solid var(--accent); padding: 1.6mm 3mm; vertical-align: top; }}
        .kv td:first-child {{ width: 26mm; background: var(--tint); font-weight: bold; color: var(--accent); }}
        table.grid th {{ background: var(--tint); color: var(--accent); }}
        h2 {{ font-size: 11.5pt; color: var(--accent); border-bottom: 1.2pt solid var(--accent);
              padding-bottom: .8mm; margin: 3.8mm 0 1.6mm; }}
        ul {{ margin: 1mm 0 2mm; padding-left: 5mm; }} li {{ margin: .7mm 0; }}
        p {{ margin: 1mm 0; }}
        """
        body = (
            '<div class="title-band">履　歴　書</div>'
            '<div class="head-row">'
            f'<div class="person">{escape(profile.name)} '
            f'<span class="kana">（{escape(profile.name_kana)}）</span></div>'
            f'<div class="photo-box">{escape(profile.photo_note or "写真")}<br>（3×4cm）</div>'
            '</div>'
        )
        kv_rows = [
            ("生年月日", birth_jp),
            ("電話", profile.phone),
            ("メール", profile.email),
            ("現住所", profile.address),
            ("最寄駅", profile.nearest_station),
        ]
        body += (
            '<table class="grid kv">'
            + "".join(
                f"<tr><td>{escape(key)}</td><td>{escape(value) or '（未記入）'}</td></tr>"
                for key, value in kv_rows
            )
            + "</table>"
        )
        body += (
            '<h2>学歴・職歴</h2><table class="grid">'
            '<tr><th style="width:34mm">年　　月</th><th>学歴・職歴</th></tr>'
            + events_rows
            + "</table>"
        )
        body += "<h2>免許・資格</h2>" + cert_html
        body += "<h2>志望動機</h2><p>" + escape(japan_extra.motivation or "（未記入）") + "</p>"
        body += "<h2>本人希望欄</h2><p>" + escape(japan_extra.desired_position or "貴社規定に従います。") + "</p>"
        return (
            '<!DOCTYPE html>\n<html lang="ja"><head><meta charset="utf-8">'
            "<title>履歴書</title><style>"
            + css
            + "</style></head><body>"
            + body
            + "</body></html>"
        )

    @staticmethod
    def _filename_stem(name: str, locale: str) -> str:
        normalized = re.sub(r"[^\w\u3400-\u9fff-]+", "_", name, flags=re.UNICODE)
        normalized = normalized.strip("_-") or "resume"
        return f"{normalized}_{locale}"

    @staticmethod
    def _markdown_escape(value: str) -> str:
        escaped = value.replace("\\", "\\\\")
        for marker in ("*", "_", "`", "[", "]", "#"):
            escaped = escaped.replace(marker, f"\\{marker}")
        return escaped

    def _markdown(
        self,
        locale: str,
        candidate_name: str,
        headline: str,
        contact_line: str,
        summary: str,
        experiences: Iterable[RenderedExperience],
        skills: list[str],
    ) -> str:
        copy = COPY[locale]
        lines = [f"# {self._markdown_escape(candidate_name)}", ""]
        if headline:
            lines.extend(
                [f"**{copy['target']}：** {self._markdown_escape(headline)}", ""]
            )
        if contact_line:
            lines.extend([self._markdown_escape(contact_line), ""])
        lines.extend([f"## {copy['summary']}", "", self._markdown_escape(summary), ""])
        lines.extend([f"## {copy['experience']}", ""])
        for experience in experiences:
            heading = f"{experience.role} — {experience.organization}"
            if experience.period:
                heading += f" | {experience.period}"
            lines.extend([f"### {self._markdown_escape(heading)}", ""])
            lines.extend(f"- {self._markdown_escape(item)}" for item in experience.bullets)
            lines.append("")
        if skills:
            lines.extend(
                [
                    f"## {copy['skills']}",
                    "",
                    " · ".join(self._markdown_escape(item) for item in skills),
                    "",
                ]
            )
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _html(
        locale,
        theme,
        candidate_name,
        headline,
        contact_line,
        summary,
        experiences,
        skills,
    ) -> str:
        copy = COPY[locale]
        escape = lambda value: html.escape(value, quote=True)
        experience_html = []
        for experience in experiences:
            meta = " · ".join(
                value
                for value in (experience.organization, experience.period)
                if value
            )
            bullets = "".join(f"<li>{escape(item)}</li>" for item in experience.bullets)
            experience_html.append(
                f'<section class="experience"><h3>{escape(experience.role)}</h3>'
                f'<p class="meta">{escape(meta)}</p><ul>{bullets}</ul></section>'
            )
        skills_html = "".join(f'<span class="skill">{escape(item)}</span>' for item in skills)
        css = f"""
        :root {{--accent:{theme.accent};--secondary:{theme.secondary};--tint:{theme.tint};--border:{theme.border};}}
        @page {{ size: A4; margin: 14mm 16mm; }}
        * {{ box-sizing: border-box; }}
        body {{ font-family:{theme.font_family}; color:#1f2937; font-size:10pt; line-height:1.58; margin:0; }}
        header {{ border-bottom:2.2pt solid var(--accent); padding-bottom:3mm; margin-bottom:5mm; }}
        h1 {{ color:var(--accent); font-size:21pt; margin:0; letter-spacing:.4px; }}
        .headline {{ color:var(--secondary); font-size:10.5pt; margin:1mm 0; }}
        .contact,.meta {{ color:#5f6772; font-size:9pt; margin:.8mm 0; }}
        h2 {{ color:var(--accent); font-size:11.5pt; border-left:3.5pt solid var(--accent); padding-left:2.5mm; margin:5mm 0 2mm; }}
        h3 {{ font-size:10.5pt; margin:2.5mm 0 .5mm; color:#20252b; }}
        p {{ margin:1mm 0; }}
        ul {{ margin:1mm 0 2mm; padding-left:5mm; }}
        li {{ margin:.7mm 0; }}
        li::marker {{ color:var(--accent); }}
        .skill {{ display:inline-block; background:var(--tint); border:.5pt solid var(--border); border-radius:2.5mm; padding:.5mm 2.2mm; margin:.5mm; color:var(--accent); font-size:9pt; }}
        """
        contact = f'<p class="contact">{escape(contact_line)}</p>' if contact_line else ""
        skills_section = (
            f"<h2>{copy['skills']}</h2><div>{skills_html}</div>" if skills else ""
        )
        body = (
            f'<header><h1>{escape(candidate_name)}</h1>'
            f'<p class="headline">{escape(copy["target"])}：{escape(headline)}</p>'
            f"{contact}</header>"
            f'<h2>{copy["summary"]}</h2><p>{escape(summary)}</p>'
            f'<h2>{copy["experience"]}</h2>{"".join(experience_html)}'
            f"{skills_section}"
        )
        return (
            "<!DOCTYPE html>\n"
            f'<html lang="{locale}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(copy["title"])}</title><style>{css}</style></head>'
            f"<body>{body}</body></html>"
        )
