"""Audio-based sync engine using FFT cross-correlation.

Matches video scratch audio against external audio recordings to find
sync offsets.  Returns the same SyncMatch structure used by the
timecode matcher so the FCPXML generator works unchanged.

Requires numpy (optional dependency):
    pip install sync-hole[audio]
"""

import subprocess
from pathlib import Path
from typing import Optional

from .sync_engine import MediaFile, SyncMatch


def _extract_audio_pcm(path: Path, sample_rate: int = 8000):
    """Extract mono audio as float32 PCM via ffmpeg pipe.

    Decodes audio → mono → resamples to *sample_rate* → pipes raw
    float32 little-endian to stdout.  No temp files written.

    Returns a 1-D numpy float32 array.
    """
    import numpy as np

    cmd = [
        "ffmpeg", "-i", str(path),
        "-vn",                     # drop video
        "-ac", "1",                # mono
        "-ar", str(sample_rate),   # resample
        "-f", "f32le",             # raw float32 LE
        "-acodec", "pcm_f32le",
        "pipe:1",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[:200]
        raise RuntimeError(f"ffmpeg failed for {path.name}: {stderr}")

    return np.frombuffer(result.stdout, dtype=np.float32)


def _cross_correlate(reference, candidate):
    """FFT cross-correlation between two 1-D float32 signals.

    Returns *(offset_samples, confidence)* where:

    * **offset_samples** — how many samples to shift *candidate*
      rightward to align with *reference*.  Positive means candidate
      leads (starts earlier); negative means candidate trails.
    * **confidence** — normalised peak correlation in [0, 1].

    Uses zero-padded FFT for O(n log n) computation.
    """
    import numpy as np

    n = len(reference) + len(candidate) - 1
    fft_size = 1
    while fft_size < n:
        fft_size <<= 1  # next power of 2

    R = np.fft.rfft(reference, fft_size)
    C = np.fft.rfft(candidate, fft_size)

    # Cross-correlation in frequency domain
    xcorr = np.fft.irfft(R * np.conj(C), fft_size)

    # Normalise by geometric mean of energies
    energy_r = float(np.sqrt(np.sum(reference ** 2)))
    energy_c = float(np.sqrt(np.sum(candidate ** 2)))
    denom = energy_r * energy_c

    if denom < 1e-12:
        return 0, 0.0

    xcorr /= denom

    peak_idx = int(np.argmax(np.abs(xcorr)))
    confidence = float(np.abs(xcorr[peak_idx]))

    # Convert circular FFT index → signed linear offset
    if peak_idx > fft_size // 2:
        offset = peak_idx - fft_size
    else:
        offset = peak_idx

    return offset, confidence


def match_by_audio(
    video_files: list,
    audio_files: list,
    *,
    sample_rate: int = 8000,
    confidence_threshold: float = 0.15,
    progress_callback=None,
) -> list:
    """Match video and audio files by audio cross-correlation.

    Strategy:
      1. Extract PCM from all files (skip videos without audio).
      2. Cross-correlate every video × audio pair.
      3. Greedy 1:1 assignment by descending confidence.

    Args:
        video_files: Probed MediaFile list.
        audio_files: Probed MediaFile list.
        sample_rate: Down-sample rate for comparison (default 8 kHz).
        confidence_threshold: Minimum normalised correlation to accept.
        progress_callback: Optional ``callable(step, total, message)``.

    Returns:
        ``list[SyncMatch]`` sorted by video filename.
    """
    import numpy as np

    total_files = len(video_files) + len(audio_files)
    step = 0

    def _progress(msg):
        nonlocal step
        step += 1
        if progress_callback:
            progress_callback(step, total_files, msg)

    # ── Phase 1: extract PCM ──────────────────────────────────
    video_pcm: dict[Path, Optional[np.ndarray]] = {}
    for v in video_files:
        _progress(f"Extracting audio: {v.path.name}")
        if not v.has_audio:
            video_pcm[v.path] = None
            continue
        try:
            video_pcm[v.path] = _extract_audio_pcm(v.path, sample_rate)
        except Exception:
            video_pcm[v.path] = None

    audio_pcm: dict[Path, Optional[np.ndarray]] = {}
    for a in audio_files:
        _progress(f"Extracting audio: {a.path.name}")
        try:
            audio_pcm[a.path] = _extract_audio_pcm(a.path, sample_rate)
        except Exception:
            audio_pcm[a.path] = None

    # ── Phase 2: correlate every pair ─────────────────────────
    Pair = tuple  # (video_idx, audio_idx, offset_samples, confidence)
    pairs: list[Pair] = []

    for vi, v in enumerate(video_files):
        v_sig = video_pcm.get(v.path)
        if v_sig is None or len(v_sig) < 800:  # < 0.1 s at 8 kHz
            continue
        for ai, a in enumerate(audio_files):
            a_sig = audio_pcm.get(a.path)
            if a_sig is None or len(a_sig) < 800:
                continue
            offset, conf = _cross_correlate(v_sig, a_sig)
            pairs.append((vi, ai, offset, conf))

    # ── Phase 3: greedy 1:1 assignment ────────────────────────
    pairs.sort(key=lambda p: p[3], reverse=True)

    used_v: set[int] = set()
    used_a: set[int] = set()
    matches: list[SyncMatch] = []

    for vi, ai, offset_samples, conf in pairs:
        if vi in used_v or ai in used_a:
            continue
        if conf < confidence_threshold:
            break  # sorted descending — all remaining are worse
        offset_seconds = offset_samples / sample_rate
        matches.append(SyncMatch(
            video=video_files[vi],
            audio=audio_files[ai],
            offset_seconds=offset_seconds,
        ))
        used_v.add(vi)
        used_a.add(ai)

    matches.sort(key=lambda m: m.video.path.name)
    return matches
