"""Finite process-configuration inspection for the operator CLI (204).

This service inspects ONLY the CURRENT process's cached ``Settings``
snapshot (``get_settings`` is an lru-cached ``Settings()`` constructed
from the process environment/defaults). The default ``process_scope``
is ``"cli"`` and preserves the exact CLI output contract; the explicit
``"api"`` scope (211-a GUI) relabels the same finite allowlist for the
API process without changing any value or default.

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

# Finite, explicit process scopes (211-a): the CLI keeps its exact
# default wording; the GUI asks for the API process scope.
PROCESS_SCOPES: tuple[str, ...] = ("cli", "api")

PROCESS_RESTART_SCOPE = (
    "process restart; Compose env_file changes require recreating the "
    "affected containers (a plain restart does not reload them)"
)

API_PROCESS_RESTART_SCOPE = (
    "API process restart/recreate; Compose env_file changes require "
    "recreating the affected containers (a plain restart does not reload "
    "their environment)"
)

# Finite, reviewed practical units + meaning for each allowlisted
# setting (211-a GUI display). NULL/zero meanings follow each actual
# Settings contract; these are operator units, not per-key effective
# policy, and not the limits of every worker or the reverse proxy.
CONFIG_INSPECTION_MEANINGS: tuple[tuple[str, str, str], ...] = (
    ("CODEX_REPLAY_REFERENCE_TTL_SECONDS", "seconds",
     "lifetime of reusable Codex replay references"),
    ("DEFAULT_MAX_OUTPUT_TOKENS", "tokens",
     "default per-request output allowance for ordinary completions"),
    ("HARD_MAX_OUTPUT_TOKENS", "tokens",
     "hard per-request output ceiling (operator bound)"),
    ("HARD_MAX_INPUT_TOKENS", "tokens",
     "hard per-request input ceiling (operator bound)"),
    ("CODEX_ABSOLUTE_MAX_INPUT_TOKENS", "tokens",
     "absolute Codex request input ceiling"),
    ("CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS", "tokens",
     "absolute Codex request output ceiling"),
    ("CHAT_MAX_CHOICES_PER_REQUEST", "count",
     "maximum choices (n) per chat request"),
    ("CHAT_MAX_MESSAGES_PER_REQUEST", "count",
     "maximum messages per chat request"),
    ("CHAT_MAX_MESSAGE_CONTENT_BYTES", "bytes",
     "maximum UTF-8 bytes of a message content string, or the sum of its "
     "text-part bytes per message"),
    ("CHAT_MAX_TEXT_PARTS_PER_MESSAGE", "count",
     "maximum text parts per message"),
    ("CHAT_MAX_VIDEOS_PER_REQUEST", "count",
     "maximum video inputs per chat request"),
    ("CHAT_MAX_VIDEO_DATA_URL_BYTES", "bytes",
     "maximum size of one video data URL"),
    ("CHAT_MAX_IMAGES_PER_REQUEST", "count",
     "maximum image inputs per chat request"),
    ("CHAT_MAX_IMAGES_PER_MESSAGE", "count",
     "maximum image parts per message"),
    ("CHAT_MAX_IMAGE_URL_BYTES", "bytes",
     "maximum length of one image URL"),
    ("CHAT_MAX_IMAGE_DATA_URL_BYTES", "bytes",
     "maximum size of one image data URL"),
    ("CHAT_MAX_FILES_PER_REQUEST", "count",
     "maximum file inputs per chat request"),
    ("CHAT_MAX_FILES_PER_MESSAGE", "count",
     "maximum file parts per message"),
    ("CHAT_MAX_FILE_DATA_BYTES", "bytes",
     "maximum bytes of one file part's encoded base64/data-URL text "
     "(before decoding)"),
    ("CHAT_MAX_FILE_NAME_BYTES", "bytes",
     "maximum length of one file part name"),
    ("CHAT_MAX_AUDIO_INPUTS_PER_REQUEST", "count",
     "maximum audio inputs per chat request"),
    ("CHAT_MAX_AUDIO_INPUTS_PER_MESSAGE", "count",
     "maximum audio parts per message"),
    ("CHAT_MAX_AUDIO_INPUT_DATA_BYTES", "bytes",
     "maximum size of one audio input part"),
    ("RESPONSES_MAX_INPUT_TEXT_BYTES", "bytes",
     "maximum UTF-8 bytes of the scalar string input in a Responses or "
     "compact request"),
    ("RESPONSES_MAX_INPUT_ITEMS", "count",
     "maximum input items per Responses request"),
    ("RESPONSES_MAX_INPUT_ITEM_TEXT_BYTES", "bytes",
     "maximum text bytes in one Responses input item"),
    ("RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES", "bytes",
     "maximum total input text bytes per Responses request"),
    ("RESPONSES_MAX_INSTRUCTIONS_BYTES", "bytes",
     "maximum instructions bytes per Responses request"),
    ("RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST", "count",
     "maximum image parts per Responses request"),
    ("RESPONSES_MAX_IMAGE_URL_BYTES", "bytes",
     "maximum length of one Responses image URL"),
    ("RESPONSES_MAX_IMAGE_DATA_URL_BYTES", "bytes",
     "maximum size of one Responses image data URL"),
    ("RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES", "bytes",
     "maximum total image data URL bytes per Responses request"),
    ("RESPONSES_MAX_FILE_PARTS_PER_REQUEST", "count",
     "maximum file parts per Responses request"),
    ("RESPONSES_MAX_FILE_URL_BYTES", "bytes",
     "maximum length of one Responses file URL"),
    ("RESPONSES_MAX_FILE_DATA_URL_BYTES", "bytes",
     "maximum size of one Responses file data URL"),
    ("RESPONSES_MAX_TOTAL_FILE_DATA_URL_BYTES", "bytes",
     "maximum total file data URL bytes per Responses request"),
    ("RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS", "tokens",
     "default output tokens for Responses compact"),
    ("RESPONSES_COMPACT_HARD_MAX_OUTPUT_TOKENS", "tokens",
     "hard output tokens for Responses compact"),
    ("DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE", "requests/minute or none",
     "default key-policy request rate limit (None = no default)"),
    ("DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE", "tokens/minute or none",
     "default key-policy token rate limit (None = no default)"),
    ("DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS", "concurrent or none",
     "default key-policy concurrency limit (None = no default)"),
    ("LAZY_THROTTLING_MAX_WAIT_SECONDS", "seconds",
     "maximum bounded lazy-throttling wait per request"),
    ("LAZY_THROTTLING_MAX_WAITING_PER_KEY", "count",
     "maximum waiting requests held per key"),
    ("LAZY_THROTTLING_MAX_WAITING_TOTAL", "count",
     "maximum waiting requests held total"),
    ("LAZY_THROTTLING_WAITING_LEASE_TTL_SECONDS", "seconds",
     "TTL of a bounded waiting-request lease"),
)


def setting_meaning(name: str) -> tuple[str, str] | None:
    """Finite (units, meaning) for one allowlisted setting, else None."""
    for setting, units, meaning in CONFIG_INSPECTION_MEANINGS:
        if setting == name:
            return units, meaning
    return None

INSPECTION_LIMITATIONS: tuple[str, ...] = (
    "snapshot is the CURRENT CLI process's cached Settings, not live API/worker state",
    "configured/default source comes from this process's model_fields_set",
    "no database, network, broker, or provider access was performed",
    "no credential values or secret file contents are exposed",
    "a configured database URL is not connectivity or authentication proof",
    "external reverse-proxy request-size limits are NOT observed by this command",
)

# API-scope local copy of the limitations (211-a GUI): the same honest
# boundaries, worded for the API process rather than the CLI command.
API_PROCESS_LIMITATIONS: tuple[str, ...] = (
    "snapshot is the CURRENT API process's cached Settings, not worker/"
    "scheduler or reverse-proxy state",
    "configured/default source comes from this process's model_fields_set",
    "no database, network, broker, or provider access was performed",
    "no credential values or secret file contents are exposed",
    "a configured database URL is not connectivity or authentication proof",
    "external reverse-proxy request-size limits are NOT observed by this "
    "inspection",
    "worker and scheduler processes may hold different cached settings",
)


def inspect_process_configuration(
    settings: Settings, *, process_scope: str = "cli"
) -> dict[str, object]:
    """Project the finite allowlist from the current process Settings.

    ``process_scope`` must be one of :data:`PROCESS_SCOPES`; the default
    ``"cli"`` keeps the exact existing CLI payload contract (snapshot
    scope text, restart scope, and limitations unchanged).
    """
    if process_scope not in PROCESS_SCOPES:
        raise ValueError("unknown_process_scope")
    entries: dict[str, object] = {}
    configured = set(settings.model_fields_set)
    for name in CONFIG_INSPECTION_ALLOWLIST:
        entries[name] = {
            "value": getattr(settings, name),
            "source": "configured" if name in configured else "default",
            "restart_scope": (
                API_PROCESS_RESTART_SCOPE
                if process_scope == "api"
                else PROCESS_RESTART_SCOPE
            ),
        }
    snapshot_scope = (
        "current API process cached Settings"
        if process_scope == "api"
        else "current CLI process cached Settings"
    )
    limitations = list(
        API_PROCESS_LIMITATIONS if process_scope == "api" else INSPECTION_LIMITATIONS
    )
    return {
        "config": {
            "snapshot_scope": snapshot_scope,
            "settings": entries,
            "limitations": limitations,
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
