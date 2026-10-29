"""Finite process-configuration inspection for the operator CLI (204).

This service inspects ONLY the CURRENT CLI process's cached
``Settings`` snapshot (``get_settings`` is an lru-cached ``Settings()``
constructed from the process environment/defaults).

Honest boundaries:

- the snapshot is what THIS CLI process loaded, NOT live API/worker
  state; other processes may hold different cached settings;
- "configured" means the name appears in this process's
  ``Settings.model_fields_set`` (explicitly supplied at construction);
  "default" means the built-in default applied;
- the restart scope is a process restart: Compose ``env_file`` edits
  require recreating the affected containers (a plain restart does not
  reload a container's environment);
- no database/network/broker/provider access, no credential values,
  and no .env inference of any kind.
"""

from __future__ import annotations

from slaif_gateway.config import Settings

# Finite, reviewed allowlist of EXISTING numeric/boolean/nullable-numeric
# settings relevant to replay lifetime, input/output and media/content
# budgets. There is deliberately NO wildcard enumeration, no model_dump,
# and no arbitrary setting lookup.
CONFIG_INSPECTION_ALLOWLIST: tuple[str, ...] = (
    # Codex replay reference lifetime
    "CODEX_REPLAY_REFERENCE_TTL_SECONDS",
    # Default/hard output and input token bounds
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "HARD_MAX_OUTPUT_TOKENS",
    "HARD_MAX_INPUT_TOKENS",
    "CODEX_ABSOLUTE_MAX_INPUT_TOKENS",
    "CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS",
    # Chat request budgets
    "CHAT_MAX_CHOICES_PER_REQUEST",
    "CHAT_MAX_MESSAGES_PER_REQUEST",
    "CHAT_MAX_MESSAGE_CONTENT_BYTES",
    "CHAT_MAX_TEXT_PARTS_PER_MESSAGE",
    "CHAT_MAX_VIDEOS_PER_REQUEST",
    "CHAT_MAX_VIDEO_DATA_URL_BYTES",
    "CHAT_MAX_IMAGES_PER_REQUEST",
    "CHAT_MAX_IMAGES_PER_MESSAGE",
    "CHAT_MAX_IMAGE_URL_BYTES",
    "CHAT_MAX_IMAGE_DATA_URL_BYTES",
    "CHAT_MAX_FILES_PER_REQUEST",
    "CHAT_MAX_FILES_PER_MESSAGE",
    "CHAT_MAX_FILE_DATA_BYTES",
    "CHAT_MAX_FILE_NAME_BYTES",
    "CHAT_MAX_AUDIO_INPUTS_PER_REQUEST",
    "CHAT_MAX_AUDIO_INPUTS_PER_MESSAGE",
    "CHAT_MAX_AUDIO_INPUT_DATA_BYTES",
    # Responses request budgets
    "RESPONSES_MAX_INPUT_TEXT_BYTES",
    "RESPONSES_MAX_INPUT_ITEMS",
    "RESPONSES_MAX_INPUT_ITEM_TEXT_BYTES",
    "RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES",
    "RESPONSES_MAX_INSTRUCTIONS_BYTES",
    "RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST",
    "RESPONSES_MAX_IMAGE_URL_BYTES",
    "RESPONSES_MAX_IMAGE_DATA_URL_BYTES",
    "RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES",
    "RESPONSES_MAX_FILE_PARTS_PER_REQUEST",
    "RESPONSES_MAX_FILE_URL_BYTES",
    "RESPONSES_MAX_FILE_DATA_URL_BYTES",
    "RESPONSES_MAX_TOTAL_FILE_DATA_URL_BYTES",
    "RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS",
    "RESPONSES_COMPACT_HARD_MAX_OUTPUT_TOKENS",
    # Default rate limits and bounded lazy-throttling ceilings
    "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE",
    "DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE",
    "DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS",
    "LAZY_THROTTLING_MAX_WAIT_SECONDS",
    "LAZY_THROTTLING_MAX_WAITING_PER_KEY",
    "LAZY_THROTTLING_MAX_WAITING_TOTAL",
    "LAZY_THROTTLING_WAITING_LEASE_TTL_SECONDS",
)

PROCESS_RESTART_SCOPE = (
    "process restart; Compose env_file changes require recreating the "
    "affected containers (a plain restart does not reload them)"
)

INSPECTION_LIMITATIONS: tuple[str, ...] = (
    "snapshot is the CURRENT CLI process's cached Settings, not live API/worker state",
    "configured/default source comes from this process's model_fields_set",
    "no database, network, broker, or provider access was performed",
    "no credential values or secret file contents are exposed",
    "a configured database URL is not connectivity or authentication proof",
    "external reverse-proxy request-size limits are NOT observed by this command",
)


def inspect_process_configuration(settings: Settings) -> dict[str, object]:
    """Project the finite allowlist from the current process Settings."""
    entries: dict[str, object] = {}
    configured = set(settings.model_fields_set)
    for name in CONFIG_INSPECTION_ALLOWLIST:
        entries[name] = {
            "value": getattr(settings, name),
            "source": "configured" if name in configured else "default",
            "restart_scope": PROCESS_RESTART_SCOPE,
        }
    return {
        "config": {
            "snapshot_scope": "current CLI process cached Settings",
            "settings": entries,
            "limitations": list(INSPECTION_LIMITATIONS),
        }
    }


def render_process_configuration_text(payload: dict[str, object]) -> str:
    """Render the inspection payload as compact operator-readable text."""
    config = payload["config"]
    lines = [
        "Process configuration snapshot (current CLI process; not live "
        "API/worker state):",
        f"  restart scope for every listed setting: {PROCESS_RESTART_SCOPE}",
    ]
    settings = config["settings"]
    for name in CONFIG_INSPECTION_ALLOWLIST:
        entry = settings[name]
        lines.append(f"  {name} = {entry['value']} (source: {entry['source']})")
    lines.append("")
    lines.append("Limitations:")
    for item in config["limitations"]:
        lines.append(f"  - {item}")
    return "\n".join(lines)
