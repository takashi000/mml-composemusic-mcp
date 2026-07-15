"""End-to-end pitch conformance tests for MML and the NTSC 2A03 renderer."""

import math
import wave

import numpy as np
import pytest

from mml_composemusic_mcp.ir import NoteEvent, SweepEvent
from mml_composemusic_mcp.server import _dict_to_note_sequence, _parse_mml
from mml_composemusic_mcp.synthesizer import (
    CPU_CLOCK,
    NOISE_PERIODS,
    ChannelSynthesizer,
    _clock_noise_lfsr,
    _noise_period_index,
    frequency_to_timer,
    midi_to_freq,
    synthesize,
    timer_to_frequency,
    write_wav,
)

PITCH_CASES = (
    ("C4", 60, 427, 213),
    ("C#4", 61, 403, 201),
    ("D4", 62, 380, 189),
    ("D#4", 63, 359, 179),
    ("E4", 64, 338, 169),
    ("F4", 65, 319, 159),
    ("F#4", 66, 301, 150),
    ("G4", 67, 284, 142),
    ("G#4", 68, 268, 134),
    ("A4", 69, 253, 126),
    ("A#4", 70, 239, 119),
    ("B4", 71, 225, 112),
    ("C5", 72, 213, 106),
)

CHROMATIC_MML = {
    "ppmck": "A t120 l4 o4 c c+ d d+ e f f+ g g+ a a+ b > c",
    "pyxel": "0: T120 L4 O4 C C+ D D+ E F F+ G G+ A A+ B > C",
}

OCTAVE_MML = {
    "ppmck": "A t120 l4 o4 c > c < c",
    "pyxel": "0: T120 L4 O4 C > C < C",
}

ENHARMONIC_MML = {
    "ppmck": "A t120 l1 o4 @2 q8 c+ d-",
    "pyxel": "0: T120 L1 O4 V127 Q100 @1 C+ D-",
}

CHANNEL_MML = {
    "ppmck": "A o4 c\nB o4 c\nT o4 c\nN o4 c",
    "pyxel": "0: O4 C\n1: O4 C\n2: O4 @0 C\n3: O4 @3 C",
}

WAV_CASES = (
    ("ppmck", "Pulse1", "A t120 l1 o4 @2 q8 c", 60, "pulse"),
    ("ppmck", "Pulse2", "B t120 l1 o4 @2 q8 a", 69, "pulse"),
    ("ppmck", "Triangle", "T t120 l1 o5 c", 72, "triangle"),
    ("pyxel", "Pulse1", "0: T120 L1 O4 V127 Q100 @1 C", 60, "pulse"),
    ("pyxel", "Pulse2", "1: T120 L1 O4 V127 Q100 @1 A", 69, "pulse"),
    ("pyxel", "Triangle", "2: T120 L1 O5 V127 Q100 @0 C", 72, "triangle"),
)

NOISE_WAV_CASES = (
    ("ppmck", "N t120 l1 v15 c"),
    ("pyxel", "3: T120 L1 O4 V127 Q100 @3 C"),
)

LONG_LFSR_GOLDEN = (
    16384,
    8192,
    4096,
    2048,
    1024,
    512,
    256,
    128,
    64,
    32,
    16,
    8,
    4,
    2,
    16385,
    24576,
)

SHORT_LFSR_GOLDEN = (
    16384,
    8192,
    4096,
    2048,
    1024,
    512,
    256,
    128,
    64,
    16416,
    8208,
    4104,
    2052,
    1026,
    513,
    16640,
)


def compile_mml(source: str, mode: str):  # type: ignore[no-untyped-def]
    data, errors = _parse_mml(source, mode)
    assert not [error for error in errors if error.severity == "error"]
    assert data is not None
    return _dict_to_note_sequence(data), errors


def channel_notes(note_sequence, channel: str) -> list[NoteEvent]:  # type: ignore[no-untyped-def]
    return [
        event
        for event in note_sequence.channels[channel].events
        if isinstance(event, NoteEvent)
    ]


def timer_frequency(timer: int, channel_type: str) -> float:
    divider = 16 if channel_type == "pulse" else 32
    return CPU_CLOCK / (divider * (timer + 1))


def cents_error(measured: float, expected: float) -> float:
    return 1200.0 * math.log2(measured / expected)


