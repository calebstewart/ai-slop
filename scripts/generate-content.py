#!/usr/bin/env python3
"""Turn skills/ into Zola content/.

The skills in this repo are the documentation. Each one already carries a
`SKILL.md` (written for the agent) and a `README.md` (written for a person), and
those files are the only place that prose should ever live. So instead of the
site restating them, this script reads the skill tree and writes the Zola
content files that render it:

    skills/<slug>/README.md         -> content/skills/<slug>/_index.md   (the page body)
    skills/<slug>/SKILL.md          -> front matter for that page, plus its own sub-page
    skills/<slug>/reference/*.md    -> content/skills/<slug>/reference-<stem>.md
    skills/<slug>/templates/*.md    -> content/skills/<slug>/templates-<stem>.md
    skills/<slug>/**  (non-markdown)-> static/files/<slug>/<path>, linked as a raw download

Nothing it writes is committed (see .gitignore) — `nix build` regenerates it
every time, so there is no second copy of anything to drift.

Run with --check to validate the skill tree without writing anything; that is
what `nix flake check` calls.

Stdlib only, deliberately: `skills/pr-status/scripts/pr_status.py` already sets
that precedent, and pulling in PyYAML to read six keys would be silly.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
CONTENT_SKILLS = ROOT / "content" / "skills"
STATIC_FILES = ROOT / "static" / "files"

# Site paths here are written WITHOUT the /ai-slop prefix. Templates prepend it,
# deriving it from `base_url` at render time, because `zola serve` rewrites
# base_url to http://127.0.0.1:1111 and serves at the root — a prefix baked in
# here would 404 every internal link during local preview.
#
# Links inside markdown bodies get a third treatment: they are made relative to
# the page they appear on (see rewrite_links), which is immune to both the prefix
# and the question of where the site root is.

# Directories inside a skill whose markdown becomes a sub-page, in the order
# they should appear in the "Bundled files" list.
DOC_DIRS = ("reference", "templates")

# Site metadata every skill must declare under `metadata:` in its SKILL.md.
# Enforced rather than defaulted: a silently missing tagline turns into a blank
# page subtitle, which is worse than a failed build.
REQUIRED_METADATA = ("tagline", "tags", "requires")


def csv_list(value) -> list[str]:
    """Split a comma-separated metadata string into a list.

    The Agent Skills spec defines `metadata` as a map of string keys to *string*
    values, so tags and requirements are stored comma-separated rather than as
    YAML lists — staying conformant matters more than saving a split() here,
    since a non-conformant skill may be rejected by tooling that isn't this site.
    """
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [part.strip() for part in str(value).split(",") if part.strip()]


class SkillError(Exception):
    """A problem with the skill tree that the author has to fix."""


# --------------------------------------------------------------------------- #
# Front matter
# --------------------------------------------------------------------------- #


def parse_front_matter(text: str, origin: Path) -> tuple[dict, str]:
    """Split a `---`-fenced YAML front matter block off the top of a document.

    Returns (mapping, body). Handles exactly the shapes the skills actually use:
    scalars, inline `[a, b]` lists, `- item` block lists, and one level of
    nesting (the `metadata:` map). Anything else raises, rather than being
    quietly misread — a docs generator that guesses at its own inputs is how you
    end up publishing the wrong thing.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise SkillError(f"{rel(origin)}: expected YAML front matter opening '---'")

    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise SkillError(f"{rel(origin)}: front matter is never closed with '---'") from None

    block = lines[1:end]

    def next_content(index: int) -> str | None:
        """The next line that isn't blank or a comment, for look-ahead."""
        for candidate in block[index + 1 :]:
            if candidate.strip() and not candidate.lstrip().startswith("#"):
                return candidate
        return None

    data: dict = {}
    container: dict | list | None = None  # what indented lines are filling
    container_indent = 0

    for index, raw in enumerate(block):
        lineno = index + 2  # 1-based, and the '---' took line 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()

        if indent == 0:
            container = None

        if stripped.startswith("- "):
            if not isinstance(container, list):
                raise SkillError(f"{rel(origin)}:{lineno}: list item with no list key above it")
            container.append(unquote(stripped[2:].strip()))
            continue

        if ":" not in stripped:
            raise SkillError(f"{rel(origin)}:{lineno}: cannot parse {stripped!r}")

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        if indent > 0:
            if not isinstance(container, dict):
                raise SkillError(
                    f"{rel(origin)}:{lineno}: indented key {key!r} has no parent map"
                )
            if indent != container_indent:
                raise SkillError(
                    f"{rel(origin)}:{lineno}: inconsistent indentation for {key!r}; "
                    "only one level of nesting is supported"
                )
            target: dict = container
        else:
            target = data

        if value != "":
            target[key] = parse_scalar(value)
            continue

        # An empty value opens either a block list or a nested map. The next
        # content line says which, so ask it rather than guessing and patching up
        # afterwards.
        following = next_content(index)
        if following is None or len(following) - len(following.lstrip()) <= indent:
            raise SkillError(f"{rel(origin)}:{lineno}: key {key!r} has no value")
        if following.lstrip().startswith("- "):
            opened: dict | list = []
        else:
            opened = {}
            container_indent = len(following) - len(following.lstrip())
        target[key] = opened
        container = opened

    return data, "\n".join(lines[end + 1 :])


