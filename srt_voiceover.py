"""
srt_voiceover.py
-----------------
Fully automated: reads an SRT file, generates TTS for every line through your
ComfyUI Qwen3-TTS workflow, places each clip at its exact timestamp, and writes
one finished audio file synced to your video. No per-line manual work.

ONE-TIME SETUP:
1. Build your voice-cloning workflow in ComfyUI (reference audio -> Qwen3-TTS ->
   SaveAudio), test it on one line to confirm it sounds right.
2. Settings -> Enable Dev Mode Options -> menu -> "Save (API Format)" -> save
   as workflow_api.json. This is required because ComfyUI has no other way to
   run a workflow programmatically -- it needs this file as the template.

EVERY TIME AFTER THAT, it's one command:
    python srt_voiceover.py --srt input.srt --workflow workflow_api.json --out voiceover.wav

The script auto-detects which node holds the text and which node is the audio
output. If it can't (ambiguous or unusual node names), it will print the
candidates it found and tell you which line to edit -- that only happens once
per workflow file, not per run.
"""

from __future__ import annotations

import argparse
import json
import time
import subprocess
import tempfile
from pathlib import Path

# ======================= CONFIG (defaults, can be overridden by CLI flags) =======================

COMFY_URL = "http://127.0.0.1:8188"          # ComfyUI server address

# Leave these as None to auto-detect. Only set manually if auto-detect fails.
TEXT_NODE_ID = None
TEXT_INPUT_KEY = None
AUDIO_OUTPUT_NODE_ID = None

MAX_SPEEDUP = 1.15          # cap on how much we'll speed up a clip to fit its slot
CLIP_TEMP_DIR = "tts_clips" # where per-line renders get cached (safe to delete after)

# ===========================================================================


TEXT_KEY_NAMES = {"text", "prompt", "input_text", "text_input", "target_text", "string"}


def auto_detect_nodes(workflow):
    """Find the likely text-input node and the SaveAudio-like output node."""
    text_candidates = []
    audio_candidates = []
    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if "audio" in class_type.lower() and "save" in class_type.lower():
            audio_candidates.append(node_id)
        if isinstance(inputs, dict):
            for k, v in inputs.items():
                if k.lower() in TEXT_KEY_NAMES and isinstance(v, str):
                    text_candidates.append((node_id, k, class_type))
    return text_candidates, audio_candidates


def load_srt(path):
    import srt

    with open(path, "r", encoding="utf-8-sig") as f:
        return list(srt.parse(f.read()))


def queue_prompt(comfy_url, workflow, text, text_node_id, text_input_key):
    """Send one line of text into the workflow and queue it."""
    import requests

    wf = json.loads(json.dumps(workflow))  # deep copy
    wf[text_node_id]["inputs"][text_input_key] = text
    resp = requests.post(f"{comfy_url}/prompt", json={"prompt": wf})
    resp.raise_for_status()
    return resp.json()["prompt_id"]


def wait_for_result(comfy_url, prompt_id, audio_node_id, poll_interval=1.0, timeout=180):
    """Poll ComfyUI's history endpoint until the render finishes, return output info."""
    import requests

    elapsed = 0
    while elapsed < timeout:
        resp = requests.get(f"{comfy_url}/history/{prompt_id}")
        resp.raise_for_status()
        hist = resp.json()
        if prompt_id in hist:
            outputs = hist[prompt_id]["outputs"]
            if audio_node_id in outputs:
                return outputs[audio_node_id]
        time.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError(f"Render for prompt {prompt_id} did not finish in {timeout}s")


def download_audio(comfy_url, output_info, dest_path):
    """ComfyUI audio outputs list files under 'audio' (or 'files' on some custom nodes)."""
    import requests

    if "audio" in output_info:
        key = "audio"
    elif "files" in output_info:
        key = "files"
    else:
        raise RuntimeError(f"Audio output did not contain downloadable files: {output_info}")

    file_info = output_info[key][0]
    params = {
        "filename": file_info["filename"],
        "subfolder": file_info.get("subfolder", ""),
        "type": file_info.get("type", "output"),
    }
    r = requests.get(f"{comfy_url}/view", params=params)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(r.content)


def render_line(comfy_url, workflow, text, out_path, text_node_id, text_input_key, audio_node_id):
    prompt_id = queue_prompt(comfy_url, workflow, text, text_node_id, text_input_key)
    output_info = wait_for_result(comfy_url, prompt_id, audio_node_id)
    download_audio(comfy_url, output_info, out_path)


def fit_to_slot(clip: AudioSegment, slot_ms: int, max_speedup: float, warn_label: str):
    """If clip is longer than its slot, speed it up (capped). Otherwise return as-is."""
    clip_ms = len(clip)
    if clip_ms <= slot_ms:
        return clip

    needed_factor = clip_ms / slot_ms
    if needed_factor <= max_speedup:
        return speed_change(clip, needed_factor)

    # Can't fit even at max allowed speedup -> speed up as much as we allow and warn
    print(f"[warn] {warn_label}: line runs {clip_ms - slot_ms}ms over its slot "
          f"even after {max_speedup}x speedup. Consider shortening the translation.")
    return speed_change(clip, max_speedup)


