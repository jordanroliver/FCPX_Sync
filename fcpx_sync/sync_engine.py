"""Audio waveform cross-correlation engine for detecting sync offsets."""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import correlate, correlation_lags


# Target sample rate for analysis (lower = faster, 8kHz is plenty for sync)
ANALYSIS_SR = 8000

# Minimum correlation score to consider a match valid (0-1 normalized)
MIN_CORRELATION_THRESHOLD = 0.1


@dataclass
class SyncMatch:
    """Result of a sync match between a video and audio file."""

    video_path: Path
    audio_path: Path
    offset_seconds: float  # positive = audio starts after video
    correlation_score: float
    video_duration: float
    audio_duration: float


def extract_audio_from_video(video_path: Path) -> np.ndarray:
    """Extract audio from a video file using ffmpeg and return as numpy array.

    Extracts mono audio at ANALYSIS_SR sample rate as raw PCM float32.
    """
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vn",                    # no video
        "-ac", "1",               # mono
        "-ar", str(ANALYSIS_SR),  # resample
        "-f", "f32le",            # raw float32 little-endian
        "-loglevel", "error",
        "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype=np.float32)


def load_audio_file(audio_path: Path) -> np.ndarray:
    """Load an audio file and return as numpy array at analysis sample rate."""
    cmd = [
        "ffmpeg", "-i", str(audio_path),
        "-vn",
        "-ac", "1",
        "-ar", str(ANALYSIS_SR),
        "-f", "f32le",
        "-loglevel", "error",
        "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype=np.float32)


def get_media_duration(path: Path) -> float:
    """Get duration of a media file in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def get_media_info(path: Path) -> dict:
    """Get detailed media info (duration, frame rate, sample rate, etc.)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,r_frame_rate,sample_rate,channels,width,height",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    import json
    return json.loads(result.stdout)


def find_sync_offset(video_audio: np.ndarray, ext_audio: np.ndarray) -> tuple[float, float]:
    """Find the time offset between two audio signals using cross-correlation.

    Returns:
        (offset_seconds, normalized_correlation_score)

        offset_seconds: How many seconds the external audio is ahead of the
                       video audio. Positive means ext_audio starts after the
                       video's audio begins. To sync them, you'd place the
                       audio starting at this offset on the timeline.
    """
    # Normalize both signals to prevent amplitude bias
    v_std = np.std(video_audio)
    a_std = np.std(ext_audio)

    if v_std < 1e-10 or a_std < 1e-10:
        # One of the signals is silent - can't correlate
        return 0.0, 0.0

    v_norm = (video_audio - np.mean(video_audio)) / v_std
    a_norm = (ext_audio - np.mean(ext_audio)) / a_std

    # Cross-correlate using FFT method (fast for large arrays)
    correlation = correlate(v_norm, a_norm, mode="full", method="fft")

    # Normalize by the geometric mean of signal lengths
    correlation /= np.sqrt(len(video_audio) * len(ext_audio))

    # Find peak
    peak_idx = np.argmax(np.abs(correlation))
    peak_score = abs(correlation[peak_idx])

    # Calculate lag from peak index
    lags = correlation_lags(len(video_audio), len(ext_audio), mode="full")
    lag_samples = lags[peak_idx]

    # Convert to seconds. Positive lag means video_audio leads (ext_audio starts later).
    offset_seconds = lag_samples / ANALYSIS_SR

    return offset_seconds, peak_score


def match_files(
    video_paths: list[Path],
    audio_paths: list[Path],
    *,
    progress_callback=None,
) -> list[SyncMatch]:
    """Match video files to audio files by finding best correlation pairs.

    For each video, finds the best-matching audio file based on waveform
    cross-correlation score.

    Args:
        video_paths: List of video file paths.
        audio_paths: List of external audio file paths.
        progress_callback: Optional callable(step, total, message) for progress.

    Returns:
        List of SyncMatch results for each matched pair.
    """
    total_steps = len(video_paths) + len(audio_paths) + (len(video_paths) * len(audio_paths))
    step = 0

    def _progress(msg: str):
        nonlocal step
        step += 1
        if progress_callback:
            progress_callback(step, total_steps, msg)

    # Pre-load all audio
    video_audios = {}
    for vp in video_paths:
        _progress(f"Extracting audio from {vp.name}")
        try:
            video_audios[vp] = extract_audio_from_video(vp)
        except subprocess.CalledProcessError as e:
            _progress(f"  WARNING: Could not extract audio from {vp.name}: {e}")
            continue

    ext_audios = {}
    for ap in audio_paths:
        _progress(f"Loading {ap.name}")
        try:
            ext_audios[ap] = load_audio_file(ap)
        except subprocess.CalledProcessError as e:
            _progress(f"  WARNING: Could not load {ap.name}: {e}")
            continue

    # Cross-correlate every video against every audio to find best pairs
    # Store: { video_path: (best_audio_path, offset, score) }
    best_matches: dict[Path, tuple[Path, float, float]] = {}

    for vp, v_audio in video_audios.items():
        best_score = -1.0
        best_ap = None
        best_offset = 0.0

        for ap, a_audio in ext_audios.items():
            _progress(f"Comparing {vp.name} <-> {ap.name}")
            offset, score = find_sync_offset(v_audio, a_audio)

            if score > best_score:
                best_score = score
                best_ap = ap
                best_offset = offset

        if best_ap is not None and best_score >= MIN_CORRELATION_THRESHOLD:
            best_matches[vp] = (best_ap, best_offset, best_score)

    # Build results
    results = []
    for vp, (ap, offset, score) in best_matches.items():
        v_dur = get_media_duration(vp)
        a_dur = get_media_duration(ap)
        results.append(SyncMatch(
            video_path=vp,
            audio_path=ap,
            offset_seconds=offset,
            correlation_score=score,
            video_duration=v_dur,
            audio_duration=a_dur,
        ))

    # Sort by video filename for consistent output
    results.sort(key=lambda m: m.video_path.name)

    return results
