#!/usr/bin/env python3
"""Serve the CryNet alert page over HTTPS, so a phone can use Web Bluetooth.

Web Bluetooth only works in a *secure context*, and on a phone that
means HTTPS: a plain http:// page from the PC's address is not secure
enough, and neither is a file:// page.  So this serves the page with a
self-signed certificate; the phone shows a certificate warning once, and
"Advanced -> Proceed to..." makes the page a secure context, after which
the browser will offer the hub in its device chooser.

The page itself is research/web/alert.html.  Nothing is sent anywhere:
the server only hands out the one file, and the browser talks to the hub
over Bluetooth.

Usage:
    python firmware/tools/serve_alert_page.py
    python firmware/tools/serve_alert_page.py --port 8443 --no-tls
"""

from __future__ import annotations

import argparse
import http.server
import os
import socket
import shutil
import ssl
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "research" / "web" / "alert.html"
CERT_DIR = ROOT / "research" / "web" / ".cert"


def local_addresses() -> list[str]:
    """The addresses a phone on the same network could reach."""
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return out


def make_certificate() -> tuple[Path, Path]:
    """A self-signed certificate for this machine, made once."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    cert = CERT_DIR / "cert.pem"
    key = CERT_DIR / "key.pem"
    if cert.is_file() and key.is_file():
        return cert, key
    # openssl ships with Git for Windows; it is the simplest way to make a
    # certificate without another dependency.  It is not on the Windows
    # PATH, though, so the usual places are tried as well.
    openssl = shutil.which("openssl")
    if openssl is None:
        for candidate in (r"C:\Program Files\Git\mingw64\bin\openssl.exe",
                          r"C:\Program Files\Git\usr\bin\openssl.exe",
                          "/mingw64/bin/openssl", "/usr/bin/openssl"):
            if Path(candidate).is_file():
                openssl = candidate
                break
    if openssl is None:
        print("openssl was not found", file=sys.stderr)
        sys.exit(1)
    cmd = [
        openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "365",
        "-subj", "/CN=crynet-hub-alert",
    ]
    # openssl takes one -addext per name, so the addresses go into a
    # single comma-separated list.
    addresses = ["127.0.0.1"] + local_addresses()
    cmd += ["-addext",
            "subjectAltName=" + ",".join(f"IP:{a}" for a in addresses)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"the certificate could not be made: {exc}", file=sys.stderr)
        print("openssl is needed for the HTTPS mode; --no-tls serves it "
              "plainly, which the PC can use but a phone cannot (Web "
              "Bluetooth needs a secure context).", file=sys.stderr)
        sys.exit(1)
    return cert, key


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--no-tls", action="store_true",
                    help="serve plain HTTP (the PC can use it; a phone cannot)")
    ap.add_argument("--bind", default="0.0.0.0")
    args = ap.parse_args()

    if not PAGE.is_file():
        print(f"{PAGE} is missing", file=sys.stderr)
        return 1

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(PAGE.parent), **kw)

        def log_message(self, fmt, *a):
            pass   # quiet

    httpd = http.server.ThreadingHTTPServer((args.bind, args.port), Handler)
    scheme = "http"
    if not args.no_tls:
        cert, key = make_certificate()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"

    print(f"serving {PAGE.name} on {scheme}://{args.bind}:{args.port}")
    for address in local_addresses():
        print(f"  on the phone: {scheme}://{address}:{args.port}/")
    print("  the certificate is self-signed, so the phone will warn once: "
          "Advanced -> Proceed to ...")
    print("Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
