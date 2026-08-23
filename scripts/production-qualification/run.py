#!/usr/bin/env python3
"""Run the disposable production-appliance qualification.

This is intentionally an opt-in destructive harness.  It creates one uniquely
named Compose project, uses only generated credentials and canaries, and
removes that exact project and volume on exit.  It never prints request bodies,
keys, passwords, or canary values.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BASE_COMPOSE = ROOT / "docker-compose.production.yml"
QUAL_COMPOSE = ROOT / "scripts/production-qualification/qualification-compose.yml"
GATEWAY_MODEL = "qualification-double/qualification-model"


class QualificationError(RuntimeError):
    pass


class Runner:
    def __init__(self, *, keep: bool = False) -> None:
        self.keep = keep
        self.project = f"slaif-151-{os.getpid()}-{secrets.token_hex(3)}"
        self.runtime = ROOT / f".qualification-runtime-{self.project}"
        self.tls = self.runtime / "tls"
        self.logs = self.runtime / "logs"
        self.compose_env = self.runtime / "compose.env"
        self.secret_paths: dict[str, Path] = {}
        self.secret_values: list[str] = []
        self.canaries: list[str] = []
        self.env = os.environ.copy()
        self.docker: list[str] = ["docker"]
        self.compose: list[str] = [
            *self.docker,
            "compose",
            "--project-name",
            self.project,
            "--file",
            str(BASE_COMPOSE),
            "--file",
            str(QUAL_COMPOSE),
        ]
        self.ports = {
            "http": self._free_port(),
            "https": self._free_port(),
            "api": self._free_port(),
            "provider": self._free_port(),
        }
        self.phase_results: list[dict[str, Any]] = []
        self.gateway_key = ""
        self.key_id = ""
        self.owner_id = ""
        self.admin_id = ""
        self.provider_requests_before = 0

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def redact(self, value: str) -> str:
        result = value
        for secret in self.secret_values + self.canaries:
            if secret:
                result = result.replace(secret, "[REDACTED]")
        return result

    def command(self, args: list[str], *, input_text: str | None = None, check: bool = True, name: str = "command") -> subprocess.CompletedProcess[str]:
        safe_args = [self.redact(str(arg)) for arg in args]
        completed = subprocess.run(
            safe_args,
            cwd=ROOT,
            env=self.env,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output = self.redact(completed.stdout)
        if self.logs.exists():
            (self.logs / f"{len(self.phase_results):03d}-{name}.log").write_text(output, encoding="utf-8")
        if check and completed.returncode != 0:
            raise QualificationError(f"{name} failed with exit {completed.returncode}: {output[-1800:]}")
        return subprocess.CompletedProcess(completed.args, completed.returncode, output)

    def compose_command(self, args: list[str], *, input_text: str | None = None, check: bool = True, name: str = "compose") -> subprocess.CompletedProcess[str]:
        return self.command(self.compose + args, input_text=input_text, check=check, name=name)

    def phase(self, name: str, callback) -> None:
        started = time.monotonic()
        try:
            callback()
        except Exception as exc:
            result = {"name": name, "status": "FAIL", "seconds": round(time.monotonic() - started, 2), "error": self.redact(str(exc))}
            self.phase_results.append(result)
            raise
        self.phase_results.append({"name": name, "status": "OK", "seconds": round(time.monotonic() - started, 2)})
        print(f"PHASE_OK {name}", flush=True)

    def prepare(self) -> None:
        for forbidden in ("DATABASE_URL", "TEST_DATABASE_URL", "RUN_UPSTREAM_TESTS"):
            if os.environ.get(forbidden):
                raise QualificationError(f"refusing inherited {forbidden}")
        if os.environ.get("APP_ENV") == "production":
            raise QualificationError("refusing host APP_ENV=production")
        for executable in ("docker", "curl", "openssl"):
            if shutil.which(executable) is None:
                raise QualificationError(f"required executable missing: {executable}")
        docker_probe = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if docker_probe.returncode != 0:
            sudo_probe = subprocess.run(["sudo", "-n", "docker", "info", "--format", "{{.ServerVersion}}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if sudo_probe.returncode != 0:
                raise QualificationError("Docker daemon is unavailable to docker and sudo -n docker")
            self.docker = ["sudo", "-n", "docker"]
            self.compose = [
                *self.docker,
                "compose",
                "--project-name",
                self.project,
                "--file",
                str(BASE_COMPOSE),
                "--file",
                str(QUAL_COMPOSE),
            ]
        self.runtime.mkdir(mode=0o700)
        self.tls.mkdir(mode=0o700)
        self.logs.mkdir(mode=0o700)
        self.env.update(
            {
                "APP_ENV": "development",
                "SLAIF_API_DIAGNOSTIC_PORT": str(self.ports["api"]),
                "SLAIF_NGINX_HTTP_PORT": str(self.ports["http"]),
                "SLAIF_NGINX_HTTPS_PORT": str(self.ports["https"]),
                "QUALIFICATION_PROVIDER_PORT": str(self.ports["provider"]),
                "QUALIFICATION_PROJECT_NAME": self.project,
                "QUALIFICATION_MODEL": "qualification-model",
                "ENABLE_EMAIL_DELIVERY": "false",
            }
        )
        for label in ("gateway-key", "upstream-key", "prompt", "completion", "media", "malformed", "authorization"):
            value = f"qualification-{label}-{secrets.token_urlsafe(18)}"
            self.canaries.append(value)
        generated = {
            "postgres_password": secrets.token_urlsafe(30),
            "database_url": "postgresql+asyncpg://slaif:"
            + "PLACEHOLDER"
            + "@postgres:5432/slaif_gateway",
            "token_hmac_secret_v1": secrets.token_urlsafe(48),
            "admin_session_secret": secrets.token_urlsafe(48),
            "one_time_secret_encryption_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("="),
            "openai_upstream_api_key": secrets.token_urlsafe(30),
            "openrouter_api_key": self.canaries[1],
            "redis_password": secrets.token_urlsafe(30),
        }
        generated["database_url"] = generated["database_url"].replace("PLACEHOLDER", generated["postgres_password"])
        generated["redis_url"] = f"redis://:{generated['redis_password']}@redis:6379/0"
        self.secret_values.extend(generated.values())
        self.env["QUALIFICATION_PROVIDER_KEY"] = self.canaries[1]
        self.secret_values.append(self.env["QUALIFICATION_PROVIDER_KEY"])
        for name, value in generated.items():
            path = self.runtime / name
            path.write_bytes(value.encode("utf-8"))
            path.chmod(0o600)
            self.secret_paths[name] = path
        self.env.update(
            {
                "SLAIF_POSTGRES_PASSWORD_FILE": str(self.secret_paths["postgres_password"]),
                "SLAIF_DATABASE_URL_FILE": str(self.secret_paths["database_url"]),
                "SLAIF_TOKEN_HMAC_SECRET_V1_FILE": str(self.secret_paths["token_hmac_secret_v1"]),
                "SLAIF_ADMIN_SESSION_SECRET_FILE": str(self.secret_paths["admin_session_secret"]),
                "SLAIF_ONE_TIME_SECRET_ENCRYPTION_KEY_FILE": str(self.secret_paths["one_time_secret_encryption_key"]),
                "SLAIF_OPENAI_UPSTREAM_API_KEY_FILE": str(self.secret_paths["openai_upstream_api_key"]),
                "SLAIF_OPENROUTER_API_KEY_FILE": str(self.secret_paths["openrouter_api_key"]),
                "SLAIF_REDIS_PASSWORD_FILE": str(self.secret_paths["redis_password"]),
                "SLAIF_REDIS_URL_FILE": str(self.secret_paths["redis_url"]),
                "SLAIF_TLS_DIR": str(self.tls),
                "QUALIFICATION_GATEWAY_KEY_CANARY": self.canaries[0],
                "QUALIFICATION_UPSTREAM_KEY_CANARY": self.canaries[1],
                "QUALIFICATION_PROMPT_CANARY": self.canaries[2],
                "QUALIFICATION_COMPLETION_CANARY": self.canaries[3],
                "QUALIFICATION_MEDIA_CANARY": self.canaries[4],
                "QUALIFICATION_MALFORMED_CANARY": self.canaries[5],
                "QUALIFICATION_AUTHORIZATION_CANARY": self.canaries[6],
            }
        )
        compose_variables = {
            key: self.env[key]
            for key in (
                "SLAIF_API_DIAGNOSTIC_PORT",
                "SLAIF_NGINX_HTTP_PORT",
                "SLAIF_NGINX_HTTPS_PORT",
                "QUALIFICATION_PROVIDER_PORT",
                "QUALIFICATION_PROJECT_NAME",
                "QUALIFICATION_MODEL",
                "QUALIFICATION_PROVIDER_KEY",
                "QUALIFICATION_GATEWAY_KEY_CANARY",
                "QUALIFICATION_UPSTREAM_KEY_CANARY",
                "QUALIFICATION_PROMPT_CANARY",
                "QUALIFICATION_COMPLETION_CANARY",
                "QUALIFICATION_MEDIA_CANARY",
                "QUALIFICATION_MALFORMED_CANARY",
                "QUALIFICATION_AUTHORIZATION_CANARY",
                "SLAIF_POSTGRES_PASSWORD_FILE",
                "SLAIF_DATABASE_URL_FILE",
                "SLAIF_TOKEN_HMAC_SECRET_V1_FILE",
                "SLAIF_ADMIN_SESSION_SECRET_FILE",
                "SLAIF_ONE_TIME_SECRET_ENCRYPTION_KEY_FILE",
                "SLAIF_OPENAI_UPSTREAM_API_KEY_FILE",
                "SLAIF_OPENROUTER_API_KEY_FILE",
                "SLAIF_REDIS_PASSWORD_FILE",
                "SLAIF_REDIS_URL_FILE",
                "SLAIF_TLS_DIR",
            )
        }
        self.compose_env.write_text("".join(f"{key}={value}\n" for key, value in compose_variables.items()), encoding="utf-8")
        self.compose_env.chmod(0o600)
        self.compose = [
            *self.docker,
            "compose",
            "--env-file",
            str(self.compose_env),
            "--project-name",
            self.project,
            "--file",
            str(BASE_COMPOSE),
            "--file",
            str(QUAL_COMPOSE),
        ]

    def make_tls(self) -> None:
        key = self.tls / "privkey.pem"
        cert = self.tls / "fullchain.pem"
        self.command(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            name="tls",
        )
        key.chmod(0o600)
        cert.chmod(0o600)

    def cleanup(self) -> None:
        if self.keep:
            print(f"KEEP_RUNTIME={self.runtime}")
            return
        subprocess.run(self.compose + ["--profile", "async", "down", "--volumes", "--remove-orphans"], cwd=ROOT, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def wait_url(self, url: str, *, cafile: Path | None = None, timeout: float = 180.0) -> None:
        deadline = time.monotonic() + timeout
        context = ssl.create_default_context(cafile=str(cafile)) if cafile else None
        last = ""
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=4, context=context) as response:
                    if response.status < 500:
                        return
            except Exception as exc:  # noqa: BLE001
                last = str(exc)
            time.sleep(2)
        raise QualificationError(f"timed out waiting for {url}: {self.redact(last)}")

    def api_url(self, path: str) -> str:
        return f"https://localhost:{self.ports['https']}{path}"

    def api(self, path: str, body: dict[str, Any], *, key: str | None = None, expect: set[int] = {200}, timeout: float = 30.0) -> tuple[int, dict[str, Any] | str]:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(self.api_url(path), data=data, method="POST", headers={"Content-Type": "application/json"})
        if key:
            request.add_header("Authorization", f"Bearer {key}")
        context = ssl.create_default_context(cafile=str(self.tls / "fullchain.pem"))
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        try:
            parsed: dict[str, Any] | str = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = raw.decode("utf-8", errors="replace")
        if status not in expect:
            raise QualificationError(f"{path} returned {status}, expected {sorted(expect)}")
        return status, parsed

    def stream_api(self, path: str, body: dict[str, Any], *, key: str, abort: bool = False) -> tuple[int, str]:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(self.api_url(path), data=data, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        context = ssl.create_default_context(cafile=str(self.tls / "fullchain.pem"))
        try:
            with urllib.request.urlopen(request, timeout=40, context=context) as response:
                status = response.status
                chunks: list[bytes] = []
                for chunk in iter(lambda: response.read(512), b""):
                    chunks.append(chunk)
                    if abort:
                        break
                return status, b"".join(chunks).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")

    def provider_control(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(f"http://127.0.0.1:{self.ports['provider']}/control", data=data, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    def provider_state(self) -> dict[str, Any]:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.ports['provider']}/state", timeout=10) as response:
            return json.loads(response.read())

    def wait_redis(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.compose_command(
                [
                    "exec",
                    "-T",
                    "redis",
                    "sh",
                    "-c",
                    "redis-cli --no-auth-warning -a \"$(cat /run/secrets/redis_password)\" ping",
                ],
                check=False,
                name="redis-health",
            )
            if result.returncode == 0 and result.stdout.strip().endswith("PONG"):
                return
            time.sleep(2)
        raise QualificationError("Redis did not recover before the readiness deadline")

    def sql(self, statement: str) -> list[list[str]]:
        result = self.compose_command(["exec", "-T", "postgres", "psql", "-U", "slaif", "-d", "slaif_gateway", "-At", "-F", "|", "-c", statement], name="sql")
        return [row.split("|") for row in result.stdout.splitlines() if row.strip()]

    def cli(self, args: list[str], *, input_text: str | None = None, name: str = "cli", remove: bool = True, container_name: str | None = None) -> dict[str, Any]:
        run_args = ["run"]
        if remove:
            run_args.append("--rm")
        if container_name:
            run_args.extend(["--name", container_name])
        run_args.extend(["--no-deps", "api", "slaif-gateway", *args])
        result = self.compose_command(run_args, input_text=input_text, name=name)
        for line in reversed(result.stdout.strip().splitlines()):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise QualificationError(f"{name} did not return JSON: {result.stdout[-1200:]}")

    def start(self) -> None:
        self.compose_command(["--profile", "async", "down", "--volumes", "--remove-orphans"], check=False, name="initial-cleanup")
        self.compose_command(["config", "--quiet"], name="compose-config")
        self.compose_command(["build", "--pull=false"], name="compose-build")
        self.compose_command(["--profile", "async", "up", "-d"], name="compose-up")
        self.wait_url(f"https://localhost:{self.ports['https']}/healthz", cafile=self.tls / "fullchain.pem")
        self.wait_url(f"http://127.0.0.1:{self.ports['provider']}/healthz")

    def configure(self) -> None:
        admin = self.cli(["admin", "create", "--email", "qualification-admin@example.invalid", "--display-name", "Qualification Admin", "--password-stdin", "--superadmin", "--json"], input_text=secrets.token_urlsafe(24) + "\n", name="admin-create")
        self.admin_id = str(admin["id"])
        owner = self.cli(["owners", "create", "--name", "Qualification", "--surname", "Owner", "--email", "qualification-owner@example.invalid", "--json"], name="owner-create")
        self.owner_id = str(owner["id"])
        provider = self.cli(["providers", "add", "--provider", "qualification-double", "--api-key-env-var", "OPENROUTER_API_KEY", "--base-url", "http://provider-double:8090/v1", "--kind", "openai_compatible", "--confirm-insecure-http", "--reason", "objective-151 disposable socket provider", "--json"], name="provider-add")
        self.cli(["providers", "setup-models", "qualification-double", "--model", "qualification-model", "--preset", "chat_and_responses_text_v1", "--pricing-mode", "explicit", "--input-price-per-1m", "1", "--output-price-per-1m", "2", "--streaming", "--confirm-enable-unqualified", "--confirm-execute", "--reason", "objective-151 disposable qualification", "--json"], name="provider-setup")
        container_name = f"{self.project}-key-create"
        container_key_path = "/tmp/qualification-gateway-key"
        key_payload = self.cli(["keys", "create", "--owner-id", self.owner_id, "--valid-days", "1", "--cost-limit-eur", "20", "--token-limit-total", "100000", "--request-limit-total", "100", "--allowed-model", GATEWAY_MODEL, "--allowed-endpoint", "/v1/chat/completions", "--allowed-endpoint", "/v1/responses", "--rate-limit-requests-per-minute", "120", "--rate-limit-tokens-per-minute", "100000", "--rate-limit-concurrent-requests", "4", "--secret-output-file", container_key_path, "--json"], name="key-create", remove=False, container_name=container_name)
        key_path = self.runtime / "gateway-key"
        self.command([*self.docker, "cp", f"{container_name}:{container_key_path}", str(key_path)], name="key-copy")
        self.command(["sudo", "-n", "chmod", "0644", str(key_path)], name="key-permissions")
        self.key_id = str(key_payload.get("gateway_key_id") or key_payload["id"])
        self.gateway_key = key_path.read_text(encoding="utf-8").rstrip("\r\n")
        key_path.unlink()
        self.command([*self.docker, "rm", "-f", container_name], check=False, name="key-container-cleanup")
        self.secret_values.append(self.gateway_key)
        self.provider_control({"mode": "normal", "canaries": self.canaries})
        if provider.get("provider") != "qualification-double":
            raise QualificationError("provider CLI returned unexpected provider")

    def exercise_requests(self) -> None:
        prompt = self.canaries[2]
        completion = self.canaries[3]
        _, chat = self.api("/v1/chat/completions", {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 16}, key=self.gateway_key)
        if not isinstance(chat, dict) or chat.get("choices", [{}])[0].get("message", {}).get("content") != "qualification-output":
            raise QualificationError("Chat normal response shape mismatch")
        status, chat_stream = self.stream_api("/v1/chat/completions", {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": True, "max_tokens": 16}, key=self.gateway_key)
        if status != 200 or "qualification-output" not in chat_stream:
            raise QualificationError("Chat streaming response shape mismatch")
        _, response = self.api("/v1/responses", {"model": GATEWAY_MODEL, "input": prompt, "max_output_tokens": 16}, key=self.gateway_key)
        if not isinstance(response, dict) or response.get("status") != "completed":
            raise QualificationError("Responses normal response shape mismatch")
        status, response_stream = self.stream_api("/v1/responses", {"model": GATEWAY_MODEL, "input": prompt, "stream": True, "max_output_tokens": 16}, key=self.gateway_key)
        if status != 200 or "response.completed" not in response_stream:
            raise QualificationError("Responses streaming response shape mismatch")
        if completion in json.dumps(response):
            raise QualificationError("unexpected completion canary in gateway response")
        state = self.provider_state()
        if state["auth_ok"] < 4 or state["auth_bad"] != 0 or not state["canary_seen"]:
            raise QualificationError("provider double did not observe isolated authenticated forwarding")
        rows = self.sql("SELECT COUNT(*), COUNT(*) FILTER (WHERE success), COUNT(*) FILTER (WHERE accounting_status = 'finalized') FROM usage_ledger")
        if not rows or int(rows[0][0]) < 4 or int(rows[0][1]) < 4 or int(rows[0][2]) < 4:
            raise QualificationError("usage ledger finalization evidence is incomplete")

    def exercise_failures(self) -> None:
        body = {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 16}
        for mode, expected in (("http_error", {502, 503}), ("malformed_json", {502, 500})):
            self.provider_control({"mode": mode})
            status, _ = self.api("/v1/chat/completions", body, key=self.gateway_key, expect=expected)
            if status not in expected:
                raise QualificationError(f"{mode} was not rejected")
        for mode in ("malformed_sse", "incomplete_sse"):
            self.provider_control({"mode": mode})
            status, stream = self.stream_api("/v1/chat/completions", {**body, "stream": True}, key=self.gateway_key)
            if status != 200 or "[DONE]" in stream:
                raise QualificationError(f"{mode} stream was treated as complete")
            latest = self.sql("SELECT success, accounting_status FROM usage_ledger ORDER BY created_at DESC LIMIT 1")
            if not latest or latest[0][0].lower() in {"t", "true"} or latest[0][1] == "finalized":
                raise QualificationError(f"{mode} stream produced successful accounting")
        self.provider_control({"mode": "normal"})
        status, _ = self.stream_api("/v1/responses", {"model": GATEWAY_MODEL, "input": self.canaries[2], "stream": True, "max_output_tokens": 16}, key=self.gateway_key, abort=True)
        if status != 200:
            raise QualificationError("Responses client-abort request did not reach provider")
        self.sql("SELECT COUNT(*) FROM quota_reservations WHERE status = 'pending'")

    def exercise_controls(self) -> None:
        before = self.provider_state()["requests"]
        self.provider_control({"mode": "timeout", "delay_seconds": 3})
        self.sql("UPDATE provider_configs SET timeout_seconds = 2, max_retries = 0 WHERE provider = 'qualification-double'")
        status, _ = self.api("/v1/chat/completions", {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8}, key=self.gateway_key, expect={502, 504, 500}, timeout=20)
        if status not in {502, 504, 500}:
            raise QualificationError("provider timeout was not rejected")
        if self.provider_state()["requests"] <= before:
            raise QualificationError("provider timeout did not reach socket double")
        self.provider_control({"mode": "normal"})
        before_redis = self.provider_state()["requests"]
        self.compose_command(["stop", "redis"], name="redis-stop")
        status, _ = self.api("/v1/chat/completions", {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8}, key=self.gateway_key, expect={429, 500, 502, 503, 504}, timeout=20)
        if status not in {429, 500, 502, 503, 504}:
            raise QualificationError("Redis outage was not fail-closed")
        if self.provider_state()["requests"] != before_redis:
            raise QualificationError("Redis outage forwarded a request to the provider")
        self.compose_command(["start", "redis"], name="redis-restart")
        self.wait_redis()
        self.wait_url(f"https://localhost:{self.ports['https']}/healthz", cafile=self.tls / "fullchain.pem")
        status, _ = self.api("/v1/chat/completions", {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8}, key=self.gateway_key)
        if status != 200:
            raise QualificationError("gateway did not recover after Redis restart")

    def exercise_quota_and_key_controls(self) -> None:
        before_provider = self.provider_state()["requests"]
        rows = self.sql("SELECT requests_used_total, tokens_used_total, cost_used_eur FROM gateway_keys WHERE id = '" + self.key_id + "'")
        if not rows:
            raise QualificationError("primary gateway key disappeared before quota qualification")
        used_requests, used_tokens, used_cost = rows[0]
        request_body = {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8}

        self.sql("UPDATE gateway_keys SET request_limit_total = NULL, token_limit_total = " + used_tokens + ", cost_limit_eur = 20 WHERE id = '" + self.key_id + "'")
        status, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={429})
        if status != 429 or self.provider_state()["requests"] != before_provider:
            raise QualificationError("token quota crossing was not rejected before provider forwarding")

        self.sql("UPDATE gateway_keys SET token_limit_total = NULL, cost_limit_eur = " + used_cost + " WHERE id = '" + self.key_id + "'")
        status, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={429})
        if status != 429 or self.provider_state()["requests"] != before_provider:
            raise QualificationError("cost quota crossing was not rejected before provider forwarding")

        self.sql("UPDATE gateway_keys SET request_limit_total = " + used_requests + ", cost_limit_eur = 20 WHERE id = '" + self.key_id + "'")
        status, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={429})
        if status != 429 or self.provider_state()["requests"] != before_provider:
            raise QualificationError("request quota crossing was not rejected before provider forwarding")

        self.sql("UPDATE gateway_keys SET valid_until = now() - interval '1 second' WHERE id = '" + self.key_id + "'")
        status, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={401, 403})
        if status not in {401, 403} or self.provider_state()["requests"] != before_provider:
            raise QualificationError("expired gateway key was not denied before provider forwarding")

        self.cli(["keys", "revoke", self.key_id, "--actor-admin-id", self.admin_id, "--reason", "objective-151 qualification revocation", "--json"], name="key-revoke")
        status, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={401, 403})
        if status not in {401, 403} or self.provider_state()["requests"] != before_provider:
            raise QualificationError("revoked gateway key was not denied before provider forwarding")

    def exercise_persistence(self) -> None:
        expected = self.sql("SELECT COUNT(*) FROM usage_ledger")[0][0]
        self.compose_command(["up", "-d", "--force-recreate", "api", "nginx"], name="api-recreate")
        self.wait_url(f"https://localhost:{self.ports['https']}/healthz", cafile=self.tls / "fullchain.pem")
        if self.sql("SELECT COUNT(*) FROM usage_ledger")[0][0] != expected:
            raise QualificationError("usage ledger changed across API recreation")
        if not self.sql("SELECT 1 FROM gateway_keys WHERE id = '" + self.key_id + "'"):
            raise QualificationError("gateway key identity did not survive API recreation")
        self.compose_command(["up", "-d", "--force-recreate", "postgres", "api", "nginx"], name="postgres-recreate")
        self.wait_url(f"https://localhost:{self.ports['https']}/healthz", cafile=self.tls / "fullchain.pem")
        if self.sql("SELECT COUNT(*) FROM usage_ledger")[0][0] != expected:
            raise QualificationError("named Postgres volume did not preserve usage ledger")

    def backup_restore(self) -> None:
        backup = self.runtime / "qualification.dump"
        dump = subprocess.run(self.compose + ["exec", "-T", "postgres", "pg_dump", "-Fc", "-U", "slaif", "-d", "slaif_gateway"], cwd=ROOT, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if dump.returncode != 0:
            raise QualificationError(f"pg_dump failed: {self.redact(dump.stderr.decode(errors='replace'))[-1200:]}")
        backup.write_bytes(dump.stdout)
        database = f"restore_{secrets.token_hex(4)}"
        self.compose_command(["exec", "-T", "postgres", "createdb", "-U", "slaif", database], name="restore-create-db")
        try:
            restore = subprocess.run(self.compose + ["exec", "-T", "postgres", "pg_restore", "--exit-on-error", "-U", "slaif", "-d", database], cwd=ROOT, env=self.env, input=dump.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if restore.returncode != 0:
                raise QualificationError(f"pg_restore failed: {self.redact(restore.stderr.decode(errors='replace'))[-1200:]}")
            verify = self.compose_command(["exec", "-T", "postgres", "psql", "-U", "slaif", "-d", database, "-At", "-c", "SELECT COUNT(*) FROM usage_ledger"], name="restore-verify")
            if not verify.stdout.strip():
                raise QualificationError("restored database verification was empty")
        finally:
            self.compose_command(["exec", "-T", "postgres", "dropdb", "-U", "slaif", database], check=False, name="restore-drop-db")

    def privacy(self) -> None:
        scans = [self.compose_command(["logs", "--no-color", "--tail", "1000"], name="privacy-logs").stdout, "\n".join("|".join(row) for row in self.sql("SELECT endpoint, provider, requested_model, success, accounting_status FROM usage_ledger"))]
        joined = "\n".join(scans)
        for value in self.canaries + self.secret_values:
            if value in joined:
                raise QualificationError("privacy scan found a canary or secret in logs/database output")
        if self.provider_state().get("canary_seen") is not True:
            raise QualificationError("provider double did not observe the request canary")
        for table in ("audit_log", "usage_ledger", "quota_reservations", "gateway_keys"):
            for canary in self.canaries:
                escaped = canary.replace("'", "''")
                rows = self.sql(f"SELECT COUNT(*) FROM {table} WHERE {table}::text LIKE '%{escaped}%'")
                if rows and int(rows[0][0]) != 0:
                    raise QualificationError(f"privacy scan found a canary in {table}")

    def run(self) -> None:
        self.phase("prepare", self.prepare)
        self.phase("tls", self.make_tls)
        self.phase("compose", self.start)
        self.phase("operator-configuration", self.configure)
        self.phase("chat-and-responses", self.exercise_requests)
        self.phase("provider-failures-and-disconnects", self.exercise_failures)
        self.phase("redis-and-timeout-controls", self.exercise_controls)
        self.phase("persistence", self.exercise_persistence)
        self.phase("backup-restore", self.backup_restore)
        self.phase("quota-and-key-controls", self.exercise_quota_and_key_controls)
        self.phase("privacy", self.privacy)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Keep the unique Compose project and runtime evidence")
    args = parser.parse_args()
    runner = Runner(keep=args.keep)
    try:
        runner.run()
    except (QualificationError, subprocess.SubprocessError, OSError, ValueError, urllib.error.URLError) as exc:
        print(f"RESULT=FAIL\nERROR={runner.redact(str(exc))}", file=sys.stderr)
        return 1
    finally:
        runner.cleanup()
    print("RESULT=OK")
    print(json.dumps({"project": runner.project, "phases": runner.phase_results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
