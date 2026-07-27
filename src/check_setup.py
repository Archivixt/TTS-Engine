"""
check_setup.py
---------------
Run this before srt_voiceover.py to verify everything is in place.

Usage:
    python check_setup.py --workflow workflow_api.json --srt input.srt

Checks:
  1. Required Python packages installed
  2. ffmpeg available on PATH
  3. ComfyUI server reachable
  4. Your workflow_api.json is valid and nodes can be auto-detected
  5. Your SRT file parses correctly
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .srt_voiceover import TEXT_KEY_NAMES, auto_detect_nodes


def main():
    parser = argparse.ArgumentParser(description="Verify prerequisites for srt_voiceover.py")
    parser.add_argument("--workflow", default=None, help="Path to workflow_api.json")
    parser.add_argument("--srt", default=None, help="Path to your .srt file")
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--text-node", default=None, help="Manually specify text-input node ID")
    parser.add_argument("--text-key", default=None, help="Manually specify text-input field name")
    parser.add_argument("--audio-node", default=None, help="Manually specify audio output node ID")
    args = parser.parse_args()

    passed = []
    failed = []

    def ok(msg):
        print(f"  [OK]   {msg}")
        passed.append(msg)

    def fail(msg):
        print(f"  [FAIL] {msg}")
        failed.append(msg)

    # 1. Python packages
    print("\n1. Python packages")
    for pkg, import_name in [("requests", "requests"), ("srt", "srt"), ("pydub", "pydub")]:
        try:
            __import__(import_name)
            ok(f"'{pkg}' is installed")
        except ImportError:
            fail(f"'{pkg}' is NOT installed -> run: pip install {pkg}")

    # 2. ffmpeg
    print("\n2. ffmpeg")
    path = shutil.which("ffmpeg")
    if not path:
        fail("ffmpeg not found on PATH. Install it:\n"
             "         - Windows: winget install ffmpeg  (or download from ffmpeg.org and add to PATH)\n"
             "         - macOS:   brew install ffmpeg\n"
             "         - Linux:   sudo apt install ffmpeg")
    else:
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=10)
            stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            version_line = stdout.splitlines()[0] if stdout else "unknown version"
            ok(f"ffmpeg found ({version_line})")
        except Exception as e:
            fail(f"ffmpeg found at {path} but failed to run: {e}")

    # 3. ComfyUI server
    print("\n3. ComfyUI server")
    try:
        import requests
        r = requests.get(f"{args.comfy_url}/system_stats", timeout=5)
        if r.status_code == 200:
            ok(f"ComfyUI is running and reachable at {args.comfy_url}")
        else:
            fail(f"ComfyUI responded with status {r.status_code} at {args.comfy_url}")
    except ImportError:
        fail("Can't check ComfyUI -- 'requests' package missing (see step 1)")
    except Exception as e:
        fail(f"Could not reach ComfyUI at {args.comfy_url} ({e}). "
             f"Make sure ComfyUI is running before you run srt_voiceover.py.")

    # 4. workflow_api.json
    print("\n4. workflow_api.json")
    if not args.workflow:
        fail("No --workflow path given, skipping this check")
    else:
        p = Path(args.workflow)
        if not p.exists():
            fail(f"File not found: {args.workflow}")
        else:
            try:
                workflow = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                fail(f"File is not valid JSON: {e}")
            else:
                # sanity check: API-format vs UI-format
                if "nodes" in workflow and "links" in workflow:
                    fail("This looks like a UI-format export, not API-format. "
                         "In ComfyUI: Settings -> Enable 'Dev Mode Options', then use "
                         "'Save (API Format)' instead of the normal Save/Export.")
                else:
                    ok(f"Valid JSON with {len(workflow)} nodes, and looks like API format")

                    # auto-detect using the same logic as the main script
                    text_candidates, audio_candidates = auto_detect_nodes(workflow)

                    if args.text_node and args.text_key:
                        node = workflow.get(args.text_node)
                        if not node:
                            fail(f"--text-node {args.text_node} does not exist in this workflow")
                        elif args.text_key not in node.get("inputs", {}):
                            fail(f"Node {args.text_node} has no input field {args.text_key!r}. "
                                 f"Available fields: {list(node.get('inputs', {}).keys())}")
                        else:
                            ok(f"Manual text node confirmed: node {args.text_node} "
                               f"(class_type={node.get('class_type')!r}, field={args.text_key!r})")
                    elif len(text_candidates) == 1:
                        nid, key, ctype = text_candidates[0]
                        ok(f"Text-input node auto-detected: node {nid} (class_type={ctype!r}, field={key!r})")
                    elif len(text_candidates) == 0:
                        fail("Could not find any text-input node automatically. "
                             "Pass --text-node <id> --text-key <field> to specify it manually.")
                    else:
                        fail(f"Found {len(text_candidates)} possible text-input nodes, ambiguous: "
                             f"{[(n, k) for n, k, _ in text_candidates]}. "
                             "Pass --text-node and --text-key manually.")

                    if args.audio_node:
                        node = workflow.get(args.audio_node)
                        if not node:
                            fail(f"--audio-node {args.audio_node} does not exist in this workflow")
                        else:
                            ok(f"Manual audio node confirmed: node {args.audio_node} "
                               f"(class_type={node.get('class_type')!r})")
                    elif len(audio_candidates) == 1:
                        nid, ctype = audio_candidates[0]
                        ok(f"Audio output node auto-detected: node {nid} (class_type={ctype!r})")
                    elif len(audio_candidates) == 0:
                        fail("Could not find a SaveAudio-like output node automatically. "
                             "Pass --audio-node manually.")
                    else:
                        fail(f"Found {len(audio_candidates)} possible audio output nodes, ambiguous: "
                             f"{audio_candidates}. Pass --audio-node manually.")

    # 5. SRT file
    print("\n5. SRT file")
    if not args.srt:
        fail("No --srt path given, skipping this check")
    else:
        p = Path(args.srt)
        if not p.exists():
            fail(f"File not found: {args.srt}")
        else:
            try:
                import srt
                with open(p, "r", encoding="utf-8-sig") as f:
                    subs = list(srt.parse(f.read()))
                if not subs:
                    fail("File parsed but contains 0 subtitle entries")
                else:
                    ok(f"Parsed successfully: {len(subs)} subtitle lines, "
                       f"last one ends at {subs[-1].end}")
                    empties = [s.index for s in subs if not s.content.strip()]
                    if empties:
                        fail(f"{len(empties)} subtitle entries have empty text (indices: {empties[:10]}...)")
            except ImportError:
                fail("Can't check SRT -- 'srt' package missing (see step 1)")
            except Exception as e:
                fail(f"File exists but failed to parse: {e}")

    # Summary
    print("\n" + "=" * 50)
    print(f"{len(passed)} passed, {len(failed)} failed")
    if failed:
        print("\nFix the [FAIL] items above, then re-run this check.")
        sys.exit(1)
    else:
        print("\nEverything looks good. You're ready to run srt_voiceover.py.")


if __name__ == "__main__":
    main()
