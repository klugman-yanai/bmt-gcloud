#!/usr/bin/env python3
"""List or delete PR active registry objects (dry-run by default)."""

from __future__ import annotations

import argparse

from cloud_bmt.gcs import delete_object, list_prefix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR registry cleanup under triggers/pr-active/")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--apply", action="store_true", help="Delete objects (default: dry-run)")
    args = parser.parse_args(argv)
    prefix = f"gs://{args.bucket}/triggers/pr-active/"
    objects = list_prefix(prefix)
    if not objects:
        print("No PR registry objects found.")
        return 0
    for uri in objects:
        if args.apply:
            delete_object(uri)
            print(f"deleted {uri}")
        else:
            print(f"would delete {uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
