"""学校模板存储：用户上传的 HTML 模板，按档案 ID 落盘。"""

from pathlib import Path
from typing import Optional
from uuid import UUID

MAX_TEMPLATE_BYTES = 2 * 1024 * 1024


class TemplateStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, fact_base_id: UUID, content: str) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        filename = f"{fact_base_id}.html"
        (self.root / filename).write_text(content, encoding="utf-8")
        return filename

    def load(self, filename: str) -> Optional[str]:
        path = self.root / filename
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def delete(self, filename: str) -> None:
        (self.root / filename).unlink(missing_ok=True)

    def save_pdf(self, fact_base_id: UUID, data: bytes) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        filename = f"{fact_base_id}.pdf"
        (self.root / filename).write_bytes(data)
        return filename

    def load_pdf(self, filename: str) -> Optional[bytes]:
        path = self.root / filename
        if not path.is_file():
            return None
        return path.read_bytes()
