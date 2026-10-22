#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["jinja2>=3.1", "pyyaml>=6", "pygments>=2.17"]
# ///
"""Render a one-page CV PDF from YAML data with a Jinja HTML template and headless Chromium.

    uv run render.py --cv examples/cv.yml --contact examples/contact.yml --out out/cv.pdf

With `source_page:` in cv.yml, a second page "CV som kod" is added. It shows excerpts taken
from the very files used for this render (cv.yml + template) and links to the repo.

The PDF is validated after rendering. Exit code is non-zero if:
  - the CV is not exactly one page, plus one for the source page (unless --allow-multipage), or
  - any contact link, the mailto: link or a source-page link is missing as a clickable /URI.
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import BashSessionLexer, HtmlDjangoLexer, YamlLexer

ROOT = Path(__file__).resolve().parent
BROWSERS = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome")


def load_yaml(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        sys.exit(f"error: cannot read {path}:\n{e}")
    if not isinstance(data, dict):
        sys.exit(f"error: {path} must contain a YAML mapping")
    return data


def photo_data_uri(path: Path | None) -> str | None:
    if path is None:
        return None
    if not path.is_file():
        sys.exit(f"error: photo not found: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def find_browser() -> str:
    if env := os.environ.get("CHROME"):
        return env
    for name in BROWSERS:
        if found := shutil.which(name):
            return found
    sys.exit("error: no Chromium/Chrome found; install one or set CHROME=/path/to/browser")


def code(src: str, lexer) -> str:
    return highlight(src, lexer, HtmlFormatter(noclasses=True, style="friendly", nobackground=True))


def clip(text: str, limit: int = 88) -> str:
    """Shorten a long string at a word boundary so excerpt lines don't wrap."""
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def yaml_excerpt(cv: dict) -> str:
    """A short, real excerpt of this CV's data: kicker, two skills, first job with three bullets."""
    job = dict(cv["experience"][0])
    job["bullets"] = [clip(b) for b in job.get("bullets", [])[:3]]
    part = {"lang": cv.get("lang", "sv"), "kicker": cv.get("kicker"),
            "skills": cv["skills"][:2], "experience": [job]}
    text = yaml.safe_dump(part, allow_unicode=True, sort_keys=False, width=1000)
    return text + "# … resten av CV:t i samma format\n"


def template_excerpt(template: Path) -> str:
    """The macro that draws every experience/project entry, cut from the real template."""
    m = re.search(r"\{%- macro entry.*?\{%- endmacro -%\}", template.read_text(encoding="utf-8"), re.S)
    return m.group(0) if m else template.read_text(encoding="utf-8")[:1500]


def source_context(cv: dict, contact: dict, args: argparse.Namespace) -> dict | None:
    conf = cv.get("source_page")
    if not conf:
        return None
    repo = conf["repo"].rstrip("/")
    ctx = {"repo": repo, "example": f"{repo}/tree/main/examples"}
    # basenames only: never leak local paths into the PDF
    cmd = (f"$ uv run render.py --cv {args.cv.name} \\\n"
           f">     --contact {args.contact.name} --out {args.out.name}\n"
           f"{ok_line(args.out.name, 2, len(wanted_links(contact, ctx)))}\n")
    return ctx | {
        "intro": conf.get("intro"),
        "cv_file": args.cv.name,
        "template_file": f"templates/{args.template.name}",
        "yaml_html": code(yaml_excerpt(cv), YamlLexer()),
        "template_html": code(template_excerpt(args.template), HtmlDjangoLexer()),
        "cmd_html": code(cmd, BashSessionLexer()),
    }


def render_html(cv: dict, contact: dict, photo: str | None, source: dict | None, template: Path) -> str:
    env = Environment(
        loader=FileSystemLoader(template.parent),
        autoescape=select_autoescape(["html", "j2"]),
    )  # default Undefined: optional fields (url, desc, bullets, ...) may simply be left out
    return env.get_template(template.name).render(cv=cv, contact=contact, photo=photo, source=source)


def print_pdf(html: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "cv.html"
        src.write_text(html, encoding="utf-8")
        cmd = [
            find_browser(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--user-data-dir={tmp}/profile", f"--print-to-pdf={out}", src.as_uri(),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0 or not out.is_file():
            sys.exit(f"error: browser failed ({res.returncode}):\n{res.stderr[-2000:]}")


def ok_line(out, pages: int, links: int) -> str:
    return f"ok: {out} ({pages} page(s), {links} links verified)"  # also shown on the source page


def count_pages(pdf: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf.read_bytes()))


def wanted_links(contact: dict, source: dict | None) -> list[str]:
    urls = [f"mailto:{contact['email']}"] + [l["url"] for l in contact.get("links", [])]
    return urls + ([source["repo"], source["example"]] if source else [])


def validate(pdf: Path, contact: dict, source: dict | None, allow_multipage: bool) -> list[str]:
    data = pdf.read_bytes()
    problems = []
    pages, expected = count_pages(pdf), 2 if source else 1
    if pages != expected and not allow_multipage:
        problems.append(f"expected {expected} page(s), got {pages} (shorten the content or pass --allow-multipage)")
    uris = {u.decode("latin-1") for u in re.findall(rb"/URI\s*\(([^)]*)\)", data)}
    for url in wanted_links(contact, source):
        if url not in uris:
            problems.append(f"link missing or not clickable in PDF: {url}")
    return problems


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cv", required=True, type=Path, help="CV content (cv.yml)")
    p.add_argument("--contact", required=True, type=Path, help="contact details (contact.yml)")
    p.add_argument("--photo", type=Path, help="portrait image; overrides `photo:` in contact.yml")
    p.add_argument("--template", type=Path, default=ROOT / "templates" / "cv.html.j2")
    p.add_argument("--out", required=True, type=Path, help="output PDF path")
    p.add_argument("--html", action="store_true", help="also write the rendered HTML next to the PDF")
    p.add_argument("--allow-multipage", action="store_true")
    args = p.parse_args()

    cv, contact = load_yaml(args.cv), load_yaml(args.contact)
    for key in ("name", "email"):
        if not contact.get(key):
            sys.exit(f"error: {args.contact} is missing `{key}`")

    photo_path = args.photo
    if photo_path is None and contact.get("photo"):
        photo_path = (args.contact.parent / contact["photo"]).resolve()  # relative to contact.yml

    source = source_context(cv, contact, args)
    html = render_html(cv, contact, photo_data_uri(photo_path), source, args.template)
    if args.html:
        args.out.with_suffix(".html").write_text(html, encoding="utf-8")
    print_pdf(html, args.out)

    if problems := validate(args.out, contact, source, args.allow_multipage):
        print(f"FAIL {args.out}", *(f"  - {m}" for m in problems), sep="\n", file=sys.stderr)
        sys.exit(1)
    print(ok_line(args.out, count_pages(args.out), len(wanted_links(contact, source))))


if __name__ == "__main__":
    main()
