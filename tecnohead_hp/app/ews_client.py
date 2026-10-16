"""Read-only HTTP/EWS client for the printer LAN."""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        self.parts.append(text)
        if self._in_title:
            self.title_parts.append(text)


@dataclass
class EwsResult:
    reachable: bool
    url: str
    status_code: int | None = None
    title: str = ""
    text: str = ""
    model: str | None = None
    error: str | None = None
    source: str = "EWS"

    def public(self) -> dict[str, object]:
        return {
            "reachable": self.reachable,
            "url": self.url,
            "status_code": self.status_code,
            "title": self.title,
            "model": self.model,
            "error": self.error,
            "source": self.source,
        }


def _extract_model(text: str) -> str | None:
    match = re.search(r"HP\s+(?:Color\s+LaserJet\s+Pro\s+)?MFP\s+M17[67]n", text, flags=re.IGNORECASE)
    return match.group(0) if match else None


def fetch_ews(host: str, *, scheme: str = "http", port: int = 80, username: str = "", password: str = "", timeout: float = 3.0) -> EwsResult:
    # Host is already validated as an IPv4 LAN address by SettingsStore.
    url = f"{scheme}://{host}:{int(port)}/"
    request = Request(url, headers={"User-Agent": "TecnoHead-HP/1.0"}, method="GET")
    if username:
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urlopen(request, timeout=max(0.1, min(timeout, 30.0))) as response:
            body = response.read(512 * 1024)
            charset = response.headers.get_content_charset() or "utf-8"
            decoded = body.decode(charset, errors="replace")
            parser = _TextParser()
            parser.feed(decoded)
            return EwsResult(
                reachable=True,
                url=url,
                status_code=getattr(response, "status", None),
                title=" ".join(parser.title_parts),
                text=" ".join(parser.parts)[:4000],
                model=_extract_model(html.unescape(" ".join(parser.parts))),
            )
    except HTTPError as exc:
        return EwsResult(False, url, status_code=exc.code, error=f"EWS respondeu HTTP {exc.code}")
    except (URLError, TimeoutError, OSError) as exc:
        return EwsResult(False, url, error=f"EWS indisponível: {type(exc).__name__}")
