from pathlib import Path


def load_knowledge_base() -> str:
    base = Path(__file__).parent / "knowledge"
    sections = []

    for path in sorted(base.glob("*.md")):
        sections.append(path.read_text(encoding="utf-8").strip())

    return "\n\n---\n\n".join(sections)