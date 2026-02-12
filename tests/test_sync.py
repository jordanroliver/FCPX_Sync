"""Tests for the sync engine."""

import numpy as np
import pytest

from fcpx_sync.sync_engine import find_sync_offset, ANALYSIS_SR


def _make_tone(freq: float, duration: float, sr: int, offset: float = 0.0) -> np.ndarray:
    """Generate a sine wave tone starting at a given offset."""
    t = np.arange(int(sr * duration)) / sr
    return np.sin(2 * np.pi * freq * (t + offset)).astype(np.float32)


def test_identical_signals_zero_offset():
    """Two identical signals should have ~0 offset."""
    signal = _make_tone(440, 2.0, ANALYSIS_SR)
    offset, score = find_sync_offset(signal, signal)
    assert abs(offset) < 0.01  # less than 10ms
    assert score > 0.5


def test_known_offset():
    """Signal B is a delayed copy of signal A — should detect the delay."""
    np.random.seed(42)
    # Use noise (unique signal) rather than a repeating tone
    full = np.random.randn(ANALYSIS_SR * 5).astype(np.float32)

    delay_samples = int(0.5 * ANALYSIS_SR)  # 500ms delay
    video_audio = full[:ANALYSIS_SR * 4]
    ext_audio = full[delay_samples:delay_samples + ANALYSIS_SR * 3]

    offset, score = find_sync_offset(video_audio, ext_audio)

    # Offset should be ~0.5 seconds (audio starts 500ms into video)
    assert abs(offset - 0.5) < 0.05, f"Expected ~0.5s, got {offset:.3f}s"
    assert score > 0.3


def test_silent_signal_returns_zero():
    """Silent signals should return 0 offset and 0 score."""
    silence = np.zeros(ANALYSIS_SR * 2, dtype=np.float32)
    tone = _make_tone(440, 2.0, ANALYSIS_SR)
    offset, score = find_sync_offset(silence, tone)
    assert offset == 0.0
    assert score == 0.0


def test_negative_offset():
    """External audio that starts before the video should give negative offset."""
    np.random.seed(123)
    full = np.random.randn(ANALYSIS_SR * 6).astype(np.float32)

    # Video starts 1 second into the full recording
    video_audio = full[ANALYSIS_SR:ANALYSIS_SR * 5]
    ext_audio = full[:ANALYSIS_SR * 4]

    offset, score = find_sync_offset(video_audio, ext_audio)

    # Offset should be ~ -1.0 (audio leads by 1 second)
    assert abs(offset - (-1.0)) < 0.05, f"Expected ~-1.0s, got {offset:.3f}s"
    assert score > 0.3
