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
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


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
        self.concurrency_key = ""
        self.concurrency_key_id = ""
        self.owner_id = ""
        self.admin_id = ""
        self.admin_password = ""
        self.provider_requests_before = 0
        self.requests: list[dict[str, Any]] = []
        self.dashboard_bodies: list[str] = []
        self.cleanup_error = ""
        self.cleanup_checks: dict[str, Any] = {}
        self.final_evidence: list[dict[str, Any]] = []
        self.restore_database_name = ""
        self.implementation_notes: list[str] = []

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

    @staticmethod
    def _header(headers: dict[str, str], name: str) -> str | None:
        wanted = name.lower()
        for key, value in headers.items():
            if key.lower() == wanted:
                return value
        return None

    def _record_request(self, *, path: str, status: int, headers: dict[str, str], streaming: bool) -> str | None:
        request_id = self._header(headers, "X-SLAIF-Diagnostic-ID") or self._header(headers, "X-Request-ID")
        self.requests.append(
            {
                "path": path,
                "status": status,
                "streaming": streaming,
                "request_id": request_id,
                "client_request_id": self._header(headers, "X-Request-ID"),
            }
        )
        return request_id

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
        restore_database = f"restore_local_{secrets.token_hex(4)}"
        self.restore_database_name = restore_database
        generated["backup_database_url"] = generated["database_url"].replace("postgresql+asyncpg://", "postgresql://")
        generated["restore_database_url"] = generated["backup_database_url"].rsplit("/", 1)[0] + "/" + restore_database
        generated["restore_async_database_url"] = generated["database_url"].rsplit("/", 1)[0] + "/" + restore_database
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
                "QUALIFICATION_RUNTIME_DIR": str(self.runtime),
                "QUALIFICATION_BACKUP_DATABASE_URL_FILE": str(self.secret_paths["backup_database_url"]),
                "QUALIFICATION_RESTORE_DATABASE_URL_FILE": str(self.secret_paths["restore_database_url"]),
                "QUALIFICATION_RESTORE_ASYNC_DATABASE_URL_FILE": str(self.secret_paths["restore_async_database_url"]),
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
                "QUALIFICATION_RUNTIME_DIR",
                "QUALIFICATION_BACKUP_DATABASE_URL_FILE",
                "QUALIFICATION_RESTORE_DATABASE_URL_FILE",
                "QUALIFICATION_RESTORE_ASYNC_DATABASE_URL_FILE",
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

    def cleanup(self) -> str | None:
        if self.keep:
            print(f"KEEP_RUNTIME={self.runtime}")
            return None
        down = subprocess.run(
            self.compose + ["--profile", "async", "--profile", "qualification", "down", "--volumes", "--remove-orphans"],
            cwd=ROOT,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        errors: list[str] = []
        if down.returncode != 0:
            errors.append(f"compose down exit {down.returncode}: {self.redact(down.stdout)[-1200:]}")
        if self.runtime.exists():
            try:
                shutil.rmtree(self.runtime)
            except OSError as exc:
                errors.append(f"runtime cleanup failed: {exc}")
        container_probe = subprocess.run(self.docker + ["ps", "-aq", "--filter", f"label=com.docker.compose.project={self.project}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        network_probe = subprocess.run(self.docker + ["network", "ls", "--format", "{{.Name}}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        volume_probe = subprocess.run(self.docker + ["volume", "ls", "--format", "{{.Name}}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        remaining_networks = sorted(
            name for name in network_probe.stdout.splitlines()
            if name in {f"{self.project}_internal", f"{self.project}_edge", f"{self.project}_egress"}
        )
        remaining_volumes = [name for name in volume_probe.stdout.splitlines() if name == f"{self.project}_postgres_data"]
        self.cleanup_checks = {
            "containers_by_compose_label": not bool(container_probe.stdout.strip()),
            "networks": not remaining_networks,
            "volumes": not remaining_volumes,
            "runtime": not self.runtime.exists(),
            "remaining_networks": remaining_networks,
            "remaining_volumes": remaining_volumes,
        }
        if container_probe.returncode != 0 or not self.cleanup_checks["containers_by_compose_label"]:
            errors.append("exact Compose project containers remained")
        if network_probe.returncode != 0 or not self.cleanup_checks["networks"]:
            errors.append(f"exact project networks remained: {remaining_networks}")
        if volume_probe.returncode != 0 or not self.cleanup_checks["volumes"]:
            errors.append(f"exact project volume remained: {remaining_volumes}")
        if not self.cleanup_checks["runtime"]:
            errors.append("qualification runtime remained")
        if errors:
            self.cleanup_error = "; ".join(errors)
            return self.cleanup_error
        return None

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

    def api(
        self,
        path: str,
        body: dict[str, Any],
        *,
        key: str | None = None,
        expect: set[int] = {200},
        timeout: float = 30.0,
    ) -> tuple[int, dict[str, Any] | str, dict[str, str]]:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(self.api_url(path), data=data, method="POST", headers={"Content-Type": "application/json"})
        if key:
            request.add_header("Authorization", f"Bearer {key}")
        context = ssl.create_default_context(cafile=str(self.tls / "fullchain.pem"))
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                raw = response.read()
                status = response.status
                headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
            headers = dict(exc.headers.items())
        try:
            parsed: dict[str, Any] | str = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = raw.decode("utf-8", errors="replace")
        self._record_request(path=path, status=status, headers=headers, streaming=False)
        if status not in expect:
            raise QualificationError(f"{path} returned {status}, expected {sorted(expect)}")
        return status, parsed, headers

    def stream_api(
        self,
        path: str,
        body: dict[str, Any],
        *,
        key: str,
        abort: bool = False,
        capture: dict[str, Any] | None = None,
        timeout: float = 40.0,
    ) -> tuple[int, str, dict[str, str]]:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(self.api_url(path), data=data, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        context = ssl.create_default_context(cafile=str(self.tls / "fullchain.pem"))
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                status = response.status
                headers = dict(response.headers.items())
                if capture is not None:
                    capture.update({"status": status, "headers": headers, "request_id": self._header(headers, "X-SLAIF-Diagnostic-ID") or self._header(headers, "X-Request-ID")})
                chunks: list[bytes] = []
                for chunk in iter(lambda: response.read(512), b""):
                    chunks.append(chunk)
                    if abort:
                        break
                self._record_request(path=path, status=status, headers=headers, streaming=True)
                return status, b"".join(chunks).decode("utf-8", errors="replace"), headers
        except urllib.error.HTTPError as exc:
            headers = dict(exc.headers.items())
            if capture is not None:
                capture.update({"status": exc.code, "headers": headers, "request_id": self._header(headers, "X-SLAIF-Diagnostic-ID") or self._header(headers, "X-Request-ID")})
            self._record_request(path=path, status=exc.code, headers=headers, streaming=True)
            return exc.code, exc.read().decode("utf-8", errors="replace"), headers

    def request_evidence(self, request_id: str) -> dict[str, Any] | None:
        escaped = request_id.replace("'", "''")
        rows = self.sql(
            "SELECT COALESCE(ul.request_id, qr.request_id), qr.endpoint, "
            "COALESCE(ul.provider,''), qr.requested_model, COALESCE(ul.resolved_model,''), "
            "COALESCE(ul.streaming::text,''), COALESCE(ul.success::text,''), "
            "COALESCE(ul.accounting_status,'pending'), COALESCE(ul.http_status::text,''), "
            "COALESCE(ul.total_tokens::text,'0'), COALESCE(ul.estimated_cost_eur::text,''), "
            "COALESCE(ul.actual_cost_eur::text,''), COALESCE(ul.finished_at::text,''), qr.status, "
            "qr.provider, qr.resolved_model, COALESCE(qr.streaming::text,''), "
            "qr.reserved_tokens, qr.reserved_cost_eur, qr.reserved_requests, "
            "COALESCE(qr.finalized_at::text,''), COALESCE(qr.released_at::text,'') "
            "FROM quota_reservations qr LEFT JOIN usage_ledger ul ON ul.quota_reservation_id = qr.id "
            f"WHERE qr.request_id = '{escaped}'"
        )
        if not rows:
            return None
        row = rows[0]
        fields = (
            "request_id", "endpoint", "provider", "requested_model", "resolved_model", "streaming",
            "success", "accounting_status", "http_status", "total_tokens", "estimated_cost", "actual_cost",
            "finished_at", "reservation_status", "reservation_provider", "reservation_resolved_model",
            "reservation_streaming", "reserved_tokens", "reserved_cost", "reserved_requests",
            "reservation_finalized_at", "reservation_released_at",
        )
        return dict(zip(fields, row, strict=False))

    def wait_request_terminal(self, request_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last = self.request_evidence(request_id)
            if last and last["accounting_status"] != "pending" and last["reservation_status"] != "pending":
                return last
            time.sleep(1)
        raise QualificationError(f"request {request_id} did not reach terminal accounting: {last}")

    def accounting_snapshot(self) -> tuple[str, ...]:
        rows = self.sql(
            "SELECT (SELECT COUNT(*) FROM quota_reservations), "
            "(SELECT COUNT(*) FROM quota_reservations WHERE status = 'pending'), "
            "(SELECT COUNT(*) FROM usage_ledger), "
            "(SELECT COUNT(*) FROM usage_ledger WHERE accounting_status = 'pending'), "
            "(SELECT COALESCE(tokens_reserved_total,0)::text || ':' || COALESCE(requests_reserved_total,0)::text || ':' || COALESCE(cost_reserved_eur,0)::text "
            "FROM gateway_keys WHERE id = '" + self.key_id.replace("'", "''") + "')"
        )
        if not rows or len(rows[0]) != 5:
            raise QualificationError("could not capture PostgreSQL accounting snapshot")
        return tuple(rows[0])

    def request_ids_for(self, path: str) -> list[str]:
        return [str(row["request_id"]) for row in self.requests if row["path"] == path and row.get("request_id")]

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
        self.admin_password = secrets.token_urlsafe(24)
        admin = self.cli(["admin", "create", "--email", "qualification-admin@example.invalid", "--display-name", "Qualification Admin", "--password-stdin", "--superadmin", "--json"], input_text=self.admin_password + "\n", name="admin-create")
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
        concurrency_container = f"{self.project}-concurrency-key-create"
        concurrency_key_path = "/tmp/qualification-concurrency-key"
        concurrency_payload = self.cli(
            [
                "keys", "create", "--owner-id", self.owner_id, "--valid-days", "1", "--cost-limit-eur", "20",
                "--token-limit-total", "100000", "--request-limit-total", "100", "--allowed-model", GATEWAY_MODEL,
                "--allowed-endpoint", "/v1/chat/completions", "--allowed-endpoint", "/v1/responses",
                "--rate-limit-requests-per-minute", "120", "--rate-limit-tokens-per-minute", "100000",
                "--rate-limit-concurrent-requests", "1", "--secret-output-file", concurrency_key_path, "--json",
            ],
            name="concurrency-key-create",
            remove=False,
            container_name=concurrency_container,
        )
        concurrency_path = self.runtime / "concurrency-key"
        self.command([*self.docker, "cp", f"{concurrency_container}:{concurrency_key_path}", str(concurrency_path)], name="concurrency-key-copy")
        self.command(["sudo", "-n", "chmod", "0644", str(concurrency_path)], name="concurrency-key-permissions")
        self.concurrency_key_id = str(concurrency_payload.get("gateway_key_id") or concurrency_payload["id"])
        self.concurrency_key = concurrency_path.read_text(encoding="utf-8").rstrip("\r\n")
        concurrency_path.unlink()
        self.command([*self.docker, "rm", "-f", concurrency_container], check=False, name="concurrency-key-container-cleanup")
        self.secret_values.append(self.concurrency_key)
        self.provider_control({"mode": "normal", "canaries": self.canaries, "completion": self.canaries[3]})
        if provider.get("provider") != "qualification-double":
            raise QualificationError("provider CLI returned unexpected provider")

    def exercise_requests(self) -> None:
        request_start = len(self.requests)
        prompt = self.canaries[2]
        completion = self.canaries[3]
        _, chat, _ = self.api("/v1/chat/completions", {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 16}, key=self.gateway_key)
        if not isinstance(chat, dict) or chat.get("choices", [{}])[0].get("message", {}).get("content") != completion:
            raise QualificationError("Chat normal response shape mismatch")
        status, chat_stream, _ = self.stream_api("/v1/chat/completions", {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": True, "max_tokens": 16}, key=self.gateway_key)
        if status != 200 or completion not in chat_stream:
            raise QualificationError("Chat streaming response shape mismatch")
        _, response, _ = self.api("/v1/responses", {"model": GATEWAY_MODEL, "input": prompt, "max_output_tokens": 16}, key=self.gateway_key)
        if not isinstance(response, dict) or response.get("status") != "completed":
            raise QualificationError("Responses normal response shape mismatch")
        status, response_stream, _ = self.stream_api("/v1/responses", {"model": GATEWAY_MODEL, "input": prompt, "stream": True, "max_output_tokens": 16}, key=self.gateway_key)
        if status != 200 or "response.completed" not in response_stream:
            raise QualificationError("Responses streaming response shape mismatch")
        if not isinstance(response, dict) or completion not in json.dumps(response):
            raise QualificationError("completion canary did not traverse the provider response")
        state = self.provider_state()
        if state["auth_ok"] < 4 or state["auth_bad"] != 0 or not state["canary_seen"]:
            raise QualificationError("provider double did not observe isolated authenticated forwarding")
        for request in self.requests[request_start:]:
            if request.get("request_id"):
                evidence = self.wait_request_terminal(str(request["request_id"]))
                if evidence["accounting_status"] != "finalized" or evidence["reservation_status"] != "finalized":
                    raise QualificationError(f"normal request accounting was not finalized: {evidence}")

    def exercise_failures(self) -> None:
        request_start = len(self.requests)
        body = {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 16}
        for mode, expected in (("http_error", {502, 503}), ("malformed_json", {502, 500})):
            self.provider_control({"mode": mode})
            status, _, _ = self.api("/v1/chat/completions", body, key=self.gateway_key, expect=expected)
            if status not in expected:
                raise QualificationError(f"{mode} was not rejected")
        for mode in ("malformed_sse", "incomplete_sse"):
            self.provider_control({"mode": mode})
            status, stream, _ = self.stream_api("/v1/chat/completions", {**body, "stream": True}, key=self.gateway_key)
            if status != 200 or "[DONE]" in stream:
                raise QualificationError(f"{mode} stream was treated as complete")
        for request in self.requests[request_start:]:
            if request.get("request_id"):
                evidence = self.wait_request_terminal(str(request["request_id"]))
                if evidence["accounting_status"] not in {"failed", "interrupted", "released", "estimated"}:
                    raise QualificationError(f"failure request did not reach a failure terminal: {evidence}")
        self.provider_control({"mode": "client_abort", "stream_pause_seconds": 1, "completion": self.canaries[3]})
        for path, payload in (
            ("/v1/chat/completions", {**body, "stream": True}),
            ("/v1/responses", {"model": GATEWAY_MODEL, "input": self.canaries[2], "stream": True, "max_output_tokens": 16}),
        ):
            status, _, _ = self.stream_api(path, payload, key=self.gateway_key, abort=True)
            if status != 200:
                raise QualificationError(f"{path} client-abort request did not reach provider")
            request = self.requests[-1]
            if request.get("request_id"):
                evidence = self.wait_request_terminal(str(request["request_id"]))
                if evidence["accounting_status"] not in {"failed", "interrupted", "released", "estimated"}:
                    raise QualificationError(f"client-abort accounting was not terminal failure evidence: {evidence}")
        self.provider_control({"mode": "normal", "stream_pause_seconds": 0, "completion": self.canaries[3]})

    def exercise_controls(self) -> None:
        request_start = len(self.requests)
        before = self.provider_state()["requests"]
        self.provider_control({"mode": "timeout", "delay_seconds": 3})
        self.sql("UPDATE provider_configs SET timeout_seconds = 2, max_retries = 0 WHERE provider = 'qualification-double'")
        status, _, _ = self.api("/v1/chat/completions", {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8}, key=self.gateway_key, expect={502, 504, 500}, timeout=20)
        if status not in {502, 504, 500}:
            raise QualificationError("provider timeout was not rejected")
        if self.provider_state()["requests"] <= before:
            raise QualificationError("provider timeout did not reach socket double")
        for request in self.requests[request_start:]:
            if request.get("request_id"):
                self.wait_request_terminal(str(request["request_id"]))
        time.sleep(4)
        self.provider_control({"mode": "normal"})
        self.sql("UPDATE provider_configs SET timeout_seconds = 120, max_retries = 1 WHERE provider = 'qualification-double'")
        before_redis = self.provider_state()["requests"]
        before_accounting = self.accounting_snapshot()
        self.compose_command(["stop", "redis"], name="redis-stop")
        status, _, _ = self.api("/v1/chat/completions", {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8}, key=self.gateway_key, expect={429, 500, 502, 503, 504}, timeout=20)
        if status not in {429, 500, 502, 503, 504}:
            raise QualificationError("Redis outage was not fail-closed")
        if self.provider_state()["requests"] != before_redis:
            raise QualificationError("Redis outage forwarded a request to the provider")
        after_accounting = self.accounting_snapshot()
        if after_accounting != before_accounting:
            raise QualificationError(f"Redis outage changed PostgreSQL accounting: before={before_accounting} after={after_accounting}")
        self.compose_command(["start", "redis"], name="redis-restart")
        self.wait_redis()
        self.wait_url(f"https://localhost:{self.ports['https']}/healthz", cafile=self.tls / "fullchain.pem")
        status = 503
        for _ in range(10):
            status, _, _ = self.api(
                "/v1/chat/completions",
                {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8},
                key=self.gateway_key,
                expect={200, 502, 503, 504},
            )
            if status == 200:
                break
            time.sleep(1)
        if status != 200:
            raise QualificationError("gateway did not recover after Redis restart")

    def exercise_concurrency(self) -> None:
        self.provider_control({"mode": "normal", "stream_pause_seconds": 8, "completion": self.canaries[3]})
        capture: dict[str, Any] = {}
        result: dict[str, Any] = {}

        def run_first() -> None:
            try:
                result["response"] = self.stream_api(
                    "/v1/chat/completions",
                    {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "stream": True, "max_tokens": 16},
                    key=self.concurrency_key,
                    capture=capture,
                    timeout=30,
                )
            except Exception as exc:  # noqa: BLE001
                result["error"] = str(exc)

        thread = threading.Thread(target=run_first, name="qualification-slow-stream")
        thread.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and "request_id" not in capture:
            time.sleep(0.1)
        if not capture.get("request_id"):
            thread.join(timeout=1)
            raise QualificationError(f"slow stream did not expose a gateway request ID: {capture} {result}")
        status, _, _ = self.api(
            "/v1/chat/completions",
            {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8},
            key=self.concurrency_key,
            expect={429, 503},
            timeout=20,
        )
        if status not in {429, 503}:
            raise QualificationError("overlapping request was not rejected by Redis concurrency")
        thread.join(timeout=20)
        if thread.is_alive() or "error" in result:
            raise QualificationError(f"slow stream did not release concurrency slot: {result}")
        evidence = self.wait_request_terminal(str(capture["request_id"]))
        if evidence["accounting_status"] not in {"finalized", "estimated"} or evidence["reservation_status"] != "finalized":
            raise QualificationError(f"slow stream accounting was not terminal: {evidence}")
        self.provider_control({"mode": "normal", "stream_pause_seconds": 0, "completion": self.canaries[3]})
        status = 503
        for _ in range(20):
            status, _, _ = self.api(
                "/v1/chat/completions",
                {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8},
                key=self.concurrency_key,
                expect={200, 429, 503},
            )
            if status == 200:
                break
            time.sleep(1)
        if status != 200:
            raise QualificationError("released Redis concurrency slot did not admit a following request")

    def exercise_api_termination_reconciliation(self) -> None:
        self.provider_control({"mode": "normal", "stream_pause_seconds": 20, "completion": self.canaries[3]})
        capture: dict[str, Any] = {}
        result: dict[str, Any] = {}

        def run_stream() -> None:
            try:
                result["response"] = self.stream_api(
                    "/v1/responses",
                    {"model": GATEWAY_MODEL, "input": self.canaries[2], "stream": True, "max_output_tokens": 16},
                    key=self.gateway_key,
                    capture=capture,
                    timeout=45,
                )
            except Exception as exc:  # noqa: BLE001
                result["error"] = str(exc)

        thread = threading.Thread(target=run_stream, name="qualification-api-termination")
        thread.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and "request_id" not in capture:
            time.sleep(0.1)
        request_id = capture.get("request_id")
        if not request_id:
            thread.join(timeout=1)
            raise QualificationError(f"active stream did not expose request ID before API termination: {capture} {result}")
        if not any(request.get("request_id") == request_id for request in self.requests):
            headers = capture.get("headers") or {}
            self._record_request(
                path="/v1/responses",
                status=int(capture.get("status") or 0),
                headers=headers,
                streaming=True,
            )
        pretermination = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            pretermination = self.request_evidence(str(request_id))
            if pretermination:
                break
            time.sleep(0.5)
        if not pretermination:
            raise QualificationError(f"active stream had no persisted reservation before API termination: {request_id}")
        if pretermination["reservation_status"] != "pending":
            raise QualificationError(f"active stream was not pending before API termination: {pretermination}")
        self.compose_command(["kill", "api"], name="api-terminate")
        thread.join(timeout=15)
        self.compose_command(["up", "-d", "api", "nginx"], name="api-restart-after-termination")
        self.wait_url(f"https://localhost:{self.ports['https']}/healthz", cafile=self.tls / "fullchain.pem")
        evidence = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            evidence = self.request_evidence(str(request_id))
            if evidence:
                break
            time.sleep(1)
        if not evidence:
            raise QualificationError(f"interrupted request was not persisted: {request_id}")
        if evidence["reservation_status"] != "pending":
            raise QualificationError(f"termination request was not left pending for reconciliation: {evidence}")
        escaped = str(request_id).replace("'", "''")
        self.sql(f"UPDATE quota_reservations SET expires_at = now() - interval '1 second' WHERE request_id = '{escaped}' AND status = 'pending'")
        self.cli(
            [
                "quota", "reconcile-expired-reservations", "--limit", "100", "--execute",
                "--actor-admin-id", self.admin_id, "--reason", "objective-151 API termination reconciliation", "--json",
            ],
            name="documented-reconciliation",
        )
        evidence = self.wait_request_terminal(str(request_id), timeout=30)
        if evidence["reservation_status"] not in {"released", "expired"} or evidence["accounting_status"] == "pending":
            raise QualificationError(f"documented reconciliation did not repair interrupted request: {evidence}")
        if (
            evidence["provider"] != "qualification-double"
            or evidence["resolved_model"] != "qualification-model"
            or evidence["streaming"] != "true"
            or evidence["reservation_provider"] != "qualification-double"
            or evidence["reservation_resolved_model"] != "qualification-model"
            or evidence["reservation_streaming"] != "true"
        ):
            raise QualificationError(f"interrupted request lost immutable route facts: {evidence}")
        counters = self.sql("SELECT tokens_reserved_total, requests_reserved_total, cost_reserved_eur FROM gateway_keys WHERE id = '" + self.key_id.replace("'", "''") + "'")
        if not counters or any(value not in {"0", "0.000000000", "0.0"} for value in counters[0]):
            raise QualificationError(f"reconciliation left key reservations outstanding: {counters}")
        audit = self.sql(
            "SELECT COUNT(*) FROM audit_log WHERE request_id = '" + escaped + "' "
            "AND action = 'quota_reservation_expired' AND note ILIKE '%objective-151%'"
        )
        if not audit or int(audit[0][0]) < 1:
            raise QualificationError("reconciliation audit metadata was not persisted")
        self.provider_control({"mode": "normal", "stream_pause_seconds": 0, "completion": self.canaries[3]})

    def exercise_dashboard(self) -> None:
        context = ssl.create_default_context(cafile=str(self.tls / "fullchain.pem"))
        jar = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), urllib.request.HTTPCookieProcessor(jar))

        def fetch(path: str, *, form: dict[str, str] | None = None) -> tuple[int, str, dict[str, str]]:
            request = urllib.request.Request(
                self.api_url(path),
                data=urlencode(form).encode("utf-8") if form is not None else None,
                method="POST" if form is not None else "GET",
                headers={"Content-Type": "application/x-www-form-urlencoded"} if form is not None else {},
            )
            try:
                with opener.open(request, timeout=20) as response:
                    return response.status, response.read().decode("utf-8", errors="replace"), dict(response.headers.items())
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read().decode("utf-8", errors="replace"), dict(exc.headers.items())

        status, login_html, _ = fetch("/admin/login")
        if status != 200:
            raise QualificationError(f"dashboard login page returned {status}")
        csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', login_html)
        if csrf_match is None:
            raise QualificationError("dashboard login page did not expose CSRF form token")
        if not any(cookie.name == "slaif_admin_login_csrf" and cookie.secure for cookie in jar):
            raise QualificationError("dashboard login CSRF cookie was not Secure over HTTPS")
        status, _, login_headers = fetch(
            "/admin/login",
            form={"email": "qualification-admin@example.invalid", "password": self.admin_password, "csrf_token": csrf_match.group(1)},
        )
        if status != 200 or not any(cookie.name == "slaif_admin_session" for cookie in jar):
            raise QualificationError(f"dashboard authenticated session was not established: {status}")
        if "Secure" not in login_headers.get("Set-Cookie", "") and not any(cookie.name == "slaif_admin_session" and cookie.secure for cookie in jar):
            raise QualificationError("dashboard session cookie was not Secure")
        for path, marker in (("/admin/usage", "Usage Ledger"), ("/admin/audit", "Audit Log")):
            status, body, _ = fetch(path)
            if status != 200 or marker not in body:
                raise QualificationError(f"dashboard page {path} returned {status} without expected content")
            self.dashboard_bodies.append(body)

    def exercise_async_liveness(self) -> None:
        deadline = time.monotonic() + 45
        services: dict[str, dict[str, Any]] = {}
        while time.monotonic() < deadline:
            result = self.compose_command(["--profile", "async", "ps", "--format", "json"], check=False, name="async-ps")
            for line in result.stdout.splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and item.get("Service"):
                    services[str(item["Service"])] = item
            if all(
                str(services.get(name, {}).get("State", "")).lower() in {"running", "up"}
                or str(services.get(name, {}).get("Status", "")).lower().startswith("up")
                for name in ("worker", "scheduler")
            ):
                break
            time.sleep(2)
        if not all(
            str(services.get(name, {}).get("State", "")).lower() in {"running", "up"}
            or str(services.get(name, {}).get("Status", "")).lower().startswith("up")
            for name in ("worker", "scheduler")
        ):
            raise QualificationError(f"Celery services were not running: {services}")
        ping = self.compose_command(
            ["exec", "-T", "worker", "/usr/local/bin/load-production-secrets", "celery", "-A", "slaif_gateway.workers.celery_app:celery_app", "inspect", "ping"],
            check=False,
            name="celery-ping",
        )
        if ping.returncode != 0 or "pong" not in ping.stdout.lower():
            raise QualificationError(f"Celery worker did not answer inspect ping: {ping.stdout[-1200:]}")
        registered = self.compose_command(
            ["exec", "-T", "worker", "/usr/local/bin/load-production-secrets", "celery", "-A", "slaif_gateway.workers.celery_app:celery_app", "inspect", "registered"],
            check=False,
            name="celery-registered",
        )
        if registered.returncode != 0 or "slaif_gateway" not in registered.stdout:
            raise QualificationError("Celery registered-task inspection did not expose gateway tasks")
        beat = self.compose_command(
            [
                "exec", "-T", "scheduler", "python", "-c",
                "import glob; print('BEAT_PRESENT' if any('celery beat' in open(p, 'rb').read().decode(errors='ignore') for p in glob.glob('/proc/[0-9]*/cmdline')) else 'BEAT_MISSING')",
            ],
            check=False,
            name="celery-beat-process",
        )
        if beat.returncode != 0 or "BEAT_PRESENT" not in beat.stdout:
            raise QualificationError(f"Celery Beat process was not proven live: {beat.stdout[-1200:]}")

    def exercise_privacy_inputs(self) -> None:
        before = self.provider_state()["requests"]
        invalid_status, _, _ = self.api(
            "/v1/chat/completions",
            {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8},
            key=self.canaries[6],
            expect={401, 403},
        )
        if invalid_status not in {401, 403} or self.provider_state()["requests"] != before:
            raise QualificationError("invalid authorization was not rejected before provider forwarding")
        media_status, _, _ = self.api(
            "/v1/chat/completions",
            {
                "model": GATEWAY_MODEL,
                "messages": [{"role": "user", "content": [{"type": "text", "text": "media rejection"}, {"type": "image_url", "image_url": {"url": "https://invalid.example/" + self.canaries[4]}}]}],
                "max_tokens": 8,
            },
            key=self.gateway_key,
            expect={400, 403, 422},
        )
        if media_status not in {400, 403, 422} or self.provider_state()["requests"] != before:
            raise QualificationError("media-shaped rejected input reached the provider")

    def exercise_quota_and_key_controls(self) -> None:
        rows = self.sql("SELECT requests_used_total, tokens_used_total, cost_used_eur FROM gateway_keys WHERE id = '" + self.key_id + "'")
        if not rows:
            raise QualificationError("primary gateway key disappeared before quota qualification")
        used_requests, used_tokens, used_cost = rows[0]
        overrun_limit = int(used_tokens) + 2
        self.sql(
            "UPDATE gateway_keys SET request_limit_total = " + str(int(used_requests) + 20) + ", "
            "token_limit_total = " + str(overrun_limit) + ", cost_limit_eur = 20, valid_until = now() + interval '1 day' "
            "WHERE id = '" + self.key_id.replace("'", "''") + "'"
        )
        provider_before_overrun = self.provider_state()["requests"]
        status, _, _ = self.api(
            "/v1/chat/completions",
            {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": "x"}], "max_tokens": 1},
            key=self.gateway_key,
        )
        if status != 200:
            raise QualificationError("bounded admitted overrun request was rejected before provider forwarding")
        overrun_request = self.requests[-1].get("request_id")
        if not overrun_request:
            raise QualificationError("bounded admitted overrun request did not expose request ID")
        overrun_evidence = self.wait_request_terminal(str(overrun_request))
        after_overrun_rows = self.sql(
            "SELECT requests_used_total, tokens_used_total, cost_used_eur FROM gateway_keys WHERE id = '" + self.key_id + "'"
        )
        if not after_overrun_rows:
            raise QualificationError("primary gateway key disappeared after bounded overrun")
        _, after_tokens, _ = after_overrun_rows[0]
        if (
            int(after_tokens) <= int(overrun_limit)
            or int(after_tokens) <= int(used_tokens)
            or int(overrun_evidence["total_tokens"]) != int(after_tokens) - int(used_tokens)
        ):
            raise QualificationError(f"authoritative usage did not cross the remaining token limit: {overrun_evidence}")
        if self.provider_state()["requests"] != provider_before_overrun + 1:
            raise QualificationError("bounded overrun did not produce exactly one provider call")
        provider_before_following = self.provider_state()["requests"]
        status, _, _ = self.api(
            "/v1/chat/completions",
            {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": "x"}], "max_tokens": 1},
            key=self.gateway_key,
            expect={429},
        )
        if status != 429 or self.provider_state()["requests"] != provider_before_following:
            raise QualificationError("following request was not denied after authoritative quota overrun")

        rows = self.sql("SELECT requests_used_total, tokens_used_total, cost_used_eur FROM gateway_keys WHERE id = '" + self.key_id.replace("'", "''") + "'")
        used_requests, used_tokens, used_cost = rows[0]
        request_body = {"model": GATEWAY_MODEL, "messages": [{"role": "user", "content": self.canaries[2]}], "max_tokens": 8}

        self.sql("UPDATE gateway_keys SET request_limit_total = NULL, token_limit_total = " + used_tokens + ", cost_limit_eur = 20 WHERE id = '" + self.key_id + "'")
        provider_before_token_denial = self.provider_state()["requests"]
        status, _, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={429})
        if status != 429 or self.provider_state()["requests"] != provider_before_token_denial:
            raise QualificationError("token quota crossing was not rejected before provider forwarding")

        self.sql("UPDATE gateway_keys SET token_limit_total = NULL, cost_limit_eur = " + used_cost + " WHERE id = '" + self.key_id + "'")
        provider_before_cost_denial = self.provider_state()["requests"]
        status, _, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={429})
        if status != 429 or self.provider_state()["requests"] != provider_before_cost_denial:
            raise QualificationError("cost quota crossing was not rejected before provider forwarding")

        self.sql("UPDATE gateway_keys SET request_limit_total = " + used_requests + ", cost_limit_eur = 20 WHERE id = '" + self.key_id + "'")
        provider_before_request_denial = self.provider_state()["requests"]
        status, _, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={429})
        if status != 429 or self.provider_state()["requests"] != provider_before_request_denial:
            raise QualificationError("request quota crossing was not rejected before provider forwarding")

        self.sql("UPDATE gateway_keys SET valid_until = now() - interval '1 second' WHERE id = '" + self.key_id + "'")
        provider_before_expiry_denial = self.provider_state()["requests"]
        status, _, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={401, 403})
        if status not in {401, 403} or self.provider_state()["requests"] != provider_before_expiry_denial:
            raise QualificationError("expired gateway key was not denied before provider forwarding")

        self.sql(
            "UPDATE gateway_keys SET status = 'active', valid_until = now() + interval '1 day', "
            "request_limit_total = NULL, token_limit_total = NULL, cost_limit_eur = 20 "
            "WHERE id = '" + self.key_id + "'"
        )
        provider_before_valid_probe = self.provider_state()["requests"]
        valid_status, _, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key)
        if valid_status != 200 or self.provider_state()["requests"] != provider_before_valid_probe + 1:
            raise QualificationError("otherwise-valid gateway key was not proven before revocation")
        self.cli(["keys", "revoke", self.key_id, "--actor-admin-id", self.admin_id, "--reason", "objective-151 qualification revocation", "--json"], name="key-revoke")
        provider_before_revocation_denial = self.provider_state()["requests"]
        status, _, _ = self.api("/v1/chat/completions", request_body, key=self.gateway_key, expect={401, 403})
        if status not in {401, 403} or self.provider_state()["requests"] != provider_before_revocation_denial:
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
        backup = "/qualification-runtime/qualification.dump"
        source_rows = (
            self.sql("SELECT COUNT(*) FROM gateway_keys")[0][0],
            self.sql("SELECT COUNT(*) FROM usage_ledger")[0][0],
        )
        backup_run = self.compose_command(
            [
                "--profile", "qualification", "run", "--rm", "--no-deps", "backup-adapter", "sh", "-c",
                "export BACKUP_DATABASE_URL=\"$(cat /run/secrets/backup_database_url)\"; export BACKUP_OUTPUT=" + backup + "; /qualification/backup.sh",
            ],
            name="documented-backup-script",
        )
        if "BACKUP_WRITTEN=" not in backup_run.stdout:
            raise QualificationError("scripts/backup.sh did not report its output")
        create = self.compose_command(
            [
                "--profile", "qualification", "run", "--rm", "--no-deps", "backup-adapter", "sh", "-c",
                "PGPASSWORD=\"$(cat /run/secrets/postgres_password)\" createdb -h postgres -U slaif --maintenance-db=postgres " + self.restore_database_name,
            ],
            name="restore-create-db",
        )
        _ = create
        restore = self.compose_command(
            [
                "--profile", "qualification", "run", "--rm", "--no-deps", "backup-adapter", "sh", "-c",
                "export RESTORE_DATABASE_URL=\"$(cat /run/secrets/restore_database_url)\"; export BACKUP_INPUT=" + backup + "; /qualification/restore.sh",
            ],
            name="documented-restore-script",
        )
        if "RESTORE_COMPLETED=" not in restore.stdout:
            raise QualificationError("scripts/restore.sh did not report completion")
        verify = self.compose_command(
            [
                "--profile", "qualification", "run", "--rm", "--no-deps", "verify-adapter", "sh", "-c",
                "export RESTORE_DATABASE_URL=\"$(cat /run/secrets/restore_async_database_url)\"; python /qualification/verify_restore.py",
            ],
            name="documented-restore-verification",
        )
        if "RESULT=OK" not in verify.stdout:
            raise QualificationError("scripts/verify_restore.py did not report RESULT=OK")
        counts_match = re.search(r"row_counts=gateway_keys:(\d+),usage_ledger:(\d+)", verify.stdout)
        if counts_match is None:
            raise QualificationError("restore verifier did not emit bounded row counts")
        restored_rows = tuple(counts_match.groups())
        if restored_rows != tuple(str(value) for value in source_rows):
            raise QualificationError(
                f"restored row counts did not match source snapshot: source={source_rows} restored={restored_rows}"
            )

    def privacy(self) -> None:
        logs = self.compose_command(["logs", "--no-color", "--tail", "1000"], name="privacy-logs").stdout
        metrics = ""
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.ports['api']}/metrics", timeout=10) as response:
                metrics = response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            raise QualificationError(f"metrics privacy scan could not read /metrics: {exc}") from exc
        provider_text = json.dumps(self.provider_state(), sort_keys=True)
        database_text = "\n".join("|".join(row) for row in self.sql("SELECT endpoint, provider, requested_model, success, accounting_status FROM usage_ledger"))
        joined = "\n".join([logs, metrics, provider_text, database_text, *self.dashboard_bodies])
        tables = ("audit_log", "usage_ledger", "quota_reservations", "gateway_keys", "admin_sessions", "one_time_secrets", "email_deliveries")
        for value in self.canaries + self.secret_values:
            if value in joined:
                raise QualificationError("privacy scan found a canary or secret in logs, metrics, dashboard, provider state, or database output")
            for table in tables:
                escaped = value.replace("'", "''")
                rows = self.sql(f"SELECT COUNT(*) FROM {table} WHERE {table}::text LIKE '%{escaped}%'")
                if rows and int(rows[0][0]) != 0:
                    raise QualificationError(f"privacy scan found a generated value in {table}")
        if self.provider_state().get("canary_seen") is not True:
            raise QualificationError("provider double did not observe the request canary")

    def run(self) -> None:
        self.phase("prepare", self.prepare)
        self.phase("tls", self.make_tls)
        self.phase("compose", self.start)
        self.phase("operator-configuration", self.configure)
        self.phase("async-worker-and-scheduler-liveness", self.exercise_async_liveness)
        self.phase("chat-and-responses", self.exercise_requests)
        self.phase("provider-failures-and-disconnects", self.exercise_failures)
        self.phase("redis-and-timeout-controls", self.exercise_controls)
        self.phase("redis-concurrency", self.exercise_concurrency)
        self.phase("api-termination-and-cli-reconciliation", self.exercise_api_termination_reconciliation)
        self.phase("persistence", self.exercise_persistence)
        self.phase("backup-restore", self.backup_restore)
        self.phase("privacy-input-boundaries", self.exercise_privacy_inputs)
        self.phase("quota-and-key-controls", self.exercise_quota_and_key_controls)
        self.phase("admin-dashboard-session", self.exercise_dashboard)
        self.phase("privacy", self.privacy)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Keep the unique Compose project and runtime evidence")
    args = parser.parse_args()
    runner = Runner(keep=args.keep)
    failure = ""
    try:
        runner.run()
    except (QualificationError, subprocess.SubprocessError, OSError, ValueError, urllib.error.URLError) as exc:
        failure = runner.redact(str(exc))
    finally:
        if runner.runtime.exists() and runner.key_id:
            for request in runner.requests:
                if request.get("request_id"):
                    try:
                        evidence = runner.request_evidence(str(request["request_id"]))
                    except Exception:  # noqa: BLE001
                        evidence = None
                    if evidence:
                        runner.final_evidence.append(evidence)
        cleanup_error = runner.cleanup()
        if cleanup_error:
            failure = f"{failure}; cleanup: {cleanup_error}" if failure else f"cleanup: {cleanup_error}"
    if failure:
        print(f"RESULT=FAIL\nERROR={failure}", file=sys.stderr)
        print(json.dumps({"project": runner.project, "phases": runner.phase_results, "requests": runner.final_evidence, "cleanup": runner.cleanup_checks}, sort_keys=True))
        return 1
    print("RESULT=OK")
    print(json.dumps({"project": runner.project, "phases": runner.phase_results, "requests": runner.final_evidence, "cleanup": runner.cleanup_checks}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
