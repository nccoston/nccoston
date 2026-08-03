"""Tiny HTML sanitizer for imported legacy posts. No external dependencies.

Rebuilds the HTML keeping only an allowlist of tags/attributes, so old posts
keep their formatting, links and embedded images while scripts, styles and
event handlers are stripped.
"""

from html import escape
from html.parser import HTMLParser

ALLOWED_TAGS = {
    "b", "i", "u", "em", "strong", "s", "strike", "br", "p", "a", "img",
    "ul", "ol", "li", "blockquote", "font", "center", "hr", "tt", "pre",
    "span", "div", "table", "tbody", "tr", "td", "th", "small", "big", "sub", "sup",
}
VOID_TAGS = {"br", "img", "hr"}
ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "font": {"color", "size", "face"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}


def _safe_url(value):
    v = value.strip().lower()
    return v.startswith(("http://", "https://", "/", "#", "mailto:"))


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.open_stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            return
        kept = []
        for name, value in attrs:
            if value is None:
                continue
            if name in ALLOWED_ATTRS.get(tag, ()):
                if name in ("href", "src") and not _safe_url(value):
                    continue
                kept.append(f'{name}="{escape(value, quote=True)}"')
        attr_str = (" " + " ".join(kept)) if kept else ""
        if tag in VOID_TAGS:
            self.out.append(f"<{tag}{attr_str}>")
        else:
            self.out.append(f"<{tag}{attr_str}>")
            self.open_stack.append(tag)

    def handle_endtag(self, tag):
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS and tag in self.open_stack:
            # close any tags opened after this one, then this one
            while self.open_stack:
                top = self.open_stack.pop()
                self.out.append(f"</{top}>")
                if top == tag:
                    break

    def handle_data(self, data):
        self.out.append(escape(data))

    def result(self):
        while self.open_stack:
            self.out.append(f"</{self.open_stack.pop()}>")
        return "".join(self.out)


def sanitize_html(html):
    if not html:
        return ""
    p = _Sanitizer()
    p.feed(html)
    p.close()
    return p.result()
