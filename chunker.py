"""Groups transcript segments into ~N-minute chunks preserving sentence boundaries."""

from __future__ import annotations

from dataclasses import dataclass

from transcriber import Segment, format_timestamp


@dataclass
class Chunk:
    start_ts: str      # "00:05:00"
    end_ts: str        # "00:10:00"
    start_sec: float
    end_sec: float
    text: str          # Full concatenated text of the chunk


def create_chunks(segments: list[Segment], chunk_minutes: int = 5) -> list[Chunk]:
    """Group segments into chunks of approximately *chunk_minutes* minutes.

    Never splits mid-sentence — each segment is kept whole.
    """
    if not segments:
        return []

    chunk_seconds = chunk_minutes * 60
    chunks: list[Chunk] = []

    current_texts: list[str] = []
    chunk_start: float = segments[0].start
    chunk_end: float = segments[0].end

    for seg in segments:
        elapsed = seg.end - chunk_start

        # Start a new chunk if we've exceeded the target duration
        # and there's already content in the current chunk
        if elapsed > chunk_seconds and current_texts:
            chunks.append(Chunk(
                start_ts=format_timestamp(chunk_start),
                end_ts=format_timestamp(chunk_end),
                start_sec=chunk_start,
                end_sec=chunk_end,
                text=" ".join(current_texts),
            ))
            current_texts = []
            chunk_start = seg.start

        current_texts.append(seg.text)
        chunk_end = seg.end

    # Flush the last chunk
    if current_texts:
        chunks.append(Chunk(
            start_ts=format_timestamp(chunk_start),
            end_ts=format_timestamp(chunk_end),
            start_sec=chunk_start,
            end_sec=chunk_end,
            text=" ".join(current_texts),
        ))

    return chunks
