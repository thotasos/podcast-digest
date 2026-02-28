"""Builds the final Markdown output file."""

from __future__ import annotations

import os
from datetime import datetime

from transcriber import Segment, format_timestamp


def build_markdown(
    title: str,
    duration_seconds: float,
    whisper_model: str,
    ollama_model: str,
    summary: str,
    chapters: list[str],
    segments: list[Segment],
) -> str:
    """Build a complete Markdown digest document."""
    duration_str = format_timestamp(duration_seconds)
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines: list[str] = []

    # Header
    lines.append(f"# {title}")
    lines.append(
        f"_{duration_str} · Transcribed with Whisper ({whisper_model}) "
        f"· Summarized with {ollama_model}_"
    )
    lines.append(f"_Generated {date_str}_")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    if summary:
        lines.append(summary)
        lines.append("")
    else:
        lines.append("_No summary generated._")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Chapters
    lines.append("## Chapters")
    lines.append("")
    if chapters:
        for ch in chapters:
            # Format: HH:MM:SS – Title  →  - `HH:MM:SS` – Title
            if "–" in ch:
                ts_part, title_part = ch.split("–", 1)
                lines.append(f"- `{ts_part.strip()}` – {title_part.strip()}")
            elif "-" in ch and ":" in ch[:8]:
                ts_part, title_part = ch.split("-", 1)
                lines.append(f"- `{ts_part.strip()}` – {title_part.strip()}")
            else:
                lines.append(f"- {ch}")
    else:
        lines.append("_No chapters detected._")
    lines.append("")

    lines.append("---")
    lines.append("")

    # Full Transcript
    lines.append("## Full Transcript")
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>Click to expand full transcript</summary>")
    lines.append("")
    for seg in segments:
        ts = format_timestamp(seg.start)
        lines.append(f"[{ts}] {seg.text}")
        lines.append("")
    lines.append("</details>")
    lines.append("")

    lines.append("---")
    lines.append("*podcast-digest*")
    lines.append("")

    return "\n".join(lines)


def save_markdown(content: str, title: str, output_dir: str) -> str:
    """Save Markdown content to a file and return the full path."""
    expanded_dir = os.path.expanduser(output_dir)
    os.makedirs(expanded_dir, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)
    safe_title = safe_title.strip().replace(" ", "_")[:80]
    filename = f"{safe_title}_{date_str}.md"
    filepath = os.path.join(expanded_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath
