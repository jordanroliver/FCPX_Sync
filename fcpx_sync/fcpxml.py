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
    asset_map = {}   # path -> (asset_id, format_id, duration_rational)

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

        # --- Video asset ---
        v_asset_id = _make_asset_id(v.path)
        if v.path not in asset_map:
            v_attrs = {
                "id": v_asset_id,
                "name": v.path.stem,
                "start": "0/1s",
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
            asset_map[v.path] = (v_asset_id, v_fmt_id, v_dur_rat)

        # --- Audio format ---
        a_fmt_key = ("audio", a.sample_rate, a.channels)
        if a_fmt_key not in format_ids:
            format_counter += 1
            a_fmt_id = f"r{format_counter}"
            format_ids[a_fmt_key] = a_fmt_id
            ET.SubElement(resources, "format", {
                "id": a_fmt_id,
                "name": "FFAudioFormat",
            })

        a_fmt_id = format_ids[a_fmt_key]
        a_dur_rat = _seconds_to_rational(a.duration)

        # --- Audio asset ---
        a_asset_id = _make_asset_id(a.path)
        if a.path not in asset_map:
            a_asset_el = ET.SubElement(resources, "asset", {
                "id": a_asset_id,
                "name": a.path.stem,
                "start": "0/1s",
                "duration": a_dur_rat,
                "format": a_fmt_id,
                "hasAudio": "1",
                "audioSources": "1",
                "audioChannels": str(a.channels),
                "audioRate": str(a.sample_rate),
            })
            ET.SubElement(a_asset_el, "media-rep", {
                "kind": "original-media",
                "src": _file_url(a.path),
            })
            asset_map[a.path] = (a_asset_id, a_fmt_id, a_dur_rat)

    # Library > Event structure (clips live directly in the event, not a project)
    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", name=event_name)

    for match in matches:
        v = match.video
        a = match.audio
        v_asset_id, v_fmt_id, v_dur_rat = asset_map[v.path]
        a_asset_id, a_fmt_id, a_dur_rat = asset_map[a.path]

        clip_name = f"{v.path.stem} - Synced"

        sync_dur = _duration_rational(v.duration, v.fps_num, v.fps_den)

        # Create the sync-clip
        sync_clip = ET.SubElement(event, "sync-clip", {
            "name": clip_name,
            "start": "0/1s",
            "duration": sync_dur,
            "format": v_fmt_id,
            "tcFormat": "NDF",
        })

        # Video asset-clip (anchor at position 0 in the sync-clip)
        v_clip_attrs = {
            "ref": v_asset_id,
            "name": v.path.stem,
            "offset": "0/1s",
            "start": "0/1s",
            "duration": v_dur_rat,
            "format": v_fmt_id,
            "tcFormat": "NDF",
        }
        if v.has_audio:
            v_clip_attrs["audioRole"] = "dialogue"
        ET.SubElement(sync_clip, "asset-clip", v_clip_attrs)

        # Audio asset-clip positioned by timecode offset
        # offset_seconds = video_tc - audio_tc
        # If positive: audio started before video, so audio's playhead is
        #   already `offset` seconds in when the video starts.
        # If negative: video started before audio, so audio starts later
        #   in the sync-clip timeline.
        offset = match.offset_seconds

        if offset >= 0:
            # Audio started before video — skip into the audio
            audio_offset = "0/1s"
            audio_start = _seconds_to_rational(offset)
        else:
            # Audio started after video — delay audio on the timeline
            audio_offset = _seconds_to_rational(abs(offset))
            audio_start = "0/1s"

        ET.SubElement(sync_clip, "asset-clip", {
            "ref": a_asset_id,
            "name": a.path.stem,
            "offset": audio_offset,
            "start": audio_start,
            "duration": a_dur_rat,
            "audioRole": "dialogue.dialogue-1",
            "tcFormat": "NDF",
        })

        # Sync source to configure audio roles
        sync_source = ET.SubElement(sync_clip, "sync-source", sourceID="storyline")
        ET.SubElement(sync_source, "audio-role-source", {
            "role": "dialogue.dialogue-1",
            "active": "1",
        })

    # Serialize to string with XML declaration and DOCTYPE
    ET.indent(fcpxml, space="  ")
    xml_str = ET.tostring(fcpxml, encoding="unicode", xml_declaration=False)

    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype = '<!DOCTYPE fcpxml>\n'

    return header + doctype + xml_str + "\n"
