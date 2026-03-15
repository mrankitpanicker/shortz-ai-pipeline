#!/usr/bin/env python3
# Shortz.py — ALL-IN-ONE Daily Krishna Motivation → XTTS → ASS Subtitles → Final MP4 Shorts
# REVISED FULL VERSION — OPTIMIZED FOR EFFICIENCY AND ROBUSTNESS (FFMPEG & PATH FIXES)

import os
import logging
import warnings
import re
import subprocess
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Union


# ------------------------------------------------------------
# BASE PATH
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
VIDEO_W = 1080
VIDEO_H = 1920

FONT_SIZE = 100
HIGHLIGHT_COLOR = "&H0000FFFF"
BASE_COLOR = "&H00FFFFFF"
BORDER_SIZE = 10
SHADOW_SIZE = 10

INTER_CHUNK_HOLD_SECONDS = 2.5
INTER_CHUNK_DELAY_SECONDS = 0.08
MAX_CHUNK_CHARS = 250 

XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"

BIN_DIR = BASE_DIR / "bin"

FFMPEG_BIN = str(BIN_DIR / "ffmpeg.exe")
FFPROBE_BIN = str(BIN_DIR / "ffprobe.exe")

# Suppress environment warnings
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"
logging.getLogger().setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning)

# --- SUPPRESS TRANSFORMERS LOGGER WARNINGS ---
logging.getLogger("transformers").setLevel(logging.ERROR)
# ------------------------------------------

print("\n--- Running ShortZ.py ---\n")



# ------------------------------------------------------------
# IMPORT XTTS MODEL
# ------------------------------------------------------------
TTS: Optional[type] = None

try:
    import torch
    from TTS.api import TTS
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
    from TTS.config.shared_configs import BaseDatasetConfig

    torch.serialization.add_safe_globals([
        XttsConfig,
        XttsAudioConfig,
        XttsArgs,
        BaseDatasetConfig
    ])

except Exception as e:
    print("⚠️ XTTS initialization unavailable:", e)
    TTS = None

# ------------------------------------------------------------
# 📂 PATH SETUP (SMART DETECTION FOR EXE vs SCRIPT)
# ------------------------------------------------------------


if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
    INTERNAL_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent
    INTERNAL_DIR = BASE_DIR

FOLDERS = {
    "bin": BASE_DIR / "bin",
    "voices": INTERNAL_DIR / "voices",
    "input": BASE_DIR / "input",
    "logs": BASE_DIR / "logs",
    "output_hindi": BASE_DIR / "output" / "hindi",
    "subtitles": BASE_DIR / "output" / "subtitles",
    "video": BASE_DIR / "output" / "video",
    "progress": BASE_DIR / "progress.txt",
    "history": BASE_DIR / "history.json",
}

for k, p in FOLDERS.items():
    if k not in ("progress", "history"):
        p.mkdir(parents=True, exist_ok=True)

INPUT_TXT = FOLDERS["input"] / "input.txt"
XTTS_SPEAKER = str(FOLDERS["voices"] / "uvi.wav")


# ------------------------------------------------------------
# LOAD XTTS
# ------------------------------------------------------------
tts_model = None
_whisper_model = None   # Loaded on first alignment, reused across jobs
t0 = None

if TTS is None:
    print("⚠️ TTS dependencies missing. Voice generation disabled.")

else:
    try:
        use_gpu = torch.cuda.is_available()
        print(f"🔊 Activating Voice Engine… (GPU: {use_gpu})")

        t0 = time.time()
        tts_model = TTS(XTTS_MODEL_NAME, progress_bar=False, gpu=use_gpu)

        load_time = round(time.time() - t0, 2)
        print(f"⏱ XTTS load time: {load_time} seconds")
        print("🎙️ Voice Model Online.\n")

    except Exception as e:
        print(f"💥 XTTS load error: {e}")
        tts_model = None
# ------------------------------------------------------------
# PROGRESS & UTILITY FUNCTIONS
# ------------------------------------------------------------

