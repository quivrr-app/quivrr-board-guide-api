from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(".").resolve()
output = root / "board-guide-api.zip"

include_roots = [
    root / "main.py",
    root / "startup.sh",
    root / "requirements.txt",
    root / "app",
]

skip_parts = {
    "__pycache__",
    ".git",
    "venv",
    ".venv",
    "zip-test",
}

with ZipFile(output, "w", ZIP_DEFLATED) as z:
    for item in include_roots:
        if item.is_file():
            z.write(item, item.relative_to(root).as_posix())
            continue

        for path in item.rglob("*"):
            if any(part in skip_parts for part in path.parts):
                continue
            if path.is_file():
                z.write(path, path.relative_to(root).as_posix())

print(f"Created {output}")
