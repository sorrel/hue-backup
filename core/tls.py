"""TLS verification for Philips Hue Bridge connections.

The Hue Bridge presents a certificate signed by the Philips/Signify "Hue Bridge
Root CA" (issuer Common Name ``root-bridge``, or the newer ``Hue Root CA 01``),
and the certificate's own Common Name is the bridge ID. Rather than disabling
certificate verification because the chain isn't anchored in the public web PKI,
we pin those root CAs and assert the bridge ID as the certificate identity, so
every connection to the bridge is fully verified.

References:
  https://developers.meethue.com/develop/application-design-guidance/using-https/
"""

import socket
import ssl
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

# Bundled Philips/Signify Hue Bridge root CAs (legacy 'root-bridge' plus the
# newer 'Hue Root CA 01', so newer bridges continue to verify).
CA_BUNDLE_PATH = Path(__file__).parent / 'huebridge_cacert.pem'


def _verified_context() -> ssl.SSLContext:
    """Build an SSL context that verifies the chain against the pinned Hue CAs.

    Hostname checking is delegated to the adapter's ``assert_hostname`` because
    the certificate Common Name is the bridge ID rather than the IP address we
    connect to. Certificate-chain verification itself stays mandatory.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # Refuse the obsolete TLS 1.0/1.1 protocols (bridges negotiate TLS 1.2).
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(str(CA_BUNDLE_PATH))
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = False
    return ctx


class HueBridgeAdapter(HTTPAdapter):
    """Requests adapter that verifies the bridge certificate against the pinned
    Hue root CA and pins the expected bridge ID as the certificate identity.

    Connections fail closed: a certificate that does not chain to a Hue root CA,
    or whose Common Name is not the expected bridge ID, raises an SSL error.
    """

    def __init__(self, bridge_id: str, *args, **kwargs):
        self._bridge_id = bridge_id
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=_verified_context(),
            assert_hostname=self._bridge_id,
            server_hostname=self._bridge_id,
        )

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs.setdefault('ssl_context', _verified_context())
        proxy_kwargs.setdefault('assert_hostname', self._bridge_id)
        proxy_kwargs.setdefault('server_hostname', self._bridge_id)
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def make_verified_session(bridge_id: str) -> requests.Session:
    """Return a requests Session that fully verifies the Hue bridge identity."""
    session = requests.Session()
    session.mount('https://', HueBridgeAdapter(bridge_id))
    return session


def _common_name(cert: dict) -> str | None:
    """Extract the subject Common Name from a parsed certificate dict."""
    for rdn in cert.get('subject', ()):
        for key, value in rdn:
            if key == 'commonName':
                return value
    return None


def learn_bridge_id(bridge_ip: str, timeout: int = 8) -> str | None:
    """Learn a bridge's ID from its certificate, verifying the CA chain.

    The certificate must chain to a pinned Hue root CA, so the value cannot be
    spoofed by an arbitrary host on the network; its Common Name is the bridge
    ID. Used during first-time setup before the bridge ID has been stored.

    Returns the bridge ID, or None if the device could not be verified as a
    genuine Hue bridge.
    """
    ctx = _verified_context()
    try:
        with socket.create_connection((bridge_ip, 443), timeout=timeout) as sock:
            # SNI is irrelevant to the bridge and hostname checking is disabled;
            # chain verification (CERT_REQUIRED) is what protects this handshake.
            with ctx.wrap_socket(sock, server_hostname=bridge_ip) as ssock:
                cert = ssock.getpeercert()
    except (ssl.SSLError, OSError):
        return None

    return _common_name(cert)
