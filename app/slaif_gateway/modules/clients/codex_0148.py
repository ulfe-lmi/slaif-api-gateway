"""Pure observed Codex 0.148 client-tool taxonomy support."""

from __future__ import annotations

CODEX_0148_CLIENT_TOOL_TAXONOMY: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "functions",
        (
            ("exec_command", "function"),
            ("write_stdin", "function"),
            ("update_plan", "function"),
            ("request_user_input", "function"),
            ("view_image", "function"),
        ),
    ),
    (
        "multi_agent_v1",
        (
            ("close_agent", "function"),
            ("resume_agent", "function"),
            ("send_input", "function"),
            ("spawn_agent", "function"),
            ("wait_agent", "function"),
        ),
    ),
)
