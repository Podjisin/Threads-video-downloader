# Threads Video Downloader

A simple desktop app to download videos from public Threads posts.

Built with **Python**, **Playwright**, and **Tkinter**.


## Features

- Download videos from Threads URLs
- Automatically selects the best video quality
- Supports MP4 and streaming (m3u8) videos
- Windows standalone `.exe`


## Usage

### Windows (recommended)
1. Download `TVD.exe` from the **Releases** page
2. Run the app
3. Paste a Threads post URL
4. Click **Download**

### From source
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py --gui
````

Install the browser once:

```bash
python -m playwright install chromium
```


## Requirements

* Windows 10+
* Internet connection
* `ffmpeg` (only required for some videos)


## Notes

* Only works with **public** Threads posts
* No account login required (unless the post is restricted)


## Disclaimer

This project is for **educational purposes only**.
Please respect Threads’ terms of service and content creators’ rights.