def read_progress() -> int:
    try:
        if FOLDERS["progress"].exists():
            return int(FOLDERS["progress"].read_text().strip())
        return 0
    except (IOError, ValueError):
        return 0

def write_progress(index: int):
    try:
        FOLDERS["progress"].write_text(str(index))
    except IOError as e:
        print(f"💥 Generation Halted Unexpectedly. (Progress write failed: {e})")

def load_history() -> dict:
    try:
        if FOLDERS["history"].exists():
            return json.loads(FOLDERS["history"].read_text(encoding="utf-8"))
    except:
        pass
    return {}

def save_history(h: dict):
    FOLDERS["history"].write_text(json.dumps(h, ensure_ascii=False, indent=4), encoding="utf-8")


# ------------------------------------------------------------
# CLEAN TEXT
# ------------------------------------------------------------
def clean_text_for_tts(text: str) -> str:
    cleaned_text = text.strip().strip("’‘'")
    cleaned_text = re.sub(r'([.?!।])\1+', r'\1', cleaned_text)
    cleaned_text = cleaned_text.replace('—', ' ') 
    cleaned_text = re.sub(r'[\r\n\t]+', ' ', cleaned_text)
    cleaned_text = ' '.join(cleaned_text.split()).strip()
    if cleaned_text and cleaned_text[-1] not in ('.', '!', '?', ':', ';', '।'):
        cleaned_text += '।'.replace('…', '।') 
    return cleaned_text

# ------------------------------------------------------------
# WORD-SAFE CHUNK SPLITTER
# ------------------------------------------------------------
def split_word_safe(text: str, limit: int = MAX_CHUNK_CHARS) -> List[str]:
    words = text.split()
    chunks, cur = [], ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= limit:
            cur += " " + w
        else:
            chunks.append(cur)
            cur = w
    if cur:
        chunks.append(cur)
    return chunks


# ------------------------------------------------------------
# FALLBACK TIMESTAMPS
# ------------------------------------------------------------
def derive_word_timestamps_from_chunks(chunks: List[str], durations: List[float], full_text: str) -> List[Tuple[float, float]]:
    all_words = full_text.split()
    word_timestamps = []
    current_time = 0.0
    word_idx = 0

    for chunk, duration in zip(chunks, durations):
        chunk_words = chunk.split()
        num_words = len(chunk_words)
        time_per_word = duration / num_words if num_words else 0.0

        for _ in range(num_words):
            start_t = current_time
            end_t = start_t + time_per_word
            word_timestamps.append((start_t, end_t))
            current_time = end_t
            word_idx += 1
        
        if word_idx < len(all_words):
             current_time += INTER_CHUNK_HOLD_SECONDS

    return word_timestamps

# ------------------------------------------------------------
# WAV DURATION (UPDATED WITH FFPROBE_BIN)
# ------------------------------------------------------------
def get_wav_duration(path: Path) -> float:
    try:

        if not Path(FFPROBE_BIN).exists():
            print(f"💥 FFprobe not found at: {FFPROBE_BIN}")
            return 1.0

        result = subprocess.run(
            [
                FFPROBE_BIN,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path)
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        )

        out = result.stdout.strip()

        if not out:
            return 1.0

        return float(out)

    except subprocess.TimeoutExpired:
        print("⚠️ FFprobe timeout")
        return 1.0

    except subprocess.CalledProcessError as e:
        print(f"⚠️ FFprobe failed: {e}")
        return 1.0

    except Exception:
        return 1.0


