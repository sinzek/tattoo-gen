"""Refresh the runner and prompt snapshots embedded in the two Colab notebooks."""

import base64
import json
from pathlib import Path
import textwrap
import zlib


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = {
    "01_ltx2_duration_test.ipynb": "model_selection_prompts.csv",
    "02_ltx2_baseline_batch.ipynb": "prompts.csv",
}
ASSET_CELL = "tattoogen-assets"


def bundled_cell(csv_name):
    archive = {
        "ltx2_native.py": (ROOT / "notebooks/ltx2_native.py").read_text(encoding="utf-8"),
        csv_name: (ROOT / "data/metadata" / csv_name).read_text(encoding="utf-8"),
    }
    encoded = base64.b64encode(zlib.compress(json.dumps(archive, ensure_ascii=False).encode())).decode()
    strings = "\n".join(f"    {line!r}" for line in textwrap.wrap(encoded, 88))
    source = f"""# Bundled runner and prompt CSV. Regenerate with notebooks/sync_colab_assets.py.
import base64
import zlib

if SOURCE_REPO is None:
    packed = (
{strings}
    )
    assets = json.loads(zlib.decompress(base64.b64decode(packed)))
    runtime_assets = Path("/content/tattoogen-notebook-assets") / {Path(csv_name).stem!r}
    runtime_assets.mkdir(parents=True, exist_ok=True)
    for name, content in assets.items():
        (runtime_assets / name).write_text(content, encoding="utf-8")
    RUNNER = runtime_assets / "ltx2_native.py"
    PROMPT_CSV = runtime_assets / {csv_name!r}
    print("Using the runner and prompt CSV bundled in this notebook.")
else:
    checkout = Path(SOURCE_REPO)
    RUNNER = checkout / "notebooks/ltx2_native.py"
    PROMPT_CSV = checkout / "data/metadata" / {csv_name!r}
    missing = [str(path) for path in (RUNNER, PROMPT_CSV) if not path.is_file()]
    if missing:
        raise FileNotFoundError("Fix SOURCE_REPO or set it to None. Missing: " + ", ".join(missing))
    print("Using the runner and prompts from", checkout)
"""
    return {
        "cell_type": "code", "execution_count": None, "id": ASSET_CELL,
        "metadata": {"cellView": "form"}, "outputs": [], "source": source.splitlines(keepends=True),
    }


def sync(path, csv_name):
    notebook = json.loads(path.read_text(encoding="utf-8"))
    cells = [cell for cell in notebook["cells"] if cell.get("id") != ASSET_CELL]
    config_index = next(i for i, cell in enumerate(cells) if 'drive.mount("/content/drive")' in "".join(cell["source"]))
    cells.insert(config_index + 1, bundled_cell(csv_name))
    notebook["cells"] = cells
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    for name, csv_name in NOTEBOOKS.items():
        sync(ROOT / "notebooks" / name, csv_name)
