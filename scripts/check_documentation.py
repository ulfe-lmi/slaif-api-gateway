#!/usr/bin/env python3
"""Validate repository Markdown structure, links, anchors, reachability, branding, and readiness-record as-of markers."""

from __future__ import annotations

import re
import sys
from collections import Counter, deque
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
ROOT_DOC_NAMES = (
    "README.md",
    "QUICKSTART.md",
    "INSTALL.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
)
ARCHIVE_BODY_PATTERNS = (
    "docs/releases/v",
    "docs/security/reviews/2026-",
    "docs/verification/2026-",
)
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
AS_OF_MARKER_RE = re.compile(r"<!--\s*readiness-record-as-of\s*:\s*([0-9a-f]{40})\s*-->")
AS_OF_MARKER_CANDIDATE_RE = re.compile(r"<!--\s*readiness-record-as-of\s*:\s*(.*?)\s*-->")
AS_OF_SHA_RE = re.compile(r"[0-9a-f]{40}")
AS_OF_CLAIM_RE = re.compile(r"current verification/readiness", re.IGNORECASE)
BETA_READINESS_REL = "docs/beta-readiness.md"


def markdown_files(root: Path) -> list[Path]:
    root_docs = [root / name for name in ROOT_DOC_NAMES if (root / name).is_file()]
    docs_dir = root / "docs"
    doc_files = sorted(docs_dir.rglob("*.md")) if docs_dir.is_dir() else []
    return [*root_docs, *doc_files]


MARKDOWN_FILES = markdown_files(ROOT)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


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


def _resolve_link(source: Path, target: str, root: Path) -> tuple[Path | None, str]:
    if not target or target.startswith(("http://", "https://", "mailto:", "data:")):
        return None, ""
    path_text, _, anchor = target.partition("#")
    if not path_text:
        return source, unquote(anchor)
    decoded = unquote(path_text)
    path = (root / decoded.lstrip("/")) if decoded.startswith("/") else (source.parent / decoded)
    resolved = path.resolve()
    if resolved.is_dir():
        resolved = resolved / "README.md"
    return resolved, unquote(anchor)


def _is_historical_body(path: Path, root: Path) -> bool:
    relative = _relative(path, root)
    return any(relative.startswith(prefix) for prefix in ARCHIVE_BODY_PATTERNS)


def _asof_errors(path: Path, root: Path) -> list[str]:
    lines = list(_markdown_lines(path))
    body = "\n".join(line for _, line in lines)
    relative = _relative(path, root)
    is_beta_record = relative == BETA_READINESS_REL
    has_claim = (
        not _is_historical_body(path, root)
        and AS_OF_CLAIM_RE.search(body) is not None
    )
    if not is_beta_record and not has_claim:
        return []
    rule = "asof-R2" if is_beta_record else "asof-R1"

    candidates: list[tuple[int, str]] = []
    for number, line in lines:
        for match in AS_OF_MARKER_CANDIDATE_RE.finditer(line):
            candidates.append((number, match.group(1).strip()))

    errors: list[str] = []
    valid_shas: list[str] = []
    for number, payload in candidates:
        if AS_OF_SHA_RE.fullmatch(payload) is None:
            errors.append(
                f"{relative}:{number}: [{rule}] malformed readiness-record-as-of "
                f"marker payload"
            )
        else:
            valid_shas.append(payload)
    if not valid_shas:
        errors.append(f"{relative}: [{rule}] missing readiness-record-as-of marker")
    elif len(valid_shas) > 1:
        errors.append(
            f"{relative}: [{rule}] multiple readiness-record-as-of markers "
            f"({len(valid_shas)})"
        )
    else:
        sha = valid_shas[0]
        prose = AS_OF_MARKER_CANDIDATE_RE.sub("", body)
        if sha not in prose:
            errors.append(
                f"{relative}: [{rule}] readiness-record-as-of SHA {sha} not found "
                f"in document prose"
            )
    return errors


def check(root: Path | None = None) -> list[str]:
    root = (root if root is not None else ROOT).resolve()
    files = markdown_files(root)
    errors: list[str] = []
    graph: dict[Path, set[Path]] = {path.resolve(): set() for path in files}
    anchor_cache = {path.resolve(): _anchors(path) for path in files}

    for path in files:
        resolved_source = path.resolve()
        headings: list[tuple[int, int]] = []
        for number, line in _markdown_lines(path):
            heading = HEADING_RE.match(line)
            if heading:
                headings.append((number, len(heading.group(1))))
            for match in LINK_RE.finditer(line):
                target = _link_target(match.group(1))
                resolved, anchor = _resolve_link(path, target, root)
                if resolved is None:
                    continue
                if not resolved.exists():
                    errors.append(f"{_relative(path, root)}:{number}: missing link target {target}")
                    continue
                if resolved.suffix.lower() == ".md" and resolved in graph:
                    graph[resolved_source].add(resolved)
                    if anchor and anchor not in anchor_cache[resolved]:
                        errors.append(
                            f"{_relative(path, root)}:{number}: missing anchor #{anchor} in "
                            f"{_relative(resolved, root)}"
                        )

        if not _is_historical_body(path, root):
            h1 = [number for number, level in headings if level == 1]
            if len(h1) != 1:
                errors.append(f"{_relative(path, root)}: expected one H1, found {len(h1)}")
            previous = 0
            for number, level in headings:
                if previous and level > previous + 1:
                    errors.append(
                        f"{_relative(path, root)}:{number}: heading jumps from H{previous} to H{level}"
                    )
                previous = level

        errors.extend(_asof_errors(path, root))

    roots = [root / "README.md", root / "docs" / "README.md"]
    visited: set[Path] = set()
    queue = deque(path.resolve() for path in roots)
    while queue:
        path = queue.popleft()
        if path in visited:
            continue
        visited.add(path)
        queue.extend(graph.get(path, ()))
    for path in files:
        if path.resolve() not in visited:
            errors.append(f"{_relative(path, root)}: orphaned from README/docs navigation")

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

    # Front-door navigation for the public entry points. These rules are
    # conditional on the entry points existing in the checked tree so that
    # synthetic checker trees keep working while the real repository must
    # expose the canonical quickstart/install hierarchy.
    local_readme = root / "README.md"
    if local_readme.is_file():
        local_readme_text = local_readme.read_text(encoding="utf-8")
        for name in ("QUICKSTART.md", "INSTALL.md"):
            if (root / name).is_file() and name not in local_readme_text:
                errors.append(f"README.md: missing front-door link to {name}")
    quickstart_stub = root / "docs" / "quickstart.md"
    if quickstart_stub.is_file() and (root / "QUICKSTART.md").is_file():
        stub_text = quickstart_stub.read_text(encoding="utf-8")
        for target in ("../QUICKSTART.md", "../INSTALL.md", "first-time-operator-guide.md"):
            if target not in stub_text:
                errors.append(f"docs/quickstart.md: stub missing pointer to {target}")

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
