"""FCPXML generator for creating synchronized clips."""

import hashlib
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

from .sync_engine import SyncMatch


# FCPXML version - using 1.11 for broad compatibility
FCPXML_VERSION = "1.11"


def _seconds_to_rational(seconds: float, timebase: int = 1000) -> str:
    """Convert seconds to FCPXML rational time string.

    FCPXML uses rational time like '52840/1000s' meaning 52.84 seconds.
    """
    frac = Fraction(seconds).limit_denominator(timebase * 100)
    return f"{frac.numerator}/{frac.denominator}s"


def _duration_rational(seconds: float, fps_num: int, fps_den: int) -> str:
    """Convert duration to frame-aligned rational time."""
    frame_duration = Fraction(fps_den, fps_num)
    duration = Fraction(seconds).limit_denominator(100000)
    # Round to nearest frame
    frames = round(duration / frame_duration)
    result = frames * frame_duration
    return f"{result.numerator}/{result.denominator}s"


def _tc_rational(tc, fps_num: int, fps_den: int) -> str:
    """Convert a Timecode to frame-aligned rational time for FCPXML."""
    if tc is None:
        return "0/1s"
    frame_duration = Fraction(fps_den, fps_num)
    total_seconds = Fraction(tc.to_seconds()).limit_denominator(100000)
    frames = round(total_seconds / frame_duration)
    result = frames * frame_duration
    return f"{result.numerator}/{result.denominator}s"


def _tc_sample_rational(tc, sample_rate: int) -> str:
    """Convert a Timecode to sample-accurate rational time for audio assets."""
    if tc is None:
        return "0/1s"
    total_seconds = Fraction(tc.to_seconds()).limit_denominator(100000)
    samples = round(total_seconds * sample_rate)
    return f"{samples}/{sample_rate}s"


def _duration_sample_rational(seconds: float, sample_rate: int) -> str:
    """Convert duration to sample-accurate rational time for audio."""
    dur = Fraction(seconds).limit_denominator(100000)
    samples = round(dur * sample_rate)
    return f"{samples}/{sample_rate}s"


def _make_asset_id(path: Path) -> str:
    """Generate a deterministic asset ID from file path."""
    h = hashlib.md5(str(path.resolve()).encode()).hexdigest()[:8]
    return f"r{h}"


def _file_url(path: Path) -> str:
    """Convert a file path to a file:// URL."""
    resolved = path.resolve()
    return f"file://{quote(str(resolved))}"


