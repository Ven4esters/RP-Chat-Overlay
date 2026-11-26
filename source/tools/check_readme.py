"""Check project Markdown links, anchors, image alt text, and README badges.

Usage from the repository root: ``python source/tools/check_readme.py``.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
README_FILES = (ROOT / "README.md", ROOT / "README.ru.md")
DOCUMENTATION_FILES = tuple(
    path
    for group in (
        sorted(ROOT.glob("*.md")),
        sorted((ROOT / ".github").rglob("*.md")),
        sorted((ROOT / "docs").rglob("*.md")),
        sorted((ROOT / "source" / "tools" / "deeplx-local").glob("*.md")),
    )
    for path in group
    if path not in README_FILES
)
MAX_HEADER_BADGES = 6

_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_ID_RE = re.compile(r"\bid=[\"']([^\"']+)[\"']", re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


class _ImageParser(HTMLParser):
    """Collect HTML image sources and alternative text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        values = dict(attrs)
        self.images.append(
            (values.get("src") or "", values.get("alt") or "", values.get("width") or "")
        )


def _without_fenced_code(text: str) -> str:
    """Remove fenced code so examples are not treated as live links."""
    output: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)[0]
            if fence is None:
                fence = token
            elif token == fence:
                fence = None
            continue
        if fence is None:
            output.append(line)
    return "\n".join(output)


def _destination(raw: str) -> str:
    """Extract a Markdown destination, including angle-bracket syntax."""
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0] if value else ""


def _anchors(text: str) -> set[str]:
    """Return explicit HTML ids and ordinary Markdown heading slugs."""
    found = set(_ID_RE.findall(text))
    used: dict[str, int] = {}
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if not match:
            continue
        heading = re.sub(r"`([^`]*)`", r"\1", match.group(1))
        heading = re.sub(r"<[^>]*>", "", heading)
        slug = re.sub(r"[^\w-]+", "", heading.casefold().replace(" ", "-"))
        count = used.get(slug, 0)
        used[slug] = count + 1
        found.add(slug if count == 0 else f"{slug}-{count}")
    return found


def _check_readme(readme: Path) -> list[str]:
    errors: list[str] = []
    full_text = readme.read_text(encoding="utf-8")
    text = _without_fenced_code(full_text)
    html_images = _ImageParser()
    html_images.feed(text)

    for number, (src, alt, width) in enumerate(html_images.images, start=1):
        if not src:
            errors.append(f"HTML image #{number} has no src")
        if not alt.strip():
            errors.append(f"HTML image #{number} has no alt text")
        if not width.strip():
            errors.append(f"HTML image #{number} has no explicit width")
        if src:
            errors.extend(_check_destination(readme, src, full_text))

    for alt, raw in _IMAGE_RE.findall(text):
        if not alt.strip():
            errors.append(f"Markdown image has no alt text: {_destination(raw)}")
        errors.extend(_check_destination(readme, _destination(raw), full_text))

    for raw in _LINK_RE.findall(text):
        errors.extend(_check_destination(readme, _destination(raw), full_text))

    if readme in README_FILES:
        header = re.split(r"^##\s+", full_text, maxsplit=1, flags=re.MULTILINE)[0]
        badge_count = len(_IMAGE_RE.findall(header))
        if badge_count > MAX_HEADER_BADGES:
            errors.append(f"header has {badge_count} badges; maximum is {MAX_HEADER_BADGES}")
    return errors


def _check_destination(readme: Path, destination: str, source_text: str) -> list[str]:
    if not destination or destination.startswith(("//", "#")):
        if destination.startswith("#"):
            fragment = unquote(destination[1:])
            if fragment not in _anchors(source_text):
                return [f"missing anchor #{fragment}"]
        return []

    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc:
        return []

    path_text = unquote(parsed.path)
    target = (readme.parent / path_text).resolve() if path_text else readme.resolve()
    if not target.exists():
        return [f"missing local target: {destination}"]
    if parsed.fragment:
        fragment = unquote(parsed.fragment)
        try:
            target_text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return [f"cannot check anchor in non-text target: {destination}"]
        if fragment not in _anchors(target_text):
            return [f"missing anchor in {target.relative_to(ROOT)}: #{fragment}"]
    return []


def main() -> int:
    failures = 0
    for document in (*README_FILES, *DOCUMENTATION_FILES):
        if not document.is_file():
            failures += 1
            print(f"missing documentation file: {document.relative_to(ROOT)}")
            continue
        errors = _check_readme(document)
        if errors:
            failures += len(errors)
            for error in errors:
                print(f"{document.relative_to(ROOT)}: {error}")
        else:
            print(f"{document.relative_to(ROOT)}: local links, anchors, and images OK")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