def estimate_periodic_frequency(
    samples: np.ndarray, sample_rate: int, trim_seconds: float = 0.05
) -> float:
    """Measure one upward midpoint crossing per pulse/triangle cycle."""
    trim = int(trim_seconds * sample_rate)
    values = np.asarray(samples, dtype=np.float64)
    if trim and len(values) > 2 * trim:
        values = values[trim:-trim]
    threshold = (float(values.max()) + float(values.min())) / 2.0
    high = values >= threshold
    rising = np.flatnonzero((~high[:-1]) & high[1:]) + 1
    if len(rising) < 3:
        raise AssertionError("周波数測定に必要な立ち上がりエッジがありません。")
    elapsed_samples = int(rising[-1] - rising[0])
    cycle_count = len(rising) - 1
    return cycle_count * sample_rate / elapsed_samples


def read_pcm16(path) -> tuple[int, np.ndarray]:  # type: ignore[no-untyped-def]
    with wave.open(str(path), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        sample_rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    return sample_rate, samples.astype(np.float64)


@pytest.mark.parametrize("mode", ("ppmck", "pyxel"))
def test_mml_chromatic_scale_maps_to_midi_60_through_72(mode):
    note_sequence, _ = compile_mml(CHROMATIC_MML[mode], mode)
    assert [
        note.note_number for note in channel_notes(note_sequence, "Pulse1")
    ] == list(range(60, 73))


@pytest.mark.parametrize("mode", ("ppmck", "pyxel"))
def test_mml_relative_octave_sequence_is_c4_c5_c4(mode):
    note_sequence, _ = compile_mml(OCTAVE_MML[mode], mode)
    assert [note.note_number for note in channel_notes(note_sequence, "Pulse1")] == [
        60,
        72,
        60,
    ]


@pytest.mark.parametrize("mode", ("ppmck", "pyxel"))
def test_mml_enharmonic_notes_share_note_number_timer_and_wave(mode):
    note_sequence, _ = compile_mml(ENHARMONIC_MML[mode], mode)
    notes = channel_notes(note_sequence, "Pulse1")
    assert [note.note_number for note in notes] == [61, 61]
    assert frequency_to_timer(midi_to_freq(notes[0].note_number), "pulse") == 403

    waves = []
    for note in notes:
        isolated = NoteEvent(
            tick_position=0,
            duration=768,
            note_number=note.note_number,
            velocity=15,
            duty=2,
            gate_time=1.0,
        )
        waves.append(
            ChannelSynthesizer("pulse", 44100).render([isolated], 768, 120, "ppmck")
        )
    assert np.array_equal(waves[0], waves[1])


@pytest.mark.parametrize("mode", ("ppmck", "pyxel"))
def test_mml_tracks_reach_all_four_ir_channels(mode):
    note_sequence, errors = compile_mml(CHANNEL_MML[mode], mode)
    assert all(channel_notes(note_sequence, name) for name in note_sequence.channels)
    expected_noise_note = 0 if mode == "ppmck" else 60
    assert channel_notes(note_sequence, "Noise")[0].note_number == expected_noise_note
    if mode == "ppmck":
        assert any(error.severity == "warning" for error in errors)


@pytest.mark.parametrize(("name", "midi", "pulse_timer", "triangle_timer"), PITCH_CASES)
def test_midi_notes_match_fixed_2a03_timer_golden_table(
    name, midi, pulse_timer, triangle_timer
):
    del name
    theoretical = 440.0 * 2.0 ** ((midi - 69) / 12.0)
    assert midi_to_freq(midi) == pytest.approx(theoretical, rel=1e-14)
    assert frequency_to_timer(theoretical, "pulse") == pulse_timer
    assert frequency_to_timer(theoretical, "triangle") == triangle_timer


@pytest.mark.parametrize(("name", "midi", "pulse_timer", "triangle_timer"), PITCH_CASES)
def test_timer_inverse_and_cpu_cycle_period_match_2a03_formula(
    name, midi, pulse_timer, triangle_timer
):
    del name, midi
    assert 16 * (pulse_timer + 1) == pytest.approx(
        CPU_CLOCK / timer_frequency(pulse_timer, "pulse")
    )
    assert 32 * (triangle_timer + 1) == pytest.approx(
        CPU_CLOCK / timer_frequency(triangle_timer, "triangle")
    )
    assert timer_to_frequency(pulse_timer, "pulse") == timer_frequency(
        pulse_timer, "pulse"
    )
    assert timer_to_frequency(triangle_timer, "triangle") == timer_frequency(
        triangle_timer, "triangle"
    )


def test_quantized_chromatic_frequencies_are_monotonic_and_octave_aligned():
    for channel_type, timer_index in (("pulse", 2), ("triangle", 3)):
        frequencies = [
            timer_frequency(case[timer_index], channel_type) for case in PITCH_CASES
        ]
        assert frequencies == sorted(frequencies)
        assert cents_error(frequencies[-1], frequencies[0]) == pytest.approx(
            1200.0, abs=0.01
        )


@pytest.mark.parametrize("channel_name", ("Pulse1", "Pulse2"))
@pytest.mark.parametrize(("name", "midi", "pulse_timer", "triangle_timer"), PITCH_CASES)
def test_raw_pulse_pcm_matches_quantized_timer_within_point_one_cent(
    channel_name, name, midi, pulse_timer, triangle_timer
):
    del name, triangle_timer
    note = NoteEvent(
        tick_position=0,
        duration=768,
        note_number=midi,
        velocity=15,
        duty=2,
        gate_time=1.0,
    )
    samples = ChannelSynthesizer("pulse", 44100, channel_name).render(
        [note], 768, 120, "ppmck"
    )
    measured = estimate_periodic_frequency(samples, 44100)
    assert abs(cents_error(measured, timer_frequency(pulse_timer, "pulse"))) <= 0.1


@pytest.mark.parametrize(("name", "midi", "pulse_timer", "triangle_timer"), PITCH_CASES)
def test_raw_triangle_pcm_matches_quantized_timer_within_point_one_cent(
    name, midi, pulse_timer, triangle_timer
):
    del name, pulse_timer
    note = NoteEvent(
        tick_position=0,
        duration=768,
        note_number=midi,
        velocity=15,
        gate_time=1.0,
    )
    samples = ChannelSynthesizer("triangle", 44100, "Triangle").render(
        [note], 768, 120, "ppmck"
    )
    measured = estimate_periodic_frequency(samples, 44100)
    assert (
        abs(cents_error(measured, timer_frequency(triangle_timer, "triangle"))) <= 0.1
    )


@pytest.mark.parametrize("sample_rate", (48000,))
@pytest.mark.parametrize("midi", (60, 69, 72))
@pytest.mark.parametrize(
    ("channel_type", "channel_name", "timer_index"),
    (("pulse", "Pulse1", 2), ("pulse", "Pulse2", 2), ("triangle", "Triangle", 3)),
)
def test_representative_raw_pcm_pitch_at_48khz(
    sample_rate, midi, channel_type, channel_name, timer_index
):
    case = next(case for case in PITCH_CASES if case[1] == midi)
    note = NoteEvent(
        tick_position=0,
        duration=768,
        note_number=midi,
        velocity=15,
        duty=2,
        gate_time=1.0,
    )
    samples = ChannelSynthesizer(channel_type, sample_rate, channel_name).render(
        [note], 768, 120, "ppmck"
    )
    measured = estimate_periodic_frequency(samples, sample_rate)
    assert (
        abs(cents_error(measured, timer_frequency(case[timer_index], channel_type)))
        <= 0.1
    )


def test_pulse_channels_have_identical_50_percent_duty_wave_without_sweep():
    note = NoteEvent(
        tick_position=0,
        duration=768,
        note_number=69,
        velocity=15,
        duty=2,
        gate_time=1.0,
    )
    pulse1 = ChannelSynthesizer("pulse", 44100, "Pulse1").render(
        [note], 768, 120, "ppmck"
    )
    pulse2 = ChannelSynthesizer("pulse", 44100, "Pulse2").render(
        [note], 768, 120, "ppmck"
    )
    assert np.array_equal(pulse1, pulse2)
    assert set(np.unique(pulse1)) == {0.0, 15.0}
    assert np.count_nonzero(pulse1) / len(pulse1) == pytest.approx(0.5, abs=0.01)


@pytest.mark.parametrize("bpm", (60, 120, 240))
def test_tempo_changes_duration_but_not_pulse_pitch(bpm):
    note = NoteEvent(
        tick_position=0,
        duration=768,
        note_number=69,
        velocity=15,
        duty=2,
        gate_time=1.0,
    )
    samples = ChannelSynthesizer("pulse", 44100, "Pulse1").render(
        [note], 768, bpm, "ppmck"
    )
    assert len(samples) == 44100 * 240 // bpm
    measured = estimate_periodic_frequency(samples, 44100)
    assert abs(cents_error(measured, timer_frequency(253, "pulse"))) <= 0.1


@pytest.mark.parametrize(
    ("mode", "channel", "source", "midi", "channel_type"), WAV_CASES
)
def test_mml_to_wav_representative_pitch_within_point_two_five_cent(
    tmp_path, mode, channel, source, midi, channel_type
):
    note_sequence, _ = compile_mml(source, mode)
    assert channel_notes(note_sequence, channel)[0].note_number == midi
    mixed, duration, synth_errors = synthesize(
        note_sequence, mode, sample_rate=44100, normalize=False
    )
    assert not synth_errors
    assert duration == pytest.approx(2.0)
    path = tmp_path / f"{mode}-{channel}.wav"
    assert not write_wav(path, mixed, 44100)
    sample_rate, pcm = read_pcm16(path)
    timer = frequency_to_timer(midi_to_freq(midi), channel_type)
    measured = estimate_periodic_frequency(pcm, sample_rate)
    assert abs(cents_error(measured, timer_frequency(timer, channel_type))) <= 0.25


@pytest.mark.parametrize(("mode", "source"), NOISE_WAV_CASES)
def test_noise_mml_to_wav_is_non_silent_and_deterministic(tmp_path, mode, source):
    note_sequence, _ = compile_mml(source, mode)
    first, duration, errors = synthesize(
        note_sequence, mode, sample_rate=44100, normalize=False
    )
    second, second_duration, second_errors = synthesize(
        note_sequence, mode, sample_rate=44100, normalize=False
    )
    assert not errors and not second_errors
    assert duration == second_duration == pytest.approx(2.0)
    assert np.array_equal(first, second)
    assert np.any(first != 0)

    path = tmp_path / f"{mode}-noise.wav"
    assert not write_wav(path, first, 44100)
    sample_rate, pcm = read_pcm16(path)
    assert sample_rate == 44100
    assert len(pcm) == 88200
    assert np.any(pcm != 0)


def test_ntsc_noise_period_table_and_note_mapping():
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
    assert _noise_period_index(0) == 8
    assert _noise_period_index(1) == 15
    assert _noise_period_index(7) == 15
    assert _noise_period_index(8) == 14
    assert _noise_period_index(60) == 8
    assert _noise_period_index(120) == 0
    assert _noise_period_index(127) == 0


@pytest.mark.parametrize(
    ("short_mode", "golden"),
    ((False, LONG_LFSR_GOLDEN), (True, SHORT_LFSR_GOLDEN)),
)
def test_noise_lfsr_matches_fixed_2a03_state_sequence(short_mode, golden):
    lfsr = 1
    actual = []
    for _ in golden:
        lfsr = _clock_noise_lfsr(lfsr, short_mode)
        actual.append(lfsr)
    assert tuple(actual) == golden


def test_noise_long_and_short_modes_emit_different_pcm():
    note = NoteEvent(
        tick_position=0, duration=768, note_number=60, velocity=15, gate_time=1.0
    )
    long_wave = ChannelSynthesizer("noise", 44100, noise_mode=0).render(
        [note], 768, 120, "pyxel"
    )
    short_wave = ChannelSynthesizer("noise", 44100, noise_mode=1).render(
        [note], 768, 120, "pyxel"
    )
    assert np.any(long_wave != 0)
    assert np.any(short_wave != 0)
    assert not np.array_equal(long_wave, short_wave)


def test_2a03_timer_limits_are_separate_from_conformance_range():
    assert frequency_to_timer(midi_to_freq(12), "pulse") == 0x7FF
    assert frequency_to_timer(midi_to_freq(12), "triangle") == 0x7FF

    too_high = NoteEvent(
        tick_position=0,
        duration=192,
        note_number=128,
        velocity=15,
        duty=2,
        gate_time=1.0,
    )
    high_wave = ChannelSynthesizer("pulse", 44100).render([too_high], 192, 120, "ppmck")
    assert frequency_to_timer(midi_to_freq(128), "pulse") < 8
    assert np.all(high_wave == 0)

    swept_low = NoteEvent(
        tick_position=0,
        duration=192,
        note_number=36,
        velocity=15,
        duty=2,
        gate_time=1.0,
    )
    sweep = SweepEvent(tick_position=0, speed=0, depth=1)
    swept_wave = ChannelSynthesizer("pulse", 44100).render(
        [sweep, swept_low], 192, 120, "ppmck"
    )
    timer = frequency_to_timer(midi_to_freq(36), "pulse")
    assert timer + (timer >> 1) > 0x7FF
    assert np.all(swept_wave == 0)