def parse_scalar(value: str):
    """Turn a YAML scalar into a Python value, including inline `[a, b]` lists."""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [unquote(part.strip()) for part in inner.split(",")]
    if value in ("true", "false"):
        return value == "true"
    return unquote(value)


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


# --------------------------------------------------------------------------- #
# Markdown helpers
# --------------------------------------------------------------------------- #


def split_h1(body: str) -> tuple[str | None, str]:
    """Pull a leading `# Heading` off a document, returning (heading, rest).

    The heading becomes the page title, which the template renders itself — so
    leaving it in the body would print it twice.
    """
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        match = re.match(r"^#\s+(.*\S)\s*$", line)
        if match:
            return match.group(1), "\n".join(lines[i + 1 :]).lstrip("\n")
        return None, body  # first real line isn't an H1; leave the body alone
    return None, body


LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")

FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")


def split_fences(body: str):
    """Yield (is_code, text) runs, so link rewriting can skip code blocks.

    This matters more than it looks. `writing-skills/reference/templates.md`
    contains starter templates that link to illustrative files —
    `reference/finance.md`, `reference/errors.md` — which deliberately do not
    exist. They are examples of what a skill author would write, quoted inside
    fences. Rewriting or validating those would either mangle the example or fail
    the build over a file that was never meant to be real.

    Tracks the opening fence's character and length so a fence can contain a
    shorter one, which is exactly how a document that shows markdown examples is
    written.
    """
    lines = body.split("\n")
    out: list[tuple[bool, list[str]]] = []
    marker: str | None = None

    for line in lines:
        match = FENCE_RE.match(line)
        if marker is None:
            if match:
                marker = match.group(2)
                out.append((True, [line]))
                continue
            if not out or out[-1][0]:
                out.append((False, []))
            out[-1][1].append(line)
        else:
            out[-1][1].append(line)
            # Closes only on a bare fence of the same character, at least as long
            # as the one that opened it.
            if match and match.group(2)[0] == marker[0] and len(match.group(2)) >= len(marker):
                if not line.strip()[len(match.group(2)) :].strip():
                    marker = None

    for is_code, chunk in out:
        yield is_code, "\n".join(chunk)


