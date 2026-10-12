"""Objective 181 (F2 hardened in 181-f, simplified in 181-h, R1
approved): vetted connection binding with standard bounds for source
acquisition.

A preflight DNS check alone is NOT a fix: a preflight ``getaddrinfo``
followed by an independent client-side resolution still lets the actual
TCP connection land on an answer that was never vetted (mixed
public/private answer sets, rebinding between the two lookups). This
module therefore binds the ACTUAL connection to the vetted public
numeric destination in one step:

- :class:`VettedNetworkBackend` is the httpcore network backend of the
  production acquisition client. On EVERY new connection it resolves
  the approved hostname with the ordinary system resolver (in-process;
  the host, its administrator, and the OS resolver are trusted - 181-h
  R1), vets the complete answer set (every returned address must be a
  GLOBAL UNICAST address - a mixed or non-global set is refused as a
  whole, never filtered to its public members), and connects only to
  those vetted numeric addresses.
- TLS then starts on the bound socket with the ORIGINAL hostname as
  SNI and the standard verified certificate context: the backend
  returns the library's normal stream, so Host, SNI, and certificate
  chain + hostname verification remain exactly the stock httpx/httpcore
  behavior (no TLS bypass, no custom trust store, no custom stream,
  no proxy or Unix-domain-socket path).
- ``trust_env=False`` on the transport disables environment proxies and
  other implicit network configuration at the transport level; the
  client is additionally constructed with ``trust_env=False``.

Standard bounds (181-h R1, human-approved): the client uses ordinary
httpx per-operation timeouts (connect/write/pool 10 s, read 30 s) and
a COOPERATIVE whole-invocation 120-second collection target enforced
at application checkpoints in ``sources`` (between attempts, after
every returned body chunk, at phase boundaries, and around the 429
retry wait); the documented elapsed-time cutoff for the read-only
collect command is the standard operator watchdog (``timeout
--kill-after=5 300``). This module makes NO claim of a hard total
elapsed bound or of mid-library cancellation: a blocking DNS lookup,
a library operation, or a continuous slow stream can exceed the
target. No custom DNS child process, no deadline-wrapped stream, no
per-DNS processes (the 181-g machinery was removed as approved).
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable, Iterable

import httpcore
import httpx
from httpcore._backends.sync import SyncStream

from slaif_gateway.services.catalog_refresh.sources import SourceFetchError

__all__ = [
    "VettedHTTPTransport",
    "VettedNetworkBackend",
    "vet_public_destination",
]

Resolver = Callable[..., list[tuple]]


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
    applies identically whether or not a collection context is bound.
    The lookup is ordinary and in-process (trusted host/resolver,
    181-h R1); the caller re-checks the collection target before the
    next action.
    """
    try:
        results = resolve(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        raise SourceFetchError("dns_resolution_failed") from None
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


class VettedNetworkBackend(httpcore.SyncBackend):
    """httpcore backend that only ever connects to vetted global-unicast
    IPs.

    ``connect_tcp`` re-resolves and re-vets on every new connection:
    the address set bound to the TCP socket is exactly the set vetted at
    connect time, so preflight-only vetting, stale address caches, and
    rebinding between lookups cannot bypass the destination decision.
    Each candidate connect uses the caller's standard connect timeout;
    a failed candidate simply tries the next vetted IP. The returned
    stream is the LIBRARY'S NORMAL :class:`SyncStream`, so HTTPS
    Host/SNI and the default verified certificate policy remain exactly
    the stock behavior (181-h R1).
    """

    def __init__(self, *, resolve: Resolver = socket.getaddrinfo) -> None:
        self._resolve = resolve

    def connect_tcp(
        self,
        host: str,
        port: int,
        *,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable | None = None,
    ) -> SyncStream:
        ips = vet_public_destination(host, resolve=self._resolve)
        source_address = None if local_address is None else (local_address, 0)
        if socket_options is None:
            socket_options = []
        for ip in ips:
            try:
                sock = socket.create_connection(
                    (ip, port), timeout, source_address=source_address
                )
            except OSError:
                continue
            for option in socket_options:
                sock.setsockopt(*option)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return SyncStream(sock)
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
    """

    def __init__(
        self,
        *,
        resolve: Resolver = socket.getaddrinfo,
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
            network_backend=VettedNetworkBackend(resolve=resolve),
        )
        standard.close()