def generate_fcpxml(
    matches: list,
    event_name: str = "Synced Clips",
) -> str:
    """Generate an FCPXML document with synchronized clips.

    Creates an FCPXML file with one sync-clip per matched video/audio pair.
    The structure mirrors what FCP itself generates when creating synchronized
    clips: spine contains a gap (with audio at lane -1) followed by the video
    asset-clip.

    Args:
        matches: List of SyncMatch results from the sync engine.
        event_name: Name for the FCPX event.

    Returns:
        FCPXML document as a string.
    """
    # Root element
    fcpxml = ET.Element("fcpxml", version=FCPXML_VERSION)

    # Resources section
    resources = ET.SubElement(fcpxml, "resources")

    # Collect format and asset info for each file
    format_ids = {}  # key -> format_id
    asset_map = {}   # path -> asset_id

    format_counter = 0

    for match in matches:
        v = match.video
        a = match.audio

        # --- Video format ---
        format_key = (v.width, v.height, v.fps_num, v.fps_den)
        if format_key not in format_ids:
            format_counter += 1
            fmt_id = f"r{format_counter}"
            format_ids[format_key] = fmt_id

            # Use fps_den*100 / fps_num but keep large denominator (don't reduce)
            # FCP expects 100/2400s for 24fps, not simplified 25/6s
            frame_dur_num = v.fps_den * 100
            frame_dur_den = v.fps_num * 100
            frame_dur_str = f"{frame_dur_num}/{frame_dur_den}s"
            ET.SubElement(resources, "format", {
                "id": fmt_id,
                "frameDuration": frame_dur_str,
                "width": str(v.width),
                "height": str(v.height),
            })

        v_fmt_id = format_ids[format_key]

        # --- Video asset ---
        v_asset_id = _make_asset_id(v.path)
        if v.path not in asset_map:
            v_tc_start = _tc_rational(v.timecode, v.fps_num, v.fps_den)
            v_dur_rat = _duration_rational(v.duration, v.fps_num, v.fps_den)
            v_attrs = {
                "id": v_asset_id,
                "name": v.path.stem,
                "start": v_tc_start,
                "duration": v_dur_rat,
                "hasVideo": "1",
                "format": v_fmt_id,
            }
            if v.has_audio:
                v_attrs["hasAudio"] = "1"
                v_attrs["audioSources"] = "1"
                v_attrs["audioChannels"] = str(v.channels)
                v_attrs["audioRate"] = str(v.sample_rate)
            v_asset_el = ET.SubElement(resources, "asset", v_attrs)
            ET.SubElement(v_asset_el, "media-rep", {
                "kind": "original-media",
                "src": _file_url(v.path),
            })
            asset_map[v.path] = v_asset_id

        # --- Audio clip format (FCP uses a default video format for the clip timeline) ---
        a_clip_fmt_key = ("audio_clip", v.fps_num, v.fps_den)
        if a_clip_fmt_key not in format_ids:
            format_counter += 1
            a_clip_fmt_id = f"r{format_counter}"
            format_ids[a_clip_fmt_key] = a_clip_fmt_id
            frame_dur_num = v.fps_den * 100
            frame_dur_den = v.fps_num * 100
            ET.SubElement(resources, "format", {
                "id": a_clip_fmt_id,
                "name": "FFVideoFormat720p24",
                "frameDuration": f"{frame_dur_num}/{frame_dur_den}s",
                "width": "1280",
                "height": "720",
            })

        # --- Audio asset (sample-rate timing, no format ref — matches FCP) ---
        a_asset_id = _make_asset_id(a.path)
        if a.path not in asset_map:
            a_tc_start = _tc_sample_rational(a.timecode, a.sample_rate)
            a_dur_str = f"{round(a.duration)}s"
            a_asset_el = ET.SubElement(resources, "asset", {
                "id": a_asset_id,
                "name": a.path.stem,
                "start": a_tc_start,
                "duration": a_dur_str,
                "hasAudio": "1",
                "audioSources": "1",
                "audioChannels": str(a.channels),
                "audioRate": str(a.sample_rate),
            })
            ET.SubElement(a_asset_el, "media-rep", {
                "kind": "original-media",
                "src": _file_url(a.path),
            })
            asset_map[a.path] = a_asset_id

    # Library > Event structure
    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", name=event_name)

    for match in matches:
        v = match.video
        a = match.audio
        v_asset_id = asset_map[v.path]
        a_asset_id = asset_map[a.path]

        v_fmt_id = format_ids[(v.width, v.height, v.fps_num, v.fps_den)]
        a_clip_fmt_id = format_ids[("audio_clip", v.fps_num, v.fps_den)]
        clip_name = f"{v.path.stem} - Synced"

        # Compute timecodes
        v_tc_secs = Fraction(v.timecode.to_seconds()).limit_denominator(100000)
        a_tc_secs = Fraction(a.timecode.to_seconds()).limit_denominator(100000)
        a_dur = Fraction(round(a.duration))

        # Frame-aligned video times
        frame_duration = Fraction(v.fps_den, v.fps_num)
        v_frames = round(v_tc_secs / frame_duration)
        v_start_frac = v_frames * frame_duration
        v_start_rat = f"{v_start_frac.numerator}/{v_start_frac.denominator}s"

        v_dur_frames = round(Fraction(v.duration).limit_denominator(100000) / frame_duration)
        v_dur_frac = v_dur_frames * frame_duration
        v_dur_rat = f"{v_dur_frac.numerator}/{v_dur_frac.denominator}s"

        # Audio sample-accurate start
        a_start_samples = round(a_tc_secs * a.sample_rate)
        a_start_rat = f"{a_start_samples}/{a.sample_rate}s"
        a_dur_str = f"{round(a.duration)}s"

        # Sync-clip starts at audio TC (which is typically earlier)
        # and its duration covers the full audio
        sync_start = f"{int(round(float(a_tc_secs)))}s"
        sync_dur = a_dur_str

        # Gap fills time between audio start and video start
        gap_dur_secs = v_start_frac - Fraction(int(round(float(a_tc_secs))))
        if gap_dur_secs < 0:
            gap_dur_secs = Fraction(0)
        # Frame-align the gap
        gap_frames = round(gap_dur_secs / frame_duration)
        gap_dur_frac = gap_frames * frame_duration
        gap_dur_rat = f"{gap_dur_frac.numerator}/{gap_dur_frac.denominator}s"

        # Create the sync-clip (mirrors FCP's own export structure)
        sync_clip = ET.SubElement(event, "sync-clip", {
            "name": clip_name,
            "start": sync_start,
            "duration": sync_dur,
            "format": v_fmt_id,
            "tcFormat": "NDF",
        })

        # Spine: gap (with audio inside) → video
        spine = ET.SubElement(sync_clip, "spine")

        # Gap element — fills time before video starts
        gap_offset = sync_start
        gap = ET.SubElement(spine, "gap", {
            "name": "Gap",
            "offset": gap_offset,
            "start": "3600s",
            "duration": gap_dur_rat,
        })

        # Audio clip inside gap at lane -1
        audio_clip = ET.SubElement(gap, "clip", {
            "lane": "-1",
            "offset": "3600s",
            "name": a.path.stem,
            "start": a_start_rat,
            "duration": a_dur_str,
            "format": a_clip_fmt_id,
            "tcFormat": "NDF",
        })

        # Audio element referencing the audio asset
        # srcCh="1" tells FCP to use channel 1 (typically the mix channel)
        ET.SubElement(audio_clip, "audio", {
            "ref": a_asset_id,
            "offset": a_start_rat,
            "start": a_start_rat,
            "duration": a_dur_str,
            "role": "dialogue",
            "srcCh": "1",
        })

        # Video asset-clip follows the gap in the spine
        ET.SubElement(spine, "asset-clip", {
            "ref": v_asset_id,
            "offset": v_start_rat,
            "name": v.path.stem,
            "start": v_start_rat,
            "duration": v_dur_rat,
            "tcFormat": "NDF",
        })

    # Serialize to string with XML declaration and DOCTYPE
    ET.indent(fcpxml, space="  ")
    xml_str = ET.tostring(fcpxml, encoding="unicode", xml_declaration=False)

    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype = '<!DOCTYPE fcpxml>\n'

    return header + doctype + xml_str + "\n"
