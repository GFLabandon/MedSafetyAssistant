"""Extract one allowlisted FDA section from a manually fetched HTML snapshot.

Usage: python scripts/extract_fda_safe_use.py INPUT_HTML OUTPUT_TEXT
The caller reviews the source URL, reuse policy, and output before updating the manifest.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path


class SafeUseSectionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_article = False
        self.in_heading = False
        self.heading_parts = []
        self.collecting = False
        self.finished = False
        self.lines = []
        self.current_parts = []
        self.block_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "article" and attributes.get("id") == "main-content":
            self.in_article = True
        if not self.in_article or self.finished:
            return
        if tag == "h2":
            if self.collecting:
                self.finished = True
                return
            self.in_heading = True
            self.heading_parts = []
        elif self.collecting and tag in {"p", "li"}:
            if self.block_depth == 0:
                self.current_parts = []
            self.block_depth += 1

    def handle_data(self, data):
        if self.in_heading:
            self.heading_parts.append(data)
        elif self.collecting and self.block_depth:
            self.current_parts.append(data + " ")

    def handle_endtag(self, tag):
        if tag == "h2" and self.in_heading:
            heading = " ".join("".join(self.heading_parts).split())
            self.in_heading = False
            if heading == "Safe Use of Acetaminophen":
                self.collecting = True
                self.lines = ["# Safe Use of Acetaminophen"]
        elif tag in {"p", "li"} and self.collecting and self.block_depth:
            self.block_depth -= 1
            if self.block_depth == 0:
                line = " ".join("".join(self.current_parts).split())
                if line:
                    self.lines.append(line)
                self.current_parts = []
        elif tag == "article" and self.in_article:
            self.in_article = False


def extract_section(html: str) -> str:
    parser = SafeUseSectionParser()
    parser.feed(html)
    if not parser.finished or len(parser.lines) < 3:
        raise ValueError("FDA safe-use section not found or incomplete")
    return "\n\n".join(parser.lines) + "\n"


def main():
    args = argparse.ArgumentParser()
    args.add_argument("input_html", type=Path)
    args.add_argument("output_text", type=Path)
    parsed = args.parse_args()
    output = extract_section(parsed.input_html.read_text(encoding="utf-8"))
    parsed.output_text.parent.mkdir(parents=True, exist_ok=True)
    parsed.output_text.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
