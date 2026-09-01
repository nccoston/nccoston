"""Render post bodies: allow a safe subset of HTML, auto-link bare URLs,
preserve newlines. Everything not on the allowlist is shown as plain text;
scripts, event handlers, and javascript: URLs are stripped.
"""

import re
from html import escape
from html.parser import HTMLParser

ALLOWED_TAGS = {
    "b", "i", "u", "em", "strong", "s", "strike", "br", "p", "a", "img",
    "ul", "ol", "li", "blockquote", "pre", "tt", "center", "font", "hr",
    "big", "small", "sub", "sup",
}
VOID_TAGS = {"br", "img", "hr"}
ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "font": {"color", "size", "face"},
}
URL_RE = re.compile(r"(https?://[^\s<>\"]+)")
YOUTUBE_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?\S*?v=|youtu\.be/|"
    r"youtube\.com/shorts/)([A-Za-z0-9_-]{6,20})")
TWEET_RE = re.compile(
    r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]+/status/\d+\S*")
STREAMABLE_RE = re.compile(
    r"https?://(?:www\.)?streamable\.com/(?:e/)?([A-Za-z0-9]+)")
IMAGE_RE = re.compile(
    r"https?://\S+\.(?:gif|jpe?g|png|webp)(?:\?\S*)?$", re.IGNORECASE)
REDDIT_RE = re.compile(
    r"https?://(?:www\.|old\.)?reddit\.com/r/[^/\s]+/comments/\S+")
TIKTOK_RE = re.compile(
    r"https?://(?:www\.)?tiktok\.com/@[^/\s]+/video/(\d+)")


def _linkify(url):
    """Turn a bare URL into a link — or a player/embed for YouTube and tweets."""
    esc = escape(url, quote=True)
    m = YOUTUBE_RE.match(url)
    if m:
        return (f'<div class="yt-embed"><iframe '
                f'src="https://www.youtube-nocookie.com/embed/{m.group(1)}" '
                f'loading="lazy" allowfullscreen></iframe></div>'
                f'<a href="{esc}" rel="nofollow noopener" target="_blank">{escape(url)}</a>')
    if TWEET_RE.match(url):
        return (f'<blockquote class="twitter-tweet">'
                f'<a href="{esc}" rel="nofollow noopener" target="_blank">{escape(url)}</a></blockquote>')
    m = STREAMABLE_RE.match(url)
    if m:
        return (f'<div class="yt-embed"><iframe '
                f'src="https://streamable.com/e/{m.group(1)}" '
                f'loading="lazy" allowfullscreen></iframe></div>'
                f'<a href="{esc}" rel="nofollow noopener" target="_blank">{escape(url)}</a>')
    if IMAGE_RE.match(url):
        # a bare picture/GIF link shows the picture itself
        return (f'<a href="{esc}" rel="nofollow noopener" target="_blank">'
                f'<img src="{esc}" alt="" loading="lazy" '
                f'referrerpolicy="no-referrer"></a>')
    if REDDIT_RE.match(url):
        return (f'<blockquote class="reddit-embed-bq" data-embed-height="500">'
                f'<a href="{esc}" rel="nofollow noopener" target="_blank">{escape(url)}</a></blockquote>')
    m = TIKTOK_RE.match(url)
    if m:
        return (f'<blockquote class="tiktok-embed" cite="{esc}" '
                f'data-video-id="{m.group(1)}" style="max-width:605px">'
                f'<a href="{esc}" rel="nofollow noopener" target="_blank">{escape(url)}</a></blockquote>')
    return f'<a href="{esc}" rel="nofollow noopener" target="_blank">{escape(url)}</a>'


def _safe_url(value):
    v = value.strip().lower()
    return v.startswith(("http://", "https://", "/", "#", "mailto:"))


class _Renderer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.open_stack = []
        self.in_link = 0  # don't auto-link text that's already inside <a>

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
        extra = ""
        if tag == "img":
            # GIF/image hosts hotlink-block by Referer; send none
            extra = ' referrerpolicy="no-referrer"'
        if tag == "a":
            external = any(n == "href" and v and v.strip().lower().startswith("http")
                           for n, v in attrs)
            extra = (' rel="nofollow noopener" target="_blank"' if external
                     else ' rel="nofollow"')
        self.out.append(f"<{tag}{attr_str}{extra}>")
        if tag not in VOID_TAGS:
            self.open_stack.append(tag)
            if tag == "a":
                self.in_link += 1

    def handle_endtag(self, tag):
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS and tag in self.open_stack:
            while self.open_stack:
                top = self.open_stack.pop()
                self.out.append(f"</{top}>")
                if top == "a":
                    self.in_link = max(0, self.in_link - 1)
                if top == tag:
                    break

    def handle_data(self, data):
        if self.in_link:
            self.out.append(escape(data).replace("\n", "<br>\n"))
            return
        # split on URLs so embeds are built from the raw URL, not escaped text
        pieces = []
        last = 0
        for m in URL_RE.finditer(data):
            pieces.append(escape(data[last:m.start()]))
            pieces.append(_linkify(m.group(1)))
            last = m.end()
        pieces.append(escape(data[last:]))
        self.out.append("".join(pieces).replace("\n", "<br>\n"))

    def result(self):
        while self.open_stack:
            self.out.append(f"</{self.open_stack.pop()}>")
        return "".join(self.out)


def render_post(text):
    if not text:
        return ""
    p = _Renderer()
    p.feed(text)
    p.close()
    return p.result()
