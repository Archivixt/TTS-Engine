"""
batch_process.py
-----------------
Finds every .srt file inside a source folder, including nested subfolders,
and generates one synced voiceover .wav for each -- automatically, in one run.

Usage:
    python batch_process.py --source-dir "D:/Videos/Course" --workflow workflow_api.json

What it does:
- Recursively scans --source-dir for every *.srt file, wherever it sits.
- For each one, renders every line through your ComfyUI workflow and builds
  a timestamp-synced .wav, same as srt_voiceover.py does for a single file.
- Writes each output to --out-dir, mirroring the source subfolder structure
  and naming the output after its source SRT
  (e.g. folder/input.srt -> voiceovers/folder/input.wav).
- Skips a file if its output .wav already exists, so if it gets interrupted
  partway through a run, re-running picks up where it left off.

The workflow/node auto-detection happens ONCE at the start (not per file),
so this is efficient even for large batches.
"""

import argparse
import json
import logging
from pathlib import Path

from .srt_voiceover import (
    COMFY_URL, MAX_SPEEDUP, resolve_nodes, process_srt_file,
)

log = logging.getLogger(__name__)


def find_srt_files(source_dir: Path):
    return sorted(source_dir.rglob("*.srt"))


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Generate synced voiceovers for every SRT in a source folder."
    )
    parser.add_argument("--source-dir", required=True, help="Top-level folder to scan for .srt files")
    parser.add_argument("--workflow", required=True, help="Path to the exported workflow_api.json")
    parser.add_argument("--out-dir", default=None,
                         help="Where to write output .wav files (mirrors source subfolders). "
                              "Defaults to <source-dir>/voiceovers")
    parser.add_argument("--comfy-url", default=COMFY_URL)
    parser.add_argument("--text-node", default=None)
    parser.add_argument("--text-key", default=None)
    parser.add_argument("--audio-node", default=None)
    parser.add_argument("--max-speedup", type=float, default=MAX_SPEEDUP)
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        raise SystemExit(f"Source folder not found: {source_dir}")

    out_dir = Path(args.out_dir) if args.out_dir else source_dir / "voiceovers"

    srt_files = find_srt_files(source_dir)
    if not srt_files:
        raise SystemExit(f"No .srt files found under: {source_dir}")

    log.info("Found %d SRT file(s) under %s:", len(srt_files), source_dir)
    for f in srt_files:
        log.info("  - %s", f.relative_to(source_dir))

    workflow = json.loads(Path(args.workflow).read_text(encoding="utf-8"))
    text_node_id, text_input_key, audio_node_id = resolve_nodes(workflow, args)

    log.info("\nOutput folder: %s\n", out_dir)

    total_lines = 0
    failed = []
    for idx, srt_path in enumerate(srt_files, start=1):
        rel_path = srt_path.relative_to(source_dir)
        out_path = out_dir / rel_path.with_suffix(".wav")
        clip_cache_dir = out_dir / ".clip_cache" / rel_path.with_suffix("")

        if out_path.exists():
            log.info("[%d/%d] Skipping (already done): %s", idx, len(srt_files), rel_path)
            continue

        log.info("[%d/%d] Processing: %s", idx, len(srt_files), rel_path)
        try:
            n = process_srt_file(
                args.comfy_url, workflow, text_node_id, text_input_key, audio_node_id,
                srt_path, out_path,
                max_speedup=args.max_speedup,
                clip_dir=clip_cache_dir,
                log_prefix="    ",
            )
            total_lines += n
        except Exception as e:
            log.error("  [ERROR] %s failed: %s", rel_path, e)
            failed.append((rel_path, e))

    log.info("\nAll done. Processed %d file(s), %d total lines.", len(srt_files) - len(failed), total_lines)
    if failed:
        log.warning("%d file(s) failed:", len(failed))
        for path, err in failed:
            log.warning("  - %s: %s", path, err)
    log.info("Output voiceovers are in: %s", out_dir)


if __name__ == "__main__":
    main()
