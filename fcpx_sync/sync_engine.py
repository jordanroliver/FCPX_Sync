"""Timecode-based sync engine for matching video and audio files."""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Timecode:
    """SMPTE timecode representation."""

    hours: int
    minutes: int
    seconds: int
    frames: int
    fps: float  # frame rate used to convert to seconds

    @classmethod
    def parse(cls, tc_str: str, fps: float = 24.0) -> "Timecode":
        """Parse a timecode string like '01:02:03:04' or '01:02:03;04' (drop-frame)."""
        # Handle both : and ; separators
        parts = re.split(r"[:;]", tc_str.strip())
        if len(parts) != 4:
            raise ValueError(f"Invalid timecode format: {tc_str!r}")
        return cls(
            hours=int(parts[0]),
            minutes=int(parts[1]),
            seconds=int(parts[2]),
            frames=int(parts[3]),
            fps=fps,
        )

    def to_seconds(self) -> float:
        """Convert timecode to total seconds."""
        total = self.hours * 3600 + self.minutes * 60 + self.seconds
        total += self.frames / self.fps
        return total

    def __str__(self) -> str:
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}:{self.frames:02d}"


@dataclass
class MediaFile:
    """Metadata for a video or audio file."""

    path: Path
    timecode: Optional[Timecode]
    duration: float  # seconds
    has_video: bool
    has_audio: bool
    fps_num: int  # e.g. 24000
    fps_den: int  # e.g. 1001
    width: int
    height: int
    sample_rate: int
    channels: int


@dataclass
class SyncMatch:
    """Result of a sync match between a video and audio file."""

    video: MediaFile
    audio: MediaFile
    offset_seconds: float  # how much to shift audio relative to video


def _run_ffprobe(path: Path) -> dict:
    """Run ffprobe and return parsed JSON."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=duration,tags:stream=codec_type,r_frame_rate,sample_rate,channels,width,height,tags",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _extract_timecode(probe: dict) -> Optional[str]:
    """Extract timecode string from ffprobe output.

    Timecode can be in:
    - Stream tags (timecode stream or video stream)
    - Format tags
    """
    # Check stream tags first (most reliable)
    for stream in probe.get("streams", []):
        tags = stream.get("tags", {})
        tc = tags.get("timecode")
        if tc:
            return tc

    # Check format tags
    fmt_tags = probe.get("format", {}).get("tags", {})
    tc = fmt_tags.get("timecode")
    if tc:
        return tc

    return None


def _get_fps(probe: dict) -> tuple:
    """Extract frame rate as (numerator, denominator)."""
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            fps_str = stream.get("r_frame_rate", "24/1")
            parts = fps_str.split("/")
            num = int(parts[0])
            den = int(parts[1]) if len(parts) > 1 else 1
            return num, den
    return 24, 1


def probe_media(path: Path) -> MediaFile:
    """Probe a media file and extract all relevant metadata."""
    probe = _run_ffprobe(path)

    # Determine stream types present
    has_video = False
    has_audio = False
    fps_num, fps_den = 24, 1
    width, height = 0, 0
    sample_rate, channels = 48000, 2

    for stream in probe.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video":
            has_video = True
            fps_str = stream.get("r_frame_rate", "24/1")
            parts = fps_str.split("/")
            fps_num = int(parts[0])
            fps_den = int(parts[1]) if len(parts) > 1 else 1
            width = stream.get("width", 1920)
            height = stream.get("height", 1080)
        elif codec_type == "audio":
            has_audio = True
            sample_rate = int(stream.get("sample_rate", 48000))
            channels = int(stream.get("channels", 2))

    # Duration
    duration = float(probe.get("format", {}).get("duration", 0))

    # Timecode
    tc_str = _extract_timecode(probe)
    fps_float = fps_num / fps_den if has_video else 24.0
    timecode = Timecode.parse(tc_str, fps=fps_float) if tc_str else None

    return MediaFile(
        path=path,
        timecode=timecode,
        duration=duration,
        has_video=has_video,
        has_audio=has_audio,
        fps_num=fps_num,
        fps_den=fps_den,
        width=width,
        height=height,
        sample_rate=sample_rate,
        channels=channels,
    )


def match_by_timecode(
    video_files: list[MediaFile],
    audio_files: list[MediaFile],
    *,
    tolerance_seconds: float = 0.5,
    progress_callback=None,
) -> list[SyncMatch]:
    """Match video and audio files by overlapping timecode.

    For each video, finds the audio file whose timecode range overlaps
    with the video's timecode range. The sync offset is the difference
    between their start timecodes.

    Args:
        video_files: List of probed video MediaFile objects.
        audio_files: List of probed audio MediaFile objects.
        tolerance_seconds: Max gap between TC ranges to still consider a match.
        progress_callback: Optional callable(step, total, message).

    Returns:
        List of SyncMatch results.
    """
    total_steps = len(video_files) * len(audio_files)
    step = 0

    def _progress(msg: str):
        nonlocal step
        step += 1
        if progress_callback:
            progress_callback(step, total_steps, msg)

    # Filter to files that have timecode
    tc_videos = [v for v in video_files if v.timecode is not None]
    tc_audios = [a for a in audio_files if a.timecode is not None]

    if not tc_videos:
        raise ValueError(
            "No video files have embedded timecode. "
            "Ensure your camera is recording timecode to the file metadata."
        )
    if not tc_audios:
        raise ValueError(
            "No audio files have embedded timecode. "
            "Ensure your audio recorder is writing timecode (BWF/WAV with TC)."
        )

    matches = []
    used_audio = set()  # track which audio files are already matched

    for v in tc_videos:
        v_start = v.timecode.to_seconds()
        v_end = v_start + v.duration

        best_audio = None
        best_overlap = -1.0

        for a in tc_audios:
            _progress(f"Comparing {v.path.name} <-> {a.path.name}")

            if id(a) in used_audio:
                continue

            a_start = a.timecode.to_seconds()
            a_end = a_start + a.duration

            # Check for overlap (with tolerance)
            overlap_start = max(v_start, a_start)
            overlap_end = min(v_end, a_end)
            overlap = overlap_end - overlap_start

            if overlap >= -tolerance_seconds:
                # They overlap (or are within tolerance)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_audio = a

        if best_audio is not None:
            # Offset = how much the audio TC is ahead of the video TC
            # Positive: audio started before video (audio leads)
            # Negative: audio started after video (audio trails)
            offset = v.timecode.to_seconds() - best_audio.timecode.to_seconds()

            matches.append(SyncMatch(
                video=v,
                audio=best_audio,
                offset_seconds=offset,
            ))
            used_audio.add(id(best_audio))

    # Sort by video filename
    matches.sort(key=lambda m: m.video.path.name)

    return matches
