"""Tests for TLS verification in core/tls.py

NOTE: These are offline tests only - no network connections are made. The live
handshake behaviour (learn_bridge_id against a real bridge) is exercised
manually, not here.
"""

import ssl

import requests

from core.tls import (
    CA_BUNDLE_PATH,
    HueBridgeAdapter,
    make_verified_session,
    _common_name,
    _verified_context,
)


class TestCaBundle:
    """The pinned Hue root CA bundle must be present and loadable."""

    def test_bundle_exists(self):
        assert CA_BUNDLE_PATH.exists()

    def test_bundle_contains_both_roots(self):
        text = CA_BUNDLE_PATH.read_text()
        assert text.count('-----BEGIN CERTIFICATE-----') == 2

    def test_bundle_loads_into_context(self):
        # Loading invalid CA data would raise; success means the PEM is valid.
        ctx = _verified_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        # Hostname checking is delegated to the adapter's assert_hostname.
        assert ctx.check_hostname is False


class TestVerifiedContext:
    """The verifying context must require certificate verification."""

    def test_verification_is_mandatory(self):
        ctx = _verified_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED


class TestHueBridgeAdapter:
    """The adapter pins the bridge ID it was constructed with."""

    def test_stores_bridge_id(self):
        adapter = HueBridgeAdapter('C42996FFFEC59BBC')
        assert adapter._bridge_id == 'C42996FFFEC59BBC'


class TestMakeVerifiedSession:
    """make_verified_session wires the verifying adapter onto https://."""

    def test_returns_session(self):
        session = make_verified_session('ABC123')
        assert isinstance(session, requests.Session)

    def test_https_uses_hue_adapter(self):
        session = make_verified_session('ABC123')
        adapter = session.get_adapter('https://10.0.0.1/clip/v2')
        assert isinstance(adapter, HueBridgeAdapter)
        assert adapter._bridge_id == 'ABC123'


class TestCommonName:
    """Extracting the bridge ID (Common Name) from a parsed certificate."""

    def test_extracts_common_name(self):
        cert = {'subject': ((('commonName', 'C42996FFFEC59BBC'),),
                            (('organizationName', 'Philips Hue'),))}
        assert _common_name(cert) == 'C42996FFFEC59BBC'

    def test_returns_none_when_absent(self):
        cert = {'subject': ((('organizationName', 'Philips Hue'),),)}
        assert _common_name(cert) is None

    def test_returns_none_for_empty_cert(self):
        assert _common_name({}) is None
