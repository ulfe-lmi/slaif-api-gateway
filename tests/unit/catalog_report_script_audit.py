"""192-a test support: fixed-trusted-script audit for generated reports.

The generated catalog ``REVIEW.html`` embeds exactly ONE ``<script>``
element: the fixed, reviewed, self-contained sorting source
(``web/static/js/table-sort.js``), byte-identical at generation time.

This module parses a report with the stdlib ``html.parser`` (no regex
tag matching — CodeQL py/bad-tag-filter) and proves the executable
surface is exactly that one attribute-free script with the exact fixed
bytes, while also collecting the document structure so callers can make
data-level assertions:

- no inline event handlers (``on*``) on any element;
- no external resource loaders (``src=``) on any element;
- no forbidden real tags (link/iframe/object/embed/form/video/audio/img);
- visible (non-script, non-style) text, so unsafe-data assertions
  (e.g. a malformed port never reaching the visible DOM) are evaluated
  on report data excluding the verified fixed script body.

Test support only: no product code imports this module, and it adds no
dependencies or parsers beyond the Python standard library.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

FIXED_SORT_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "slaif_gateway"
    / "web"
    / "static"
    / "js"
    / "table-sort.js"
)

FORBIDDEN_REPORT_TAGS = frozenset(
    {"link", "iframe", "object", "embed", "form", "video", "audio", "img"}
)


class CatalogReportAuditor(HTMLParser):
    """Collect scripts, styles, attributes, and visible text from a report."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[dict] = []
        self.styles: list[str] = []
        self.event_handlers: list[str] = []
        self.resource_loaders: list[str] = []
        self.forbidden_tags: list[str] = []
        self.attributes: list[tuple[str, str, str | None]] = []
        self.script_start_count = 0
        self.script_end_count = 0
        self._visible_parts: list[str] = []
        self._in_script = False
        self._in_style = False
        self._script_attrs: list[tuple[str, str | None]] = []
        self._script_body: list[str] = []
        self._style_body: list[str] = []

    @property
    def open_script(self) -> bool:
        """True when a <script> start tag was never closed."""
        return self._in_script

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in FORBIDDEN_REPORT_TAGS:
            self.forbidden_tags.append(tag)
        for name, value in attrs:
            lname = name.lower()
            self.attributes.append((tag, lname, value))
            if lname.startswith("on"):
                self.event_handlers.append(f"{tag} {name}")
            elif lname == "src":
                self.resource_loaders.append(f"{tag} {name}")
        if tag == "script":
            self.script_start_count += 1
            self._in_script = True
            self._script_attrs = list(attrs)
            self._script_body = []
        elif tag == "style":
            self._in_style = True
            self._style_body = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_script:
            self.script_end_count += 1
            self._in_script = False
            self.scripts.append(
                {"attrs": self._script_attrs, "body": "".join(self._script_body)}
            )
        elif tag == "style":
            self._in_style = False
            self.styles.append("".join(self._style_body))

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_body.append(data)
        elif self._in_style:
            self._style_body.append(data)
        else:
            self._visible_parts.append(data)

    @property
    def visible_text(self) -> str:
        return "".join(self._visible_parts)

    def href_values(self) -> list[str]:
        return [value for _tag, name, value in self.attributes if name == "href" and value]


def audit_fixed_report_script(
    html_text: str, *, fixed_source: str | None = None
) -> CatalogReportAuditor:
    """Assert the report's executable surface is exactly the one fixed
    script: a single ``<script>`` with no attributes, byte-identical to
    ``web/static/js/table-sort.js``, plus no inline event handlers, no
    external resource loaders, and no forbidden real tags.

    Returns the populated auditor so callers can keep asserting on
    report data (visible text, href values, styles) with the verified
    script body excluded.
    """
    auditor = CatalogReportAuditor()
    auditor.feed(html_text)
    auditor.close()
    # Count START tags (an extra unclosed <script> has no end tag to
    # count) and require the element to be closed/balanced.
    assert auditor.script_start_count == 1, (
        f"expected exactly one <script> start tag, found {auditor.script_start_count}"
    )
    assert not auditor.open_script, "a <script> element was never closed"
    assert auditor.script_end_count == 1, (
        f"expected exactly one closing </script>, found {auditor.script_end_count}"
    )
    script = auditor.scripts[0]
    assert script["attrs"] == [], (
        f"the fixed script must carry no attributes, got {script['attrs']}"
    )
    expected = (
        fixed_source if fixed_source is not None else FIXED_SORT_SCRIPT.read_text(encoding="utf-8")
    )
    assert script["body"] == expected, (
        "embedded script body differs from web/static/js/table-sort.js"
    )
    assert auditor.event_handlers == [], (
        f"inline event handlers are forbidden in generated reports: {auditor.event_handlers}"
    )
    assert auditor.resource_loaders == [], (
        f"external resource loaders are forbidden in generated reports: "
        f"{auditor.resource_loaders}"
    )
    assert auditor.forbidden_tags == [], (
        f"forbidden real tags in generated report: {auditor.forbidden_tags}"
    )
    return auditor
