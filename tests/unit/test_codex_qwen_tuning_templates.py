"""Client profile selection, usable headroom, and installation custody."""

import importlib.util
import json
from pathlib import Path
import tomllib

import pytest

ROOT = Path("examples/codex/qwen38-tuning")
spec = importlib.util.spec_from_file_location("qwen_tuning_install", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_installed_profiles_select_their_models_and_leave_generation_headroom(tmp_path):
    home = tmp_path / "codex"
    paths = installer.install(home, "https://gateway.example:8443/v1")
    assert len(paths) == 4
    catalog = json.loads((home / "qwen-tuning-models.json").read_text())
    models = {m["slug"]: m for m in catalog["models"]}
    selected = set()
    for path in home.glob("*.config.toml"):
        profile = tomllib.loads(path.read_text())
        model = models[profile["model"]]
        selected.add(model["slug"])
        assert model["auto_compact_token_limit"] + 64_000 < model["context_window"]
        assert model["max_context_window"] == model["context_window"]
        assert Path(profile["model_catalog_json"]).is_absolute()
        assert Path(profile["model_catalog_json"]).read_text() == (home / "qwen-tuning-models.json").read_text()
        provider = profile["model_providers"][profile["model_provider"]]
        assert provider["env_key"] == "OPENAI_API_KEY"
        assert provider["base_url"] == "https://gateway.example:8443/v1"
        assert "experimental_bearer_token" not in provider
        assert profile["approval_policy"] == "on-request"
        assert profile["sandbox_mode"] == "workspace-write"
        assert path.stat().st_mode & 0o777 == 0o600
    assert selected == {"qwen3.8-27b", "qwen3.8-27b-V100", "qwen3.8-27b-rtx3090"}


@pytest.mark.parametrize("symlink", [False, True])
def test_installer_preserves_existing_files_and_creates_no_partial_install(tmp_path, symlink):
    home = tmp_path / "codex"
    home.mkdir()
    existing = home / "qwen-a100.config.toml"
    if symlink:
        target = tmp_path / "private"
        target.write_text("preserve")
        existing.symlink_to(target)
    else:
        existing.write_text("preserve")
    with pytest.raises(FileExistsError):
        installer.install(home, "https://gateway.example/v1")
    assert existing.read_text() == "preserve"
    assert sorted(p.name for p in home.iterdir()) == [existing.name]


@pytest.mark.parametrize("url", [
    "https://user:password@gateway.example/v1",
    "https://gateway.example/v1?api_key=secret",
    "https://gateway.example/wrong",
])
def test_installer_refuses_credentials_in_urls_and_wrong_endpoint(tmp_path, url):
    with pytest.raises(ValueError):
        installer.install(tmp_path / "codex", url)
    assert not (tmp_path / "codex").exists()
