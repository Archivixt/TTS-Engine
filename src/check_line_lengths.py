"""
check_line_lengths.py
----------------------
Scans an SRT file and reports the longest subtitle lines by character count.
Useful for diagnosing TTS voice drift: very long lines are more likely to
cause an autoregressive TTS model to lose track of the cloned voice partway
through a single generation.

Usage:
    python check_line_lengths.py --srt "./subtitles/Chapter-01.srt"
    python check_line_lengths.py --srt "./subtitles/Chapter-01.srt" --threshold 150
"""

import argparse
import logging

import srt

log = logging.getLogger(__name__)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    parser = argparse.ArgumentParser(description="Report the longest lines in an SRT file.")
    parser.add_argument("--srt", required=True)
    parser.add_argument("--threshold", type=int, default=150,
                         help="Character count above which a line is flagged as 'long' (default: 150)")
    parser.add_argument("--top", type=int, default=15, help="How many longest lines to show")
    args = parser.parse_args()

    with open(args.srt, "r", encoding="utf-8-sig") as f:
        subs = list(srt.parse(f.read()))

    if not subs:
        log.info("Total lines: 0")
        log.info("No subtitle entries found.")
        return

    lengths = [(len(s.content), s.index, s.content) for s in subs]
    lengths.sort(reverse=True)

    over_threshold = [x for x in lengths if x[0] > args.threshold]

    log.info("Total lines: %d", len(subs))
    log.info("Average length: %.0f characters", sum(l for l, _, _ in lengths) / len(lengths))
    log.info("Lines over %d chars: %d\n", args.threshold, len(over_threshold))

    log.info("Top %d longest lines:", args.top)
    for length, idx, content in lengths[:args.top]:
        flag = "  <-- LONG" if length > args.threshold else ""
        preview = content.replace("\n", " ")[:80]
        log.info("  [%4d] %4d chars: %r%s", idx, length, preview, flag)


if __name__ == "__main__":
    main()
