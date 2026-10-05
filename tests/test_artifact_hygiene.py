from pathlib import Path
from zipfile import ZipFile

from scripts.build_artifact import build_artifact


def test_artifact_builder_excludes_secrets_and_runtime_files(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / ".env").write_text("SANOVA_SECRET=do-not-package\n", encoding="utf-8")
    (root / ".env.example").write_text("SANOVA_SECRET=\n", encoding="utf-8")
    (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
    cache = root / "__pycache__"
    cache.mkdir()
    (cache / "app.cpython-313.pyc").write_bytes(b"cache")
    pytest_cache = root / ".pytest_cache"
    pytest_cache.mkdir()
    (pytest_cache / "state").write_text("runtime", encoding="utf-8")

    output = tmp_path / "artifact.zip"
    count = build_artifact(root, output)

    with ZipFile(output) as archive:
        names = set(archive.namelist())

    assert count == 2
    assert ".env" not in names
    assert ".env.example" in names
    assert "app.py" in names
    assert all("__pycache__" not in name for name in names)
    assert all(".pytest_cache" not in name for name in names)
    assert all(not name.endswith((".pyc", ".pyo")) for name in names)


def test_artifact_builder_excludes_output_when_output_is_inside_root(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
    output = root / "dist" / "sanova-source.zip"

    count = build_artifact(root, output)

    with ZipFile(output) as archive:
        names = set(archive.namelist())

    assert count == 1
    assert "app.py" in names
    assert "dist/sanova-source.zip" not in names
