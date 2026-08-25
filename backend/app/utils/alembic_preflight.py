"""
Validate the alembic revision graph before `alembic upgrade head` loads it.

Why this exists
---------------
The image is built with `COPY alembic/ ./alembic/` from whatever the build
host's working tree happens to contain. A migration file that exists on that
host but not in git -- a leftover `alembic revision` run on the server, a file
from an abandoned branch -- gets baked into the image and joins the revision
graph. If it closes a loop, or re-parents the root, alembic dies at import time
with:

    CommandError: Cycle is detected in revisions (<every revision id>)

That message lists the entire map, not the offending file, because alembic
raises it from `_detect_cycles` whenever the graph has no head or no base -- at
that point it has no idea which file caused it. Debugging that on a machine you
may not have shell access to is miserable.

What this does
--------------
Parses `alembic/versions/*.py` with `ast` (no imports, no side effects) and
reports the *files* behind the breakage: duplicate revision ids, parents that
reference a revision no file defines, and cycles.

When the graph is unusable it also tries a one-file repair: if removing exactly
one version file turns the graph back into a single-base/single-head DAG, that
file is the stray, and it is moved to `alembic/_quarantine/` -- outside the
directory alembic scans, since `Script._list_py_dir` walks `versions/`
recursively and a subdirectory would not be enough. The deploy then proceeds on
the repository's own history.

The repair only ever fires on a graph that would have crashed the deploy
anyway, and only when the culprit is unambiguous. It moves, never deletes. Set
ALEMBIC_NO_QUARANTINE=1 to report without repairing.
"""
import ast
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("alembic.preflight")

QUARANTINE_DIRNAME = "_quarantine"


def _versions_dir() -> Path:
    override = os.getenv("ALEMBIC_VERSIONS_DIR", "").strip()
    if override:
        return Path(override)
    # app/utils/alembic_preflight.py -> app/utils -> app -> project root
    return Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _parse_file(path: Path):
    """Return (revision, (down_revisions...)) or None if not a revision file."""
    try:
        # utf-8-sig: at least one migration in this tree carries a BOM, which
        # ast.parse rejects as a non-printable character on line 1.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        log.warning("could not parse %s: %s", path.name, exc)
        return None

    revision = None
    down = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            value = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            targets = [stmt.target.id]
            value = stmt.value
        else:
            continue
        if value is None:
            continue
        if "revision" in targets:
            revision = _literal(value)
        if "down_revision" in targets:
            down = _literal(value)

    if not isinstance(revision, str):
        return None
    if down is None:
        parents = ()
    elif isinstance(down, str):
        parents = (down,)
    else:
        parents = tuple(p for p in down if isinstance(p, str))
    return revision, parents


def collect(versions_dir: Path):
    """Map every version file to the revision it defines.

    Returns (nodes, duplicates) where nodes maps revision id -> (path, parents)
    and duplicates lists (revision, path) for ids defined more than once.
    """
    nodes = {}
    duplicates = []
    for path in sorted(versions_dir.glob("*.py")):
        parsed = _parse_file(path)
        if parsed is None:
            continue
        revision, parents = parsed
        if revision in nodes:
            duplicates.append((revision, path))
            continue
        nodes[revision] = (path, parents)
    return nodes, duplicates


def _cycles(nodes):
    """Every cycle in the parent graph, as lists of revision ids."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(nodes, WHITE)
    found = []

    def visit(start):
        # Iterative DFS: this chain is ~70 deep today, but a file that points
        # at itself or at a long tail could otherwise blow the recursion limit.
        stack = [(start, iter(nodes[start][1]))]
        path = [start]
        colour[start] = GREY
        while stack:
            node, parents = stack[-1]
            advanced = False
            for parent in parents:
                if parent not in nodes:
                    continue
                if colour[parent] == GREY:
                    found.append(path[path.index(parent):] + [parent])
                elif colour[parent] == WHITE:
                    colour[parent] = GREY
                    path.append(parent)
                    stack.append((parent, iter(nodes[parent][1])))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                stack.pop()
                path.pop()

    for revision in nodes:
        if colour[revision] == WHITE:
            visit(revision)
    return found


def analyse(nodes):
    """Describe the graph the way alembic's RevisionMap will see it."""
    referenced = set()
    missing = []
    for revision, (path, parents) in nodes.items():
        for parent in parents:
            referenced.add(parent)
            if parent not in nodes:
                missing.append((revision, parent, path))
    return {
        "heads": sorted(r for r in nodes if r not in referenced),
        "bases": sorted(r for r, (_, parents) in nodes.items() if not parents),
        "missing": missing,
        "cycles": _cycles(nodes),
    }


def is_usable(report) -> bool:
    """True when alembic can build a revision map from this graph at all."""
    return (
        bool(report["heads"])
        and bool(report["bases"])
        and not report["missing"]
        and not report["cycles"]
    )


