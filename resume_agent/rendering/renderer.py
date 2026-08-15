"""Pure, evidence-only resume rendering."""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from uuid import UUID

from resume_agent.domain.models import (
    CareerFactBase,
    ConfidenceStatus,
    Experience,
    ExperienceType,
    QualityDimension,
    ResumeVersion,
)
from resume_agent.rendering.models import (
    RenderedEducation,
    RenderedExperience,
    RenderedResume,
    RenderWarning,
)
from resume_agent.rendering.styles import default_style, get_theme


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
        "education": "教育背景",
        "internshipWork": "实习/工作经历",
        "campusProjects": "项目经历",
        "skills": "技能与证书",
        "courses": "核心课程",
        "summary": "职业概述",
        "target": "求职意向",
        "present": "至今",
        "selfSummary": "自我评价",
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
        photo_data_uri: str = "",
        template_html: str = "",
    ) -> RenderedResume:
        if base.id != version.fact_base_id:
            raise ValueError("version does not belong to fact base")
        if version.locale not in COPY:
            raise ValueError(f"unsupported locale: {version.locale}")

        style = version.styles.get(version.locale) or default_style(version.locale)
        theme = get_theme(version.locale, style)
        experiences, has_estimates = self._resolve_experiences(base, version)
        educations = self._resolve_educations(base)
        skills = self._collect_skills(base, version)
        if version.locale == "zh":
            for skill in base.profile.skills:
                normalized = skill.strip()
                if normalized and normalized not in skills:
                    skills.append(normalized)
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
            educations,
            version,
            photo_data_uri,
            list(base.profile.certificates),
            list(base.profile.language_scores),
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
            educations,
            version,
            photo_data_uri,
            list(base.profile.certificates),
            list(base.profile.language_scores),
            template_html,
        )
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
            educations=educations,
            skills=skills,
            self_summary=version.selected_summary,
            custom_snippets=version.custom_sections,
            markdown=markdown,
            html=rendered_html,
            warnings=warnings,
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
        # 未显式选择时默认展示全部经历
        selected_ids = list(version.selected_experience_ids) or [
            experience.id for experience in base.experiences
        ]
        ordered_experiences = sorted(
            (by_id[experience_id] for experience_id in selected_ids),
            key=lambda experience: experience.start or "",
            reverse=True,
        )
        rendered = []
        has_estimates = False
        for experience in ordered_experiences:
            bullets, experience_has_estimates = self._bullets(experience)
            has_estimates = has_estimates or experience_has_estimates
            rendered.append(
                RenderedExperience(
                    id=experience.id,
                    organization=experience.organization,
                    role=experience.role,
                    period=self._period(
                        experience.start,
                        experience.end,
                        version.locale,
                    ),
                    bullets=bullets,
                    type=experience.type,
                )
            )
        return rendered, has_estimates

    @staticmethod
    def _bullets(experience: Experience) -> tuple[list[str], bool]:
        """经历板块如实展示已确认事实，不再被片段覆盖。"""
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
        normalized_start = start.replace("-", ".") if start else ""
        normalized_end = end.replace("-", ".") if end else COPY[locale]["present"]
        return f"{normalized_start} – {normalized_end}".strip()

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

    def _resolve_educations(self, base):
        ordered = sorted(
            base.educations,
            key=lambda education: education.start or "",
            reverse=True,
        )
        return [
            RenderedEducation(
                school=education.school,
                major=education.major,
                degree=education.degree,
                period=self._period(education.start, education.end or "", "zh"),
                courses=list(education.core_courses),
                gpa=education.gpa,
                rank=education.rank,
                research_direction=education.research_direction,
                thesis=education.thesis,
            )
            for education in ordered
        ]

    @staticmethod
    def _zh_group(experiences):
        work = [
            item for item in experiences
            if item.type in (ExperienceType.WORK, ExperienceType.INTERNSHIP)
        ]
        campus = [
            item for item in experiences
            if item.type not in (ExperienceType.WORK, ExperienceType.INTERNSHIP)
        ]
        return work, campus

    def _zh_markdown(self, candidate_name, headline, contact_line, summary,
                     experiences, skills, educations, version, photo_data_uri="",
                     certificates=(), language_scores=()):
        copy = COPY["zh"]
        lines = [f"# {self._markdown_escape(candidate_name)}", ""]
        if photo_data_uri:
            lines.append(f'<img src="{photo_data_uri}" width="130" alt="照片" />')
            lines.append("")
        if headline:
            lines.append(f"**{copy['target']}：** {self._markdown_escape(headline)}")
            lines.append("")
        if contact_line:
            lines.append(self._markdown_escape(contact_line))
            lines.append("")
        if educations:
            lines.append(f"## {copy['education']}")
            lines.append("")
            for education in educations:
                meta = " | ".join(
                    item for item in (education.major, education.degree, education.period) if item
                )
                heading = education.school + (f" | {meta}" if meta else "")
                lines.append(f"### {self._markdown_escape(heading)}")
                lines.append("")
                detail = []
                if education.gpa:
                    detail.append(f"GPA：{education.gpa}")
                if education.rank:
                    detail.append(f"排名：{education.rank}")
                if education.research_direction:
                    detail.append(f"研究方向：{education.research_direction}")
                if education.thesis:
                    detail.append(f"毕业论文：{education.thesis}")
                if detail:
                    lines.append(
                        " | ".join(self._markdown_escape(item) for item in detail)
                    )
                    lines.append("")
                if education.courses:
                    lines.append(
                        f"{copy['courses']}："
                        + "、".join(self._markdown_escape(item) for item in education.courses)
                    )
                    lines.append("")
        work, campus = self._zh_group(experiences)
        for heading, group in ((copy["internshipWork"], work), (copy["campusProjects"], campus)):
            if not group:
                continue
            lines.append(f"## {heading}")
            lines.append("")
            for experience in group:
                experience_heading = (
                    f"{experience.role} — {experience.organization}"
                    if experience.role else experience.organization
                )
                if experience.period:
                    experience_heading += f" | {experience.period}"
                lines.append(f"### {self._markdown_escape(experience_heading)}")
                lines.append("")
                lines.extend(f"- {self._markdown_escape(item)}" for item in experience.bullets)
                lines.append("")
        # 技能与证书：技能标签 + 证书荣誉 + 语言成绩 + 自定义条目
        skill_lines = [
            " · ".join(self._markdown_escape(item) for item in skills),
            *[f"- {self._markdown_escape(item)}" for item in certificates],
            *[f"- {self._markdown_escape(item)}" for item in language_scores],
            *[f"- {self._markdown_escape(item.text)}" for item in version.custom_sections],
        ]
        skill_lines = [line for line in skill_lines if line.strip()]
        if skill_lines:
            lines.append(f"## {copy['skills']}")
            lines.append("")
            lines.extend(skill_lines)
            lines.append("")
        if version.selected_summary:
            lines.append(f"## {copy['selfSummary']}")
            lines.append("")
            lines.append(self._markdown_escape(version.selected_summary))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _zh_html(self, theme, candidate_name, headline, contact_line,
                 experiences, skills, educations, version, photo_data_uri="",
                 certificates=(), language_scores=(), template_html=""):
        copy = COPY["zh"]
        escape = lambda value: html.escape(value, quote=True)
        css = f"""
        :root {{--accent:{theme.accent};--secondary:{theme.secondary};--tint:{theme.tint};--border:{theme.border};}}
        @page {{ size: A4; margin: 17mm 20mm; }}
        * {{ box-sizing: border-box; }}
        body {{ font-family:{theme.font_family}; color:#1f2937; font-size:10pt; line-height:1.66; margin:0; }}
        header {{ border-bottom:2.5pt solid var(--accent); padding-bottom:4mm; margin-bottom:6mm; display:flex; justify-content:space-between; gap:6mm; align-items:center; }}
        .header-text {{ flex:1; }}
        h1 {{ color:var(--accent); font-size:22pt; margin:0 0 1mm; letter-spacing:1px; }}
        .headline {{ color:var(--secondary); font-size:10.8pt; margin:0 0 1.2mm; letter-spacing:.3px; }}
        .contact {{ color:#5f6772; font-size:9.2pt; margin:0; }}
        .photo {{ width:28mm; height:36mm; object-fit:cover; border-radius:2mm; border:.5pt solid var(--border); }}
        h2 {{ color:var(--accent); font-size:12pt; letter-spacing:.6px; border-left:4pt solid var(--accent); padding-left:3mm; margin:6.5mm 0 2.8mm; }}
        h3 {{ font-size:10.8pt; margin:0 0 .5mm; color:#20252b; }}
        p {{ margin:1mm 0; }}
        .meta {{ color:#5f6772; font-size:9pt; margin:.6mm 0; }}
        ul {{ margin:1.2mm 0 2.4mm; padding-left:5.5mm; }}
        li {{ margin:.9mm 0; padding-left:.6mm; }}
        li::marker {{ color:var(--accent); }}
        section.education {{ margin:0 0 3mm; }}
        section.experience {{ margin:0 0 2.8mm; }}
        .skill {{ display:inline-block; background:var(--tint); border:.6pt solid var(--border); border-radius:3mm; padding:.6mm 2.8mm; margin:.6mm .6mm 0 0; color:var(--accent); font-size:9pt; letter-spacing:.3px; }}
        .drop-zone {{ border-radius:3mm; transition: outline .1s; }}
        .drop-zone.drop-active {{ outline: 2.2pt dashed var(--accent); outline-offset: 2mm; }}
        .drop-hint {{ color:#9aa3ad; font-size:8.5pt; margin:.8mm 0; }}
        """
        contact = f'<p class="contact">{escape(contact_line)}</p>' if contact_line else ""
        photo_html = (
            f'<img class="photo" src="{photo_data_uri}" alt="照片" />'
            if photo_data_uri else ""
        )
        header_text = (
            f'<div class="header-text"><h1>{escape(candidate_name)}</h1>'
            f'<p class="headline">{copy["target"]}：{escape(headline)}</p>'
            f"{contact}</div>"
        )
        header_html = f"<header>{header_text}{photo_html}</header>"
        education_html = []
        for education in educations:
            meta = " · ".join(
                item for item in (education.major, education.degree, education.period) if item
            )
            details = []
            if education.gpa:
                details.append(f"GPA：{education.gpa}")
            if education.rank:
                details.append(f"排名：{education.rank}")
            if education.research_direction:
                details.append(f"研究方向：{education.research_direction}")
            if education.thesis:
                details.append(f"毕业论文：{education.thesis}")
            detail_line = (
                f'<p class="meta">{" · ".join(escape(item) for item in details)}</p>'
                if details else ""
            )
            courses = (
                f'<p class="meta">{copy["courses"]}：'
                + "、".join(escape(item) for item in education.courses)
                + "</p>"
                if education.courses else ""
            )
            education_html.append(
                f'<section class="education" data-school="{escape(education.school)}">'
                f"<h3>{escape(education.school)}</h3>"
                f'<p class="meta">{escape(meta)}</p>{detail_line}{courses}</section>'
            )
        work, campus = self._zh_group(experiences)
        group_fragments = {}
        for key, heading, group in (
            ("work", copy["internshipWork"], work),
            ("projects", copy["campusProjects"], campus),
        ):
            if not group:
                group_fragments[key] = ""
                continue
            section_html = []
            for experience in group:
                if experience.role:
                    title = escape(experience.role)
                    meta = " · ".join(
                        item for item in (experience.organization, experience.period) if item
                    )
                else:
                    title = escape(experience.organization)
                    meta = escape(experience.period)
                bullets = "".join(
                    f"<li>{escape(item)}</li>" for item in experience.bullets
                )
                section_html.append(
                    f'<section class="experience" data-experience-id="{experience.id}">'
                    f"<h3>{title}</h3>"
                    f'{f"<p class=\"meta\">{meta}</p>" if meta else ""}'
                    f"{'<ul>' + bullets + '</ul>' if bullets else ''}</section>"
                )
            group_fragments[key] = f"<h2>{heading}</h2>{''.join(section_html)}"
        skills_html = "".join(f'<span class="skill">{escape(item)}</span>' for item in skills)
        education_section = (
            f"<h2>{copy['education']}</h2>{''.join(education_html)}" if educations else ""
        )
        # 技能与证书：技能标签 + 证书荣誉 + 语言成绩 + 自定义条目（唯一可拖放的自定义区）
        extra_items = "".join(
            f"<li>{escape(item)}</li>"
            for item in [*certificates, *language_scores]
        )
        custom_items = "".join(
            f'<li class="snippet" data-snippet-id="{item.id}">{escape(item.text)}</li>'
            for item in version.custom_sections
        )
        skills_certs = (
            '<section class="drop-zone skills-certs" data-section="custom">'
            f"<h2>{copy['skills']}</h2>"
            f"{'<div>' + skills_html + '</div>' if skills else ''}"
            f"{'<ul>' + extra_items + custom_items + '</ul>' if (extra_items or custom_items) else ''}"
            '<p class="meta drop-hint">可把证书、语言成绩、奖学金等片段卡拖到此处。</p>'
            "</section>"
        )
        summary_section = (
            f"<h2>{copy['selfSummary']}</h2><p>{escape(version.selected_summary)}</p>"
            if version.selected_summary else ""
        )
        body = (
            f"{header_html}"
            f"{education_section}"
            f"{group_fragments['work']}"
            f"{group_fragments['projects']}"
            f"{skills_certs}"
            f"{summary_section}"
        )
        if template_html:
            return self._zh_template(
                template_html, body, header_html, education_section,
                group_fragments, skills_certs, summary_section,
            )
        return (
            "<!DOCTYPE html>\n"
            f'<html lang="zh"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(copy["title"])}</title><style>{css}</style></head>'
            f'<body data-template-version="2">{body}</body></html>'
        )

    @staticmethod
    def _zh_template(template_html, full_body, header_html, education_section,
                     group_fragments, skills_certs, summary_section):
        """把系统生成的片段注入用户上传的学校模板（占位符约定见工具页说明）。"""
        import re

        replacements = {
            "{{full_content}}": full_body,
            "{{header}}": header_html,
            "{{education}}": education_section,
            "{{experience_work}}": group_fragments["work"],
            "{{experience_projects}}": group_fragments["projects"],
            "{{skills}}": skills_certs,
            "{{summary}}": summary_section,
        }
        filled = template_html
        has_placeholder = False
        for token, value in replacements.items():
            if token in filled:
                has_placeholder = True
                filled = filled.replace(token, value)
        if not has_placeholder:
            # 模板没有任何占位符：退回系统版式，避免导出空白简历
            return full_body
        filled = re.sub(r"\{\{\s*[a-zA-Z_]+\s*\}\}", "", filled)
        return filled

    def _markdown(
        self,
        locale: str,
        candidate_name: str,
        headline: str,
        contact_line: str,
        summary: str,
        experiences: Iterable[RenderedExperience],
        skills: list[str],
        educations: list[RenderedEducation],
        version: ResumeVersion,
        photo_data_uri: str = "",
        certificates: list[str] = (),
        language_scores: list[str] = (),
    ) -> str:
        copy = COPY[locale]
        if locale == "zh":
            return self._zh_markdown(
                candidate_name, headline, contact_line, summary,
                experiences, skills, educations, version, photo_data_uri,
                certificates, language_scores,
            )
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

    def _html(
        self,
        locale,
        theme,
        candidate_name,
        headline,
        contact_line,
        summary,
        experiences,
        skills,
        educations,
        version,
        photo_data_uri: str = "",
        certificates: list[str] = (),
        language_scores: list[str] = (),
        template_html: str = "",
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
        if locale == "zh":
            return self._zh_html(
                theme, candidate_name, headline, contact_line,
                experiences, skills, educations, version, photo_data_uri,
                certificates, language_scores, template_html,
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
