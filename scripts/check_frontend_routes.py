#!/usr/bin/env python3
"""Fail if frontend/src no longer produces every route production serves.

Why this exists
---------------
The Next.js source in this repo covers only a fraction of the routes the live
site serves (see docs/BLOCKED.md). Building the frontend image from this repo and
deploying it would 404 every missing page -- the country pages, city pages,
emirate pages, /about, /contact, and the rest.

The deploy workflow runs this before it will build or ship a frontend image. It is
a stop, not a warning: losing 28 indexed pages is unrecoverable in a way that a
failed deploy is not.

Usage
-----
    python scripts/check_frontend_routes.py            # exit 1 if routes missing
    python scripts/check_frontend_routes.py --summary  # always exit 0, just report

Exit codes: 0 all present, 1 routes missing, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
APP_DIR = REPO / "frontend" / "src" / "app"
EXPECTED = REPO / ".github" / "expected-routes.txt"


def expected_routes() -> list[str]:
    if not EXPECTED.is_file():
        sys.exit(f"error: missing {EXPECTED.relative_to(REPO)}")
    out = []
    for line in EXPECTED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return sorted(set(out))


def actual_routes() -> list[str]:
    """Derive routes from the App Router file layout.

    A route is a directory containing page.tsx/page.js. Route groups -- (auth) and
    friends -- do not appear in the URL, so they are stripped.
    """
    if not APP_DIR.is_dir():
        return []
    found = set()
    for pattern in ("**/page.tsx", "**/page.ts", "**/page.jsx", "**/page.js"):
        for page in APP_DIR.glob(pattern):
            rel = page.parent.relative_to(APP_DIR)
            segments = [s for s in rel.parts if not (s.startswith("(") and s.endswith(")"))]
            found.add("/" + "/".join(segments) if segments else "/")
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        action="store_true",
        help="report without failing (exit 0 regardless)",
    )
    args = parser.parse_args()

    expected = expected_routes()
    actual = actual_routes()
    missing = [r for r in expected if r not in actual]
    extra = [r for r in actual if r not in expected]

    print(f"expected routes (production): {len(expected)}")
    print(f"routes in frontend/src      : {len(actual)}")

    if extra:
        print(f"\nnew routes not yet in the manifest ({len(extra)}):")
        for route in extra:
            print(f"  + {route}")
        print("  -> add these to .github/expected-routes.txt in the same commit")

    if not missing:
        print("\nOK: frontend source produces every route production serves.")
        return 0

    print(f"\nBLOCKED: {len(missing)} route(s) production serves are absent from this repo:")
    for route in missing:
        print(f"  - {route}")
    print(
        "\nBuilding and deploying the frontend from this source would return 404 for\n"
        "every route listed above. Restore the missing source before deploying the\n"
        "frontend image. See docs/BLOCKED.md for how.\n"
        "\n"
        "The backend and the static /gold-rates pages deploy independently and are\n"
        "unaffected by this check."
    )
    return 0 if args.summary else 1


if __name__ == "__main__":
    sys.exit(main())
