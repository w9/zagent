"""Development-only vendoring of pinned Wikipedia text; publication never uses the network."""

import argparse
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from zknowledge.connectors import slug
from zknowledge.snapshot import corpus_root

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "zagent-knowledge-fetch/0.1 (https://github.com/w9/zagent; research demo)"
LICENSE = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
EXCLUDED = (
    "treatment",
    "management",
    "prognosis",
    "therap",
    "see also",
    "references",
    "external links",
    "further reading",
    "notes",
    "bibliography",
    "sources",
    "citations",
    "footnotes",
    "works cited",
    "gallery",
)


def convert(extract: str) -> str:
    output, skipping = [], None
    for line in extract.splitlines():
        heading = re.match(r"^(=+)\s*(.*?)\s*=+$", line.strip())
        if heading:
            level = len(heading.group(1))
            if skipping is not None and level > skipping:
                continue
            skipping = level if heading.group(2).lower().startswith(EXCLUDED) else None
            if skipping is None:
                output += ["", "#" * level + " " + heading.group(2), ""]
            continue
        if skipping is not None or "\\displaystyle" in line:
            continue
        output.append(line.strip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip() + "\n"


def fetch(client: httpx.Client, title: str) -> dict:
    response = client.get(
        API,
        params={
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "extracts|revisions|info",
            "titles": title,
            "redirects": "1",
            "explaintext": "1",
            "exsectionformat": "wiki",
            "rvprop": "ids|timestamp",
            "inprop": "url",
        },
    )
    response.raise_for_status()
    page = response.json()["query"]["pages"][0]
    if page.get("missing") or not page.get("extract"):
        raise LookupError(f"No article for {title!r}")
    return page


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kb-fetch-wikipedia")
    parser.add_argument("--root", type=Path, default=corpus_root() / "public" / "wikipedia")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch already pinned titles")
    args = parser.parse_args(argv)
    sources = yaml.safe_load((args.root / "sources.yaml").read_text())
    lock_path = args.root / "sources.lock.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    retrieved = datetime.now(UTC).date().isoformat()
    missing = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
        for title in [title for group in sources["clusters"].values() for title in group]:
            if title in lock and not args.refresh:
                continue
            try:
                page = fetch(client, title)
            except LookupError as error:
                missing.append(str(error))
                continue
            revision = page["revisions"][0]
            name = slug(page["title"])
            url = f"https://en.wikipedia.org/w/index.php?oldid={revision['revid']}"
            meta = {
                "title": page["title"],
                "requested_title": title,
                "revision_id": revision["revid"],
                "revision_timestamp": revision["timestamp"],
                "url": url,
                "retrieved": retrieved,
                "license": LICENSE,
                "license_url": LICENSE_URL,
                "attribution": "Wikipedia contributors",
            }
            body = convert(page["extract"])
            (args.root / f"{name}.md").write_text(
                "---\n" + yaml.safe_dump(meta, sort_keys=False) + "---\n\n" + body
            )
            lock[title] = {key: meta[key] for key in ("title", "revision_id", "retrieved")}
            lock[title]["file"] = f"{name}.md"
            time.sleep(0.5)
    lock_path.write_text(json.dumps(dict(sorted(lock.items())), indent=2) + "\n")
    notice = [
        "Wikipedia text in this directory",
        "",
        f"Each Markdown file is adapted from a Wikipedia article and is licensed {LICENSE}",
        f"({LICENSE_URL}). Attribution: Wikipedia contributors. The file's front matter",
        "names the article and the exact revision used.",
        "",
        "Changes: converted to plain text by the MediaWiki TextExtracts API, headings",
        "rewritten as Markdown, and treatment, management, prognosis, therapy, reference and",
        "link sections removed. No other text was edited.",
        "",
        "Articles:",
    ]
    notice += [
        f"- {entry['title']}, revision {entry['revision_id']}, retrieved {entry['retrieved']}"
        for entry in sorted(lock.values(), key=lambda entry: entry["title"])
    ]
    (args.root / "NOTICE").write_text("\n".join(notice) + "\n")
    for problem in missing:
        print("missing: " + problem)
    print(f"Pinned {len(lock)} articles")


if __name__ == "__main__":
    main()
