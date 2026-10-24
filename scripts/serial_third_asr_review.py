#!/usr/bin/env python3
"""Third-model diagnostic for disputed subtitle words.

Uses only 7-second audio excerpts from the existing GitHub triage artifact.
Neither ASR agreement nor disagreement constitutes proof of the spoken words.
Never edits video, subtitle files, or Google Drive.
"""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from faster_whisper import WhisperModel


def norm(s):
    return re.sub(r"[^а-яё0-9]", "", str(s).lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--part", type=int, required=True)
    ap.add_argument("--model", default="distil-large-v3")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.input / "review_queue.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise RuntimeError("No disputed audio samples found")
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=4)
    results = []
    errors = []
    for i, row in enumerate(rows, 1):
        audio_file = args.input / row["audio_file"]
        result = dict(row)
        try:
            if not audio_file.is_file():
                raise FileNotFoundError(audio_file)
            segments, info = model.transcribe(
                str(audio_file), language="ru", beam_size=5, temperature=0,
                vad_filter=False, condition_on_previous_text=False,
                word_timestamps=True,
            )
            segments = list(segments)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            words = [
                {"text": w.word.strip(), "start": round(float(w.start), 3),
                 "end": round(float(w.end), 3),
                 "probability": round(float(w.probability), 3)}
                for seg in segments for w in (seg.words or [])
                if w.start is not None and w.end is not None
            ]
            rel = float(row["relative_time"])
            target = min(3.0, rel)
            nearest = min(
                words, key=lambda w: min(abs(w["start"] - target),
                                         abs(w["end"] - target))
            ) if words else None
            nearby = [
                w for w in words if w["start"] <= target + 1.0
                and w["end"] >= target - 1.0
            ]
            original = norm(row["original_word"])
            near_match = any(norm(w["text"]) == original for w in nearby)
            anywhere_match = any(norm(w["text"]) == original for w in words)
            independent_match = original in [
                norm(w) for w in re.findall(r"[а-яёА-ЯЁ0-9-]+",
                                           row["independent_transcript"])
            ]
            if near_match and independent_match:
                category = "THREE_WAY_TEXT_SUPPORT_UNVERIFIED"
            elif near_match:
                category = "THIRD_SUPPORTS_ORIGINAL_UNVERIFIED"
            elif not independent_match:
                category = "TWO_ALTERNATIVES_DO_NOT_SUPPORT_ORIGINAL_REVIEW_AUDIO"
            else:
                category = "CONFLICTING_ASR_REVIEW_AUDIO"
            result.update({
                "third_model": args.model,
                "third_transcript": text,
                "third_word_nearest_target": nearest["text"] if nearest else "",
                "third_nearest_word_probability": nearest["probability"] if nearest else "",
                "third_nearby_words": " ".join(w["text"] for w in nearby),
                "third_original_within_one_second": near_match,
                "third_original_anywhere": anywhere_match,
                "second_original_anywhere": independent_match,
                "triage_category": category,
                "verified_by_listening": False,
                "third_word_timestamps": json.dumps(words, ensure_ascii=False),
            })
        except Exception as exc:
            errors.append({"audio_file": str(audio_file), "error": str(exc)})
            result.update({"triage_category": "THIRD_ASR_ERROR",
                           "error": str(exc), "verified_by_listening": False})
        results.append(result)
        if i % 15 == 0 or i == len(rows):
            print(f"PART {args.part} THIRD_ASR {i}/{len(rows)} ERRORS {len(errors)}",
                  flush=True)
    fields = list(dict.fromkeys(k for row in results for k in row))
    with (args.output / "three_way_review.csv").open(
            "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    (args.output / "three_way_review.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "part": args.part, "third_model": args.model,
        "samples": len(rows), "categories": dict(Counter(
            row["triage_category"] for row in results)),
        "errors": errors, "subtitle_text_verified": False,
        "word_timing_verified": False, "video_files_changed": False,
        "note": "Independent ASR outputs are diagnostic only; human listening is still needed. Original and second-model word presence may be elsewhere in the context window."
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("THIRD_ASR_SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
    if errors:
        raise RuntimeError(f"{len(errors)} audio samples could not be processed")


if __name__ == "__main__":
    main()
