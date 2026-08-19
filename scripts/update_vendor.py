#!/usr/bin/env python3
"""Re-vendor pinned third-party frontend assets (clarification #22).

Assets live in ``src/llmdmz/static/vendor/`` and are committed to the repo so
Docker builds and the offline test suite never touch a network. Run this
script manually when upgrading a pin; it records versions in VENDOR_VERSIONS.

  python scripts/update_vendor.py [--force]
"""

from __future__ import annotations

import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
VENDOR = ROOT / "src" / "llmdmz" / "static" / "vendor"

# Pinned versions. Datastar is fetched from the official jsdelivr bundle.
VENDOR_VERSIONS = {
    "datastar.min.js": {
        "version": "1.0.0-beta.11",
        "url": (
            "https://cdn.jsdelivr.net/npm/@starfederation/datastar@"
            "1.0.0-beta.11/dist/datastar.min.js"
        ),
    },
    # No canonical npm distribution of "0build" was locatable; the committed
    # bundle is a hand-authored minimal utility stylesheet. Set a URL here
    # when an upstream is chosen, then re-run this script to replace it.
    "0build.min.css": {"version": "vendored-minimal", "url": None},
}


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        return resp.read()


def main() -> None:
    force = "--force" in __import__("sys").argv
    VENDOR.mkdir(parents=True, exist_ok=True)
    for name, spec in VENDOR_VERSIONS.items():
        target = VENDOR / name
        if target.exists() and not force:
            print(f"keep    {name} ({spec['version']}) — exists; use --force to re-fetch")
            continue
        if not spec["url"]:
            print(f"skip    {name} ({spec['version']}) — no upstream URL pinned")
            continue
        target.write_bytes(fetch(spec["url"]))
        print(f"fetched {name} -> {spec['version']}")


if __name__ == "__main__":
    main()
