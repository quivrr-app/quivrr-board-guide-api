"""Immutable, checksummed loader for Bodhi Surf Knowledge Pack v1."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from jsonschema import Draft202012Validator


PACK_ROOT = Path(__file__).parent / "knowledge" / "surf_domain" / "bodhi_surf_knowledge_pack_v1"


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class SurfDomainKnowledge:
    pack_id: str
    version: str
    documents: MappingProxyType

    def document(self, name: str):
        return self.documents[name]

    @property
    def stages(self):
        return self.document("01_surfer_stages.json")

    @property
    def stage_matrix(self):
        return self.document("03_stage_family_matrix.json")

    @property
    def premium_positioning(self):
        return self.document("16_premium_catalogue_positioning.json")


@lru_cache(maxsize=1)
def load_surf_domain_knowledge() -> SurfDomainKnowledge:
    manifest_path = PACK_ROOT / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema_path = PACK_ROOT / "schemas" / "knowledge_document.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    documents = {}
    for item in manifest.get("files", []):
        relative = item["path"]
        content = (PACK_ROOT / relative).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != item["sha256"] or len(content) != item["bytes"]:
            raise RuntimeError(f"Bodhi surf knowledge pack validation failed: {relative}")
        if relative.startswith("knowledge/") and relative.endswith(".json"):
            document = json.loads(content.decode("utf-8"))
            errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
            if errors:
                raise RuntimeError(
                    f"Bodhi surf knowledge schema validation failed: {relative}: {errors[0].message}"
                )
            documents[Path(relative).name] = _freeze(document)
    metadata = documents.get("00_pack_metadata.json")
    if len(documents) != 20 or not metadata:
        raise RuntimeError("Bodhi surf knowledge pack is incomplete")
    return SurfDomainKnowledge(metadata["pack_id"], metadata["version"], MappingProxyType(documents))