# ------------------------------------------------------------
# TTS GENERATION + CONCAT + DURATION (UPDATED WITH FFMPEG_BIN)
# ------------------------------------------------------------
def tts_generate_and_measure(clean_text: str, out_wav: Path) -> Tuple[List[str], List[float]]:
    chunks = split_word_safe(clean_text, MAX_CHUNK_CHARS)
    temp_files = []
    durations = []

    for i, chunk in enumerate(chunks):
        # Progress Bar
        bar_len = 40
        for p in range(1, 101):
            filled = int(bar_len * p / 100)
            bar = "█" * filled + "-" * (bar_len - filled)
            sys.stdout.write(f"\r🎶 Synthesizing Speech Segments: [{bar}] {p:3d}%")
            sys.stdout.flush()
            time.sleep(0.01)

        tmp = out_wav.parent / f"tmp_{i}.wav"
        
        try: 
            tts_model.tts_to_file(
                text=chunk,
                speaker_wav=XTTS_SPEAKER if Path(XTTS_SPEAKER).exists() else None,
                language="hi",
                file_path=str(tmp)
            )
        except Exception as e:
            print(f"💥 TTS Synthesis Failed for chunk {i}: {e}")
            raise RuntimeError("TTS Synthesis Failed.") from e
        
        dur = get_wav_duration(tmp)
        durations.append(max(0.4, dur)) 
        temp_files.append(tmp)

    print("\n") 

    concat_list = out_wav.parent / "concat_list.txt"
    with concat_list.open("w", encoding="utf-8") as fh:
        for f in temp_files:
            clean_path = str(f).replace("\\", "/")
            fh.write(f"file '{clean_path}'\n")

    print("🔗 Merging Audio Layers…")
    try:
        # Use safe FFMPEG_BIN path
        subprocess.run([
            FFMPEG_BIN, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(out_wav)
        ], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"💥 Generation Halted Unexpectedly. (FFmpeg concatenation failed: {e})")
        concat_list.unlink(missing_ok=True)
        for f in temp_files:
            f.unlink(missing_ok=True)
        raise RuntimeError("Audio merging failed.") from e
    except FileNotFoundError:
        print(f"💥 Critical Error: FFmpeg binary not found at {FFMPEG_BIN}")
        raise

        bar_len = 40
        for p in range(1, 101):
            filled = int(bar_len * p / 100)
            bar = "█" * filled + "-" * (bar_len - filled)
            sys.stdout.write(f"\r🎧 Finalizing Vocal Stream: [{bar}] {p:3d}%")
            sys.stdout.flush()
            time.sleep(0.01)

    concat_list.unlink(missing_ok=True)
    for f in temp_files:
        f.unlink(missing_ok=True)
        
    return chunks, durations

    print("\n")


# ------------------------------------------------------------
# ASS TIME FORMAT
# ------------------------------------------------------------
def format_ass_time(sec: float) -> str:
    if sec < 0:
        sec = 0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ------------------------------------------------------------
