"""
check_line_lengths.py
----------------------
Scans an SRT file and reports the longest subtitle lines by character count.
Useful for diagnosing TTS voice drift: very long lines are more likely to
cause an autoregressive TTS model to lose track of the cloned voice partway
through a single generation.

Usage:
    python check_line_lengths.py --srt "path\\to\\file.srt"
    python check_line_lengths.py --srt "path\\to\\file.srt" --threshold 150
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Report the longest lines in an SRT file.")
    parser.add_argument("--srt", required=True)
    parser.add_argument("--threshold", type=int, default=150,
                         help="Character count above which a line is flagged as 'long' (default: 150)")
    parser.add_argument("--top", type=int, default=15, help="How many longest lines to show")
    args = parser.parse_args()

    import srt

    with open(args.srt, "r", encoding="utf-8-sig") as f:
        subs = list(srt.parse(f.read()))

    if not subs:
        print("Total lines: 0")
        print("No subtitle entries found.")
        return

    lengths = [(len(s.content), s.index, s.content) for s in subs]
    lengths.sort(reverse=True)

    over_threshold = [x for x in lengths if x[0] > args.threshold]

    print(f"Total lines: {len(subs)}")
    print(f"Average length: {sum(l for l, _, _ in lengths) / len(lengths):.0f} characters")
    print(f"Lines over {args.threshold} chars: {len(over_threshold)}\n")

    print(f"Top {args.top} longest lines:")
    for length, idx, content in lengths[:args.top]:
        flag = "  <-- LONG" if length > args.threshold else ""
        preview = content.replace("\n", " ")[:80]
        print(f"  [{idx:>4}] {length:>4} chars: {preview!r}{flag}")


if __name__ == "__main__":
    main()
