"""Objective 181-f (F2/F3): vetted connection binding for source acquisition.

A preflight DNS check alone is NOT a fix: a preflight ``getaddrinfo``
followed by an independent client-side resolution still lets the actual
TCP connection land on an answer that was never vetted (mixed
public/private answer sets, rebinding between the two lookups). This
module therefore binds the ACTUAL connection to the vetted public numeric
destination in one step:

- :class:`VettedNetworkBackend` is the httpcore network backend of the
  production acquisition client. On EVERY new connection it resolves the
  approved hostname, vets the complete answer set (every returned address
  must be globally public - a mixed or non-public set is refused, never
  filtered), and connects only to those vetted numeric addresses.
- TLS is then started by httpcore on the bound socket with the ORIGINAL
  hostname as SNI and the standard verified certificate context, so the
  Host header, SNI, and certificate chain + hostname verification remain
  exactly the library default (no TLS bypass, no custom trust store).
- ``trust_env=False`` on the transport disables environment proxies and
  other implicit network configuration at the transport level; the
  client is additionally constructed with ``trust_env=False``.

The backend is the only TCP connection path inside the acquisition
client: connection reuse reuses sockets that a vetted connect created,
and retries and redirect hops open new connections that pass through
this backend again. Nothing else in the acquisition subsystem opens a
socket. The backend performs no I/O of its own beyond the vetted connect
and no decoding of any kind (F3: the caller reads identity-encoded wire
bytes and rejects any other Content-Encoding before expansion).
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable, Iterable

import httpcore
import httpx

from httpcore._backends.sync import SyncStream

from slaif_gateway.services.catalog_refresh.sources import SourceFetchError

__all__ = ["VettedHTTPTransport", "VettedNetworkBackend", "vet_public_destination"]

Resolver = Callable[..., list[tuple]]


def _is_public_ip(text: str) -> bool:
    """True only for globally public unicast addresses (v4 or v6)."""
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    return not (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def vet_public_destination(host: str, *, resolve: Resolver) -> tuple[str, ...]:
    """Resolve ``host`` and vet the COMPLETE answer set.

    Returns the vetted public numeric destinations in answer order.
    A resolver failure or empty answer set is ``dns_resolution_failed``;
    an answer set with NO public address is ``destination_not_public``;
    a MIXED answer set (at least one public and at least one
    loopback/private/link-local/reserved/multicast/unspecified or
    unparseable address) is ``destination_mixed_or_not_public`` - mixed
    sets cannot be bound safely and are refused as a whole, never
    filtered down to their public subset.
    """
    try:
        results = resolve(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        raise SourceFetchError("dns_resolution_failed") from None
    if not results:
        raise SourceFetchError("dns_resolution_failed")
    vetted: list[str] = []
    non_public = 0
    for item in results:
        ip = item[4][0]
        if _is_public_ip(ip):
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
    return tuple(dict.fromkeys(vetted))


class VettedNetworkBackend(httpcore.SyncBackend):
    """httpcore backend that only ever connects to vetted public IPs.

    ``connect_tcp`` re-resolves and re-vets on every new connection:
    the address set bound to the TCP socket is exactly the set vetted at
    connect time, so preflight-only vetting, stale address caches, and
    rebinding between lookups cannot bypass the destination decision.
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

    def __init__(self, *, resolve: Resolver = socket.getaddrinfo, **kwargs) -> None:
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
