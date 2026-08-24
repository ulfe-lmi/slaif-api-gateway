#!/usr/bin/env python3
"""Validate repository Markdown structure, links, anchors, reachability, and branding."""

from __future__ import annotations

import re
import sys
from collections import Counter, deque
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
ROOT_DOCS = (ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "CHANGELOG.md")
MARKDOWN_FILES = (*ROOT_DOCS, *sorted((ROOT / "docs").rglob("*.md")))
ARCHIVE_BODY_PATTERNS = (
    "docs/releases/v",
    "docs/security/reviews/2026-",
    "docs/verification/2026-",
)
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _markdown_lines(path: Path):
    in_fence = False
    fence = ""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.lstrip()
        if not in_fence and stripped.startswith(("```", "~~~")):
            in_fence = True
            fence = stripped[:3]
            continue
        if in_fence and stripped.startswith(fence):
            in_fence = False
            fence = ""
            continue
        if not in_fence:
            yield number, line


def _slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("`", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "-", text)


def _anchors(path: Path) -> set[str]:
    counts: Counter[str] = Counter()
    anchors: set[str] = set()
    for _, line in _markdown_lines(path):
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = _slug(match.group(2))
        suffix = counts[base]
        counts[base] += 1
        anchors.add(base if suffix == 0 else f"{base}-{suffix}")
    return anchors


def _link_target(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def _resolve_link(source: Path, target: str) -> tuple[Path | None, str]:
    if not target or target.startswith(("http://", "https://", "mailto:", "data:")):
        return None, ""
    path_text, _, anchor = target.partition("#")
    if not path_text:
        return source, unquote(anchor)
    decoded = unquote(path_text)
    path = (ROOT / decoded.lstrip("/")) if decoded.startswith("/") else (source.parent / decoded)
    resolved = path.resolve()
    if resolved.is_dir():
        resolved = resolved / "README.md"
    return resolved, unquote(anchor)


def _is_historical_body(path: Path) -> bool:
    relative = _relative(path)
    return any(relative.startswith(prefix) for prefix in ARCHIVE_BODY_PATTERNS)


def check() -> list[str]:
    errors: list[str] = []
    graph: dict[Path, set[Path]] = {path.resolve(): set() for path in MARKDOWN_FILES}
    anchor_cache = {path.resolve(): _anchors(path) for path in MARKDOWN_FILES}

    for path in MARKDOWN_FILES:
        resolved_source = path.resolve()
        headings: list[tuple[int, int]] = []
        for number, line in _markdown_lines(path):
            heading = HEADING_RE.match(line)
            if heading:
                headings.append((number, len(heading.group(1))))
            for match in LINK_RE.finditer(line):
                target = _link_target(match.group(1))
                resolved, anchor = _resolve_link(path, target)
                if resolved is None:
                    continue
                if not resolved.exists():
                    errors.append(f"{_relative(path)}:{number}: missing link target {target}")
                    continue
                if resolved.suffix.lower() == ".md" and resolved in graph:
                    graph[resolved_source].add(resolved)
                    if anchor and anchor not in anchor_cache[resolved]:
                        errors.append(
                            f"{_relative(path)}:{number}: missing anchor #{anchor} in {_relative(resolved)}"
                        )

        if not _is_historical_body(path):
            h1 = [number for number, level in headings if level == 1]
            if len(h1) != 1:
                errors.append(f"{_relative(path)}: expected one H1, found {len(h1)}")
            previous = 0
            for number, level in headings:
                if previous and level > previous + 1:
                    errors.append(
                        f"{_relative(path)}:{number}: heading jumps from H{previous} to H{level}"
                    )
                previous = level

    roots = [ROOT / "README.md", ROOT / "docs" / "README.md"]
    visited: set[Path] = set()
    queue = deque(path.resolve() for path in roots)
    while queue:
        path = queue.popleft()
        if path in visited:
            continue
        visited.add(path)
        queue.extend(graph.get(path, ()))
    for path in MARKDOWN_FILES:
        if path.resolve() not in visited:
            errors.append(f"{_relative(path)}: orphaned from README/docs navigation")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not readme.startswith('<div align="center">'):
        errors.append("README.md: brand block must remain first")
    for fragment in (
        'href="https://www.slaif.si"',
        'src="https://slaif.si/img/logos/SLAIF_logo_ANG_barve.svg"',
        'alt="SLAIF"',
        "docs/product-scope.md",
        "docs/README.md",
    ):
        if fragment not in readme:
            errors.append(f"README.md: missing required brand/navigation fragment {fragment}")

    return errors


def main() -> int:
    errors = check()
    if errors:
        for error in errors:
            print(error)
        print(f"DOCUMENTATION_CHECK=FAIL errors={len(errors)}")
        return 1
    print(f"DOCUMENTATION_CHECK=OK files={len(MARKDOWN_FILES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