def _candidates(nodes):
    """Every revision whose removal on its own would restore a usable graph.

    Yields (revision, orphans) where `orphans` are the revisions that point at
    it and would be left with a dangling down_revision.

    Removing a revision nothing references is a clean repair. Removing one that
    sits *between* other revisions is not: its children would be left dangling,
    and what they pointed at before it was spliced in is not recoverable from
    what is on disk. A cycle can also usually be broken at more than one link,
    and the files alone do not say which link is the intruder -- so anything
    short of a single clean candidate is reported rather than repaired.
    """
    found = []
    for revision in nodes:
        trimmed = {r: v for r, v in nodes.items() if r != revision}
        if not trimmed:
            continue
        report = analyse(trimmed)
        # Children left pointing at the revision under test are expected;
        # any other dangling reference means this removal is not the answer.
        if any(parent != revision for _, parent, _ in report["missing"]):
            continue
        orphans = tuple(sorted({child for child, _, _ in report["missing"]}))
        if report["cycles"] or len(report["heads"]) != 1:
            continue
        if not orphans and len(report["bases"]) != 1:
            continue
        found.append((revision, orphans))
    return found


def _name(nodes, revision) -> str:
    node = nodes.get(revision)
    return f"{revision} ({node[0].name})" if node else revision


def _describe(nodes, report, duplicates) -> None:
    log.error("alembic revision graph is unusable (%d version files).", len(nodes))
    for revision, path in duplicates:
        log.error("  duplicate revision id %s defined again in %s", revision, path.name)
    for revision, parent, path in report["missing"]:
        log.error("  %s (%s) has down_revision %s, which no file defines",
                  revision, path.name, parent)
    if report["cycles"]:
        # The full paths run to the length of the whole history; the shortest
        # cycle is the one that localises the problem.
        shortest = min(report["cycles"], key=len)
        involved = {r for cycle in report["cycles"] for r in cycle}
        log.error("  %d cycle(s) involving %d revisions; shortest:",
                  len(report["cycles"]), len(involved))
        for revision in shortest[:12]:
            log.error("      %s", _name(nodes, revision))
        if len(shortest) > 12:
            log.error("      ... and %d more", len(shortest) - 12)
    if not report["heads"]:
        log.error("  no head revision: every revision is some other revision's parent")
    if not report["bases"]:
        log.error("  no base revision: every revision has a down_revision")


def _report_unrepairable(nodes, candidates, duplicates) -> None:
    if duplicates:
        log.error("Duplicate revision ids are always a stray file, never a "
                  "repository state; remove the file listed above.")
    elif candidates:
        # A cycle that runs the length of the history can be broken at any of
        # its links, so this list is a starting point, not an accusation. Keep
        # it short -- printing thirty filenames is the noise this check exists
        # to replace.
        log.error("%d revisions would each, on their own, make the graph valid "
                  "again, so the file to blame is not decidable from the tree "
                  "alone. The first few:", len(candidates))
        for revision, orphans in candidates[:5]:
            log.error("      %s -- removing it orphans %s", _name(nodes, revision),
                      ", ".join(orphans) or "nothing")
    else:
        log.error("No single version file explains this.")
    log.error(
        "This instance is not running the repository's migration history. "
        "Rebuild the image from a clean checkout -- `git status --short "
        "alembic/versions` on the build host lists the files that are not "
        "committed, and those are what got baked in."
    )


def run(versions_dir: Path = None) -> int:
    versions_dir = versions_dir or _versions_dir()
    if not versions_dir.is_dir():
        log.warning("no versions directory at %s; skipping preflight.", versions_dir)
        return 0

    nodes, duplicates = collect(versions_dir)
    report = analyse(nodes)

    if is_usable(report) and not duplicates:
        if len(report["heads"]) > 1:
            log.warning("revision graph has %d heads (%s); `upgrade head` will "
                        "need a merge revision.",
                        len(report["heads"]), ", ".join(report["heads"]))
        else:
            log.info("revision graph OK: %d revisions, base %s, head %s.",
                     len(nodes), report["bases"][0], report["heads"][0])
        return 0

    _describe(nodes, report, duplicates)

    if os.getenv("ALEMBIC_NO_QUARANTINE", "").strip() in ("1", "true", "True"):
        log.error("ALEMBIC_NO_QUARANTINE is set; not attempting a repair.")
        return 1

    candidates = [] if duplicates else _candidates(nodes)
    clean = [(rev, orphans) for rev, orphans in candidates if not orphans]

    if len(clean) != 1:
        _report_unrepairable(nodes, candidates, duplicates)
        return 1

    stray = clean[0][0]
    path = nodes[stray][0]
    quarantine = versions_dir.parent / QUARANTINE_DIRNAME
    quarantine.mkdir(exist_ok=True)
    destination = quarantine / path.name
    path.replace(destination)
    log.error(
        "revision %s (%s) is not part of the repository's history and breaks "
        "the graph; moved to %s so the deploy can continue. If that migration "
        "was intended, commit it and re-chain its down_revision onto the "
        "current head.", stray, path.name, destination,
    )

    nodes, duplicates = collect(versions_dir)
    report = analyse(nodes)
    if not is_usable(report):
        _describe(nodes, report, duplicates)
        return 1
    log.warning("revision graph repaired: %d revisions, base %s, head %s.",
                len(nodes), report["bases"][0], report["heads"][0])
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
    )
    try:
        return run()
    except Exception:  # a broken preflight must not be what fails a deploy
        log.exception("preflight check failed; continuing to alembic anyway")
        return 0


if __name__ == "__main__":
    sys.exit(main())
