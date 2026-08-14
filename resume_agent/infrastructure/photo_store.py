"""照片文件存储：按档案 ID 落盘，支持 JPG/PNG/WebP。"""

from pathlib import Path
from typing import Optional
from uuid import UUID

ALLOWED_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

MAX_PHOTO_BYTES = 5 * 1024 * 1024


class PhotoStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path_for(self, filename: str) -> Path:
        return self.root / filename

    def _existing(self, fact_base_id: UUID) -> Optional[Path]:
        if not self.root.is_dir():
            return None
        for extension in ALLOWED_EXTENSIONS:
            candidate = self.root / f"{fact_base_id}{extension}"
            if candidate.is_file():
                return candidate
        return None

    def save(self, fact_base_id: UUID, data: bytes, extension: str) -> str:
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError(f"unsupported photo extension: {extension}")
        self.root.mkdir(parents=True, exist_ok=True)
        for existing_extension in ALLOWED_EXTENSIONS:
            old = self.root / f"{fact_base_id}{existing_extension}"
            if old.exists() and existing_extension != extension:
                old.unlink(missing_ok=True)
        filename = f"{fact_base_id}{extension}"
        self._path_for(filename).write_bytes(data)
        return filename

    def load(self, filename: str) -> Optional[bytes]:
        path = self._path_for(filename)
        if not path.is_file():
            return None
        return path.read_bytes()

    def media_type(self, filename: str) -> str:
        extension = Path(filename).suffix.lower()
        return ALLOWED_EXTENSIONS.get(extension, "application/octet-stream")

    def delete(self, filename: str) -> None:
        self._path_for(filename).unlink(missing_ok=True)

    def find(self, fact_base_id: UUID) -> Optional[str]:
        existing = self._existing(fact_base_id)
        return existing.name if existing else None
