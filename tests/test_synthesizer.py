"""Tests for the retro APU synthesizer engine."""

import wave

import numpy as np
import pytest

from mml_composemusic_mcp.ir import (
    NoteEvent,
    NoteSequence,
    TempoEvent,
    VolumeEnvelopeEvent,
    VolumeEvent,
)
from mml_composemusic_mcp.synthesizer import (
    NOISE_PERIODS,
    PULSE_SEQUENCES,
    TRIANGLE_SEQUENCE,
    ChannelSynthesizer,
    TempoMap,
    apu_mix,
    build_channel_summary,
    build_tempo_map,
    frequency_to_timer,
    midi_to_freq,
    noise_period_to_rate,
    synthesize,
    tick_to_second,
    timer_to_frequency,
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


def test_ntsc_noise_period_table():
    assert NOISE_PERIODS == (
        4,
        8,
        16,
        32,
        64,
        96,
        128,
        160,
        202,
        254,
        380,
        508,
        762,
        1016,
        2034,
        4068,
    )


def test_apu_step_sequences():
    assert [sum(sequence) for sequence in PULSE_SEQUENCES] == [1, 2, 4, 6]
    assert TRIANGLE_SEQUENCE[:16] == tuple(range(15, -1, -1))
    assert TRIANGLE_SEQUENCE[16:] == tuple(range(16))


def test_timer_quantization_matches_2a03_formula():
    timer = frequency_to_timer(440.0, "pulse")
    assert timer == round(1_789_772.5 / (16 * 440.0) - 1)
    assert timer_to_frequency(timer, "pulse") == pytest.approx(440.0, rel=0.003)


def test_nonlinear_apu_mixer():
    one = np.array([15.0])
    zero = np.array([0.0])
    single = apu_mix(one, zero, zero, zero)[0]
    double = apu_mix(one, one, zero, zero)[0]
    assert 0 < single < double < single * 2


def test_tempo_map_integrates_mid_song_change():
    tempo = TempoMap([(0, 120), (192, 60)])
    assert tempo.tick_to_second(192) == pytest.approx(0.5)
    assert tempo.tick_to_second(384) == pytest.approx(1.5)


def test_note_sequence_tempo_map_keeps_default_before_late_change():
    ns = NoteSequence(bpm=120)
    ns.channels["Pulse1"].events.append(TempoEvent(tick_position=192, bpm=60))
    tempo = build_tempo_map(ns)
    assert tempo.tick_to_second(192) == pytest.approx(0.5)
    assert tempo.tick_to_second(384) == pytest.approx(1.5)


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
    # Raw channel output is the 2A03's four-bit DAC value.
    peak = np.max(np.abs(wave_out))
    assert peak == 15


def test_triangle_render_pyxel():
    synth = ChannelSynthesizer("triangle", 44100)
    events = [
        VolumeEvent(tick_position=0, value=7),
        NoteEvent(tick_position=0, duration=192, note_number=69, velocity=7),
    ]
    wave_out = synth.render(events, 192, 120, "pyxel")
    assert len(wave_out) > 0
    assert np.any(wave_out != 0)
    # Triangle volume is not controlled by the 2A03 DAC.
    peak = np.max(np.abs(wave_out))
    assert peak == 15


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


def test_noise_short_mode_uses_different_lfsr_tap():
    events = [NoteEvent(tick_position=0, duration=192, note_number=48, velocity=15)]
    long_wave = ChannelSynthesizer("noise", 8000, noise_mode=0).render(
        events, 192, 120, "pyxel"
    )
    short_wave = ChannelSynthesizer("noise", 8000, noise_mode=1).render(
        events, 192, 120, "pyxel"
    )
    assert not np.array_equal(long_wave, short_wave)


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


def test_volume_envelope_changes_apu_dac_at_48_ticks():
    definitions = {"volume_envelopes": {1: {"points": [15, 0], "loop_points": []}}}
    events = [
        VolumeEnvelopeEvent(tick_position=0, slot=1),
        NoteEvent(tick_position=0, duration=96, note_number=69, velocity=15),
    ]
    wave_out = ChannelSynthesizer("pulse", 8000).render(
        events, 96, 120, "ppmck", definitions
    )
    midpoint = len(wave_out) // 2
    assert np.max(wave_out[:midpoint]) == 15
    assert np.max(wave_out[midpoint:]) == 0


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
