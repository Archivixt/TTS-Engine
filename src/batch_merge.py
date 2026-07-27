"""
batch_merge.py
---------------
Automatically pairs every generated .wav in your voiceovers folder with its
matching .mp4 in the source folder (matched by filename), and merges them
into finished dubbed videos using ffmpeg.

Usage:
    python batch_merge.py --source-dir "path/to/videos" --voiceovers-dir "path/to/videos/voiceovers"

Output goes into a 'dubbed' subfolder inside --source-dir, mirroring the
source subfolder structure. Original files are never touched.

If a merged output already exists, that file is skipped -- safe to re-run
if interrupted partway through.
"""

import argparse
import subprocess
from pathlib import Path


def find_pairs(source_dir: Path, voiceovers_dir: Path):
    """
    Match every .wav in voiceovers_dir to a .mp4 in source_dir by filename stem.
    Returns list of (mp4_path, wav_path, relative_path) tuples.
    Skips .clip_cache folders (intermediate per-line render cache).
    """
    # Build a lookup: stem -> mp4 path, for every mp4 in the source folder
    mp4_lookup = {}
    for mp4 in source_dir.rglob("*.mp4"):
        # Skip anything already inside the voiceovers or dubbed output folders
        parts = mp4.parts
        if "voiceovers" in parts or "dubbed" in parts:
            continue
        mp4_lookup[mp4.stem.strip()] = mp4

    pairs = []
    missing = []
    for wav in sorted(voiceovers_dir.rglob("*.wav")):
        # Skip per-line clip cache files
        if ".clip_cache" in wav.parts:
            continue
        stem = wav.stem.strip()
        if stem in mp4_lookup:
            rel = wav.relative_to(voiceovers_dir)
            pairs.append((mp4_lookup[stem], wav, rel))
        else:
            missing.append(wav)

    return pairs, missing


def merge(mp4_path: Path, wav_path: Path, out_path: Path):
    """Merge wav into mp4, replacing original audio, using the command confirmed to work."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(mp4_path),
        "-i", str(wav_path),
        "-map", "0:v:0",       # only the real video stream (skips embedded thumbnail)
        "-map", "1:a:0",       # the generated voiceover
        "-c:v", "copy",        # copy video without re-encoding (fast, no quality loss)
        "-c:a", "aac",         # encode audio as AAC
        "-disposition:a:0", "default",  # mark as default audio track
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[-1000:]
        raise RuntimeError(f"ffmpeg failed:\n{stderr}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch merge generated voiceover .wav files into matching .mp4 videos."
    )
    parser.add_argument("--source-dir", required=True,
                        help="Top-level folder containing the original .mp4 files")
    parser.add_argument("--voiceovers-dir", default=None,
                        help="Folder containing generated .wav files (default: <source-dir>/voiceovers)")
    parser.add_argument("--out-dir", default=None,
                        help="Where to save merged videos (default: <source-dir>/dubbed)")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    voiceovers_dir = Path(args.voiceovers_dir) if args.voiceovers_dir else source_dir / "voiceovers"
    out_dir = Path(args.out_dir) if args.out_dir else source_dir / "dubbed"

    if not source_dir.exists():
        raise SystemExit(f"Source folder not found: {source_dir}")
    if not voiceovers_dir.exists():
        raise SystemExit(f"Voiceovers folder not found: {voiceovers_dir}\n"
                         f"Run batch_process.py first to generate the audio files.")

    print(f"Scanning for matching pairs...")
    pairs, missing = find_pairs(source_dir, voiceovers_dir)

    if missing:
        print(f"\n[warn] {len(missing)} .wav file(s) had no matching .mp4 (skipping):")
        for w in missing:
            print(f"  - {w.name}")

    if not pairs:
        raise SystemExit("No matching pairs found. Make sure your .wav filenames match your .mp4 filenames.")

    print(f"\nFound {len(pairs)} matching pair(s). Output folder: {out_dir}\n")

    done = 0
    for idx, (mp4, wav, rel) in enumerate(pairs, start=1):
        out_path = out_dir / rel.with_suffix(".mp4")

        if out_path.exists():
            print(f"[{idx}/{len(pairs)}] Skipping (already merged): {rel.with_suffix('.mp4')}")
            done += 1
            continue

        print(f"[{idx}/{len(pairs)}] Merging: {rel.with_suffix('.mp4')}")
        try:
            merge(mp4, wav, out_path)
            done += 1
        except RuntimeError as e:
            print(f"  [ERROR] {e}")
            print(f"  Skipping this file and continuing...")

    print(f"\nDone. {done}/{len(pairs)} videos merged successfully.")
    print(f"Dubbed videos saved to: {out_dir}")


if __name__ == "__main__":
    main()