def speed_change(clip: AudioSegment, factor: float) -> AudioSegment:
    """Speed up audio without pitch dropping into chipmunk territory as fast, via ffmpeg atempo."""
    from pydub import AudioSegment

    with tempfile.TemporaryDirectory(prefix="srt_voiceover_") as tmp_dir:
        tmp_in = Path(tmp_dir) / "input.wav"
        tmp_out = Path(tmp_dir) / "output.wav"
        clip.export(tmp_in, format="wav")
        # atempo supports 0.5-2.0 per filter instance; fine for our capped range
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp_in), "-filter:a", f"atempo={factor}", str(tmp_out)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return AudioSegment.from_wav(tmp_out)


def resolve_nodes(workflow, args):
    text_node_id = args.text_node or TEXT_NODE_ID
    text_input_key = args.text_key or TEXT_INPUT_KEY
    audio_node_id = args.audio_node or AUDIO_OUTPUT_NODE_ID

    if text_node_id and text_input_key and audio_node_id:
        return text_node_id, text_input_key, audio_node_id

    text_candidates, audio_candidates = auto_detect_nodes(workflow)

    if not text_node_id or not text_input_key:
        if len(text_candidates) == 1:
            text_node_id, text_input_key, _ = text_candidates[0]
            print(f"[auto-detect] Using text node {text_node_id!r} (field {text_input_key!r})")
        else:
            print("Could not confidently auto-detect the text-input node. Candidates found:")
            for nid, key, ctype in text_candidates:
                print(f"  node {nid}  field={key!r}  class_type={ctype!r}")
            raise SystemExit(
                "Re-run with --text-node <id> --text-key <field> to specify which one to use."
            )

    if not audio_node_id:
        if len(audio_candidates) == 1:
            audio_node_id = audio_candidates[0]
            print(f"[auto-detect] Using audio output node {audio_node_id!r}")
        else:
            print("Could not confidently auto-detect the audio output node. Candidates found:")
            for nid in audio_candidates:
                print(f"  node {nid}  class_type={workflow[nid].get('class_type')!r}")
            raise SystemExit("Re-run with --audio-node <id> to specify which one to use.")

    return text_node_id, text_input_key, audio_node_id


def process_srt_file(comfy_url, workflow, text_node_id, text_input_key, audio_node_id,
                      srt_path, out_path, max_speedup=MAX_SPEEDUP, clip_dir=None, log_prefix=""):
    """
    Renders every line of one SRT file through the workflow and writes a single
    timestamp-synced audio file to out_path. Returns the number of lines processed.
    Reused by both srt_voiceover.py (single file) and batch_process.py (batch mode).
    """
    from pydub import AudioSegment

    subs = load_srt(srt_path)
    if not subs:
        print(f"{log_prefix}[skip] {srt_path} has no subtitle entries")
        return 0

    clip_dir = Path(clip_dir) if clip_dir else Path(CLIP_TEMP_DIR)
    clip_dir.mkdir(parents=True, exist_ok=True)

    total_duration_ms = int(subs[-1].end.total_seconds() * 1000) + 1000
    master = AudioSegment.silent(duration=total_duration_ms)

    for i, sub in enumerate(subs):
        start_ms = int(sub.start.total_seconds() * 1000)
        end_ms = int(sub.end.total_seconds() * 1000)
        next_start_ms = (
            int(subs[i + 1].start.total_seconds() * 1000)
            if i + 1 < len(subs) else total_duration_ms
        )
        slot_ms = max(end_ms - start_ms, next_start_ms - start_ms)

        raw_path = clip_dir / f"line_{sub.index:04d}.wav"
        if not raw_path.exists():  # cache so reruns don't re-render everything
            print(f"{log_prefix}[{i+1}/{len(subs)}] Rendering: {sub.content[:50]!r}")
            render_line(
                comfy_url, workflow, sub.content, raw_path,
                text_node_id, text_input_key, audio_node_id,
            )

        clip = AudioSegment.from_file(raw_path)
        clip = fit_to_slot(clip, slot_ms, max_speedup, warn_label=f"{log_prefix}line {sub.index}")

        master = master.overlay(clip, position=start_ms)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    master.export(out_path, format="wav")
    print(f"{log_prefix}Done -> {out_path}")
    return len(subs)


def main():
    parser = argparse.ArgumentParser(description="Generate a synced voiceover from an SRT file via ComfyUI Qwen3-TTS.")
    parser.add_argument("--srt", required=True, help="Path to the translated .srt file")
    parser.add_argument("--workflow", required=True, help="Path to the exported workflow_api.json")
    parser.add_argument("--out", default="voiceover_synced.wav", help="Output audio file path")
    parser.add_argument("--comfy-url", default=COMFY_URL)
    parser.add_argument("--text-node", default=None, help="Override: node ID holding the text input")
    parser.add_argument("--text-key", default=None, help="Override: input field name for the text")
    parser.add_argument("--audio-node", default=None, help="Override: node ID of the SaveAudio output")
    parser.add_argument("--max-speedup", type=float, default=MAX_SPEEDUP)
    args = parser.parse_args()

    workflow = json.loads(Path(args.workflow).read_text(encoding="utf-8"))
    text_node_id, text_input_key, audio_node_id = resolve_nodes(workflow, args)

    process_srt_file(
        args.comfy_url, workflow, text_node_id, text_input_key, audio_node_id,
        args.srt, args.out, max_speedup=args.max_speedup,
    )


if __name__ == "__main__":
    main()
