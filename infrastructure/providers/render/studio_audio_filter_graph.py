"""Shared FFmpeg filter-graph builder for SELMA's studio audio master."""
from __future__ import annotations

import math
from typing import Any

from core.domain.value_objects.sound_design_plan import AudioCue, SoundDesignPlan


def build_studio_audio_filters(
    *,
    voice_input_index: int,
    music_input_index: int | None,
    audio_start_seconds: float,
    duration_seconds: float,
    background_music_volume: float,
    sound_design_plan: dict[str, Any] | None,
    legacy_procedural_accents: bool,
) -> list[str]:
    """Return a complete speech-first stereo mix ending at ``[audio]``."""
    plan = (
        SoundDesignPlan.from_dict(sound_design_plan)
        if sound_design_plan is not None
        else _legacy_plan(duration_seconds, legacy_procedural_accents)
    )
    target_lufs = plan.target_integrated_lufs if plan is not None else -14.0
    target_peak = plan.target_true_peak_dbfs if plan is not None else -1.5
    filters: list[str] = []
    voice = (
        f"[{voice_input_index}:a]"
        f"atrim=start={audio_start_seconds:.6f}:duration={duration_seconds:.6f},"
        "asetpts=PTS-STARTPTS,aresample=48000,"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "highpass=f=70,lowpass=f=16500,"
        "acompressor=threshold=0.125:ratio=3:attack=5:release=90:makeup=1.45"
    )
    if music_input_index is None:
        filters.append(f"{voice}[dialogue]")
        base_label = "dialogue"
    else:
        filters.append(f"{voice},asplit=2[dialogue][dialogue_key]")
        fade_out = max(0.0, duration_seconds - 1.2)
        automation = _music_volume_expression(background_music_volume, plan)
        filters.append(
            f"[{music_input_index}:a]atrim=duration={duration_seconds:.6f},"
            "asetpts=PTS-STARTPTS,aresample=48000,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume='{automation}':eval=frame,"
            "afade=t=in:st=0:d=0.6,"
            f"afade=t=out:st={fade_out:.6f}:d=1.2[music_bed]"
        )
        filters.append(
            "[music_bed][dialogue_key]sidechaincompress="
            "threshold=0.025:ratio=10:attack=12:release=420:makeup=1[ducked_music]"
        )
        filters.append(
            "[dialogue][ducked_music]amix=inputs=2:duration=first:"
            "dropout_transition=2:normalize=0[dialogue_music]"
        )
        base_label = "dialogue_music"

    layer_labels: list[str] = [base_label]
    if plan is not None and plan.ambience_profile != "none":
        filters.append(_ambience_filter(plan.ambience_profile, duration_seconds, "ambience"))
        layer_labels.append("ambience")
    if plan is not None:
        for index, cue in enumerate(plan.cues):
            label = f"sfx_{index}"
            filters.append(_cue_filter(cue, label))
            layer_labels.append(label)

    if len(layer_labels) == 1:
        premaster = f"[{layer_labels[0]}]"
    else:
        inputs = "".join(f"[{label}]" for label in layer_labels)
        filters.append(
            f"{inputs}amix=inputs={len(layer_labels)}:duration=first:"
            "dropout_transition=0:normalize=0[premaster]"
        )
        premaster = "[premaster]"
    filters.append(
        f"{premaster}alimiter=limit=0.95:attack=5:release=80,"
        f"loudnorm=I={target_lufs:.1f}:TP={target_peak:.1f}:LRA=9[audio]"
    )
    return filters


def _legacy_plan(duration_seconds: float, enabled: bool) -> SoundDesignPlan | None:
    if not enabled or duration_seconds < 2.0:
        return None
    duration_ms = round(duration_seconds * 1_000)
    payoff_at = max(650, duration_ms - 550)
    return SoundDesignPlan(
        duration_ms=duration_ms,
        ambience_profile="none",
        cues=(
            AudioCue(0, "hook_impact", min(420, duration_ms), -18.0, "Legacy opening accent."),
            AudioCue(payoff_at, "payoff", min(500, duration_ms - payoff_at), -21.0, "Legacy payoff accent."),
        ),
        music_automation=(),
    )


def _music_volume_expression(base_volume: float, plan: SoundDesignPlan | None) -> str:
    points = plan.music_automation if plan is not None else ()
    if not points:
        return f"{base_volume:.6f}"
    expression = f"{base_volume * _db_multiplier(points[-1].relative_gain_db):.6f}"
    for index in range(len(points) - 2, -1, -1):
        start = points[index].timestamp_ms / 1_000
        end = points[index + 1].timestamp_ms / 1_000
        value = base_volume * _db_multiplier(points[index].relative_gain_db)
        expression = f"if(between(t,{start:.3f},{end:.3f}),{value:.6f},{expression})"
    first_value = base_volume * _db_multiplier(points[0].relative_gain_db)
    return f"if(lt(t,{points[0].timestamp_ms / 1_000:.3f}),{first_value:.6f},{expression})"


def _cue_filter(cue: AudioCue, label: str) -> str:
    duration = cue.duration_ms / 1_000
    equations = {
        "hook_impact": "(sin(2*PI*62*t)+0.30*sin(2*PI*124*t))*exp(-10*t)",
        "transition": "sin(2*PI*(220+620*t)*t)*exp(-7*t)",
        "mechanism": "(sin(2*PI*520*t)+0.4*sin(2*PI*760*t))*exp(-9*t)",
        "reveal": "(sin(2*PI*(310+540*t)*t)+0.30*sin(2*PI*930*t))*exp(-4.5*t)",
        "payoff": "(sin(2*PI*740*t)+0.35*sin(2*PI*1110*t))*exp(-7*t)",
        "warning": "(sin(2*PI*88*t)+0.22*sin(2*PI*176*t))*exp(-5*t)",
    }
    return (
        f"aevalsrc='{equations[cue.kind]}':s=48000:d={duration:.3f},"
        f"volume={_db_multiplier(cue.gain_db):.6f},"
        f"afade=t=out:st=0:d={duration:.3f},"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"adelay={cue.timestamp_ms}:all=1[{label}]"
    )


def _ambience_filter(profile: str, duration_seconds: float, label: str) -> str:
    color, highpass, lowpass, volume = {
        "laboratory": ("white", 90, 650, 0.0014),
        "space": ("brown", 45, 420, 0.0018),
        "nature": ("pink", 180, 3200, 0.0012),
        "tension": ("brown", 35, 260, 0.0016),
    }[profile]
    return (
        f"anoisesrc=color={color}:amplitude=1:d={duration_seconds:.6f}:s=48000,"
        f"highpass=f={highpass},lowpass=f={lowpass},volume={volume:.6f},"
        "afade=t=in:st=0:d=0.8,"
        f"afade=t=out:st={max(0.0, duration_seconds - 1.0):.6f}:d=1.0,"
        f"aformat=sample_fmts=fltp:channel_layouts=stereo[{label}]"
    )


def _db_multiplier(gain_db: float) -> float:
    return math.pow(10.0, gain_db / 20.0)
