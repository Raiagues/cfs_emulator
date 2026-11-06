"""Native cFE startup records shared by the mission UI and project generator."""

from dataclasses import dataclass
from pathlib import PurePosixPath
import re


@dataclass(frozen=True)
class StartupEntry:
    fields: tuple
    raw: str
    line: int

    @property
    def name(self):
        return PurePosixPath(self.fields[1]).name.removesuffix(".so")

    @property
    def kind(self):
        return self.fields[0]


def parse_startup(text):
    """Parse the actual cFE format; `!` ends input and `;` ends a record.

    Disabled recipes live after the EOF marker, where cFE never reads them.
    Hash comments must not be put in the active portion of a cFE script.
    """
    active, marker, archived = text.partition("!")

    def records(part, base_line=1, archive=False):
        result = []
        if archive:
            part = re.sub(r"(?m)^[ \t]*#[^\n]*", "", part)
        offset = 0
        for match in re.finditer(r"([^;]*);", part):
            raw = match.group(1).strip()
            line = base_line + part.count("\n", 0, match.start())
            leading = match.group(1)[:len(match.group(1)) - len(match.group(1).lstrip())]
            line += leading.count("\n")
            offset = match.end()
            if not raw:
                continue
            fields = tuple(re.sub(r"\s+", "", field) for field in raw.split(","))
            if len(fields) != 8 or fields[0] not in ("CFE_APP", "CFE_LIB"):
                raise ValueError(f"Invalid cFE startup record at line {line}")
            if not re.fullmatch(r"[A-Za-z0-9_/.-]+", fields[1]):
                raise ValueError(f"Invalid startup module at line {line}")
            if not all(re.fullmatch(r"[A-Za-z_]\w*", fields[i]) for i in (2, 3)):
                raise ValueError(f"Invalid startup entry point or app name at line {line}")
            try:
                if any(int(value, 0) < 0 for value in fields[4:]):
                    raise ValueError()
            except ValueError:
                raise ValueError(f"Invalid startup numeric field at line {line}") from None
            result.append(StartupEntry(fields, raw + ";", line))
        if part[offset:].strip():
            raise ValueError("Startup record is missing its terminating semicolon")
        names = [entry.name for entry in result]
        task_names = [entry.fields[3] for entry in result]
        if len(names) != len(set(names)) or len(task_names) != len(set(task_names)):
            raise ValueError("A module occurs more than once in the startup script")
        return result

    return records(active), records(archived, text[:len(active) + 1].count("\n") + 1, True) if marker else []


def render_startup(active, archived=()):
    content = "\n".join(entry.raw for entry in active) + "\n"
    if archived:
        content += "!\n# Inactive module recipes. cFE stops reading at the ! marker above.\n"
        content += "\n".join(entry.raw for entry in archived) + "\n"
    return content


def reconcile_removed_modules(startup, names):
    """Remove only explicitly deleted modules; all other choices stay intact."""
    removed = set(names)
    active, archived = parse_startup(startup)
    if not any(entry.name in removed for entry in active + archived):
        return startup
    return render_startup([entry for entry in active if entry.name not in removed],
                          [entry for entry in archived if entry.name not in removed])


def reconcile_generated_modules(startup, previous, replacement):
    """Update generated dependencies; which applications start is unchanged."""
    before, _ = parse_startup(previous)
    after, _ = parse_startup(replacement)
    removed = {entry.name for entry in before} - {entry.name for entry in after}
    current, archived = parse_startup(startup)
    removed_apps = {entry.name for entry in before if entry.kind == "CFE_APP"} & removed
    recipes = {entry.name: entry for entry in archived if entry.name not in removed or entry.name in removed_apps}
    recipes.update({entry.name: entry for entry in current if entry.name in removed_apps})
    updated = (render_startup([entry for entry in current if entry.name not in removed], list(recipes.values()))
               if removed else startup)
    active, archived = parse_startup(updated)
    generated = [entry for entry in after if entry.kind == "CFE_LIB"]
    if not generated:
        return updated
    generated_names = {entry.name for entry in generated}
    existing = {entry.name: entry for entry in active if entry.name in generated_names}
    # The replacement is in dependency order (transport before sensor). Move
    # only that generated library group; retain native record fields verbatim
    # and preserve the relative order of unrelated libraries and applications.
    boundary = next((i for i, entry in enumerate(active)
                     if entry.kind == "CFE_APP" or entry.name in generated_names), len(active))
    index = sum(entry.name not in generated_names for entry in active[:boundary])
    retained = [entry for entry in active if entry.name not in generated_names]
    ordered = [existing.get(entry.name, entry) for entry in generated]
    retained[index:index] = ordered
    remaining = [entry for entry in archived if entry.name not in generated_names]
    if [entry.raw for entry in retained] == [entry.raw for entry in active] and remaining == archived:
        return updated
    return render_startup(retained, remaining)

