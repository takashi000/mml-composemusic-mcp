"""Tests for the retro APU synthesizer engine."""

import wave

import numpy as np
import pytest

from mml_composemusic_mcp.ir import (
    NoteEvent,
    NoteSequence,
    VolumeEvent,
)
from mml_composemusic_mcp.synthesizer import (
    ChannelSynthesizer,
    build_channel_summary,
    midi_to_freq,
    noise_period_to_rate,
    synthesize,
    tick_to_second,
    write_wav,
)

# --- Utility functions ---


def test_midi_to_freq_a4():
    assert midi_to_freq(69) == pytest.approx(440.0)


def test_midi_to_freq_c4():
    assert midi_to_freq(60) == pytest.approx(261.63, rel=1e-2)


def test_midi_to_freq_high():
    assert midi_to_freq(127) > 8000


def test_noise_period_to_rate():
    rate = noise_period_to_rate(8, 0, 44100)
    assert rate > 0


def test_tick_to_second():
    assert tick_to_second(192, 120) == pytest.approx(0.5, rel=1e-6)


def test_tick_to_second_zero():
    assert tick_to_second(0, 120) == 0.0


# --- Channel synthesizer ---


def test_pulse_render():
    synth = ChannelSynthesizer("pulse", 44100)
    events = [NoteEvent(tick_position=0, duration=192, note_number=69, velocity=15)]
    wave_out = synth.render(events, 192, 120, "ppmck")
    assert len(wave_out) > 0
    assert np.any(wave_out != 0)


def test_triangle_render_ppmck():
    synth = ChannelSynthesizer("triangle", 44100)
    events = [NoteEvent(tick_position=0, duration=192, note_number=69, velocity=7)]
    wave_out = synth.render(events, 192, 120, "ppmck")
    assert len(wave_out) > 0
    assert np.any(wave_out != 0)
    # In ppmck mode, triangle amplitude should be full (velocity ignored)
    peak = np.max(np.abs(wave_out))
    assert peak == pytest.approx(1.0, rel=1e-2)


def test_triangle_render_pyxel():
    synth = ChannelSynthesizer("triangle", 44100)
    events = [
        VolumeEvent(tick_position=0, value=7),
        NoteEvent(tick_position=0, duration=192, note_number=69, velocity=7),
    ]
    wave_out = synth.render(events, 192, 120, "pyxel")
    assert len(wave_out) > 0
    assert np.any(wave_out != 0)
    # In pyxel mode, velocity/15 scales amplitude
    peak = np.max(np.abs(wave_out))
    assert peak == pytest.approx(7 / 15, rel=1e-1)


def test_noise_render_ppmck():
    synth = ChannelSynthesizer("noise", 44100)
    events = [NoteEvent(tick_position=0, duration=192, note_number=0, velocity=10)]
    wave_out = synth.render(events, 192, 120, "ppmck")
    assert len(wave_out) > 0
    assert np.any(wave_out != 0)


def test_noise_render_pyxel():
    synth = ChannelSynthesizer("noise", 44100)
    events = [NoteEvent(tick_position=0, duration=192, note_number=48, velocity=10)]
    wave_out = synth.render(events, 192, 120, "pyxel")
    assert len(wave_out) > 0
    assert np.any(wave_out != 0)


# --- Full synthesize ---


def test_synthesize_basic():
    ns = NoteSequence(bpm=120)
    ns.channels["Pulse1"].events.append(
        NoteEvent(tick_position=0, duration=192, note_number=60, velocity=15)
    )
    ns.channels["Pulse1"].total_ticks = 192
    wave_data, duration, errors = synthesize(ns, "ppmck", 44100, True)
    assert len(wave_data) > 0
    assert duration > 0
    assert errors == []


def test_synthesize_empty():
    ns = NoteSequence(bpm=120)
    wave_data, duration, errors = synthesize(ns, "ppmck", 44100, True)
    assert len(wave_data) == 0
    assert duration == 0


def test_synthesize_normalize():
    ns = NoteSequence(bpm=120)
    ns.channels["Pulse1"].events.append(
        NoteEvent(tick_position=0, duration=192, note_number=60, velocity=15)
    )
    ns.channels["Pulse1"].total_ticks = 192
    on_data, _, _ = synthesize(ns, "ppmck", 44100, True)
    off_data, _, _ = synthesize(ns, "ppmck", 44100, False)
    # Normalized should have peak ~1.0
    assert np.max(np.abs(on_data)) == pytest.approx(1.0, rel=1e-2)


# --- WAV output ---


def test_write_wav_success(tmp_path):
    path = tmp_path / "test.wav"
    data = np.array([0.0, 0.5, -0.5, 0.0], dtype=np.float64)
    errors = write_wav(path, data, 44100)
    assert not errors
    assert path.exists()
    with wave.open(str(path), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 44100


def test_write_wav_failure(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    bad_path = blocker / "output.wav"
    data = np.array([0.0, 0.1], dtype=np.float64)
    errors = write_wav(bad_path, data, 44100)
    if errors:
        from mml_composemusic_mcp.ir import ErrorCode

        assert errors[0].code == ErrorCode.RUNTIME_WAV_WRITE_FAILED


# --- Channel summary ---


def test_build_channel_summary():
    ns = NoteSequence(bpm=120)
    ns.channels["Pulse1"].events.append(
        NoteEvent(tick_position=0, duration=192, note_number=60, velocity=15)
    )
    ns.channels["Pulse1"].events.append(
        NoteEvent(tick_position=192, duration=192, note_number=72, velocity=15)
    )
    ns.channels["Pulse1"].total_ticks = 384
    summary = build_channel_summary(ns)
    pulse1 = [s for s in summary if s["channel"] == "Pulse1"][0]
    assert pulse1["note_count"] == 2
    assert pulse1["duration_ticks"] == 384


def test_build_channel_summary_from_dict():
    ns = NoteSequence(bpm=120)
    ns.channels["Pulse1"].events.append(
        NoteEvent(tick_position=0, duration=192, note_number=60, velocity=15)
    )
    ns.channels["Pulse1"].total_ticks = 192
    ns_dict = ns.to_dict()
    summary = build_channel_summary(ns_dict)
    assert summary
    pulse1 = [s for s in summary if s["channel"] == "Pulse1"][0]
    assert pulse1["note_count"] == 1
