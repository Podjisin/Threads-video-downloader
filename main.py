import argparse
import json
import os
import sys

from tvd.core import (
    default_outname_from_url,
    ffmpeg_download,
    pick_best_candidate,
    sniff_media_urls,
    stream_download,
)

def cli():
    ap = argparse.ArgumentParser(description="Threads downloader (CLI).")
    ap.add_argument("url", nargs="?", help="Threads post URL")
    ap.add_argument("-o", "--out", default=None, help="Output file path (default: ./<postid>.mp4)")
    ap.add_argument("--headful", action="store_true", help="Run browser with UI.")
    ap.add_argument("--timeout", type=int, default=35, help="Browser timeout in seconds.")
    ap.add_argument("--user-data-dir", default=None, help="Persistent Chromium profile dir (login).")
    ap.add_argument("--dump", action="store_true", help="Print candidates JSON and exit.")
    ap.add_argument("--gui", action="store_true", help="Launch Tkinter GUI.")
    args = ap.parse_args()

    # Default to GUI if no args
    if args.gui or len(sys.argv) == 1:
        from tvd.gui import run
        run()
        return

    if not args.url:
        ap.print_help()
        sys.exit(1)

    candidates, ua = sniff_media_urls(
        args.url,
        playwright_timeout_s=max(5, args.timeout),
        headful=args.headful,
        user_data_dir=args.user_data_dir or None,
    )

    if not candidates:
        print("No media URLs found. Try --headful or --user-data-dir.", file=sys.stderr)
        sys.exit(2)

    if args.dump:
        print(
            json.dumps(
                [c.__dict__ for c in candidates],
                indent=2,
            )
        )
        return

    best = pick_best_candidate(candidates)
    if not best:
        print("Could not pick a media candidate.", file=sys.stderr)
        sys.exit(3)

    base = default_outname_from_url(args.url)
    out = args.out or os.path.join(".", f"{base}.mp4")

    headers = {"User-Agent": ua, "Referer": args.url}

    if best.type == "mp4":
        stream_download(best.url, out, headers=headers, on_progress=None)
    else:
        ffmpeg_download(best.url, out, referer=args.url, user_agent=ua)

    print("Saved:", out)


if __name__ == "__main__":
    cli()
