"""Read documentary tags and update explicitly delimited regions of mission C files."""
from bisect import bisect_right
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

from project.c_source import comments


_DOC = re.compile(r"(?<!\w)[@\\](brief|unit|range|check)\b")
_MARKER = re.compile(r"/\* @studio\.(begin|end) ([a-z][a-z0-9_.-]*)(?: ([a-f0-9]{16}))? \*/")


def annotations(source):
    """Return the reference design's one-line Doxygen annotations, in source order."""
    result = []
    newlines = [m.start() for m in re.finditer("\n", source)]
    for token in comments(source):
        line = bisect_right(newlines, token.start()) + 1
        body = token[0][2:-2] if token[0].startswith("/*") else token[0][2:]
        for offset, row in enumerate(body.splitlines()):
            matches = list(_DOC.finditer(row))
            for index, match in enumerate(matches):
                stop = matches[index + 1].start() if index + 1 < len(matches) else len(row)
                value = row[match.end():stop].strip()
                result.append({"tag": match[1], "value": value, "line": line + offset})
    return result


def digest(body):
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def region(name, body):
    if body and not body.endswith("\n"):
        body += "\n"
    return f"/* @studio.begin {name} {digest(body)} */\n{body}/* @studio.end {name} */\n"


@dataclass(frozen=True)
class Region:
    start: int
    end: int
    body: str
    recorded: str


def regions(source, path):
    result = {}
    active = None
    for comment in comments(source):
        if not comment[0].startswith(("/* @studio.begin", "/* @studio.end")):
            continue
        match = _MARKER.fullmatch(comment[0])
        end = comment.end()
        if not match or (comment.start() and source[comment.start() - 1] != "\n") or source[end:end + 1] != "\n":
            raise ValueError(f"{path}: malformed Studio region at line {source.count(chr(10), 0, end) + 1}")
        kind, name, recorded = match.groups()
        if kind == "begin" and recorded and active is None and name not in result:
            active = (name, recorded, comment.start(), end + 1)
        elif kind == "end" and not recorded and active and active[0] == name:
            _, checksum, start, body_start = active
            result[name] = Region(start, end + 1, source[body_start:comment.start()], checksum)
            active = None
        else:
            raise ValueError(f"{path}: duplicate, nested or unmatched @studio.{kind} {name}")
    if active:
        raise ValueError(f"{path}: missing @studio.end {active[0]}")
    return result


def without_markers(source):
    for section in reversed(tuple(regions(source, "template").values())):
        source = source[:section.start] + section.body + source[section.end:]
    return source


def renamed_source(original, renamed, path):
    """Refresh region checksums for a verified module rename in the same transaction."""
    original_regions = regions(original, path)
    changed = regions(renamed, path)
    if changed.keys() != original_regions.keys():
        raise ValueError(f"{path}: rename changed the set of Studio regions")
    for name, section in reversed(tuple(changed.items())):
        before = original_regions[name]
        if section.body != before.body:
            if digest(before.body) != before.recorded:
                raise ValueError(f"{path}: local changes inside {name}; reconcile this region before renaming")
            renamed = renamed[:section.start] + region(name, section.body) + renamed[section.end:]
    return renamed


def adopt(current, marked, path):
    """Three-way adoption of earlier unmarked copies, using their original settings."""
    previous = without_markers(marked)
    if current == previous:
        return marked
    with tempfile.TemporaryDirectory(prefix="studio-source-") as tmp:
        files = [Path(tmp) / name for name in ("working", "original", "tagged")]
        for file, content in zip(files, (current, previous, marked)):
            file.write_text(content)
        merge = subprocess.run(["git", "merge-file", "-p", *files], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, timeout=10)
    if merge.returncode:
        raise ValueError(f"{path}: cannot uniquely adopt Studio regions in this edited legacy file")
    return merge.stdout


def update(current, desired, path, previous):
    wanted = regions(desired, path)
    existing = regions(current, path)
    if not existing:
        current = adopt(current, previous(), path)
        existing = regions(current, path)
    if wanted.keys() != existing.keys():
        missing = sorted(wanted.keys() ^ existing.keys())
        raise ValueError(f"{path}: missing or unexpected Studio regions: {', '.join(missing)}")
    for name, old in reversed(tuple(existing.items())):
        new = wanted[name]
        if old.body != new.body and digest(old.body) != old.recorded:
            raise ValueError(f"{path}: local changes inside @studio.begin {name}; reconcile this region before syncing")
        current = current[:old.start] + desired[new.start:new.end] + current[old.end:]
    return current
