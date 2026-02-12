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
    The sync-clip combines the video with the external audio at the correct
    timecode offset.

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
    format_ids = {}  # (width, height, fps_num, fps_den) -> format_id
    asset_map = {}   # path -> (asset_id, format_id_or_none, duration_rational, tc_start_rational)

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

            frame_dur = _seconds_to_rational(v.fps_den / v.fps_num)
            fps_label = v.fps_num // v.fps_den if v.fps_den == 1 else round(v.fps_num / v.fps_den * 100) / 100
            ET.SubElement(resources, "format", {
                "id": fmt_id,
                "name": f"FFVideoFormat{v.height}p{fps_label}",
                "frameDuration": frame_dur,
                "width": str(v.width),
                "height": str(v.height),
            })

        v_fmt_id = format_ids[format_key]
        v_dur_rat = _duration_rational(v.duration, v.fps_num, v.fps_den)
        v_tc_start = _tc_rational(v.timecode, v.fps_num, v.fps_den)

        # --- Video asset ---
        v_asset_id = _make_asset_id(v.path)
        if v.path not in asset_map:
            v_attrs = {
                "id": v_asset_id,
                "name": v.path.stem,
                "start": v_tc_start,
                "duration": v_dur_rat,
                "format": v_fmt_id,
                "hasVideo": "1",
                "hasAudio": "1" if v.has_audio else "0",
            }
            if v.has_audio:
                v_attrs["audioSources"] = "1"
                v_attrs["audioChannels"] = str(v.channels)
                v_attrs["audioRate"] = str(v.sample_rate)
            v_asset_el = ET.SubElement(resources, "asset", v_attrs)
            ET.SubElement(v_asset_el, "media-rep", {
                "kind": "original-media",
                "src": _file_url(v.path),
            })
            asset_map[v.path] = (v_asset_id, v_fmt_id, v_dur_rat, v_tc_start)

        # --- Audio asset ---
        a_dur_rat = _seconds_to_rational(a.duration)
        a_tc_start = _tc_rational(a.timecode, v.fps_num, v.fps_den)

        a_asset_id = _make_asset_id(a.path)
        if a.path not in asset_map:
            a_asset_el = ET.SubElement(resources, "asset", {
                "id": a_asset_id,
                "name": a.path.stem,
                "start": a_tc_start,
                "duration": a_dur_rat,
                "hasAudio": "1",
                "audioSources": "1",
                "audioChannels": str(a.channels),
                "audioRate": str(a.sample_rate),
            })
            ET.SubElement(a_asset_el, "media-rep", {
                "kind": "original-media",
                "src": _file_url(a.path),
            })
            asset_map[a.path] = (a_asset_id, None, a_dur_rat, a_tc_start)

    # Library > Event structure
    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", name=event_name)

    for match in matches:
        v = match.video
        a = match.audio
        v_asset_id, v_fmt_id, v_dur_rat, v_tc_start = asset_map[v.path]
        a_asset_id, a_fmt_id, a_dur_rat, a_tc_start = asset_map[a.path]

        clip_name = f"{v.path.stem} - Synced"
        sync_dur = _duration_rational(v.duration, v.fps_num, v.fps_den)

        v_tc_secs = v.timecode.to_seconds()
        a_tc_secs = a.timecode.to_seconds()

        # Create the sync-clip
        sync_clip = ET.SubElement(event, "sync-clip", {
            "name": clip_name,
            "offset": "0/1s",
            "start": v_tc_start,
            "duration": sync_dur,
            "format": v_fmt_id,
            "tcFormat": "NDF",
        })

        # Video asset-clip inside a spine (primary storyline)
        spine = ET.SubElement(sync_clip, "spine")

        v_clip_attrs = {
            "ref": v_asset_id,
            "name": v.path.stem,
            "offset": v_tc_start,
            "start": v_tc_start,
            "duration": v_dur_rat,
            "format": v_fmt_id,
            "tcFormat": "NDF",
        }
        if v.has_audio:
            v_clip_attrs["audioRole"] = "dialogue"
        ET.SubElement(spine, "asset-clip", v_clip_attrs)

        # Audio asset-clip as a connected clip (lane 1)
        # Sync point = max(video_tc, audio_tc) — works for both cases:
        #   Audio leads: skip into audio to where video starts
        #   Video leads: delay audio to where it actually starts
        sync_point_secs = max(v_tc_secs, a_tc_secs)
        frame_duration = Fraction(v.fps_den, v.fps_num)
        sync_point_frac = Fraction(sync_point_secs).limit_denominator(100000)
        sync_point_frames = round(sync_point_frac / frame_duration)
        sync_point_result = sync_point_frames * frame_duration
        sync_point_rat = f"{sync_point_result.numerator}/{sync_point_result.denominator}s"

        ET.SubElement(sync_clip, "asset-clip", {
            "ref": a_asset_id,
            "lane": "1",
            "name": a.path.stem,
            "offset": sync_point_rat,
            "start": sync_point_rat,
            "duration": a_dur_rat,
            "audioRole": "dialogue",
            "tcFormat": "NDF",
        })

    # Serialize to string with XML declaration and DOCTYPE
    ET.indent(fcpxml, space="  ")
    xml_str = ET.tostring(fcpxml, encoding="unicode", xml_declaration=False)

    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype = '<!DOCTYPE fcpxml>\n'

    return header + doctype + xml_str + "\n"