def rewrite_links(body: str, skill: "Skill", base: Path, page: str) -> str:
    """Point relative markdown links at the pages this script generates.

    `base` is the directory of the file the body came from, because a link in
    `reference/best-practices.md` that says `api-wrappers.md` means its sibling,
    not a file at the skill root. `page` is the site path the body will be
    rendered at, because the rewritten link is made relative to it.

    Relative rather than absolute on purpose: the site is served under /ai-slop/
    in production but at / by `zola serve`, and a page-relative link is correct
    under both without the generator needing to know which.

    Anything relative that does not resolve to a real file in the skill directory
    is a hard error: a 404 discovered by a reader is worse than a build that
    refuses to publish. Code blocks are exempt — see split_fences.
    """
    page_dir = page.rstrip("/") or "/"

    def replace(match: re.Match) -> str:
        text, target, title = match.group(1), match.group(2), match.group(3) or ""
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", target, re.I):
            return match.group(0)  # absolute, protocol-relative, or a fragment

        path_part, _, fragment = target.partition("#")
        fragment = f"#{fragment}" if fragment else ""
        resolved = (base / path_part).resolve()

        try:
            relative = resolved.relative_to(skill.path)
        except ValueError:
            raise SkillError(
                f"{rel(base)}: link {target!r} escapes the skill directory"
            ) from None

        if not resolved.exists():
            raise SkillError(f"{rel(base)}: link {target!r} does not exist")

        key = relative.as_posix()
        destination = skill.doc_urls.get(key) or skill.asset_urls.get(key)
        if destination:
            href = posixpath.relpath(destination, page_dir)
            if destination.endswith("/"):
                href += "/"
            return f"[{text}]({href}{fragment}){title}"
        raise SkillError(
            f"{rel(base)}: link {target!r} resolves to {key!r}, "
            "which is neither a generated page nor a copied asset"
        )

    return "".join(
        chunk if is_code else LINK_RE.sub(replace, chunk)
        for is_code, chunk in _joined(split_fences(body))
    )


def _joined(chunks):
    """Re-add the newlines that split_fences' join consumed between runs."""
    chunks = list(chunks)
    for index, (is_code, text) in enumerate(chunks):
        yield is_code, text if index == len(chunks) - 1 else text + "\n"


# --------------------------------------------------------------------------- #
# TOML emission
# --------------------------------------------------------------------------- #


