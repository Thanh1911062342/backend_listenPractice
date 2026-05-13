import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _normalize_audio(input_path: Path) -> str:
    """Normalize to 16kHz mono WAV — optimal input for Whisper + pyannote."""
    tmp = tempfile.mktemp(suffix=".wav")
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(input_path),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "16000", "-ac", "1", tmp,
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg normalize failed: {result.stderr.decode(errors='replace')[:300]}")
    return tmp


def _fix_overlaps(segments: list[dict]) -> list[dict]:
    """Split overlapping timestamps at their midpoint."""
    for i in range(1, len(segments)):
        if segments[i]["start"] < segments[i - 1]["end"]:
            mid = (segments[i]["start"] + segments[i - 1]["end"]) / 2
            segments[i - 1]["end"] = mid
            segments[i]["start"] = mid
    return segments


def _merge_consecutive(segments: list[dict], gap_ms: float = 400) -> list[dict]:
    """Merge consecutive same-speaker segments separated by a small gap."""
    merged: list[dict] = []
    for seg in segments:
        spk = seg.get("speaker")
        gap = (seg["start"] - merged[-1]["end"]) * 1000 if merged else float("inf")
        if merged and merged[-1].get("speaker") == spk and gap < gap_ms:
            merged[-1]["end"] = seg["end"]
            # Japanese: no space between words; other languages: add space
            merged[-1]["text"] += seg["text"]
        else:
            merged.append(dict(seg))
    return merged


def transcribe(audio_path: Path, language: str = "ja", n_speakers: int = 0) -> list[dict]:
    """
    Transcribe audio using WhisperX with optional speaker diarization.

    Returns list of dicts: {seq, start_ms, end_ms, raw_text, clean_text, speaker}
    compatible with repository.bulk_create_segments.

    Env vars:
        STT_MODEL      — whisper model size (default: large-v3)
        STT_BATCH_SIZE — transcription batch size (default: 4)
        HF_TOKEN       — HuggingFace token for pyannote diarization
    """
    import whisperx  # imported lazily to avoid slow startup on Railway

    device = "cpu"
    compute_type = "int8"
    model_name = os.environ.get("STT_MODEL", "large-v3")
    batch_size = int(os.environ.get("STT_BATCH_SIZE", "4"))

    tmp_wav: str | None = None
    try:
        # ── Step 1: Normalize audio ──────────────────────────────────────────
        logger.info("[STT] Normalizing audio: %s", audio_path.name)
        tmp_wav = _normalize_audio(audio_path)
        audio = whisperx.load_audio(tmp_wav)

        # ── Step 2: Transcribe ───────────────────────────────────────────────
        logger.info("[STT] Loading model %s on %s", model_name, device)
        model = whisperx.load_model(
            model_name, device=device, language=language, compute_type=compute_type
        )
        result = model.transcribe(audio, batch_size=batch_size)
        del model
        logger.info("[STT] Transcription done: %d raw segments", len(result["segments"]))

        # ── Step 3: Word-level alignment for accurate timestamps ─────────────
        detected_lang = result.get("language", language)
        model_a, metadata = whisperx.load_align_model(
            language_code=detected_lang, device=device
        )
        result = whisperx.align(
            result["segments"], model_a, metadata, audio, device,
            return_char_alignments=False,
        )
        del model_a

        # ── Step 4: Speaker diarization (optional) ───────────────────────────
        if n_speakers > 0:
            hf_token = os.environ.get("HF_TOKEN", "")
            if not hf_token:
                logger.warning("[STT] HF_TOKEN not set — skipping diarization")
            else:
                logger.info("[STT] Diarizing with n_speakers=%d", n_speakers)
                diarize_model = whisperx.diarize.DiarizationPipeline(
                    token=hf_token, device=device
                )
                diarize_segments = diarize_model(
                    audio,
                    min_speakers=max(1, n_speakers),
                    max_speakers=n_speakers,
                )
                result = whisperx.assign_word_speakers(diarize_segments, result)
                del diarize_model

        segments: list[dict] = result["segments"]

        # ── Step 5: Post-process ─────────────────────────────────────────────
        segments = _fix_overlaps(segments)
        segments = _merge_consecutive(segments)

        # ── Step 6: Map SPEAKER_00/01/… → A/B/C/D ───────────────────────────
        speaker_map: dict[str, str] = {}
        labels = ["A", "B", "C", "D"]

        def get_label(spk: str | None) -> str | None:
            if not spk or spk.upper() == "UNKNOWN":
                return None
            if spk not in speaker_map and len(speaker_map) < len(labels):
                speaker_map[spk] = labels[len(speaker_map)]
            return speaker_map.get(spk)

        # ── Step 7: Build output dicts ───────────────────────────────────────
        output: list[dict] = []
        for i, seg in enumerate(segments, start=1):
            text = seg["text"].strip()
            if not text:
                continue
            speaker = get_label(seg.get("speaker"))
            raw_text = f"[{speaker}] {text}" if speaker else text
            output.append({
                "seq": i,
                "start_ms": int(seg["start"] * 1000),
                "end_ms": int(seg["end"] * 1000),
                "raw_text": raw_text,
                "clean_text": text,
                "speaker": speaker,
            })

        logger.info("[STT] Done: %d output segments, speaker_map=%s", len(output), speaker_map)
        return output

    finally:
        if tmp_wav and os.path.exists(tmp_wav):
            os.unlink(tmp_wav)
