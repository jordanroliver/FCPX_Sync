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

    @classmethod
    def from_seconds(cls, total_seconds: float, fps: float = 24.0) -> "Timecode":
        """Create a Timecode from a total number of seconds."""
        total = total_seconds
        hours = int(total // 3600)
        total -= hours * 3600
        minutes = int(total // 60)
        total -= minutes * 60
        seconds = int(total)
        fractional = total - seconds
        frames = int(round(fractional * fps))
        # Handle frame overflow
        if frames >= int(round(fps)):
            frames = 0
            seconds += 1
            if seconds >= 60:
                seconds = 0
                minutes += 1
                if minutes >= 60:
                    minutes = 0
                    hours += 1
        return cls(hours=hours, minutes=minutes, seconds=seconds, frames=frames, fps=fps)

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
    """Run ffprobe and return parsed JSON with all metadata."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=duration,tags:stream=codec_type,r_frame_rate,sample_rate,channels,width,height,tags",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _get_frame_timecode(path: Path) -> Optional[str]:
    """Try to read timecode from the first video frame (works for MXF/MOV).

    Some container formats store timecode per-frame rather than in
    stream/format tags. This reads just the first frame to check.
    """
    # Try video stream frame tags
    cmd = [
        "ffprobe", "-v", "error",
        "-read_intervals", "%+#1",
        "-show_entries", "frame_tags=timecode",
        "-select_streams", "v:0",
        "-of", "csv=p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    tc = result.stdout.strip()
    if tc and re.match(r"\d{2}:\d{2}:\d{2}[:;]\d{2}", tc):
        return tc

    # Try data stream packet tags (MXF timecode track)
    cmd = [
        "ffprobe", "-v", "error",
        "-read_intervals", "%+#1",
        "-show_entries", "packet_tags=timecode",
        "-select_streams", "d:0",
        "-of", "csv=p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    tc = result.stdout.strip()
    if tc and re.match(r"\d{2}:\d{2}:\d{2}[:;]\d{2}", tc):
        return tc

    # Try reading the first packet side data from data stream
    cmd = [
        "ffprobe", "-v", "error",
        "-read_intervals", "%+#1",
        "-show_entries", "packet=pts_time",
        "-select_streams", "d:0",
        "-of", "csv=p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # This gives pts_time which is just the timestamp, not TC — skip for now

    return None


def _extract_timecode(probe: dict, path: Path, fps: float, sample_rate: int) -> Optional[str]:
    """Extract timecode string from ffprobe output.

    Checks multiple locations where timecode can be stored:
    1. Stream tags (timecode field)
    2. Format tags (timecode field)
    3. BWF time_reference (sample offset from midnight, common in Sound Devices WAV)
    4. Frame-level timecode (for MXF/MOV containers)
    """
    # 1. Check stream tags
    for stream in probe.get("streams", []):
        tags = stream.get("tags", {})
        tc = tags.get("timecode")
        if tc:
            return tc

    # 2. Check format tags
    fmt_tags = probe.get("format", {}).get("tags", {})
    tc = fmt_tags.get("timecode")
    if tc:
        return tc

    # 3. BWF time_reference (Sound Devices, Zoom, etc.)
    # This is a sample count from midnight — convert to timecode
    time_ref = fmt_tags.get("time_reference")
    if time_ref:
        try:
            samples = int(time_ref)
            if samples > 0 and sample_rate > 0:
                total_seconds = samples / sample_rate
                tc_obj = Timecode.from_seconds(total_seconds, fps=fps)
                return str(tc_obj)
        except (ValueError, ZeroDivisionError):
            pass

    # 4. Frame-level timecode (MXF, MOV containers)
    frame_tc = _get_frame_timecode(path)
    if frame_tc:
        return frame_tc

    return None


def _parse_bwf_fps(probe: dict) -> Optional[float]:
    """Try to extract frame rate from BWF iXML/comment metadata.

    Sound Devices 688 stores speed in the comment tag like:
    sSPEED=024.000-ND (24fps non-drop)
    sSPEED=023.976-ND (23.976 non-drop)
    sSPEED=029.970-DF (29.97 drop-frame)
    """
    fmt_tags = probe.get("format", {}).get("tags", {})
    comment = fmt_tags.get("comment", "")

    match = re.search(r"sSPEED=(\d+\.\d+)", comment)
    if match:
        return float(match.group(1))

    return None


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

    # Determine fps for timecode conversion
    fps_float = fps_num / fps_den if has_video else 24.0

    # For audio-only files, try to get fps from BWF metadata
    if not has_video:
        bwf_fps = _parse_bwf_fps(probe)
        if bwf_fps:
            fps_float = bwf_fps

    # Timecode — try all known locations
    tc_str = _extract_timecode(probe, path, fps=fps_float, sample_rate=sample_rate)
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
    video_files: list,
    audio_files: list,
    *,
    tolerance_seconds: float = 0.5,
    progress_callback=None,
) -> list:
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
        no_tc_names = ", ".join(v.path.name for v in video_files[:5])
        raise ValueError(
            f"No video files have embedded timecode. "
            f"Checked: {no_tc_names}{'...' if len(video_files) > 5 else ''}. "
            f"Ensure your camera is recording timecode to the file metadata, "
            f"or that timecode was preserved during transcoding."
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
