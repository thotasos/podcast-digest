"""Ollama-based summarization — per-chunk takeaways, final best-of, chapter detection."""

from __future__ import annotations

from dataclasses import dataclass

import ollama as ollama_client
from rich.console import Console

console = Console()


@dataclass
class ChunkSummary:
    start_ts: str
    end_ts: str
    takeaways: list[str]


def _call_ollama(prompt: str, model: str, host: str) -> str:
    """Make a single Ollama generate call and return the response text."""
    client = ollama_client.Client(host=host)
    response = client.generate(model=model, prompt=prompt)
    return response["response"].strip()


def _check_ollama(host: str) -> None:
    """Verify Ollama is reachable."""
    try:
        client = ollama_client.Client(host=host)
        client.list()
    except Exception:
        console.print(
            "[bold red]Ollama not running. Start with: ollama serve[/bold red]\n"
            f"[dim]Tried to connect to: {host}[/dim]"
        )
        raise SystemExit(1)


def summarize_chunk(
    text: str,
    start_ts: str,
    end_ts: str,
    max_takeaways: int,
    model: str,
    host: str,
) -> ChunkSummary:
    """Extract key takeaways from a single transcript chunk."""
    prompt = (
        "You are extracting key insights from a podcast transcript segment.\n"
        f"Segment starts at {start_ts}.\n\n"
        f"Extract up to {max_takeaways} key takeaways from this segment.\n"
        "Each takeaway must be a single, specific, actionable or insightful sentence.\n"
        "Format each as: [HH:MM:SS] The insight here.\n"
        "Use timestamps within this segment that best represent when the insight was mentioned.\n"
        "Only output the takeaways, nothing else.\n\n"
        f"Transcript:\n{text}"
    )
    response = _call_ollama(prompt, model, host)

    # Parse takeaways — each line starting with [HH:MM:SS]
    takeaways: list[str] = []
    for line in response.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Remove leading numbering like "1. " or "- "
        cleaned = line.lstrip("0123456789.-) ").strip()
        if cleaned.startswith("["):
            takeaways.append(cleaned)
        elif line.startswith("["):
            takeaways.append(line)

    return ChunkSummary(start_ts=start_ts, end_ts=end_ts, takeaways=takeaways[:max_takeaways])


def final_summary(all_takeaways: list[str], top_n: int, model: str, host: str) -> str:
    """Synthesize all chunk takeaways into one coherent summary paragraph."""
    combined = "\n".join(all_takeaways)
    prompt = (
        "Below are key takeaways extracted from a podcast episode, with timestamps.\n\n"
        f"Write a single coherent summary paragraph ({top_n - 2}–{top_n + 2} sentences) "
        "that captures the most valuable insights from the episode.\n"
        "Weave the key points together naturally — do not use bullet points or numbered lists.\n"
        "Do NOT include timestamps in the summary.\n"
        "Write in a clear, informative tone as if briefing someone who hasn't listened.\n"
        "Only output the summary paragraph, nothing else.\n\n"
        f"Takeaways:\n{combined}"
    )
    return _call_ollama(prompt, model, host)


def _normalize_timestamp(ts: str) -> str:
    """Ensure timestamp is in HH:MM:SS format (pad missing parts)."""
    ts = ts.strip().lstrip(":")
    parts = ts.split(":")
    if len(parts) == 2:
        parts = ["00"] + parts
    return ":".join(p.zfill(2) for p in parts)


def detect_chapters(transcript_text: str, model: str, host: str) -> list[str]:
    """Identify chapter/topic transitions from the transcript."""
    # Use first 8000 chars for chapter detection
    sample = transcript_text[:8000]
    prompt = (
        "Based on this podcast transcript, identify 4-8 chapter/topic transitions.\n"
        "Format each as: HH:MM:SS – Chapter title (short, 3-6 words)\n"
        "Return only the chapter list, nothing else.\n\n"
        f"Transcript (partial):\n{sample}"
    )
    response = _call_ollama(prompt, model, host)

    chapters: list[str] = []
    for line in response.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Strip leading numbering/bullets
        cleaned = line.lstrip("0123456789.-) ").strip()
        # Accept lines that look like timestamps
        if cleaned and len(cleaned) > 8 and (":" in cleaned[:8]):
            # Normalize the timestamp portion
            for sep in ["–", "-"]:
                if sep in cleaned:
                    ts_part, title_part = cleaned.split(sep, 1)
                    ts_part = _normalize_timestamp(ts_part)
                    cleaned = f"{ts_part} – {title_part.strip()}"
                    break
            chapters.append(cleaned)

    return chapters


def run_summarization(
    chunks: list[dict],
    transcript_text: str,
    model: str,
    host: str,
    max_takeaways_per_chunk: int,
    top_takeaways_final: int,
    progress_callback: callable | None = None,
) -> tuple[str, list[str]]:
    """Full summarization pipeline. Returns (summary_paragraph, chapters).

    chunks: list of dicts with keys start_ts, end_ts, text
    progress_callback: called with (current_chunk_index, total_chunks) for progress display
    """
    _check_ollama(host)

    all_takeaways: list[str] = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(i, total)
        try:
            summary = summarize_chunk(
                text=chunk["text"],
                start_ts=chunk["start_ts"],
                end_ts=chunk["end_ts"],
                max_takeaways=max_takeaways_per_chunk,
                model=model,
                host=host,
            )
            all_takeaways.extend(summary.takeaways)
        except Exception as exc:
            console.print(f"[yellow]Warning: Chunk {i + 1}/{total} summarization failed: {exc}[/yellow]")
            continue

    if not all_takeaways:
        console.print("[bold red]No takeaways extracted from any chunk.[/bold red]")
        return "", []

    # Final summary pass
    summary_text = final_summary(all_takeaways, top_takeaways_final, model, host)

    # Chapter detection
    try:
        chapters = detect_chapters(transcript_text, model, host)
    except Exception as exc:
        console.print(f"[yellow]Warning: Chapter detection failed: {exc}[/yellow]")
        chapters = []

    return summary_text, chapters
