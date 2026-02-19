from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright

MP4_RE = re.compile(r"\.mp4(\?|$)", re.IGNORECASE)
M3U8_RE = re.compile(r"\.m3u8(\?|$)", re.IGNORECASE)


ProgressCb = Callable[[int, Optional[int], str], None]


@dataclass(frozen=True)
class MediaCandidate:
    url: str
    type: str  # "mp4" | "m3u8" | or idk
    content_type: str
    status: int
    content_length: Optional[int]


def safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\-\. ]+", "_", s, flags=re.UNICODE).strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s[:200] if s else "threads_video"


def default_outname_from_url(post_url: str) -> str:
    p = urlparse(post_url)
    parts = [x for x in p.path.split("/") if x]
    base = parts[-1] if parts else "threads_video"
    return safe_filename(base)


def pick_best_candidate(candidates: list[MediaCandidate]) -> Optional[MediaCandidate]:
    if not candidates:
        return None

    def score(c: MediaCandidate):
        is_mp4 = 1 if c.type == "mp4" else 0
        clen = c.content_length or 0
        return (is_mp4, clen)

    return sorted(candidates, key=score, reverse=True)[0]


def sniff_media_urls(
    url: str,
    *,
    playwright_timeout_s: int = 35,
    headful: bool = False,
    user_data_dir: Optional[str] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> tuple[list[MediaCandidate], str]:
    """Returns (candidates, user_agent)."""
    candidates: list[MediaCandidate] = []
    ua_used = ""

    def log(msg: str):
        if on_log:
            on_log(msg)

    with sync_playwright() as p:
        browser_type = p.chromium

        browser = None
        if user_data_dir:
            context = browser_type.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=not headful,
            )
        else:
            browser = browser_type.launch(headless=not headful)
            context = browser.new_context()

        page = context.new_page()
        ua_used = page.evaluate("() => navigator.userAgent")

        def on_response(resp):
            try:
                rurl = resp.url
                if not (MP4_RE.search(rurl) or M3U8_RE.search(rurl)):
                    return

                ctype = (resp.headers.get("content-type") or "").lower()
                kind = "mp4" if MP4_RE.search(rurl) else "m3u8"

                clen = None
                if "content-length" in resp.headers:
                    with contextlib.suppress(Exception):
                        clen = int(resp.headers["content-length"])

                candidates.append(
                    MediaCandidate(
                        url=rurl,
                        type=kind,
                        content_type=ctype,
                        status=resp.status,
                        content_length=clen,
                    )
                )
                log(f"Found {kind}: {rurl[:80]}...")
            except Exception:
                return

        page.on("response", on_response)

        timeout_ms = max(5, playwright_timeout_s) * 1000
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

        deadline = time.time() + (timeout_ms / 1000.0)
        tried_click = False

        while time.time() < deadline:
            if candidates:
                time.sleep(1.0)
                break

            if not tried_click:
                tried_click = True
                with contextlib.suppress(Exception):
                    page.mouse.wheel(0, 300)
                    time.sleep(0.5)
                    page.mouse.wheel(0, -300)
                    time.sleep(0.5)
                    box = page.viewport_size or {"width": 1200, "height": 800}
                    page.mouse.click(box["width"] // 2, box["height"] // 2)
            time.sleep(0.5)

        # Deduplicate by URL, keeping the first occurrence (which is likkely the most complete one)
        seen = set()
        uniq: list[MediaCandidate] = []
        for c in candidates:
            if c.url in seen:
                continue
            seen.add(c.url)
            uniq.append(c)

        context.close()
        if browser:
            browser.close()

    return uniq, ua_used


def stream_download(
    url: str,
    out_path: str,
    *,
    headers: Optional[dict] = None,
    timeout: int = 60,
    chunk_size: int = 1024 * 1024,
    on_progress: Optional[ProgressCb] = None,
):
    """Range-aware downloader with simple progress callback."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    base_headers: dict = dict(headers or {})

    def progress(done: int, total: Optional[int], msg: str):
        if on_progress:
            on_progress(done, total, msg)

    existing_size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
    total_size: Optional[int] = None
    supports_ranges = False

    with contextlib.suppress(Exception):
        head_resp = requests.head(url, headers=base_headers, timeout=timeout, allow_redirects=True)
        head_resp.raise_for_status()
        if head_resp.headers.get("accept-ranges", "").lower() == "bytes":
            supports_ranges = True
        if "content-length" in head_resp.headers:
            with contextlib.suppress(Exception):
                total_size = int(head_resp.headers["content-length"])

    mode = "ab" if existing_size and supports_ranges else "wb"
    downloaded = existing_size

    if total_size is not None and downloaded >= total_size > 0:
        progress(downloaded, total_size, "Already downloaded")
        return

    with open(out_path, mode) as f:
        while True:
            req_headers = dict(base_headers)
            if supports_ranges and downloaded:
                req_headers["Range"] = f"bytes={downloaded}-"

            resp = requests.get(url, stream=True, headers=req_headers, timeout=timeout)
            resp.raise_for_status()

            status = resp.status_code
            if status not in (200, 206):
                raise RuntimeError(f"Unexpected HTTP status code: {status}")

            if total_size is None and "content-length" in resp.headers:
                with contextlib.suppress(Exception):
                    clen = int(resp.headers["content-length"])
                    total_size = downloaded + clen if status == 206 else clen

            if "Range" in req_headers and status == 200 and downloaded:
                f.seek(0)
                f.truncate()
                downloaded = 0
                progress(downloaded, total_size, "Server ignored Range; restarting")

            wrote_any = False
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                wrote_any = True
                downloaded += len(chunk)
                progress(downloaded, total_size, "Downloading")

            resp.close()

            if not wrote_any:
                break
            if total_size is not None and downloaded >= total_size:
                break
            if not supports_ranges:
                break

    progress(downloaded, total_size, "Done")


def ffmpeg_download(
    m3u8_url: str,
    out_path: str,
    *,
    referer: Optional[str] = None,
    user_agent: Optional[str] = None,
    on_log: Optional[Callable[[str], None]] = None,
):
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH. Install ffmpeg first.")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    headers = []
    if referer:
        headers.append(f"Referer: {referer}")
    if user_agent:
        headers.append(f"User-Agent: {user_agent}")
    header_arg = "\\r\\n".join(headers) + ("\\r\\n" if headers else "")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-headers", header_arg,
        "-i", m3u8_url,
        "-c", "copy",
        out_path,
    ]
    if on_log:
        on_log("Running ffmpeg...")
    subprocess.run(cmd, check=True)
    if on_log:
        on_log("ffmpeg done.")
