"""Owned-container qualification for operator branding (187-a, V3).

Runs ONE owned, labeled, loopback-published application container from the
repository image with the read-only ``/branding`` mount. The bootstrap is
test-only and explicit: a synthetic ``Settings`` object (no ambient
environment) and uvicorn ``lifespan="off"``, so public asset and login
rendering are proven without a database engine or live provider. Everything
else is real: the repository image build (labeled at build time), the
nonroot container user, the read-only bind mount, and the HTTP responses.

Ownership discipline (183/184/185 pattern): a unique ``slaif187a.owner``
label on both the built image and the created container, an explicit
127.0.0.1 host port binding, create -> record exact ID -> start, and
cleanup that re-verifies the exact created IDs and their owner label. Only
``docker.errors.NotFound`` is treated as already removed; the built image is
removed by exact ID after identity verification, never by a bare tag
sweep. Unrelated containers and images are never touched.

Real vs mocked: image, container, mount, and HTTP traffic are REAL. The
bootstrap is test-only (synthetic settings, lifespan off, no DB/provider);
no model, provider, email, or protected-credential access occurs.
"""

from __future__ import annotations

import secrets
import shutil
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CUSTOM = REPO_ROOT / "tests" / "fixtures" / "branding" / "custom"
PACKAGED_LOGO = REPO_ROOT / "app" / "slaif_gateway" / "web" / "static" / "img" / "slaif-logo.svg"
PACKAGED_LOGO_URL = "/admin/static/img/slaif-logo.svg"
LABEL_KEY = "slaif187a.owner"

# Test-only bootstrap: real app factory with explicit synthetic settings and
# uvicorn lifespan disabled, so no database engine is created. The app binds
# 0.0.0.0 INSIDE the container; loopback exposure is enforced by the host
# port binding (HostIp 127.0.0.1).
_BOOTSTRAP_TEMPLATE = (
    "import uvicorn\n"
    "from slaif_gateway.config import Settings\n"
    "from slaif_gateway.main import create_app\n"
    "settings = Settings(\n"
    "    APP_ENV='test',\n"
    "    DATABASE_URL=None,\n"
    "    GATEWAY_KEY_PREFIX='sk-slaif-',\n"
    "    GATEWAY_KEY_ACCEPTED_PREFIXES='sk-slaif-',\n"
    "    SLAIF_BRANDING_DIR='/branding',\n"
    "    ADMIN_SESSION_SECRET='{session_secret}',\n"
    ")\n"
    "uvicorn.run(\n"
    "    create_app(settings), host='0.0.0.0', port=8000, log_level='error', lifespan='off'\n"
    ")\n"
)

_STATE: dict[str, object] = {}


@pytest.fixture(scope="module")
def branding_container(tmp_path_factory) -> Iterator[dict[str, object]]:
    import docker

    owner = f"slaif187a-{secrets.token_hex(8)}"
    image_tag = f"slaif187a-branding-{uuid.uuid4().hex[:12]}"
    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    image = None
    container = None
    try:
        image, _logs = client.images.build(
            path=str(REPO_ROOT),
            tag=image_tag,
            labels={LABEL_KEY: owner},
            rm=True,
            pull=False,
        )
        image_id = image.id

        branding_host = tmp_path_factory.mktemp("branding") / "branding"
        shutil.copytree(CUSTOM, branding_host)
        session_secret = secrets.token_urlsafe(32)

        container = client.containers.create(
            image_tag,
            entrypoint="python",
            command=["-c", _BOOTSTRAP_TEMPLATE.format(session_secret=session_secret)],
            ports={8000: ("127.0.0.1", None)},
            labels={LABEL_KEY: owner},
            volumes={str(branding_host): {"bind": "/branding", "mode": "ro"}},
        )
        # Exact created container ID is recorded before start, so a failed
        # start is still cleanable by ID.
        container.start()
        container.reload()
        attrs = container.attrs
        labels = attrs["Config"].get("Labels") or {}
        assert labels.get(LABEL_KEY) == owner, "owned container label mismatch"
        user = attrs["Config"].get("User") or ""
        assert user and user != "root", f"container must run nonroot, got {user!r}"
        bindings = (attrs["HostConfig"] or {}).get("PortBindings") or {}
        configured = bindings.get("8000/tcp") or []
        assert configured and all(b.get("HostIp") == "127.0.0.1" for b in configured), (
            f"container must bind loopback, got: {configured}"
        )
        network_ports = (attrs["NetworkSettings"] or {}).get("Ports") or {}
        bound = network_ports.get("8000/tcp") or []
        assert bound and all(b.get("HostIp") == "127.0.0.1" for b in bound), (
            f"container must publish on loopback, got: {bound}"
        )
        port = bound[0]["HostPort"]
        mounts = attrs.get("Mounts") or []
        branding_mount = next((m for m in mounts if m.get("Destination") == "/branding"), None)
        assert branding_mount is not None, "container missing /branding mount"
        assert branding_mount.get("Type") == "bind", "container /branding must be a bind"
        assert branding_mount.get("RW") is False, "container /branding mount must be read-only"

        base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 120
        last: object = None
        while time.monotonic() < deadline:
            try:
                response = httpx.get(f"{base_url}/admin/branding/style.css", timeout=3)
                if response.status_code == 200:
                    break
                last = f"status {response.status_code}"
            except Exception as exc:  # noqa: BLE001 - startup retry
                last = exc
            time.sleep(0.5)
        else:
            raise AssertionError(f"owned branding container did not become ready: {last!r}")

        _STATE["identity"] = {
            "container_id": container.id,
            "image_id": image_id,
            "owner": owner,
            "user": user,
            "port": port,
        }
        yield {
            "base_url": base_url,
            "branding_host": branding_host,
            "container": container,
        }
    finally:
        try:
            if container is not None:
                try:
                    c = client.containers.get(container.id)
                except docker.errors.NotFound:
                    _STATE["container_cleanup"] = f"already_absent:{container.id[:12]}"
                else:
                    c.reload()
                    c_labels = c.attrs["Config"].get("Labels") or {}
                    assert c_labels.get(LABEL_KEY) == owner, (
                        "refusing to remove a container whose owner label changed"
                    )
                    c.stop(timeout=10)
                    c.remove(force=True)
                    _STATE["container_cleanup"] = f"removed:{container.id[:12]}"
            if image is not None:
                try:
                    img = client.images.get(image.id)
                except docker.errors.NotFound:
                    _STATE["image_cleanup"] = f"already_absent:{image.id[:19]}"
                else:
                    img_labels = (img.attrs["Config"] or {}).get("Labels") or {}
                    assert img_labels.get(LABEL_KEY) == owner, (
                        "refusing to remove an image whose owner label changed"
                    )
                    client.images.remove(img.id, force=False)
                    _STATE["image_cleanup"] = f"removed:{image.id[:19]}"
        finally:
            client.close()


