"""Create a clean manual-install ZIP with only integration source and translations."""

import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / "dist/hcc100-local-0.1.3.zip"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((root / "custom_components/hcc100_local").rglob("*")):
        if path.is_file() and path.suffix in (".py", ".json"):
            archive.write(path, path.relative_to(root))
print(output)
