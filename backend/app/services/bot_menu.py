"""Caption pagination without splitting HTML tags, entities or emoji."""
import html
from html.parser import HTMLParser

CAPTION_LIMIT = 1000  # Telegram allows 1024 UTF-16 characters after parsing.


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _prefix(value: str, limit: int) -> str:
    size = end = 0
    for char in value:
        width = 2 if ord(char) > 0xFFFF else 1
        if size + width > limit:
            break
        size += width
        end += 1
    if end < len(value):
        boundary = max(value.rfind("\n", 0, end), value.rfind(" ", 0, end))
        if boundary > end // 2:
            end = boundary + 1
    return value[:end]


def text_chunks(value: str, limit: int = CAPTION_LIMIT) -> list[str]:
    chunks = []
    while value:
        part = _prefix(value, limit)
        if not part:
            raise ValueError("Chunk limit cannot fit a Unicode character")
        chunks.append(part)
        value = value[len(part):]
    return chunks or [""]


class _HtmlPages(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pages = []
        self.parts = []
        self.open_tags = []
        self.length = 0

    def flush(self):
        if not self.length:
            return
        self.pages.append("".join(self.parts) + "".join(f"</{tag}>" for tag, _ in reversed(self.open_tags)))
        self.parts = [raw for _, raw in self.open_tags]
        self.length = 0

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.handle_data("\n")
            return
        raw = self.get_starttag_text()
        self.parts.append(raw)
        self.open_tags.append((tag, raw))

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.handle_data("\n")

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.open_tags) - 1, -1, -1) if self.open_tags[i][0] == tag), None)
        if index is not None:
            self.parts.extend(f"</{name}>" for name, _ in reversed(self.open_tags[index:]))
            del self.open_tags[index:]

    def handle_data(self, data):
        while data:
            if self.length == CAPTION_LIMIT:
                self.flush()
            part = _prefix(data, CAPTION_LIMIT - self.length)
            if not part:
                self.flush()
                continue
            self.parts.append(html.escape(part, quote=False))
            self.length += utf16_length(part)
            data = data[len(part):]
            if data:
                self.flush()


def caption_pages(text: str, parse_mode: str | None = "HTML") -> list[tuple[str, str | None]]:
    if utf16_length(text) <= CAPTION_LIMIT:
        return [(text, parse_mode)]
    if (parse_mode or "").upper() == "HTML":
        parser = _HtmlPages()
        parser.feed(text)
        parser.close()
        parser.flush()
        return [(page, "HTML") for page in parser.pages] or [("", None)]
    # A long arbitrary Markdown fragment cannot safely be cut through escapes.
    return [(page, None) for page in text_chunks(text)]


def with_navigation(markup: dict | None, callback: str, page: int, total: int, back: bool = False) -> dict:
    rows = list((markup or {}).get("inline_keyboard", []))
    if total > 1:
        pager = []
        if page > 0:
            pager.append({"text": "←", "callback_data": f"{callback}:{page - 1}"})
        pager.append({"text": f"{page + 1} / {total}", "callback_data": f"{callback}:{page}"})
        if page < total - 1:
            pager.append({"text": "→", "callback_data": f"{callback}:{page + 1}"})
        rows.append(pager)
    if back:
        rows.append([{"text": "← Назад", "callback_data": "bot:home"}])
    return {"inline_keyboard": rows}
