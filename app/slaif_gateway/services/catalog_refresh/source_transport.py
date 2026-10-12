"""Objective 181 (F2 hardened in 181-f, G1/G3 in 181-g): vetted,
deadline-enforcing connection binding for source acquisition.

A preflight DNS check alone is NOT a fix: a preflight ``getaddrinfo``
followed by an independent client-side resolution still lets the actual
TCP connection land on an answer that was never vetted (mixed
public/private answer sets, rebinding between the two lookups). This
module therefore binds the ACTUAL connection to the vetted public
numeric destination in one step:

- :class:`VettedNetworkBackend` is the httpcore network backend of the
  production acquisition client. On EVERY new connection it resolves the
  approved hostname, vets the complete answer set (every returned
  address must be a GLOBAL UNICAST address - a mixed or non-global
  set is refused as a whole, never filtered to its public members), and
  connects only to those vetted numeric addresses.
- The collection-owned absolute monotonic deadline (181-g G1) is
  enforced at the ACTUAL operations: the default (production) resolver
  runs in a short-lived owned child process that the parent waits on
  with the REMAINING deadline seconds and KILLS + REAPS on expiry
  (bounded lifetime, reaped on success/failure/timeout - no detached
  lookup, no daemon thread, no process-global timer); every candidate-
  IP connect, the post-connect transition, the TLS handshake, and every
  stream read/partial-write re-check the deadline and clamp the socket
  timeout to the remaining whole-invocation time. No later action starts
  after expiry; one already-started blocking operation may finish
  slightly past expiry, bounded by its own deadline-clamped timeout.
- TLS is then started on the bound socket with the ORIGINAL hostname as
  SNI and the standard verified certificate context, so the Host
  header, SNI, and certificate chain + hostname verification remain
  exactly the library default (no TLS bypass, no custom trust store).
- ``trust_env=False`` on the transport disables environment proxies and
  other implicit network configuration at the transport level; the
  client is additionally constructed with ``trust_env=False``.

The backend is the only TCP connection path inside the acquisition
client: connection reuse reuses streams that a vetted connect created
(those streams keep enforcing the deadline on every operation, so
reused-connection reads/writes cannot outlive the deadline), and
retries and redirect hops open new connections that pass through this
backend again. Nothing else in the acquisition subsystem opens a
socket. The backend performs no I/O of its own beyond the vetted
connect and no decoding of any kind (F3: the caller reads
identity-encoded wire bytes and rejects any other Content-Encoding
before expansion).

Platform/runtime limits (documented honestly):

- The real resolver (``socket.getaddrinfo``) is a blocking C call that
  Python cannot cancel in-process; it therefore runs in an owned
  ``sys.executable -I`` child with an EMPTY environment (it inherits no
  secrets, PYTHONPATH, site configuration, or provider/DB/seal
  authority and executes only ``json``/``socket``/``sys``/``time``).
  On deadline expiry the parent sends SIGKILL (uncatchable) and reaps
  the child; the reap wait itself is bounded (5 s extreme safety net).
  Spawning adds a bounded, small overhead per unique resolution.
- An INJECTED resolver (the unit-test seam; production never injects
  one) is called directly in-process and cannot be killed mid-call:
  the deadline is checked before and after it, and the check between
  the resolver and the next action stops all later network activity.
  Production (default resolver) is fully interruptible via the worker.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
import sys
from typing import Callable, Iterable

import httpcore
import httpx

from httpcore._backends.sync import SyncStream
from httpcore._exceptions import (
    ReadError,
    ReadTimeout,
    WriteError,
    WriteTimeout,
    map_exceptions,
)

from slaif_gateway.services.catalog_refresh.sources import SourceFetchError

__all__ = [
    "ACQUISITION_DNS_CAP_SECONDS",
    "DNS_REAP_TIMEOUT_SECONDS",
    "VettedHTTPTransport",
    "VettedNetworkBackend",
    "resolve_vetted_public_destination",
    "vet_public_destination",
]

Resolver = Callable[..., list[tuple]]

# Real (default-resolver) DNS is ALWAYS bounded: even without a
# collection context the worker wait is capped at the standard
# acquisition deadline, so no execution context silently falls back to
# unbounded DNS (181-g G1).
ACQUISITION_DNS_CAP_SECONDS = 120.0
# Extreme bound for reaping a SIGKILLed child (the kernel reclaims a
# killed process promptly; this is a documented safety net, not a
# normal wait).
DNS_REAP_TIMEOUT_SECONDS = 5.0
# The child prints at most this many bytes; larger output is malformed.
_RESOLVER_MAX_OUTPUT = 8 * 1024
# Test seam (documented): seconds of a GENUINE blocking wait inside the
# real child process before it resolves. 0.0 in production; unit tests
# set it to prove the deadline kills AND reaps the genuinely blocked
# child (a pre-check-only fix cannot pass). The parent still passes the
# value at call time, so monkeypatching the module attribute applies.
_RESOLVER_BLOCK_SECONDS = 0.0

# The child executes ONLY stdlib (json/socket/sys/time), with an empty
# environment, under isolated mode (-I): no site packages, no user
# site, no PYTHONPATH, no configuration authority of any kind.
# The second argv element is a test seam (seconds of a GENUINE
# blocking wait inside the real child process, 0.0 in production) so
# the deadline/kill/reap mechanics can be proven deterministically.
_RESOLVER_SCRIPT = (
    "import json, socket, sys\n"
    "host = sys.argv[1]\n"
    "block = float(sys.argv[2])\n"
    "if block > 0.0:\n"
    "    import time\n"
    "    time.sleep(block)\n"
    "try:\n"
    "    rows = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)\n"
    "except Exception:\n"
    "    sys.stdout.write('ERROR')\n"
    "else:\n"
    "    sys.stdout.write(json.dumps(list(dict.fromkeys(r[4][0] for r in rows))))\n"
)


def _is_global_unicast_ip(text: str) -> bool:
    """True only for GLOBAL UNICAST addresses (v4 or v6).

    Positive classification (``is_global``) in ADDITION to explicit
    loopback/private/link-local/reserved/multicast/unspecified
    exclusions: addresses that are neither private nor global -
    notably RFC 6598 shared address space (100.64.0.0/10),
    documentation ranges, and NAT64 ranges - are refused. IPv4-mapped
    IPv6 addresses are classified by their embedded IPv4 address.
    """
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_global
        and not ip.is_loopback
        and not ip.is_private
        and not ip.is_link_local
        and not ip.is_reserved
        and not ip.is_multicast
        and not ip.is_unspecified
    )


def vet_public_destination(host: str, *, resolve: Resolver) -> tuple[str, ...]:
    """Resolve ``host`` and vet the COMPLETE answer set.

    Returns the vetted global-unicast numeric destinations in answer
    order. A resolver failure or empty answer set is
    ``dns_resolution_failed``; an answer set with NO global-unicast
    address is ``destination_not_public``; a MIXED answer set (at least
    one global-unicast and at least one non-global/loopback/private/
    link-local/reserved/multicast/unspecified or unparseable address)
    is ``destination_mixed_or_not_public`` - mixed sets cannot be bound
    safely and are refused as a whole, never filtered down to their
    global subset.

    Context-independent: this is the socket-decision classifier, so it
    applies identically whether or not a collection deadline context
    is bound (181-g G3).
    """
    try:
        results = resolve(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        raise SourceFetchError("dns_resolution_failed") from None
    return _vet(results)


def _spawn_resolver(*args: object, **kwargs: object) -> subprocess.Popen:
    """Module seam so tests can wrap the REAL Popen (spy) without
    replacing the bounded wait/kill/reap mechanics."""
    return subprocess.Popen(*args, **kwargs)  # type: ignore[arg-type]


def _resolve_default_bounded(
    host: str,
    *,
    wait_seconds: float,
    block_seconds: float = 0.0,
) -> list[str]:
    """Run the real blocking resolver in an OWNED child process.

    The parent waits with the REMAINING deadline seconds; on expiry the
    child is SIGKILLed and reaped (bounded lifetime, no detached
    lookup). The child sees an empty environment and isolated mode
    (no configuration or secret authority). Success returns the answer
    addresses in order; resolver failure, malformed output, or a
    non-zero exit is ``dns_resolution_failed``.
    """
    proc = _spawn_resolver(
        [sys.executable, "-I", "-c", _RESOLVER_SCRIPT, host, repr(block_seconds)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={},
    )
    try:
        out, _ = proc.communicate(timeout=wait_seconds)
    except subprocess.TimeoutExpired:
        # Deadline expired DURING the blocking lookup: kill (uncatchable)
        # and reap with a bounded wait, then fail the acquisition.
        proc.kill()
        try:
            proc.communicate(timeout=DNS_REAP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            proc.wait()  # documented extreme safety net after SIGKILL
        raise SourceFetchError("acquisition_deadline_exceeded") from None
    if (
        proc.returncode != 0
        or not out
        or len(out) > _RESOLVER_MAX_OUTPUT
        or out.strip() == b"ERROR"
    ):
        raise SourceFetchError("dns_resolution_failed") from None
    try:
        addrs = json.loads(out.decode("ascii"))
        if not isinstance(addrs, list) or not all(
            isinstance(a, str) and a for a in addrs
        ):
            raise ValueError
    except (UnicodeDecodeError, ValueError):
        raise SourceFetchError("dns_resolution_failed") from None
    return list(addrs)


def resolve_vetted_public_destination(
    host: str,
    *,
    resolve: Resolver,
    remaining: float | None = None,
) -> tuple[str, ...]:
    """Deadline-bounded vetting of the complete answer set (181-g G1).

    ``remaining`` is the collection context's remaining whole-
    invocation seconds (``None`` when no context is bound). With the
    DEFAULT resolver (the production path) the blocking lookup runs in
    the owned bounded child with the remaining time as its wait (capped
    at ``ACQUISITION_DNS_CAP_SECONDS`` even without a context). With an
    INJECTED resolver (test seam) the call is in-process and the
    deadline is enforced around it. Either way, expiry before a return
    is ``acquisition_deadline_exceeded``; the caller must re-check the
    deadline before the next action (no later network activity after
    expiry).
    """
    if remaining is not None and remaining <= 0:
        raise SourceFetchError("acquisition_deadline_exceeded")
    use_worker = resolve is socket.getaddrinfo
    if use_worker:
        wait = (
            min(remaining, ACQUISITION_DNS_CAP_SECONDS)
            if remaining is not None
            else ACQUISITION_DNS_CAP_SECONDS
        )
        addrs = _resolve_default_bounded(
            host, wait_seconds=wait, block_seconds=_RESOLVER_BLOCK_SECONDS
        )
        results = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (a, 0))
            for a in addrs
        ]
    else:
        try:
            results = resolve(host, None, proto=socket.IPPROTO_TCP)
        except OSError:
            raise SourceFetchError("dns_resolution_failed") from None
    if remaining is not None and remaining <= 0:
        raise SourceFetchError("acquisition_deadline_exceeded")
    return _vet(results)


def _vet(results: list[tuple]) -> tuple[str, ...]:
    """Vet the COMPLETE answer set (context-independent classifier)."""
    if not results:
        raise SourceFetchError("dns_resolution_failed")
    vetted: list[str] = []
    non_public = 0
    for item in results:
        ip = item[4][0]
        if _is_global_unicast_ip(ip):
            vetted.append(ip)
        else:
            non_public += 1
    if non_public:
        code = (
            "destination_mixed_or_not_public"
            if vetted
            else "destination_not_public"
        )
        raise SourceFetchError(code)
    if not vetted:
        raise SourceFetchError("dns_resolution_failed")
    return tuple(dict.fromkeys(vetted))


class DeadlineStream:
    """SyncStream-compatible wrapper that enforces the collection
    deadline on EVERY operation at the socket seam (181-g G1).

    - ``read``: deadline check, requested size clamped to the remaining
      body budget (where practical; a socket read returns at most the
      requested bytes), socket timeout clamped to the remaining
      whole-invocation time, then one ``recv``.
    - ``write``: the PARTIAL-SEND loop re-checks the deadline and
      re-clamps the timeout before EVERY ``send`` (httpcore's own
      loop resets the same timeout on each partial send; clamping once
      would let repeated partial sends overrun the total deadline).
    - ``start_tls``: deadline checks before AND after the handshake,
      handshake timeout clamped to the remaining time; returns a new
      :class:`DeadlineStream` over the upgraded (TLS) socket so the
      enforced stream survives the TLS transition and, through the
      connection pool, connection reuse.
    - ``close``/``get_extra_info``: delegated.

    Without a bound context the wrapper is transparent (unit-test
    streams), preserving the 181-f guard-fixture seams.
    """

    def __init__(self, backend: "VettedNetworkBackend", sock: socket.socket) -> None:
        self._backend = backend
        self._sock = sock

    def _context(self):
        return self._backend._deadline

    def _check(self) -> None:
        ctx = self._context()
        if ctx is not None:
            ctx.check_deadline()

    def _clamp(self, timeout: float | None) -> float | None:
        ctx = self._context()
        if ctx is None:
            return timeout
        rem = ctx.remaining_seconds()
        if rem <= 0:
            raise SourceFetchError("acquisition_deadline_exceeded")
        if timeout is None:
            return rem
        return min(timeout, rem)

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        ctx = self._context()
        if ctx is not None:
            ctx.check_deadline()
            if ctx.exhausted:
                raise SourceFetchError("collection_budget_exhausted")
            # Limit the REQUESTED read size by the remaining body budget
            # where practical: a socket read returns at most n bytes, so
            # the crossing read cannot overrun the budget through this
            # seam. (A mock stream that ignores the requested size is
            # still held to the charge layer in ``_read_bounded``.)
            if ctx.bytes_remaining > 0:
                max_bytes = min(max_bytes, max(1, ctx.bytes_remaining))
        exc_map: dict[type, type] = {socket.timeout: ReadTimeout, OSError: ReadError}
        with map_exceptions(exc_map):
            self._sock.settimeout(self._clamp(timeout))
            return self._sock.recv(max_bytes)

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        if not buffer:
            return
        exc_map: dict[type, type] = {socket.timeout: WriteTimeout, OSError: WriteError}
        with map_exceptions(exc_map):
            while buffer:
                # Deadline check + clamped timeout INSIDE the partial-
                # send loop: each send is bounded by the time remaining
                # AT THAT MOMENT, not a stale per-request timeout.
                self._check()
                self._sock.settimeout(self._clamp(timeout))
                n = self._sock.send(buffer)
                buffer = buffer[n:]

    def start_tls(
        self,
        ssl_context,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> "DeadlineStream":
        # Before TLS: no handshake may start on an expired deadline.
        self._check()
        base = SyncStream(self._sock)
        inner = base.start_tls(
            ssl_context, server_hostname=server_hostname, timeout=self._clamp(timeout)
        )
        # After TLS, before the first write: the transition itself may
        # have consumed the remaining time. The upgraded socket is
        # closed before the failure propagates (no detached resource).
        try:
            self._check()
        except SourceFetchError:
            inner.close()
            raise
        return DeadlineStream(self._backend, inner._sock)

    def close(self) -> None:
        self._sock.close()

    def get_extra_info(self, info: str) -> object:
        return SyncStream(self._sock).get_extra_info(info)


class VettedNetworkBackend(httpcore.SyncBackend):
    """httpcore backend that only ever connects to vetted global-unicast
    IPs, with the collection deadline enforced at the actual operations.

    ``connect_tcp`` re-resolves and re-vets on every new connection:
    the address set bound to the TCP socket is exactly the set vetted at
    connect time, so preflight-only vetting, stale address caches, and
    rebinding between lookups cannot bypass the destination decision.
    With a bound deadline context (``bind_deadline``): the default
    resolver is bounded by the remaining time via the owned killed/
    reaped child; the deadline is re-checked after the lookup, before
    EVERY candidate-IP connect (an expired attempt stops before the
    next candidate), after the connect (before TLS), and the returned
    :class:`DeadlineStream` clamps every read/partial-write/TLS
    operation to the remaining whole-invocation time.
    """

    def __init__(
        self,
        *,
        resolve: Resolver = socket.getaddrinfo,
        deadline: object | None = None,
    ) -> None:
        self._resolve = resolve
        # The collection-owned AcquisitionContext (bound per invocation
        # by ``collect_bundle``); ``None`` = unbound (unit tests, and
        # documented: real DNS still capped at ACQUISITION_DNS_CAP_SECONDS).
        self._deadline = deadline

    def bind_deadline(self, deadline: object) -> None:
        """Bind the collection-owned context for this invocation
        (budget/client lifecycle; the context is owned by the
        collection, never by the client or its JSON)."""
        self._deadline = deadline

    def _remaining(self) -> float | None:
        if self._deadline is None:
            return None
        return self._deadline.remaining_seconds()  # type: ignore[union-attr]

    def connect_tcp(
        self,
        host: str,
        port: int,
        *,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable | None = None,
    ) -> SyncStream:
        remaining = self._remaining()
        if remaining is not None and remaining <= 0:
            raise SourceFetchError("acquisition_deadline_exceeded")
        ips = resolve_vetted_public_destination(
            host, resolve=self._resolve, remaining=remaining
        )
        if self._deadline is not None:
            self._deadline.check_deadline()  # type: ignore[union-attr]
        source_address = None if local_address is None else (local_address, 0)
        if socket_options is None:
            socket_options = []
        for ip in ips:
            # Stop BEFORE connecting the next candidate IP after an
            # expired attempt.
            remaining = self._remaining()
            if remaining is not None and remaining <= 0:
                raise SourceFetchError("acquisition_deadline_exceeded")
            connect_timeout = timeout
            if remaining is not None:
                connect_timeout = (
                    min(timeout, remaining)
                    if timeout is not None
                    else remaining
                )
            if connect_timeout is not None and connect_timeout <= 0:
                raise SourceFetchError("acquisition_deadline_exceeded")
            try:
                sock = socket.create_connection(
                    (ip, port), connect_timeout, source_address=source_address
                )
            except OSError:
                continue
            # After connect, BEFORE TLS: the connect itself may have
            # consumed the remaining time. The expired socket is closed
            # BEFORE the failure propagates (no persistent resource
            # leak on the expired-connect path).
            if self._deadline is not None:
                rem = self._deadline.remaining_seconds()  # type: ignore[union-attr]
                if rem <= 0:
                    sock.close()
                    raise SourceFetchError("acquisition_deadline_exceeded")
                # Bound the TLS handshake that httpcore performs next
                # (its own timeout clamp happens inside start_tls; this
                # is the connect-time floor).
                floor = (
                    min(connect_timeout, rem)
                    if connect_timeout is not None
                    else rem
                )
                sock.settimeout(floor)
            for option in socket_options:
                sock.setsockopt(*option)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return DeadlineStream(self, sock)
        raise SourceFetchError("destination_connect_failed")

    def connect_unix_socket(
        self,
        path: str,
        *,
        timeout: float | None = None,
        socket_options: Iterable | None = None,
    ) -> SyncStream:
        raise SourceFetchError("uds_forbidden")

    def close(self) -> None:
        return None


class VettedHTTPTransport(httpx.HTTPTransport):
    """httpx transport whose connection pool connects only through
    :class:`VettedNetworkBackend`.

    The SSL context (verified chain + hostname policy, the httpx default
    trust store) and every pool limit are inherited unchanged from the
    standard httpx transport; only the network backend is replaced, so
    certificate verification is exactly what the stock client performs.
    ``deadline`` (the collection-owned context) is handed to the
    backend so every real operation is deadline-bounded (181-g G1).
    """

    def __init__(
        self,
        *,
        resolve: Resolver = socket.getaddrinfo,
        deadline: object | None = None,
        **kwargs,
    ) -> None:
        super().__init__(trust_env=False, **kwargs)
        standard = self._pool
        self._pool = httpcore.ConnectionPool(
            ssl_context=standard._ssl_context,
            max_connections=standard._max_connections,
            max_keepalive_connections=standard._max_keepalive_connections,
            keepalive_expiry=standard._keepalive_expiry,
            http1=standard._http1,
            http2=standard._http2,
            uds=standard._uds,
            local_address=standard._local_address,
            retries=standard._retries,
            socket_options=standard._socket_options,
            network_backend=VettedNetworkBackend(resolve=resolve, deadline=deadline),
        )
        standard.close()
