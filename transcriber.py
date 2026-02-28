"""Whisper transcription module — returns timestamped segments."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console()

SUPPORTED_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".ogg", ".flac", ".webm", ".opus"}


@dataclass
class Segment:
    start: float
    end: float
    text: str


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _get_audio_duration(path: str) -> float | None:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return None


def _convert_to_wav(input_path: str) -> str:
    """Convert audio to 16kHz mono WAV for Whisper. Returns path to WAV file."""
    ext = Path(input_path).suffix.lower()
    if ext == ".wav":
        return input_path

    wav_path = os.path.join(
        tempfile.gettempdir(),
        "podcast_digest",
        Path(input_path).stem + "_converted.wav",
    )
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)

    console.print(f"[dim]Converting {ext} → WAV for Whisper...[/dim]")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", input_path,
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                wav_path,
            ],
            capture_output=True, text=True, timeout=600, check=True,
        )
    except FileNotFoundError:
        console.print("[bold red]ffmpeg required. Install with: brew install ffmpeg[/bold red]")
        raise SystemExit(1)
    except subprocess.CalledProcessError as exc:
        console.print(f"[bold red]ffmpeg conversion failed:[/bold red]\n{exc.stderr}")
        raise SystemExit(1)

    return wav_path


def transcribe(audio_path: str, model_name: str, device: str, language: str | None) -> tuple[list[Segment], float]:
    """Transcribe audio and return (segments, duration_seconds).

    Shows a rich progress bar during transcription.
    """
    from faster_whisper import WhisperModel  # lazy import for startup speed

    ext = Path(audio_path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        console.print(f"[bold red]Unsupported audio format: {ext}[/bold red]")
        console.print(f"[dim]Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}[/dim]")
        raise SystemExit(1)

    wav_path = _convert_to_wav(audio_path)
    duration = _get_audio_duration(wav_path)

    console.print(f"[bold]Whisper model:[/bold] {model_name}  [bold]device:[/bold] {device}")
    if duration:
        dur_str = format_timestamp(duration)
        console.print(f"[bold]Audio duration:[/bold] {dur_str}")

    console.print("[dim]Loading Whisper model (first run downloads weights)...[/dim]")
    model = WhisperModel(model_name, device=device, compute_type="int8" if device == "cpu" else "float16")

    lang_kwargs: dict = {}
    if language:
        lang_kwargs["language"] = language

    segments_iter, info = model.transcribe(wav_path, beam_size=5, **lang_kwargs)
    total_duration = info.duration if info.duration else (duration or 0.0)

    segments: list[Segment] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Transcribing"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Transcribing", total=total_duration if total_duration > 0 else None)
        for seg in segments_iter:
            segments.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip()))
            if total_duration > 0:
                progress.update(task, completed=min(seg.end, total_duration))

    # Clean up converted WAV if we created one
    if wav_path != audio_path and os.path.exists(wav_path):
        os.remove(wav_path)

    actual_duration = segments[-1].end if segments else total_duration
    return segments, actual_duration
