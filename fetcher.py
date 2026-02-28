"""Audio fetcher — handles --file, --rss, and --youtube sources."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn

console = Console()

AUDIO_MIME_TYPES = {"audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/ogg", "audio/wav", "audio/mp3"}


def _sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:120]


def fetch_file(path: str) -> tuple[str, str]:
    """Validate local file path. Returns (audio_path, episode_title)."""
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        console.print(f"[bold red]File not found:[/bold red] {expanded}")
        raise SystemExit(1)
    title = Path(expanded).stem
    console.print(f"[bold]Source:[/bold] local file")
    console.print(f"[bold]File:[/bold] {expanded}")
    return expanded, title


def _resolve_apple_podcasts_url(url: str) -> str:
    """If url is an Apple Podcasts link, resolve it to the underlying RSS feed URL."""
    if "podcasts.apple.com" not in url:
        return url

    # Extract podcast ID from URL (e.g. /id1473872585)
    match = re.search(r"/id(\d+)", url)
    if not match:
        return url

    podcast_id = match.group(1)
    console.print(f"[dim]Resolving Apple Podcasts ID {podcast_id} to RSS feed...[/dim]")
    try:
        lookup = requests.get(
            f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcast",
            timeout=15,
        )
        lookup.raise_for_status()
        results = lookup.json().get("results", [])
        if results and "feedUrl" in results[0]:
            feed_url = results[0]["feedUrl"]
            console.print(f"[dim]Resolved to: {feed_url}[/dim]")
            return feed_url
    except (requests.RequestException, ValueError, KeyError):
        pass

    console.print("[yellow]Could not resolve Apple Podcasts URL to RSS feed.[/yellow]")
    return url


def fetch_rss(url: str, episode_index: int, temp_dir: str) -> tuple[str, str]:
    """Download episode audio from RSS feed. Returns (audio_path, episode_title).

    episode_index is 1-based (1 = latest).
    Accepts direct RSS URLs or Apple Podcasts URLs.
    """
    url = _resolve_apple_podcasts_url(url)

    console.print(f"[bold]Source:[/bold] RSS feed")
    console.print(f"[dim]Parsing feed: {url}[/dim]")

    # Fetch feed content with requests (uses certifi for SSL) then parse
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "podcast-digest/1.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except requests.RequestException as exc:
        console.print(f"[bold red]Failed to fetch RSS feed:[/bold red] {exc}")
        raise SystemExit(1)
    if feed.bozo and not feed.entries:
        console.print(f"[bold red]Failed to parse RSS feed:[/bold red] {feed.bozo_exception}")
        raise SystemExit(1)

    if not feed.entries:
        console.print("[bold red]RSS feed has no entries.[/bold red]")
        raise SystemExit(1)

    console.print(f"[bold]Feed:[/bold] {feed.feed.get('title', 'Unknown')}")
    console.print(f"[bold]Episodes found:[/bold] {len(feed.entries)}")

    # Find episodes with audio enclosures
    episodes_with_audio: list[tuple[dict, str, str]] = []  # (entry, enclosure_url, title)
    for entry in feed.entries:
        enclosures = entry.get("enclosures", [])
        for enc in enclosures:
            enc_type = enc.get("type", "")
            enc_url = enc.get("href", "") or enc.get("url", "")
            if enc_url and (enc_type in AUDIO_MIME_TYPES or enc_url.endswith((".mp3", ".m4a", ".mp4"))):
                title = entry.get("title", "Unknown Episode")
                episodes_with_audio.append((entry, enc_url, title))
                break

    if not episodes_with_audio:
        console.print("[bold red]No audio enclosures found in feed.[/bold red]")
        console.print("[dim]Found enclosure types:[/dim]")
        for entry in feed.entries[:5]:
            for enc in entry.get("enclosures", []):
                console.print(f"  - {enc.get('type', 'unknown')}: {enc.get('href', 'no url')[:80]}")
        raise SystemExit(1)

    # Select episode
    idx = episode_index - 1
    if idx < 0 or idx >= len(episodes_with_audio):
        console.print(f"[bold red]Episode {episode_index} out of range (1-{len(episodes_with_audio)}).[/bold red]")
        raise SystemExit(1)

    entry, audio_url, title = episodes_with_audio[idx]
    duration = entry.get("itunes_duration", "unknown")
    console.print(f"[bold]Episode:[/bold] {title}")
    console.print(f"[bold]Duration:[/bold] {duration}")

    # Download
    os.makedirs(temp_dir, exist_ok=True)
    ext = _guess_extension(audio_url)
    filename = _sanitize_filename(title) + ext
    output_path = os.path.join(temp_dir, filename)

    if os.path.exists(output_path):
        console.print(f"[dim]Using cached: {output_path}[/dim]")
        return output_path, title

    console.print(f"[dim]Downloading audio...[/dim]")
    response = requests.get(audio_url, stream=True, timeout=30)
    response.raise_for_status()
    total = int(response.headers.get("content-length", 0))

    with Progress(
        TextColumn("[bold blue]Downloading"),
        BarColumn(bar_width=40),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("download", total=total or None)
        with open(output_path, "wb") as f:
            for data in response.iter_content(chunk_size=1024 * 64):
                f.write(data)
                progress.update(task, advance=len(data))

    return output_path, title


def _guess_extension(url: str) -> str:
    """Guess file extension from URL."""
    path = urlparse(url).path.lower()
    for ext in (".mp3", ".m4a", ".mp4", ".ogg", ".wav"):
        if path.endswith(ext):
            return ext
    return ".mp3"


def fetch_youtube(url: str, temp_dir: str) -> tuple[str, str]:
    """Download audio from YouTube via yt-dlp. Returns (audio_path, episode_title)."""
    console.print(f"[bold]Source:[/bold] YouTube")
    console.print(f"[dim]{url}[/dim]")

    os.makedirs(temp_dir, exist_ok=True)
    output_template = os.path.join(temp_dir, "%(title)s.%(ext)s")

    # First get the title
    try:
        title_result = subprocess.run(
            ["yt-dlp", "--get-title", url],
            capture_output=True, text=True, timeout=30,
        )
        title = title_result.stdout.strip() or "youtube_audio"
    except (FileNotFoundError, subprocess.SubprocessError):
        title = "youtube_audio"

    console.print(f"[bold]Title:[/bold] {title}")

    # Check for cached file
    safe_title = _sanitize_filename(title)
    cached = os.path.join(temp_dir, safe_title + ".mp3")
    if os.path.exists(cached):
        console.print(f"[dim]Using cached: {cached}[/dim]")
        return cached, title

    console.print("[dim]Downloading audio with yt-dlp...[/dim]")
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-x", "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", output_template,
                "--no-playlist",
                "--progress",
                url,
            ],
            capture_output=True, text=True, timeout=600,
        )
    except FileNotFoundError:
        console.print("[bold red]yt-dlp not found. Install with: pip install yt-dlp[/bold red]")
        raise SystemExit(1)

    if result.returncode != 0:
        console.print(f"[bold red]yt-dlp failed:[/bold red]\n{result.stderr}")
        raise SystemExit(1)

    if result.stdout:
        # Print last few lines of yt-dlp output
        lines = result.stdout.strip().split("\n")
        for line in lines[-5:]:
            console.print(f"[dim]{line}[/dim]")

    # Find the downloaded file
    for f in os.listdir(temp_dir):
        full = os.path.join(temp_dir, f)
        if f.endswith(".mp3") and os.path.isfile(full):
            return full, title

    console.print("[bold red]yt-dlp did not produce an MP3 file.[/bold red]")
    raise SystemExit(1)
