# SRT Voiceover Pipeline

Batch-generate synced voiceover audio from `.srt` subtitle files using a local
ComfyUI/Qwen3-TTS workflow.

The scripts read subtitle timing from SRT files, generate speech for each line
through ComfyUI's API, place every generated clip at its original timestamp, and
export finished `.wav` voiceover files. A separate merge script can pair those
voiceovers with matching `.mp4` files by filename and write final videos with
the generated audio.

## What It Is For

This is useful when you already have subtitle files and want to create timed
voiceover audio automatically instead of rendering every subtitle line by hand.
It is designed for local workflows where ComfyUI is already running a
Qwen3-TTS voice-cloning graph.

The pipeline is resumable:

- Generated per-line clips are cached.
- Finished `.wav` files are skipped on rerun.
- Merged `.mp4` outputs are skipped on rerun.

## Requirements

- Python 3.10+
- ffmpeg available on your system `PATH`
- ComfyUI running locally
- A working Qwen3-TTS workflow exported from ComfyUI in API Format

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## ComfyUI Workflow

Create and test your voice-cloning workflow inside ComfyUI first. Then export it
for API use:

1. Open ComfyUI settings.
2. Enable Dev Mode Options.
3. Use Save (API Format).
4. Save the file as `workflow_api.json`.

The scripts try to auto-detect the text input node and the audio output node.
For Qwen3-TTS workflows, the text field is commonly named `target_text`.

## Check Setup

Run this before a long batch:

```bash
python -m src.check_setup --workflow workflow_api.json --srt "./subtitles/Chapter-01.srt"
```

If auto-detection fails, pass the node details manually:

```bash
python -m src.check_setup --workflow workflow_api.json --srt "./subtitles/Chapter-01.srt" --text-node 39 --text-key target_text --audio-node 8
```

## Generate One Voiceover

```bash
python -m src.srt_voiceover --srt "./subtitles/Chapter-01.srt" --workflow workflow_api.json --out "./voiceovers/Chapter-01.wav"
```

With manual node settings:

```bash
python -m src.srt_voiceover --srt "./subtitles/Chapter-01.srt" --workflow workflow_api.json --out "./voiceovers/Chapter-01.wav" --text-node 39 --text-key target_text --audio-node 8
```

## Generate Voiceovers In Batch

This scans a folder recursively for `.srt` files and writes matching `.wav`
outputs under `voiceovers/`.

```bash
python -m src.batch_process --source-dir "D:/Videos/Course" --workflow workflow_api.json
```

Optional output folder:

```bash
python -m src.batch_process --source-dir "D:/Videos/Course" --workflow workflow_api.json --out-dir "D:/Videos/Course/voiceovers"
```

## Merge Voiceovers With Videos

This pairs `.wav` files with `.mp4` files by matching filename stem.

```bash
python -m src.batch_merge --source-dir "D:/Videos/Course"
```

Optional folders:

```bash
python -m src.batch_merge --source-dir "D:/Videos/Course" --voiceovers-dir "D:/Videos/Course/voiceovers" --out-dir "D:/Videos/Course/dubbed"
```

## Check Long Subtitle Lines

Long subtitle lines can be harder for TTS models to keep consistent. This helper
shows the longest lines in an SRT:

```bash
python -m src.check_line_lengths --srt "./subtitles/Chapter-01.srt"
```

Use a custom threshold:

```bash
python -m src.check_line_lengths --srt "./subtitles/Chapter-01.srt" --threshold 150
```

## Files

- `src/srt_voiceover.py` - process one SRT into one synced WAV
- `src/batch_process.py` - process every SRT under a source folder
- `src/batch_merge.py` - merge generated WAV files into matching MP4 files
- `src/check_setup.py` - verify dependencies, ComfyUI, workflow, and SRT parsing
- `src/check_line_lengths.py` - report long subtitle lines
