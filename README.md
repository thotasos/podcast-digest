# podcast-digest

Transcribe podcasts and extract key takeaways with timestamps using local AI. Everything runs on your machine — no cloud APIs.

## Prerequisites

```bash
brew install ffmpeg
```

## Installation

```bash
pip install -r requirements.txt
```

You also need [Ollama](https://ollama.ai) running locally:

```bash
ollama serve
ollama pull llama3  # or your preferred model (e.g., mistral, codellama)
```

## Usage

### From a local file

```bash
python3 main.py --file ~/Downloads/episode.mp3
```

### From an RSS feed

```bash
# Latest episode
python3 main.py --rss https://feeds.megaphone.fm/hubermanlab

# Specific episode (1=latest, 2=second latest, etc.)
python3 main.py --rss https://feeds.megaphone.fm/hubermanlab --episode 3
```

### From YouTube

```bash
python3 main.py --youtube https://youtube.com/watch?v=abc123
```

### Options

```bash
python3 main.py --file episode.mp3 --open       # Open output file when done
python3 main.py --file episode.mp3 --config my_config.yaml  # Custom config
```

## Configuration

Edit `config.yaml` to customize behavior:

| Setting | Default | Description |
|---------|---------|-------------|
| `whisper_model` | `small` | Whisper model size (see table below) |
| `whisper_device` | `cpu` | `cpu` or `cuda` |
| `whisper_language` | `en` | Language code, or `null` for auto-detect |
| `model` | `gpt-oss:20b` | Ollama model for summarization |
| `ollama_host` | `http://localhost:11434` | Ollama server address |
| `chunk_minutes` | `5` | Minutes per summarization chunk |
| `max_takeaways_per_chunk` | `3` | Max takeaways extracted per chunk |
| `top_takeaways_final` | `8` | Final best-of count |
| `output_dir` | `~/Documents/PodcastDigests` | Where PDF files are saved |
| `open_after` | `false` | Auto-open output file |
| `temp_dir` | `/tmp/podcast_digest` | Temp directory for downloads |

## Whisper Model Comparison

| Model | Size | Speed (1hr audio) | Accuracy | VRAM |
|-------|------|-------------------|----------|------|
| `tiny` | 39M | ~1 min | Low | ~1 GB |
| `base` | 74M | ~2 min | Fair | ~1 GB |
| `small` | 244M | ~4 min | Good | ~2 GB |
| `medium` | 769M | ~10 min | Very Good | ~5 GB |
| `large-v3` | 1550M | ~20 min | Excellent | ~10 GB |

*Speed estimates on Apple M1 Pro. CPU mode uses int8 quantization automatically.*

## Suggested Feeds

| Podcast | RSS Feed |
|---------|----------|
| Huberman Lab | `https://feeds.megaphone.fm/hubermanlab` |
| KQED Forum | `https://feeds.megaphone.fm/KQINC9557381633` |
| Techmeme Ride Home | `https://feeds.megaphone.fm/ridehome` |

You can also pass Apple Podcasts URLs directly — they'll be resolved to RSS automatically:

```bash
python3 main.py --rss https://feeds.megaphone.fm/hubermanlab
python3 main.py --rss https://feeds.megaphone.fm/KQINC9557381633
python3 main.py --rss https://feeds.megaphone.fm/ridehome
python3 main.py --rss https://podcasts.apple.com/us/podcast/kqeds-forum/id73329719
```

## Example Output

The tool generates a beautifully designed PDF with the following sections:

### Summary
A coherent paragraph capturing the episode's key insights, core message, and who would benefit most from listening.

### Chapters
Timestamped topic transitions throughout the episode for easy navigation:
- `00:00:00` – Intro & Podcast Overview
- `00:01:27` – Light Spectrum & Tissue Penetration
- ...

### Key Takeaways
Individual actionable insights with timestamps, highlighting:
- Specific recommendations and advice
- Surprising or counterintuitive facts
- Studies, tools, and resources mentioned
- Claims vs. opinions

The PDF uses a clean, modern design with accent colors for visual hierarchy and easy scanning.

## Supported Audio Formats

MP3, MP4, M4A, WAV, OGG, FLAC, WebM, Opus

## Troubleshooting

- **"Ollama not running"** — Start Ollama: `ollama serve`
- **"ffmpeg required"** — Install: `brew install ffmpeg`
- **yt-dlp errors** — Update: `pip install -U yt-dlp`
- **Slow transcription** — Try `whisper_model: tiny` or `base` for faster results
- **Out of memory** — Use a smaller Whisper model or set `whisper_device: cpu`