def toml_value(value) -> str:
    """Render a Python value as TOML.

    JSON's string escaping is a subset of TOML basic-string escaping for
    everything that appears here, so json.dumps does the quoting — with
    ensure_ascii off so em dashes stay em dashes in the generated file.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(v)}" for k, v in value.items()) + " }"
    return json.dumps(str(value), ensure_ascii=False)


def front_matter(title: str, template: str, extra: dict, **top) -> str:
    lines = ["+++", f"title = {toml_value(title)}", f"template = {toml_value(template)}"]
    for key, value in top.items():
        lines.append(f"{key} = {toml_value(value)}")
    if extra:
        lines.append("")
        lines.append("[extra]")
        for key, value in extra.items():
            lines.append(f"{key} = {toml_value(value)}")
    lines.append("+++")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


LANG_BY_SUFFIX = {".py": "python", ".sh": "bash", ".bash": "bash", ".rb": "ruby", ".js": "javascript"}


def detect_language(path: Path) -> str:
    if path.suffix in LANG_BY_SUFFIX:
        return LANG_BY_SUFFIX[path.suffix]
    try:
        first = path.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
    except OSError:
        return "text"
    if first.startswith("#!"):
        if "python" in first:
            return "python"
        if "bash" in first or "sh" in first:
            return "bash"
    return "text"


class Skill:
    def __init__(self, path: Path):
        self.path = path
        self.slug = path.name

        skill_md = path / "SKILL.md"
        if not skill_md.is_file():
            raise SkillError(f"{rel(path)}: no SKILL.md")
        self.meta, self.skill_body = parse_front_matter(
            skill_md.read_text(encoding="utf-8"), skill_md
        )

        readme = path / "README.md"
        if not readme.is_file():
            raise SkillError(f"{rel(path)}: no README.md")
        self.readme_body = readme.read_text(encoding="utf-8")

        self.page = f"/skills/{self.slug}/"
        self.validate()
        self.collect_files()

    # -- validation ------------------------------------------------------- #

    def validate(self) -> None:
        name = self.meta.get("name")
        if not name:
            raise SkillError(f"{rel(self.path)}/SKILL.md: front matter has no `name`")
        if name != self.slug:
            raise SkillError(
                f"{rel(self.path)}/SKILL.md: `name: {name}` does not match "
                f"directory name {self.slug!r} — the directory is what sets the "
                "slash command, so they must agree"
            )
        if not self.meta.get("description"):
            raise SkillError(f"{rel(self.path)}/SKILL.md: front matter has no `description`")

        metadata = self.meta.get("metadata")
        if not isinstance(metadata, dict):
            raise SkillError(
                f"{rel(self.path)}/SKILL.md: needs a `metadata:` map carrying the "
                f"site fields ({', '.join(REQUIRED_METADATA)})"
            )
        for key in REQUIRED_METADATA:
            if key not in metadata:
                raise SkillError(f"{rel(self.path)}/SKILL.md: `metadata.{key}` is missing")
        self.metadata = metadata

    # -- file inventory --------------------------------------------------- #

    def collect_files(self) -> None:
        self.docs: list[dict] = []
        self.assets: list[dict] = []
        self.doc_urls: dict[str, str] = {}
        self.asset_urls: dict[str, str] = {}

        # SKILL.md gets its own page: it is what the agent actually reads, and
        # seeing it is the fastest way to judge whether a skill does what you
        # want. The README never quotes it, so without this it is invisible.
        self.doc_urls["SKILL.md"] = f"/skills/{self.slug}/skill/"

        for kind in DOC_DIRS:
            directory = self.path / kind
            if not directory.is_dir():
                continue
            for md in sorted(directory.glob("*.md")):
                key = md.relative_to(self.path).as_posix()
                slug = f"{kind}-{md.stem}"
                self.doc_urls[key] = f"/skills/{self.slug}/{slug}/"

        for path in sorted(self.path.rglob("*")):
            if not path.is_file():
                continue
            key = path.relative_to(self.path).as_posix()
            if key == "README.md" or key in self.doc_urls:
                continue
            if path.suffix == ".md":
                raise SkillError(
                    f"{rel(path)}: markdown outside README.md, SKILL.md and "
                    f"{'/'.join(DOC_DIRS)}/ has nowhere to go on the site"
                )
            self.asset_urls[key] = f"/files/{self.slug}/{key}"

    # -- derived display values ------------------------------------------ #

    @property
    def invocation(self) -> str:
        if self.meta.get("disable-model-invocation"):
            return f"You only, with /{self.slug}"
        if self.meta.get("user-invocable") is False:
            return "Claude only, automatically"
        return f"You with /{self.slug}, or Claude automatically"

    def tools(self) -> list[str]:
        raw = self.meta.get("allowed-tools")
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        return [part.strip() for part in re.split(r"[,\s]+", raw) if part.strip()]


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #


def discover() -> list[Skill]:
    if not SKILLS_DIR.is_dir():
        raise SkillError("skills/ does not exist")
    skills = [
        Skill(path)
        for path in sorted(SKILLS_DIR.iterdir())
        if path.is_dir() and (path / "SKILL.md").is_file()
    ]
    if not skills:
        raise SkillError("skills/ contains no skill directories")
    return skills


def doc_entries(skill: Skill) -> list[dict]:
    """The "Bundled files" list, in reading order: SKILL.md, reference, templates."""
    entries = []
    skill_title, _ = split_h1(skill.skill_body)
    entries.append(
        {
            "title": "SKILL.md",
            "subtitle": skill_title or "",
            "url": skill.doc_urls["SKILL.md"],
            "kind": "skill",
        }
    )
    for kind in DOC_DIRS:
        for key, url in skill.doc_urls.items():
            if not key.startswith(f"{kind}/"):
                continue
            title, _ = split_h1((skill.path / key).read_text(encoding="utf-8"))
            entries.append(
                {
                    "title": Path(key).name,
                    "subtitle": title or "",
                    "url": url,
                    "kind": kind,
                }
            )
    return entries


def asset_entries(skill: Skill) -> list[dict]:
    entries = []
    for key, url in sorted(skill.asset_urls.items()):
        path = skill.path / key
        text = path.read_text(encoding="utf-8", errors="replace")
        entries.append(
            {
                "path": key,
                "url": url,
                "lines": text.count("\n") + 1,
                "language": detect_language(path),
                "executable": bool(path.stat().st_mode & 0o111),
            }
        )
    return entries


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def generate(skills: list[Skill]) -> None:
    if CONTENT_SKILLS.exists():
        shutil.rmtree(CONTENT_SKILLS)
    if STATIC_FILES.exists():
        shutil.rmtree(STATIC_FILES)

    # The parent section exists only to hold the skills; the home page is the
    # index, so there is nothing to render at /skills/ itself. `render = false`
    # is the same trick the landing page uses for its résumé grouping sections.
    write(
        CONTENT_SKILLS / "_index.md",
        front_matter(
            "Skills",
            "index.html",
            {"slugs": [s.slug for s in skills]},
            render=False,
            sort_by="title",
        ),
    )

    for skill in skills:
        generate_skill(skill)


def generate_skill(skill: Skill) -> None:
    docs = doc_entries(skill)
    assets = asset_entries(skill)

    title, body = split_h1(skill.readme_body)
    # A README that opens with `# <slug>` is titling itself; anything else is
    # prose we should not have eaten.
    if title is not None and title.strip() != skill.slug:
        body = skill.readme_body

    extra = {
        "slug": skill.slug,
        "tagline": skill.metadata["tagline"],
        "tags": csv_list(skill.metadata["tags"]),
        "requires": csv_list(skill.metadata["requires"]),
        "agent_description": skill.meta["description"],
        "invocation": skill.invocation,
        "tools": skill.tools(),
        "docs": docs,
        "assets": assets,
    }
    if skill.meta.get("argument-hint"):
        extra["argument_hint"] = skill.meta["argument-hint"]

    write(
        CONTENT_SKILLS / skill.slug / "_index.md",
        front_matter(skill.slug, "skill.html", extra)
        + rewrite_links(body, skill, skill.path, skill.page).strip()
        + "\n",
    )

    # SKILL.md as its own page.
    skill_title, skill_body = split_h1(skill.skill_body)
    write(
        CONTENT_SKILLS / skill.slug / "skill.md",
        front_matter(
            "SKILL.md",
            "skill-doc.html",
            {
                "skill": skill.slug,
                "subtitle": skill_title or "",
                "kind": "skill",
                "source": f"skills/{skill.slug}/SKILL.md",
            },
        )
        + rewrite_links(skill_body, skill, skill.path, skill.doc_urls["SKILL.md"]).strip()
        + "\n",
    )

    for kind in DOC_DIRS:
        for key, url in skill.doc_urls.items():
            if not key.startswith(f"{kind}/"):
                continue
            source = skill.path / key
            doc_title, doc_body = split_h1(source.read_text(encoding="utf-8"))
            write(
                CONTENT_SKILLS / skill.slug / f"{kind}-{Path(key).stem}.md",
                front_matter(
                    doc_title or Path(key).name,
                    "skill-doc.html",
                    {
                        "skill": skill.slug,
                        "subtitle": Path(key).name,
                        "kind": kind,
                        "source": f"skills/{skill.slug}/{key}",
                    },
                )
                + rewrite_links(doc_body, skill, source.parent, url).strip()
                + "\n",
            )

    for key in skill.asset_urls:
        destination = STATIC_FILES / skill.slug / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(skill.path / key, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the skill tree and exit without writing anything",
    )
    args = parser.parse_args()

    try:
        skills = discover()
        if args.check:
            for skill in skills:
                # Exercise everything that can fail on bad input, so --check is a
                # real check and not just a front-matter lint. Link resolution in
                # particular has to cover the bundled docs, not just the README —
                # a sibling link inside reference/ is the case most likely to rot.
                doc_entries(skill)
                asset_entries(skill)
                rewrite_links(split_h1(skill.readme_body)[1], skill, skill.path, skill.page)
                rewrite_links(split_h1(skill.skill_body)[1], skill, skill.path, skill.doc_urls["SKILL.md"])
                for key in skill.doc_urls:
                    if key == "SKILL.md":
                        continue
                    source = skill.path / key
                    rewrite_links(
                        split_h1(source.read_text(encoding="utf-8"))[1],
                        skill,
                        source.parent,
                        skill.doc_urls[key],
                    )
            print(f"ok: {len(skills)} skills ({', '.join(s.slug for s in skills)})")
            return 0
        generate(skills)
    except SkillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    docs = sum(len(s.doc_urls) for s in skills)
    assets = sum(len(s.asset_urls) for s in skills)
    print(
        f"generated {len(skills)} skill pages, {docs} bundled doc pages, "
        f"{assets} raw files"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
