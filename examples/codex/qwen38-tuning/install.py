"""Install new client profiles without storing keys or overwriting existing files."""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def install(destination: Path, gateway_url: str) -> list[Path]:
    parsed = urlsplit(gateway_url)
    if (
        parsed.scheme not in {"https", "http"} or not parsed.hostname
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ValueError("Supply the gateway HTTP(S) /v1 URL without credentials.")
    source = Path(__file__).resolve().parent
    destination = destination.expanduser().resolve()
    catalog = destination / "qwen-tuning-models.json"
    contents = {catalog: (source / catalog.name).read_text()}
    for name in ("qwen-v100", "qwen-a100", "qwen-rtx3090"):
        text = (source / (name + ".config.toml")).read_text()
        text = text.replace('"https://gateway.example/v1"', json.dumps(gateway_url.rstrip("/")))
        text = text.replace('"qwen-tuning-models.json"', json.dumps(str(catalog)))
        contents[destination / (name + ".config.toml")] = text
    if any(path.exists() or path.is_symlink() for path in contents):
        raise FileExistsError("A destination profile/catalog already exists; review it before replacing.")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    written = []
    try:
        for path, text in contents.items():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(text)
            written.append(path)
    except Exception:
        for path in written:
            path.unlink()
        raise
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-url", default=os.environ.get("OPENAI_BASE_URL"))
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", "~/.codex")))
    args = parser.parse_args()
    if not args.gateway_url:
        parser.error("Set OPENAI_BASE_URL or supply --gateway-url.")
    for path in install(args.codex_home, args.gateway_url):
        print(path)
