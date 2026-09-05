#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path


DAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def unescape_ics(value: str) -> str:
    return (
        value.replace(r"\n", "\n")
        .replace(r"\,", ",")
        .replace(r"\;", ";")
        .replace(r"\\", "\\")
    )


def expected_events(manifest: dict) -> Counter:
    week1 = date.fromisoformat(manifest["week1_monday"])
    expected = Counter()
    for course in manifest["courses"]:
        slot = manifest["slots"][course["slot"]]
        start_clock = time.fromisoformat(slot["start"])
        end_clock = time.fromisoformat(slot["end"])
        for week in course["weeks"]:
            event_date = week1 + timedelta(
                days=(week - 1) * 7 + DAY_INDEX[course["day"]]
            )
            expected[(
                course["name"],
                course["location"],
                datetime.combine(event_date, start_clock).strftime("%Y%m%dT%H%M%S"),
                datetime.combine(event_date, end_clock).strftime("%Y%m%dT%H%M%S"),
            )] += 1
    return expected


def actual_events(text: str) -> tuple[Counter, list[str]]:
    unfolded = re.sub(r"\r\n[ \t]", "", text)
    blocks = re.findall(r"BEGIN:VEVENT\r\n(.*?)\r\nEND:VEVENT", unfolded, re.S)
    actual = Counter()
    uids: list[str] = []
    for block in blocks:
        fields: dict[str, str] = {}
        for line in block.split("\r\n"):
            key, value = line.split(":", 1)
            fields[key.split(";", 1)[0]] = value
        actual[(
            unescape_ics(fields["SUMMARY"]),
            unescape_ics(fields["LOCATION"]),
            fields["DTSTART"],
            fields["DTEND"],
        )] += 1
        uids.append(fields["UID"])
    return actual, uids


def main() -> None:
    manifest_path = Path(sys.argv[1]).resolve()
    ics_path = Path(sys.argv[2]).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = ics_path.read_bytes()
    text = raw.decode("utf-8")

    if b"\n" in raw.replace(b"\r\n", b""):
        raise SystemExit("FAIL: found bare LF line endings")
    overlong = [len(line) for line in raw.split(b"\r\n") if len(line) > 75]
    if overlong:
        raise SystemExit(f"FAIL: physical lines over 75 octets: {overlong[:5]}")
    if not text.startswith("BEGIN:VCALENDAR\r\n") or not text.endswith("END:VCALENDAR\r\n"):
        raise SystemExit("FAIL: invalid VCALENDAR envelope")

    expected = expected_events(manifest)
    actual, uids = actual_events(text)
    if actual != expected:
        missing = expected - actual
        extra = actual - expected
        raise SystemExit(f"FAIL: event mismatch missing={list(missing.items())[:3]} extra={list(extra.items())[:3]}")
    if len(uids) != len(set(uids)):
        raise SystemExit("FAIL: duplicate UID values")

    dates = sorted(key[2][:8] for key in actual.elements())
    print(
        f"OK events={sum(actual.values())} unique_uids={len(uids)} "
        f"first={dates[0]} last={dates[-1]} max_line_octets={max(map(len, raw.split(b'\r\n')))}"
    )


if __name__ == "__main__":
    main()
