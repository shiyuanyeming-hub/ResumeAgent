"""Application service joining canonical facts, version overlays, and exporters."""

import base64
from pathlib import Path
from typing import Callable, Optional
from uuid import UUID

from resume_agent.application.ports import FactBaseRepository, VersionRepository
from resume_agent.rendering.exporters import ExportedFile, RenderFormat, ResumeExporter
from resume_agent.rendering.models import RenderedResume
from resume_agent.rendering.renderer import ResumeRenderer


def data_uri_for(filename: str, data: bytes) -> str:
    extension = Path(filename).suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(extension, "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


class ResumeRenderService:
    def __init__(
        self,
        fact_bases: FactBaseRepository,
        versions: VersionRepository,
        renderer: ResumeRenderer,
        exporter: ResumeExporter,
        photo_loader: Optional[Callable[[str], Optional[bytes]]] = None,
        template_loader: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        self.fact_bases = fact_bases
        self.versions = versions
        self.renderer = renderer
        self.exporter = exporter
        self.photo_loader = photo_loader
        self.template_loader = template_loader

    def preview(self, version_id: UUID) -> RenderedResume:
        version = self.versions.get(version_id)
        base = self.fact_bases.get(version.fact_base_id)
        photo_data_uri = ""
        if base.profile.photo and self.photo_loader is not None:
            data = self.photo_loader(base.profile.photo)
            if data:
                photo_data_uri = data_uri_for(base.profile.photo, data)
        template_html = ""
        if base.profile.template and self.template_loader is not None:
            template_html = self.template_loader(base.profile.template) or ""
        rendered = self.renderer.render(
            base, version, photo_data_uri=photo_data_uri, template_html=template_html
        )
        warnings = list(rendered.warnings)
        if version.manual_html and 'data-template-version="3"' not in version.manual_html:
            from resume_agent.rendering.models import RenderWarning
            warnings.append(RenderWarning(
                code="stale_template",
                message="排版模板已更新：点击「恢复自动生成」即可看到新版式（你填写的内容都在）。",
            ))
        return rendered.model_copy(
            update={
                "photo_data_uri": photo_data_uri,
                "markdown": version.manual_markdown or rendered.markdown,
                "html": version.manual_html or rendered.html,
                "warnings": warnings,
            }
        )

    def export(self, version_id: UUID, format: RenderFormat) -> ExportedFile:
        return self.exporter.export(self.preview(version_id), format)
