"""Bounded parser and immutable loader for Codex compatibility profile DATA.

These unit tests pin the reviewed data contract: the exact schema, the
finite grammar-trait vocabulary, the engine-fixed hard caps, the reserved
legacy revisions, the canonical digest, the safe bounded file loader, and
the deep immutability of the returned snapshot.  They are pure in-memory
tests (plus bounded temp-file and monkeypatched-read fixtures); no
database, network, or provider dependency.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from slaif_gateway.modules.codex_profile_data import (
    CodexProfileData,
    CodexProfileDataError,
    canonical_profile_digest,
    load_codex_profile_file,
    load_default_codex_profile,
    parse_codex_profile_data,
)

PACKAGED_PROFILE = Path("app/slaif_gateway/modules/clients/profiles/codex_0162.json")
PACKAGED_PROFILE_DIGEST = "1d1e5b05587d1a8bf1f90057e43e357b7b3627dc3268ec09108e5fafa52e6d11"
DEFAULT_BASE = PACKAGED_PROFILE.read_text()


def _parse(document: dict) -> CodexProfileData:
    return parse_codex_profile_data(json.dumps(document, indent=2))


def _expect_code(text: str, code: str) -> None:
    with pytest.raises(CodexProfileDataError) as excinfo:
        parse_codex_profile_data(text)
    assert excinfo.value.code == code
    assert excinfo.value.safe_message
    # Safe errors never echo document content.
    assert "evil" not in excinfo.value.safe_message


def test_packaged_default_profile_is_revision8_with_stable_digest() -> None:
    profile = load_default_codex_profile()
    assert isinstance(profile, CodexProfileData)
    assert profile.schema_version == 1
    assert profile.module_id == "codex-0.162-responses-v1"
    assert profile.revision == "8"
    assert profile.digest == PACKAGED_PROFILE_DIGEST
    assert profile.builtin_names == frozenset({"functions", "multi_agent_v1"})
    assert profile.connector_prefixes == ("mcp__codex_apps__",)
    assert profile.max_namespaces == 16
    assert profile.max_total_tools == 256
    assert profile.max_tools_per_namespace == 256
    assert profile.max_schema_depth == 16
    assert profile.max_schema_properties == 4_096
    assert profile.max_tool_description_bytes == 20_000
    assert profile.max_total_description_bytes == 262_144
    assert profile.max_declaration_bytes == 589_824
    # Default behavior is exactly the accepted 190-a dialect: builtin
    # strict, connector one bounded leading underscore.
    assert profile.builtin_name_rule.max_leading_underscores == 0
    assert profile.connector_name_rule.max_leading_underscores == 1
    assert profile.is_tool_name_allowed("connector", "read_page")
    assert profile.is_tool_name_allowed("connector", "_read_page")
    assert not profile.is_tool_name_allowed("connector", "__read_page")
    assert not profile.is_tool_name_allowed("builtin", "_read_page")
    assert profile.classify_namespace_name("functions") == "builtin"
    assert profile.classify_namespace_name("mcp__codex_apps__github") == "connector"
    assert profile.classify_namespace_name("functions2") is None
    assert profile.classify_namespace_name("mcp__other__x") is None


def test_canonical_digest_is_format_independent_and_data_bound() -> None:
    document = json.loads(DEFAULT_BASE)
    assert canonical_profile_digest(document) == PACKAGED_PROFILE_DIGEST
    # Key order and whitespace must not change the digest of the same data.
    reordered = {
        "limits": document["limits"],
        "module_id": document["module_id"],
        "namespace_rules": document["namespace_rules"],
        "provenance": document["provenance"],
        "revision": document["revision"],
        "schema_version": document["schema_version"],
        "tool_name_rules": document["tool_name_rules"],
    }
    assert canonical_profile_digest(reordered) == PACKAGED_PROFILE_DIGEST
    assert parse_codex_profile_data(json.dumps(reordered)).digest == PACKAGED_PROFILE_DIGEST
    # Any data change changes the digest.
    changed = copy.deepcopy(document)
    changed["limits"]["max_namespaces"] = 15
    assert canonical_profile_digest(changed) != PACKAGED_PROFILE_DIGEST


def test_revisions_are_bounded_decimal_at_least_three() -> None:
    for revision in ("3", "9", "10", "19", "20", "100", "999999999"):
        profile = _parse({**json.loads(DEFAULT_BASE), "revision": revision})
        assert profile.revision == revision
    for bad in ("1", "2", "0", "03", "010", "", "3.0", "-3", "1e1", "10000000000"):
        _expect_code(
            DEFAULT_BASE.replace('"revision": "8"', f'"revision": "{bad}"'),
            "revision_reserved_or_invalid",
        )
    _expect_code(
        DEFAULT_BASE.replace('"revision": "8"', '"revision": 3'),
        "revision_reserved_or_invalid",
    )


def test_schema_version_strict_int() -> None:
    for bad in ("true", "1.0", '"1"', "2", "null"):
        _expect_code(
            DEFAULT_BASE.replace('"schema_version": 1', f'"schema_version": {bad}'),
            "schema_invalid",
        )


def test_unknown_fields_and_wrong_types_are_rejected() -> None:
    _expect_code(DEFAULT_BASE.rstrip("\n")[:-1] + ', "extra": 1}', "schema_invalid")
    _expect_code(
        DEFAULT_BASE.replace('"module_id": "codex-0.162-responses-v1"', '"module_id": "other"'),
        "module_id_mismatch",
    )
    _expect_code(
        DEFAULT_BASE.replace('"suffix_initial": "lowercase_ascii"', '"suffix_initial": "shouty"'),
        "grammar_trait_unknown",
    )
    _expect_code(
        DEFAULT_BASE.replace('"initial": "lowercase_ascii"', '"initial": "shouty"'),
        "grammar_trait_unknown",
    )
    _expect_code(
        DEFAULT_BASE.replace('"max_namespaces": 16', '"max_namespaces": true'),
        "limit_above_hard_cap",
    )
    _expect_code(
        DEFAULT_BASE.replace('"max_namespaces": 16', '"max_namespaces": 0'),
        "limit_above_hard_cap",
    )


def test_limits_may_only_lower_engine_hard_caps() -> None:
    for field, hard_cap in (
        ("max_namespaces", 16),
        ("max_total_tools", 256),
        ("max_tools_per_namespace", 256),
        ("max_schema_depth", 16),
        ("max_schema_properties", 4_096),
        ("max_tool_description_bytes", 20_000),
        ("max_total_description_bytes", 262_144),
        ("max_declaration_bytes", 589_824),
    ):
        _expect_code(_replace_limit(DEFAULT_BASE, field, hard_cap + 1), "limit_above_hard_cap")
        lowered = _replace_limit(DEFAULT_BASE, field, max(1, hard_cap - 1))
        assert _parse(json.loads(lowered)) is not None


def _replace_limit(base: str, field: str, value: int) -> str:
    document = json.loads(base)
    document["limits"][field] = value
    return json.dumps(document, indent=2)


def test_leading_underscore_bound_is_derived_from_total_cap() -> None:
    # Engine bound: at least one initial letter must fit in the cap, for
    # both categories; the data value itself is policy.
    for category in ("builtin", "connector"):
        _expect_code(
            _replace_name_rule(
                DEFAULT_BASE, category, {"max_characters": 64, "max_leading_underscores": 64}
            ),
            "limit_above_hard_cap",
        )
        _expect_code(
            _replace_name_rule(
                DEFAULT_BASE, category, {"max_characters": 2, "max_leading_underscores": 2}
            ),
            "limit_above_hard_cap",
        )
    profile = _parse(
        json.loads(_replace_name_rule(DEFAULT_BASE, "connector", {"max_leading_underscores": 2}))
    )
    assert profile.is_tool_name_allowed("connector", "__double")
    assert not profile.is_tool_name_allowed("connector", "___triple")
    builtin_relaxed = _parse(
        json.loads(_replace_name_rule(DEFAULT_BASE, "builtin", {"max_leading_underscores": 1}))
    )
    assert builtin_relaxed.is_tool_name_allowed("builtin", "_x")


def _replace_name_rule(base: str, category: str, overrides: dict) -> str:
    document = json.loads(base)
    rule = document["tool_name_rules"][category]
    rule.update(overrides)
    return json.dumps(document, indent=2)


def test_finite_mixed_case_traits_are_file_only() -> None:
    document = json.loads(DEFAULT_BASE)
    document["revision"] = "5"
    document["tool_name_rules"]["connector"] = {
        "initial": "ascii_letter",
        "tail": "ascii_letters_digits_underscore_hyphen",
        "max_characters": 64,
        "max_leading_underscores": 3,
    }
    profile = _parse(document)
    # Future mixed-case names are accepted through DATA only, alongside
    # the bounded leading-underscore example.
    assert profile.is_tool_name_allowed("connector", "FooBar")
    assert profile.is_tool_name_allowed("connector", "___FutureTool")
    assert profile.is_tool_name_allowed("connector", "_read_page")
    assert not profile.is_tool_name_allowed("connector", "foo_bar.baz")
    assert not profile.is_tool_name_allowed("connector", "9Foo")
    assert not profile.is_tool_name_allowed("connector", "____FutureTool")
    assert not profile.is_tool_name_allowed("builtin", "FooBar")
    # The packaged default stays lowercase-strict.
    default = load_default_codex_profile()
    assert not default.is_tool_name_allowed("connector", "FooBar")
    # Namespace suffixes share the same finite trait vocabulary.
    document2 = json.loads(DEFAULT_BASE)
    document2["revision"] = "6"
    document2["namespace_rules"]["suffix_initial"] = "ascii_letter"
    document2["namespace_rules"]["suffix_tail"] = "ascii_letters_digits_underscore_hyphen"
    profile2 = _parse(document2)
    assert profile2.classify_namespace_name("mcp__codex_apps__Foo") == "connector"
    assert profile2.classify_namespace_name("mcp__codex_apps__Foo_Bar-2") == "connector"
    assert profile2.classify_namespace_name("mcp__codex_apps__9Foo") is None
    _expect_code(
        _replace_name_rule(DEFAULT_BASE, "connector", {"tail": "anything_at_all"}),
        "grammar_trait_unknown",
    )


def test_namespace_vocabulary_is_bounded_and_unambiguous() -> None:
    _expect_code(
        DEFAULT_BASE.replace('"functions",', '"functions", "functions",'),
        "namespace_rules_invalid",
    )
    _expect_code(
        DEFAULT_BASE.replace('"functions",', '"functions", "Evil Name",'),
        "namespace_rules_invalid",
    )
    _expect_code(
        DEFAULT_BASE.replace('"mcp__codex_apps__"', '"MCP__"'),
        "namespace_rules_invalid",
    )
    _expect_code(
        DEFAULT_BASE.replace('"mcp__codex_apps__"', '"mcp__codex_apps__", "mcp__"', 1),
        "namespace_rules_invalid",
    )
    # A builtin literal colliding with a connector prefix is ambiguous.
    _expect_code(
        DEFAULT_BASE.replace('"functions",', '"mcp__codex_apps__x",', 1).replace(
            '"mcp__codex_apps__"', '"mcp__"'
        ),
        "namespace_rules_invalid",
    )


def test_provenance_is_bounded_ascii() -> None:
    _expect_code(
        DEFAULT_BASE.replace('"cli_version": "0.162.1"', '"cli_version": "0.162"'),
        "provenance_invalid",
    )
    _expect_code(
        DEFAULT_BASE.replace('"cli_version": "0.162.1"', '"cli_version": "\u0660.1.1"'),
        "provenance_invalid",
    )
    _expect_code(
        DEFAULT_BASE.replace(
            '"source_commit": "092d3acd6bec3e3a14bdc7e7a2810ab628ab759d"',
            '"source_commit": "ZZZ"',
        ),
        "provenance_invalid",
    )


def test_duplicate_keys_and_nonfinite_values_are_rejected() -> None:
    _expect_code(
        DEFAULT_BASE.replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'),
        "duplicate_key",
    )
    _expect_code(
        DEFAULT_BASE.replace('"max_namespaces": 16', '"max_namespaces": NaN'),
        "non_finite_value",
    )
    _expect_code(
        DEFAULT_BASE.replace('"max_namespaces": 16', '"max_namespaces": Infinity'),
        "non_finite_value",
    )
    _expect_code(DEFAULT_BASE + " NaN", "malformed_json")
    _expect_code("{]", "malformed_json")
    _expect_code("[]", "schema_invalid")
    _expect_code("", "malformed_json")


def test_oversize_documents_are_rejected() -> None:
    document = json.loads(DEFAULT_BASE)
    document["padding"] = "a" * 70_000
    try:
        parse_codex_profile_data(json.dumps(document))
    except CodexProfileDataError as exc:
        assert exc.code == "profile_too_large"
    else:
        raise AssertionError("expected profile_too_large")


def test_snapshot_is_deeply_immutable() -> None:
    profile = load_default_codex_profile()
    with pytest.raises(AttributeError):
        profile.revision = "9"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        profile.builtin_names.add("x")
    with pytest.raises(AttributeError):
        profile.connector_name_rule.max_characters = 1  # type: ignore[misc]


def test_loader_rejects_unsafe_or_invalid_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = tmp_path / "good.json"
    good.write_text(DEFAULT_BASE)
    assert load_codex_profile_file(good).digest == PACKAGED_PROFILE_DIGEST

    missing = tmp_path / "missing.json"
    with pytest.raises(CodexProfileDataError) as excinfo:
        load_codex_profile_file(missing)
    assert excinfo.value.code == "profile_unreadable"

    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe{")
    with pytest.raises(CodexProfileDataError) as excinfo:
        load_codex_profile_file(binary)
    assert excinfo.value.code == "malformed_json"

    big = tmp_path / "big.json"
    big.write_bytes(b"{" + b'"a"' * (65_537))
    with pytest.raises(CodexProfileDataError) as excinfo:
        load_codex_profile_file(big)
    assert excinfo.value.code == "profile_too_large"

    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(CodexProfileDataError) as excinfo:
        load_codex_profile_file(fifo)
    assert excinfo.value.code == "profile_unreadable"

    # Embedded NUL in the path is a ValueError from os.open; it must map
    # to the same safe profile error.
    with pytest.raises(CodexProfileDataError) as excinfo:
        load_codex_profile_file(str(tmp_path) + "\0x.json")
    assert excinfo.value.code == "profile_unreadable"


def test_loader_rejects_growth_and_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = tmp_path / "good.json"
    good.write_text(DEFAULT_BASE)
    original_read = os.read
    state: dict[str, int] = {"calls": 0}

    def fake_read(fd: int, size: int) -> bytes:
        state["calls"] += 1
        first = original_read(fd, size)
        if state["calls"] == 1:
            return first
        if state["calls"] == 2:
            return b'"extra": 1,'  # growth after the fstat snapshot
        return b""

    monkeypatch.setattr(os, "read", fake_read)
    with pytest.raises(CodexProfileDataError) as excinfo:
        load_codex_profile_file(good)
    assert excinfo.value.code == "profile_unreadable"

    state["calls"] = 0

    def fake_read_oversize(fd: int, size: int) -> bytes:
        state["calls"] += 1
        first = original_read(fd, size)
        if state["calls"] == 1:
            return first
        if state["calls"] == 2:
            return b"a" * 65_536
        return b""

    monkeypatch.setattr(os, "read", fake_read_oversize)
    with pytest.raises(CodexProfileDataError) as excinfo:
        load_codex_profile_file(good)
    assert excinfo.value.code == "profile_too_large"

    state["calls"] = 0

    def fake_read_truncate(fd: int, size: int) -> bytes:
        state["calls"] += 1
        first = original_read(fd, size)
        if state["calls"] == 1:
            return first[: len(first) // 2]
        return b""

    monkeypatch.setattr(os, "read", fake_read_truncate)
    with pytest.raises(CodexProfileDataError) as excinfo:
        load_codex_profile_file(good)
    assert excinfo.value.code == "profile_unreadable"


def test_loaded_profile_never_reads_at_request_time() -> None:
    # Parsing and loading are the only readers; the snapshot is plain data.
    profile = load_default_codex_profile()
    facts = profile.to_facts()
    assert facts["module_id"] == "codex-0.162-responses-v1"
    assert facts["revision"] == "8"
    assert facts["digest"] == PACKAGED_PROFILE_DIGEST
    assert facts["builtin_names"] == "functions,multi_agent_v1"
