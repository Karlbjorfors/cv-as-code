#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["jinja2>=3.1", "pyyaml>=6"]
# ///
"""Render a one-page CV PDF from YAML data with a Jinja HTML template and headless Chromium.

    uv run render.py --cv examples/cv.yml --contact examples/contact.yml --out out/cv.pdf

The PDF is validated after rendering. Exit code is non-zero if:
  - the CV is not exactly one page (unless --allow-multipage), or
  - any contact link (and the mailto: link) is missing as a clickable /URI in the PDF.
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


def render_html(cv: dict, contact: dict, photo: str | None, template: Path) -> str:
    env = Environment(
        loader=FileSystemLoader(template.parent),
        autoescape=select_autoescape(["html", "j2"]),
    )  # default Undefined: optional fields (url, desc, bullets, ...) may simply be left out
    return env.get_template(template.name).render(cv=cv, contact=contact, photo=photo)


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


def count_pages(pdf: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf.read_bytes()))


def validate(pdf: Path, contact: dict, allow_multipage: bool) -> list[str]:
    data = pdf.read_bytes()
    problems = []
    pages = count_pages(pdf)
    if pages != 1 and not allow_multipage:
        problems.append(f"expected 1 page, got {pages} (shorten the content or pass --allow-multipage)")
    uris = {u.decode("latin-1") for u in re.findall(rb"/URI\s*\(([^)]*)\)", data)}
    wanted = [f"mailto:{contact['email']}"] + [l["url"] for l in contact.get("links", [])]
    for url in wanted:
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

    html = render_html(cv, contact, photo_data_uri(photo_path), args.template)
    if args.html:
        args.out.with_suffix(".html").write_text(html, encoding="utf-8")
    print_pdf(html, args.out)

    if problems := validate(args.out, contact, args.allow_multipage):
        print(f"FAIL {args.out}", *(f"  - {m}" for m in problems), sep="\n", file=sys.stderr)
        sys.exit(1)
    print(f"ok: {args.out} ({count_pages(args.out)} page(s), {1 + len(contact.get('links', []))} links verified)")


if __name__ == "__main__":
    main()
