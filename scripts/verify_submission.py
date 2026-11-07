#!/usr/bin/env python3
"""Validate the evidence and reproduce the archived outputs in a temporary directory."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from validate_public_snapshot import ROOT, files, main as validate_public_snapshot

sys.path.insert(0, str(ROOT / "src"))
from closure_artifact.analysis import reproduce_all

MANIFEST_NAME = "MANIFEST.sha256"


def verify_manifest(root: Path) -> None:
    entries = set()
    for line in (root / MANIFEST_NAME).read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("Malformed checksum manifest entry")
        digest, name = match.groups()
        relative = PurePosixPath(name)
        if (
            relative.is_absolute() or ".." in relative.parts or ":" in name
            or "\\" in name or name != relative.as_posix() or name in entries
        ):
            raise ValueError(f"Invalid or repeated manifest path: {name}")
        path = root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError(f"Missing or unsafe manifest path: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Checksum mismatch: {name}")
        entries.add(name)
    observed = {path.relative_to(root).as_posix() for path in files()}
    if entries != observed - {MANIFEST_NAME}:
        raise ValueError("Archive files differ from the checksum inventory")
    print(f"PASS SHA-256 integrity for {len(entries)} files")


def read_output(path: Path) -> object:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.reader(handle))
    raise ValueError(f"Unsupported generated output: {path.name}")


def assert_same(expected: object, actual: object, location: str) -> None:
    if type(expected) is not type(actual):
        raise ValueError(f"Output type mismatch at {location}")
    if isinstance(expected, dict):
        if expected.keys() != actual.keys():
            raise ValueError(f"Output keys differ at {location}")
        for key, value in expected.items():
            assert_same(value, actual[key], f"{location}.{key}")
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            raise ValueError(f"Output length differs at {location}")
        for index, (left, right) in enumerate(zip(expected, actual)):
            assert_same(left, right, f"{location}[{index}]")
    elif expected != actual:
        # Permit only rounding-level differences in numeric results.
        try:
            numeric = not isinstance(expected, (bool, int))
            if isinstance(expected, str):
                numeric = any(mark in expected.lower() for mark in (".", "e"))
            if numeric and math.isclose(float(expected), float(actual), rel_tol=1e-12):
                return
        except (ValueError, TypeError):
            pass
        raise ValueError(f"Reproduced value differs at {location}: {actual!r} (expected {expected!r})")


def verify_outputs() -> None:
    archive = ROOT / "results" / "generated"
    with tempfile.TemporaryDirectory() as directory:
        fresh = Path(directory)
        reproduce_all(ROOT, fresh)
        expected_files = {path.name for path in archive.iterdir() if path.is_file()}
        actual_files = {path.name for path in fresh.iterdir() if path.is_file()}
        if expected_files != actual_files:
            raise ValueError("Reproduced output inventory differs from the archive")
        for name in sorted(expected_files):
            assert_same(read_output(archive / name), read_output(fresh / name), name)
    print(f"PASS {len(expected_files)} reproduced result files match the archive")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-manifest", action="store_true", help="Require the packaged checksum inventory")
    args = parser.parse_args()
    try:
        if args.require_manifest or (ROOT / MANIFEST_NAME).exists():
            verify_manifest(ROOT)
        if validate_public_snapshot():
            return 1
        verify_outputs()
    except (OSError, ValueError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
