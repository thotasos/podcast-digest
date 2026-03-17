#!/usr/bin/env python3
"""podcast-digest — Transcribe podcasts and extract key takeaways with local AI."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.status import Status

console = Console()


def load_config(config_path: str) -> dict:
    """Load and return config from YAML, with defaults."""
    defaults = {
        "whisper_model": "small",
        "whisper_device": "cpu",
        "whisper_language": "en",
        "model": "llama3",
        "ollama_host": "http://localhost:11434",
        "chunk_minutes": 5,
        "max_takeaways_per_chunk": 3,
        "top_takeaways_final": 8,
        "output_dir": "~/Documents/PodcastDigests",
        "open_after": False,
        "temp_dir": "/tmp/podcast_digest",
    }

    expanded = os.path.expanduser(config_path)
    if os.path.isfile(expanded):
        with open(expanded) as f:
            user_config = yaml.safe_load(f) or {}
        defaults.update(user_config)
    else:
        console.print(f"[dim]Config not found at {config_path}, using defaults.[/dim]")

    return defaults


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="podcast-digest",
        description="Transcribe podcasts and extract key takeaways with local AI.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="Path to a local audio file")
    source.add_argument("--rss", help="RSS feed URL")
    source.add_argument("--youtube", help="YouTube video URL")

    parser.add_argument("--episode", type=int, default=1, help="Episode number for RSS (1=latest, default: 1)")
    parser.add_argument("--open", action="store_true", help="Open output file when done")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML (default: config.yaml)")

    return parser.parse_args()


def check_dependencies() -> None:
    """Check that required system dependencies are available."""
    if not shutil.which("ffmpeg"):
        console.print("[bold red]ffmpeg required. Install with: brew install ffmpeg[/bold red]")
        sys.exit(1)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    # Banner
    console.print(Panel.fit(
        "[bold magenta]Podcast Digest[/bold magenta]\n"
        "[dim]Transcribe & extract insights with local AI[/dim]",
        border_style="magenta",
    ))

    check_dependencies()

    # ── Step 1: Fetch audio ───────────────────────────────────────────
    from fetcher import fetch_file, fetch_rss, fetch_youtube

    if args.file:
        audio_path, title = fetch_file(args.file)
    elif args.rss:
        audio_path, title = fetch_rss(args.rss, args.episode, config["temp_dir"])
    elif args.youtube:
        audio_path, title = fetch_youtube(args.youtube, config["temp_dir"])
    else:
        console.print("[bold red]No source provided.[/bold red]")
        sys.exit(1)

    console.print()

    # ── Step 2: Transcribe ────────────────────────────────────────────
    from transcriber import Segment, transcribe

    t_start = time.time()
    segments, duration = transcribe(
        audio_path=audio_path,
        model_name=config["whisper_model"],
        device=config["whisper_device"],
        language=config["whisper_language"] if config["whisper_language"] else None,
    )
    t_transcribe = time.time() - t_start
    console.print(f"[green]Transcription complete:[/green] {len(segments)} segments")
    console.print()

    # ── Step 3: Chunk ─────────────────────────────────────────────────
    from chunker import create_chunks

    chunks = create_chunks(segments, config["chunk_minutes"])
    console.print(f"[bold]Chunks:[/bold] {len(chunks)} (~{config['chunk_minutes']} min each)")
    console.print()

    # ── Step 4: Summarize ─────────────────────────────────────────────
    from summarizer import run_summarization

    chunk_dicts = [
        {"start_ts": c.start_ts, "end_ts": c.end_ts, "text": c.text}
        for c in chunks
    ]

    # Build full transcript text for chapter detection
    from transcriber import format_timestamp
    transcript_text = "\n".join(
        f"[{format_timestamp(s.start)}] {s.text}" for s in segments
    )

    status_holder: dict = {}

    def progress_cb(current: int, total: int) -> None:
        if "status" not in status_holder:
            status_holder["status"] = Status(
                f"[bold blue]Summarizing chunk 1/{total}...",
                console=console, spinner="dots",
            )
            status_holder["status"].start()
        status_holder["status"].update(f"[bold blue]Summarizing chunk {current + 1}/{total}...")

    t_sum_start = time.time()
    summary, chapters, takeaways = run_summarization(
        chunks=chunk_dicts,
        transcript_text=transcript_text,
        model=config["model"],
        host=config["ollama_host"],
        max_takeaways_per_chunk=config["max_takeaways_per_chunk"],
        top_takeaways_final=config["top_takeaways_final"],
        progress_callback=progress_cb,
    )
    if "status" in status_holder:
        status_holder["status"].stop()
    t_summarize = time.time() - t_sum_start

    console.print(f"[green]Summarization complete[/green]")
    console.print()

    # ── Step 5: Format and save ───────────────────────────────────────
    from formatter import build_pdf

    output_path = build_pdf(
        title=title,
        duration_seconds=duration,
        whisper_model=config["whisper_model"],
        ollama_model=config["model"],
        summary=summary,
        chapters=chapters,
        takeaways=takeaways,
        segments=segments,
        output_dir=config["output_dir"],
    )

    # ── Step 6: Summary ───────────────────────────────────────────────
    def _fmt_elapsed(secs: float) -> str:
        m = int(secs // 60)
        s = int(secs % 60)
        return f"{m}m {s:02d}s"

    console.print()
    console.print(Panel.fit(
        f"[bold green]Done![/bold green]\n"
        f"[bold]Output:[/bold] {output_path}\n"
        f"[bold]Transcription:[/bold] {_fmt_elapsed(t_transcribe)}\n"
        f"[bold]Summarization:[/bold] {_fmt_elapsed(t_summarize)}",
        border_style="green",
    ))

    # ── Step 7: Open if requested ─────────────────────────────────────
    should_open = args.open or config.get("open_after", False)
    if should_open:
        subprocess.run(["open", output_path], check=False)

    # ── Cleanup temp files ────────────────────────────────────────────
    if args.rss or args.youtube:
        try:
            # Only clean up the specific downloaded file, not the whole temp dir
            if os.path.isfile(audio_path) and audio_path.startswith(config["temp_dir"]):
                os.remove(audio_path)
                console.print("[dim]Cleaned up temp audio file.[/dim]")
        except OSError:
            pass


if __name__ == "__main__":
    main()