# ADVANCED ASS BUILDER
# ------------------------------------------------------------
def build_karaoke_ass(ref_words, timestamps, ass_path):
    CHUNK_SIZE_WORDS = 5            
    SUBTITLE_START_DELAY_SECONDS = 1 
    WORD_DELAY_CS = 3                 
    BLUR_RADIUS = 2                   

    n = len(ref_words)
    ass = f"""[Script Info]
Title: Daily Krishna Message
ScriptType: v4.00+
Collisions: Normal
PlayResX: {VIDEO_W}
PlayResY: {VIDEO_H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CenterWord, Noto Sans Devanagari,{FONT_SIZE},{HIGHLIGHT_COLOR},{BASE_COLOR},&H000000,&H000000,5,0,0,0,100,100,0,0,1,{BORDER_SIZE},{SHADOW_SIZE},5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_dialogues = []
    word_pointer = 0

    while word_pointer < n:
        chunk_start = word_pointer
        chunk_end = min(word_pointer + CHUNK_SIZE_WORDS, n)

        start_w_start = timestamps[chunk_start][0]
        end_w_end = timestamps[chunk_end - 1][1]

        start_time_chunk = start_w_start + SUBTITLE_START_DELAY_SECONDS
        if chunk_start != 0:
            start_time_chunk += INTER_CHUNK_DELAY_SECONDS

        end_time_chunk = end_w_end + SUBTITLE_START_DELAY_SECONDS + INTER_CHUNK_HOLD_SECONDS

        start_ass = format_ass_time(start_time_chunk)
        end_ass = format_ass_time(end_time_chunk)

        karaoke_text = ""
        for i in range(chunk_start, chunk_end):
            w_start, w_end, w_text = timestamps[i]
            duration_cs = round((w_end - w_start) * 100)
            if i == chunk_start:
                delay_from_start_s = (w_start + SUBTITLE_START_DELAY_SECONDS) - start_time_chunk
                delay_cs = max(0, round(delay_from_start_s * 100))
                karaoke_text += f"{{\\k{delay_cs}}}"
            else:
                karaoke_text += f"{{\\k{WORD_DELAY_CS}}}"
            karaoke_text += f"{{\\kf{duration_cs}\\1c{HIGHLIGHT_COLOR}}}{w_text}{{\\1c{BASE_COLOR}}} "

        karaoke_text = karaoke_text.strip()
        fade_in = 20
        fade_out = max(20, int((end_time_chunk - start_time_chunk) * 80))

        dialogue = (
            f"Dialogue: 0,{start_ass},{end_ass},CenterWord,,0,0,0,,"
            f"{{\\fad({fade_in},{fade_out})\\bord{BORDER_SIZE}\\blur{BLUR_RADIUS}}}{karaoke_text}\n"
        )
        ass_dialogues.append(dialogue)
        word_pointer = chunk_end

    ass += "".join(ass_dialogues)
    ass_path.write_text(ass, encoding="utf-8")


# ------------------------------------------------------------
# FINAL VIDEO BUILDER (UPDATED WITH FFMPEG_BIN)
# ------------------------------------------------------------
def create_final_video(audio_path: Path, ass_path: Path, out_video: Path):

    duration = get_wav_duration(audio_path)
    black_tmp = out_video.parent / "black_tmp.mp4"

    print("🖼️ Creating Visual Canvas…")
    try:
        # Use safe FFMPEG_BIN path
        subprocess.run([
            FFMPEG_BIN, "-y",
            "-f", "lavfi",
            f"-i", f"color=size={VIDEO_W}x{VIDEO_H}:rate=30:color=black",
            "-t", str(duration + 1),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(black_tmp)
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"💥 Generation Halted Unexpectedly. (Black video failed: {e})")
        raise
    except FileNotFoundError:
        print(f"💥 Critical Error: FFmpeg binary not found at {FFMPEG_BIN}")
        raise

    p = Path(ass_path).resolve()
    path_str = str(p)
    path_escaped = path_str.replace("\\", "\\\\").replace(":", "\\:") 
    print("\nUSING ESCAPED ASS PATH FOR FFMPEG:\n", path_escaped, "\n")

    print("🔥 Fusing Audio + Visual Layers…")
    try:
        # Use safe FFMPEG_BIN path
        subprocess.run([
            FFMPEG_BIN, "-y",
            "-i", str(black_tmp),
            "-i", str(audio_path),
            "-vf", f"ass='{path_escaped}'",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            str(out_video)
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"💥 Generation Halted Unexpectedly. (Final video render failed: {e})")
        raise
    finally:
        black_tmp.unlink(missing_ok=True)


# ------------------------------------------------------------
# NEXT LINE READER
# ------------------------------------------------------------
def get_next_line_and_number() -> Tuple[str | None, int | None]:
    if not INPUT_TXT.exists():
        return None, None

    raw_lines = INPUT_TXT.read_text(encoding="utf-8").splitlines()
    lines = [ln.strip() for ln in raw_lines if ln.strip()]

    if len(lines) < 2:
        return None, None

    idx = read_progress()
    pair_index = idx * 2 

    if pair_index >= len(lines):
        write_progress(0)
        pair_index = 0
        idx = 0 

    if pair_index + 1 >= len(lines):
        write_progress(idx + 1)
        return "मित्र… आज का संदेश उपलब्ध नहीं है।", idx + 1

    number_line = lines[pair_index]
    text_line = lines[pair_index + 1]
    cleaned_text_line = clean_text_for_tts(text_line)

    num_match = re.search(r"\d+", number_line)
    num = int(num_match.group()) if num_match else (idx + 1)

    write_progress(idx + 1)
    return cleaned_text_line, num


# ------------------------------------------------------------
# MAIN WORKFLOW
# ------------------------------------------------------------
def main_generate():
    if tts_model is None:
        print("❗ Action Required to Continue. (XTTS not loaded)")
        return

    msg_text, num = get_next_line_and_number() 
    
    if not msg_text or msg_text == "मित्र… आज का संदेश उपलब्ध नहीं है।":
        print(f"⚠️ Something Interrupted the Process. ({msg_text})" if msg_text else "⚠️ Something Interrupted the Process. (No input text found in input/input.txt.)")
        return

    clean_line = msg_text 
    now = datetime.now()
    fname = now.strftime("%d%m%Y")
    human = now.strftime("%d/%m/%Y")

    out_wav = FOLDERS["output_hindi"] / f"{fname}.wav"
    out_txt = FOLDERS["output_hindi"] / f"{fname}.txt"
    ass_file = FOLDERS["subtitles"] / f"{fname}.ass"
    final_video = FOLDERS["video"] / f"{fname}.mp4"

    out_txt.write_text(clean_line, encoding="utf-8")

    try:
        print(f"📜 Reading Today’s Script… (Line #{num})")
        chunks, durations = tts_generate_and_measure(clean_line, out_wav)

        import whisper
        import gc
        print("⏱️ Synchronizing Word Timeline…")
        global _whisper_model
        if _whisper_model is None:
            print("🔄 Loading Whisper model (first run)…")
            _whisper_model = whisper.load_model("small")
        result = _whisper_model.transcribe(str(out_wav), word_timestamps=True, language="hi")

        raw_ts = []
        for seg in result["segments"]:
            if "words" in seg:
                for w in seg["words"]:
                    raw_ts.append((float(w["start"]), float(w["end"])))

        if not raw_ts:
            print("❗ Action Required to Continue. (Fallback Timings)")
            ref_words = clean_line.split()
            fallback_ts = derive_word_timestamps_from_chunks(chunks, durations, clean_line)
            timestamps = [(s, e, w) for (s, e), w in zip(fallback_ts, ref_words)]
        else:
            ref_words = clean_line.split()
            ref_count = len(ref_words)
            if len(raw_ts) >= ref_count:
                aligned_ts = raw_ts[:ref_count]
            else:
                print("📐 Aligning Segment Boundaries…")
                last_end = raw_ts[-1][1] if raw_ts else 0.25
                interval = last_end / ref_count
                aligned_ts = [(i * interval, (i + 1) * interval) for i in range(ref_count)]
            timestamps = [(s, e, w) for (s, e), w in zip(aligned_ts, ref_words)]

        print("📝 Crafting Dynamic Highlights…")
        # Free alignment VRAM before subtitle/render stages
        del result
        gc.collect()
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
        build_karaoke_ass(ref_words, timestamps, ass_file)

        print("🎥 Rendering Final Sequence…")
        create_final_video(out_wav, ass_file, final_video)

        history = load_history()
        history[str(num)] = {"date": human, "text_preview": clean_line[:50] + "..."}
        save_history(history)

        print("\n🎉 Generation Complete!")
        print("📦 Packaging Your Creation...")
        print(f"  WAV : {out_wav.name}")
        print(f"  ASS : {ass_file.name}")
        print(f"  MP4 : {final_video.name}")
        
    except Exception as e:
        print(f"\n💥 Generation Halted Unexpectedly. (FATAL: {e})")
        write_progress(read_progress() - 1)


# ------------------------------------------------------------
# RUN
# ------------------------------------------------------------
if __name__ == "__main__":
    try:
        main_generate()
        sys.exit(0) 
    except Exception:
        sys.exit(1)