def test_container_serves_override_and_renders_login(branding_container: dict[str, object]) -> None:
    base_url = str(branding_container["base_url"])

    response = httpx.get(f"{base_url}/admin/branding/style.css", timeout=5)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "set-cookie" not in response.headers
    assert response.content == (CUSTOM / "style.css").read_bytes()

    login = httpx.get(f"{base_url}/admin/login", timeout=5)
    assert login.status_code == 200
    assert 'src="/admin/branding/logo"' in login.text
    assert 'src="/admin/branding/logo-compact"' in login.text
    assert 'src="/admin/branding/hero"' in login.text
    assert 'href="/admin/branding/style.css"' in login.text
    assert "branding-active" in login.text
    # The login page legitimately sets its own login-CSRF cookie; the
    # no-cookie guarantee applies to branding asset responses, asserted
    # above and in the asset tests below.


def test_container_mounted_update_picked_up_without_restart(branding_container: dict[str, object]) -> None:
    base_url = str(branding_container["base_url"])
    branding_host = branding_container["branding_host"]

    css_path = branding_host / "style.css"
    original = css_path.read_bytes()
    try:
        css_path.write_text("body { background-color: #123456; }\n")
        updated = httpx.get(f"{base_url}/admin/branding/style.css", timeout=5)
        assert updated.status_code == 200
        assert updated.content == b"body { background-color: #123456; }\n"
        assert "set-cookie" not in updated.headers
    finally:
        css_path.write_bytes(original)
    assert httpx.get(f"{base_url}/admin/branding/style.css", timeout=5).content == original


def test_container_app_cannot_write_mount(branding_container: dict[str, object]) -> None:
    container = branding_container["container"]

    result = container.exec_run(["python", "-c", "open('/branding/probe-write', 'w').close()"])
    assert result.exit_code != 0, "app user must not be able to write the read-only mount"
    branding_host = branding_container["branding_host"]
    assert not (Path(branding_host) / "probe-write").exists()


def test_container_invalid_slot_falls_back_to_packaged(branding_container: dict[str, object]) -> None:
    base_url = str(branding_container["base_url"])
    branding_host = branding_container["branding_host"]
    logo_path = branding_host / "logo.svg"
    original = logo_path.read_bytes()
    try:
        logo_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        )
        response = httpx.get(f"{base_url}/admin/branding/logo", timeout=5)
        assert response.status_code == 200
        assert response.content == PACKAGED_LOGO.read_bytes()
        assert "set-cookie" not in response.headers
        login = httpx.get(f"{base_url}/admin/login", timeout=5)
        assert f'src="{PACKAGED_LOGO_URL}"' in login.text
        assert 'src="/admin/branding/logo-compact"' in login.text
    finally:
        logo_path.write_bytes(original)
