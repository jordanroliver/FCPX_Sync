"""Tests for audio-based sync engine (FFT cross-correlation)."""

import numpy as np
import pytest

from fcpx_sync.audio_sync import _cross_correlate


# ── Helpers ────────────────────────────────────────────────────

def _make_signal(length=4000, seed=42):
    rng = np.random.default_rng(seed)
    return rng.normal(size=length).astype(np.float32)


# ── Tests ──────────────────────────────────────────────────────

def test_identical_signals_zero_offset():
    """Identical signals → offset 0, very high confidence."""
    sig = _make_signal()
    offset, conf = _cross_correlate(sig, sig)
    assert offset == 0
    assert conf > 0.95


def test_known_positive_shift():
    """Candidate shifted right → negative offset (candidate trails reference)."""
    sig = _make_signal(length=6000)
    shift = 200
    # reference = sig[200:], candidate = sig[:5800] — reference trails by 200
    reference = sig[shift:]
    candidate = sig[: len(sig) - shift]
    offset, conf = _cross_correlate(reference, candidate)
    assert abs(offset + shift) <= 2, f"Expected ~{-shift}, got {offset}"
    assert conf > 0.5


def test_known_negative_shift():
    """Candidate shifted left → positive offset (candidate leads reference)."""
    sig = _make_signal(length=6000)
    shift = 150
    reference = sig[: len(sig) - shift]
    candidate = sig[shift:]
    offset, conf = _cross_correlate(reference, candidate)
    assert abs(offset - shift) <= 2, f"Expected ~{shift}, got {offset}"
    assert conf > 0.5


def test_unrelated_signals_low_confidence():
    """Two unrelated random signals → confidence below threshold."""
    sig1 = _make_signal(seed=42)
    sig2 = _make_signal(seed=999)
    _, conf = _cross_correlate(sig1, sig2)
    assert conf < 0.15, f"Unrelated signals had confidence {conf}"


def test_silence_zero_confidence():
    """Silent (all-zero) signals → confidence exactly 0."""
    silence = np.zeros(1000, dtype=np.float32)
    offset, conf = _cross_correlate(silence, silence)
    assert conf == 0.0


def test_different_lengths():
    """Signals of different lengths still produce a valid result."""
    sig = _make_signal(length=8000)
    short = sig[100:2100]   # 2000 samples, offset 100
    long = sig[:8000]       # full 8000 samples
    offset, conf = _cross_correlate(long, short)
    # short starts at sample 100 within long → positive offset ~100
    assert abs(offset - 100) <= 3, f"Expected ~100, got {offset}"
    assert conf > 0.3
