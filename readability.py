#!/usr/bin/env python3
"""Minimal CLI to extract readable text from a web page.

Usage: python readability.py <URL>
"""

import re
import sys
from html.parser import HTMLParser

import httpx

SKIP_TAGS = {
    "script",
    "style",
    "nav",
    "iframe",
    "noscript",
    "svg",
    "form",
    "button",
    "input",
    "select",
    "textarea",
}
BLOCK_TAGS = {
    "p",
    "div",
    "article",
    "section",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "tr",
    "blockquote",
    "pre",
    "br",
    "hr",
    "dt",
    "dd",
    "aside",
    "header",
    "footer",
    "main",
    "figure",
}
SKIP_PAT = re.compile(
    r"\b(sidebar|comment|social|share|related|advert|promo|widget|popup)\b", re.I
)
KEEP_PAT = re.compile(r"\b(article|post|entry|content|main|body|text|story)\b", re.I)


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_stack = []  # stack of tag names being skipped
        self._chunks = []
        self.title = ""
        self._in_title = False

    @property
    def _skipping(self):
        return len(self._skip_stack) > 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
            return
        if self._skipping:
            if tag in SKIP_TAGS:
                self._skip_stack.append(tag)
            return
        if tag in SKIP_TAGS:
            self._skip_stack.append(tag)
            return
        # Check class/id for skip patterns
        a = dict(attrs)
        ci = a.get("class", "") + " " + a.get("id", "")
        if ci.strip() and SKIP_PAT.search(ci) and not KEEP_PAT.search(ci):
            self._skip_stack.append(tag)
            return
        if tag in BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            return
        if self._skipping:
            if self._skip_stack and self._skip_stack[-1] == tag:
                self._skip_stack.pop()
            return
        if tag in BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title = data.strip()
            return
        if self._skipping:
            return
        self._chunks.append(data)

    def handle_entityref(self, name):
        from html import unescape

        if self._skipping:
            return
        self._chunks.append(unescape(f"&{name};"))

    def handle_charref(self, name):
        from html import unescape

        if self._skipping:
            return
        self._chunks.append(unescape(f"&#{name};"))

    def get_text(self):
        raw = "".join(self._chunks)
        lines = [" ".join(line.split()) for line in raw.split("\n")]
        text = "\n".join(line for line in lines if line)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: python readability.py <URL>", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    r = httpx.get(
        url,
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ReadabilityBot/1.0)"},
    )
    r.raise_for_status()
    p = Parser()
    p.feed(r.text)
    if p.title:
        print(f"# {p.title}\n")
    print(p.get_text())


if __name__ == "__main__":
    main()
