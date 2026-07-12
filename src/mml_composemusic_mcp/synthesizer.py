"""Deterministic, minimal NTSC 2A03 synthesizer: NoteSequence -> WAV."""

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .ir import (
    DetuneEvent,
    DutyEnvelopeEvent,
    DutyEvent,
    EnvelopeEvent,
    ErrorCode,
    ErrorDetail,
    ErrorPhase,
    GlideEvent,
    LfoEvent,
    NoteEnvEvent,
    NoteEvent,
    NoteSequence,
    PitchEnvEvent,
    RelativeVolumeEvent,
    RestEvent,
    SweepEvent,
    TempoEvent,
    VibratoEvent,
    VolumeEnvelopeEvent,
    VolumeEvent,
)

CPU_CLOCK = 1_789_772.5
SAMPLE_RATE_DEFAULT = 44100
ENVELOPE_STEP_TICKS = 48
NOISE_PERIODS = (
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
PULSE_SEQUENCES = (
    (0, 1, 0, 0, 0, 0, 0, 0),
    (0, 1, 1, 0, 0, 0, 0, 0),
    (0, 1, 1, 1, 1, 0, 0, 0),
    (1, 0, 0, 1, 1, 1, 1, 1),
)
TRIANGLE_SEQUENCE = (
    15,
    14,
    13,
    12,
    11,
    10,
    9,
    8,
    7,
    6,
    5,
    4,
    3,
    2,
    1,
    0,
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
)


def midi_to_freq(note_number: float) -> float:
    return 440.0 * 2.0 ** ((note_number - 69.0) / 12.0)


def frequency_to_timer(frequency: float, channel_type: str) -> int:
    divider = 16.0 if channel_type == "pulse" else 32.0
    if frequency <= 0:
        return 0x7FF
    return max(0, min(0x7FF, round(CPU_CLOCK / (divider * frequency) - 1.0)))


def timer_to_frequency(timer: int, channel_type: str) -> float:
    divider = 16.0 if channel_type == "pulse" else 32.0
    return CPU_CLOCK / (divider * (timer + 1))


def noise_period_to_rate(
    period: int, mode: int = 0, sample_rate: int = SAMPLE_RATE_DEFAULT
) -> float:
    del mode, sample_rate
    return CPU_CLOCK / NOISE_PERIODS[period & 0x0F]


def apu_mix(
    pulse1: np.ndarray, pulse2: np.ndarray, triangle: np.ndarray, noise: np.ndarray
) -> np.ndarray:
    pulse_sum = pulse1 + pulse2
    pulse_out = np.zeros_like(pulse_sum, dtype=np.float64)
    mask = pulse_sum > 0
    pulse_out[mask] = 95.88 / (8128.0 / pulse_sum[mask] + 100.0)
    tnd_input = triangle / 8227.0 + noise / 12241.0
    tnd_out = np.zeros_like(tnd_input, dtype=np.float64)
    mask = tnd_input > 0
    tnd_out[mask] = 159.79 / (1.0 / tnd_input[mask] + 100.0)
    return pulse_out + tnd_out


@dataclass
class TempoMap:
    events: list[tuple[int, int]]
    ticks_per_quarter: int = 192

    def tick_to_second(self, tick: float) -> float:
        elapsed = 0.0
        previous_tick = 0
        bpm = self.events[0][1]
        for event_tick, event_bpm in self.events[1:]:
            if tick <= event_tick:
                break
            elapsed += (
                (event_tick - previous_tick) * 60.0 / (bpm * self.ticks_per_quarter)
            )
            previous_tick, bpm = event_tick, event_bpm
        return elapsed + (tick - previous_tick) * 60.0 / (bpm * self.ticks_per_quarter)

    def seconds_to_ticks(self, seconds: np.ndarray) -> np.ndarray:
        result = np.empty_like(seconds)
        segment_seconds = 0.0
        for index, (start_tick, bpm) in enumerate(self.events):
            end_tick = (
                self.events[index + 1][0] if index + 1 < len(self.events) else None
            )
            end_seconds = (
                (
                    segment_seconds
                    + (end_tick - start_tick) * 60.0 / (bpm * self.ticks_per_quarter)
                )
                if end_tick is not None
                else np.inf
            )
            mask = (seconds >= segment_seconds) & (seconds < end_seconds)
            result[mask] = (
                start_tick
                + (seconds[mask] - segment_seconds)
                * bpm
                * self.ticks_per_quarter
                / 60.0
            )
            segment_seconds = end_seconds
        return result


def build_tempo_map(note_sequence: NoteSequence) -> TempoMap:
    changes = {0: note_sequence.bpm}
    for channel in note_sequence.channels.values():
        for event in channel.events:
            if isinstance(event, TempoEvent):
                changes[event.tick_position] = event.bpm
    return TempoMap(sorted(changes.items()), note_sequence.ticks_per_quarter)


def tick_to_second(tick: int, bpm: int, ticks_per_quarter: int = 192) -> float:
    return tick * 60.0 / (bpm * ticks_per_quarter)


def _sequence_value(
    definition: dict | None, elapsed_ticks: float, default: float
) -> float:
    if not definition:
        return default
    head = list(definition.get("points", []))
    loop = list(definition.get("loop_points", []))
    values = head + loop
    if not values:
        return default
    index = max(0, int(elapsed_ticks // ENVELOPE_STEP_TICKS))
    if index < len(values):
        return values[index]
    if loop:
        return loop[(index - len(head)) % len(loop)]
    return values[-1]


def _triangle_lfo(elapsed: float, delay: float, period: float, depth: float) -> float:
    if elapsed < delay or period <= 0:
        return 0.0
    phase = ((elapsed - delay) / period) % 1.0
    return (1.0 - 4.0 * abs(phase - 0.5)) * depth


def _definition(table: dict, slot: object) -> dict | None:
    return table.get(slot) or table.get(str(slot))


def _pyxel_envelope(points: list[dict], elapsed: float, initial: float) -> float:
    value = initial * 127.0 / 15.0
    remaining = elapsed
    for point in points:
        target = point["target_volume"]
        duration = point["duration_ticks"]
        if duration <= 0:
            value = target
            continue
        if remaining <= duration:
            return round(
                (value + (target - value) * remaining / duration) * 15.0 / 127.0
            )
        value = target
        remaining -= duration
    return round(value * 15.0 / 127.0)


class ChannelSynthesizer:
    def __init__(
        self,
        channel_type: str,
        sample_rate: int = SAMPLE_RATE_DEFAULT,
        channel_name: str = "Pulse1",
        noise_mode: int = 0,
    ) -> None:
        self.channel_type = channel_type
        self.channel_name = channel_name
        self.noise_mode = 1 if noise_mode else 0
        self.sample_rate = sample_rate
        self.wave = np.zeros(0, dtype=np.float64)
        self._triangle_phase = 0.0
        self._noise_lfsr = 1
        self._noise_accumulator = 0.0

    def render(
        self,
        events: list,
        total_ticks: int,
        bpm: int,
        mode: str,
        definitions: dict | None = None,
        tempo_map: TempoMap | None = None,
    ) -> np.ndarray:
        definitions = definitions or {}
        tempo_map = tempo_map or TempoMap([(0, bpm)])
        length = int(tempo_map.tick_to_second(total_ticks) * self.sample_rate)
        self.wave = np.zeros(length, dtype=np.float64)
        if length == 0:
            return self.wave
        seconds = np.arange(length, dtype=np.float64) / self.sample_rate
        ticks = tempo_map.seconds_to_ticks(seconds)
        notes = [e for e in events if isinstance(e, NoteEvent)]
        controls = sorted(
            (
                e
                for e in events
                if not isinstance(e, (NoteEvent, RestEvent, TempoEvent))
            ),
            key=lambda e: e.tick_position,
        )
        for note in notes:
            mask = (ticks >= note.tick_position) & (
                ticks < note.tick_position + note.duration
            )
            if not np.any(mask):
                continue
            local_ticks = ticks[mask] - note.tick_position
            indices = np.flatnonzero(mask)
            self._render_note(indices, local_ticks, note, controls, definitions, mode)
        return self.wave

    def _render_note(
        self,
        indices: np.ndarray,
        local_ticks: np.ndarray,
        note: NoteEvent,
        controls: list,
        definitions: dict,
        mode: str,
    ) -> None:
        active = [e for e in controls if e.tick_position <= note.tick_position]
        volume = (
            note.velocity
            if mode == "ppmck"
            else round(note.velocity * 15 / 127)
            if note.velocity > 15
            else note.velocity
        )
        duty = note.duty
        detune = note.detune_cents
        selections: dict[str, object | None] = {
            "vol": None,
            "duty": None,
            "pitch": None,
            "note": None,
            "lfo": None,
            "env": None,
            "vib": None,
            "glide": None,
        }
        sweep: SweepEvent | None = None
        for event in active:
            if isinstance(event, VolumeEvent):
                volume = event.value
            elif isinstance(event, RelativeVolumeEvent):
                # Semantic analysis already stores the resulting velocity on
                # each note; this event additionally cancels @v selection.
                selections["vol"] = None
            elif isinstance(event, DutyEvent):
                duty = event.value
                selections["duty"] = None
            elif isinstance(event, DetuneEvent):
                detune = event.value
            elif isinstance(event, SweepEvent):
                sweep = event
            elif isinstance(event, VolumeEnvelopeEvent) and not event.is_definition:
                selections["vol"] = event.slot
            elif isinstance(event, DutyEnvelopeEvent) and not event.is_definition:
                selections["duty"] = event.slot
            elif isinstance(event, PitchEnvEvent) and not event.is_definition:
                selections["pitch"] = None if event.is_off else event.slot
            elif isinstance(event, NoteEnvEvent) and not event.is_definition:
                selections["note"] = None if event.is_off else event.slot
            elif isinstance(event, LfoEvent) and not event.is_definition:
                selections["lfo"] = None if event.is_off else event.slot
            elif isinstance(event, EnvelopeEvent):
                selections["env"] = None if event.slot == 0 else event.slot
            elif isinstance(event, VibratoEvent):
                selections["vib"] = None if event.slot == 0 else event.slot
            elif isinstance(event, GlideEvent):
                selections["glide"] = None if event.slot == 0 else event.slot
        vol_values = np.full(len(indices), float(volume))
        duty_values = np.full(len(indices), int(duty))
        cents = np.full(len(indices), float(detune))
        for i, tick in enumerate(local_ticks):
            if selections["vol"] is not None:
                vol_values[i] = _sequence_value(
                    _definition(
                        definitions.get("volume_envelopes", {}), selections["vol"]
                    ),
                    tick,
                    volume,
                )
            if selections["duty"] is not None:
                duty_values[i] = int(
                    _sequence_value(
                        _definition(
                            definitions.get("duty_envelopes", {}), selections["duty"]
                        ),
                        tick,
                        duty,
                    )
                )
            cents[i] += 100.0 * _sequence_value(
                _definition(definitions.get("note_envelopes", {}), selections["note"]),
                tick,
                0,
            )
            cents[i] += _sequence_value(
                _definition(
                    definitions.get("pitch_envelopes", {}), selections["pitch"]
                ),
                tick,
                0,
            )
            lfo = _definition(definitions.get("lfos", {}), selections["lfo"])
            if lfo:
                cents[i] += _triangle_lfo(
                    tick, lfo["delay"], lfo["speed"], lfo["depth"]
                )
            vib = _definition(definitions.get("vibratos", {}), selections["vib"])
            if vib:
                cents[i] += _triangle_lfo(
                    tick,
                    vib.get("delay_ticks", 0),
                    vib.get("period_ticks", 0),
                    vib.get("depth_cents", 0),
                )
            gli = _definition(definitions.get("glides", {}), selections["glide"])
            if gli:
                duration = gli.get("duration_ticks", 0)
                cents[i] += (
                    gli.get("initial_offset_cents", 0) * max(0.0, 1.0 - tick / duration)
                    if duration
                    else 0
                )
            env = _definition(definitions.get("envelopes", {}), selections["env"])
            if env:
                vol_values[i] = _pyxel_envelope(env.get("points", []), tick, volume)
        if self.channel_type == "noise":
            self._render_noise(indices, vol_values, note)
        elif self.channel_type == "triangle":
            self._render_triangle(indices, note, cents)
        else:
            self._render_pulse(indices, note, cents, vol_values, duty_values, sweep)

    def _render_pulse(self, indices, note, cents, volumes, duties, sweep):
        phase = 0.0
        sweep_elapsed = 0.0
        timer = frequency_to_timer(
            midi_to_freq(note.note_number + cents[0] / 100), "pulse"
        )
        for j, output_index in enumerate(indices):
            if sweep and sweep.speed > 0 and sweep.depth != 0:
                sweep_elapsed += 1 / self.sample_rate
                interval = (sweep.speed + 1) / 120.0
                if sweep_elapsed >= interval:
                    shift = abs(sweep.depth)
                    delta = timer >> shift
                    if sweep.depth < 0:
                        timer -= delta + (1 if self.channel_name == "Pulse1" else 0)
                    else:
                        timer += delta
                    sweep_elapsed -= interval
            else:
                timer = frequency_to_timer(
                    midi_to_freq(note.note_number + cents[j] / 100), "pulse"
                )
            target = (
                timer + (timer >> abs(sweep.depth))
                if sweep and sweep.depth > 0
                else timer
            )
            if timer < 8 or target > 0x7FF or timer > 0x7FF:
                self.wave[output_index] = 0
                continue
            phase = (
                phase + timer_to_frequency(timer, "pulse") * 8 / self.sample_rate
            ) % 8
            self.wave[output_index] = PULSE_SEQUENCES[int(duties[j]) & 3][
                int(phase)
            ] * max(0, min(15, volumes[j]))
        gate_index = int(len(indices) * max(0, min(1, note.gate_time)))
        self.wave[indices[gate_index:]] = 0

    def _render_triangle(self, indices, note, cents):
        phase = self._triangle_phase
        for j, output_index in enumerate(indices):
            timer = frequency_to_timer(
                midi_to_freq(note.note_number + cents[j] / 100), "triangle"
            )
            phase = (
                phase + timer_to_frequency(timer, "triangle") * 32 / self.sample_rate
            ) % 32
            self.wave[output_index] = TRIANGLE_SEQUENCE[int(phase)]
        self._triangle_phase = phase
        # The 2A03 holds the current DAC value when gated, rather than forcing zero.
        gate_index = int(len(indices) * max(0, min(1, note.gate_time)))
        if 0 < gate_index < len(indices):
            self.wave[indices[gate_index:]] = self.wave[indices[gate_index - 1]]

    def _render_noise(self, indices, volumes, note):
        period_index = (
            8 if note.note_number == 0 else max(0, min(15, 15 - note.note_number // 8))
        )
        cycles_per_sample = CPU_CLOCK / (NOISE_PERIODS[period_index] * self.sample_rate)
        accumulator = self._noise_accumulator
        lfsr = self._noise_lfsr
        for j, output_index in enumerate(indices):
            accumulator += cycles_per_sample
            for _ in range(int(accumulator)):
                tap = 6 if self.noise_mode else 1
                feedback = (lfsr & 1) ^ ((lfsr >> tap) & 1)
                lfsr = (lfsr >> 1) | (feedback << 14)
            accumulator %= 1.0
            self.wave[output_index] = 0 if lfsr & 1 else max(0, min(15, volumes[j]))
        self._noise_accumulator = accumulator
        self._noise_lfsr = lfsr
        gate_index = int(len(indices) * max(0, min(1, note.gate_time)))
        self.wave[indices[gate_index:]] = 0


def synthesize(
    note_sequence: NoteSequence,
    mode: str,
    sample_rate: int = SAMPLE_RATE_DEFAULT,
    normalize: bool = True,
) -> tuple[np.ndarray, float, list[ErrorDetail]]:
    errors: list[ErrorDetail] = []
    total_ticks = max(
        (ch.total_ticks for ch in note_sequence.channels.values()), default=0
    )
    if total_ticks <= 0:
        return np.zeros(0, dtype=np.float64), 0.0, errors
    tempo_map = build_tempo_map(note_sequence)
    rendered: dict[str, np.ndarray] = {}
    for name, channel in note_sequence.channels.items():
        rendered[name] = ChannelSynthesizer(
            channel.channel_type, sample_rate, name
        ).render(
            channel.events,
            total_ticks,
            note_sequence.bpm,
            mode,
            note_sequence.definitions,
            tempo_map,
        )
    zero = np.zeros(max(map(len, rendered.values())), dtype=np.float64)
    mixed = apu_mix(
        rendered.get("Pulse1", zero),
        rendered.get("Pulse2", zero),
        rendered.get("Triangle", zero),
        rendered.get("Noise", zero),
    )
    if normalize and mixed.size and np.max(np.abs(mixed)) > 0:
        mixed /= np.max(np.abs(mixed))
    mixed = np.clip(mixed, -1, 1)
    return mixed, len(mixed) / sample_rate, errors


def write_wav(path: Path, wave_data: np.ndarray, sample_rate: int) -> list[ErrorDetail]:
    errors: list[ErrorDetail] = []
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pcm = np.int16(np.clip(wave_data * 32767, -32768, 32767))
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm.tobytes())
    except Exception as exc:
        errors.append(
            ErrorDetail(
                code=ErrorCode.RUNTIME_WAV_WRITE_FAILED,
                phase=ErrorPhase.RUNTIME,
                line=0,
                column=0,
                message=f"WAVファイルの出力に失敗しました: {exc}",
                severity="error",
                hint="出力先を確認してください。",
            )
        )
    return errors


def build_channel_summary(note_sequence: NoteSequence | dict) -> list[dict]:
    channels = (
        note_sequence["channels"]
        if isinstance(note_sequence, dict)
        else note_sequence.channels
    )
    summary = []
    for name, channel in channels.items():
        events = channel["events"] if isinstance(channel, dict) else channel.events
        total_ticks = (
            channel["total_ticks"] if isinstance(channel, dict) else channel.total_ticks
        )
        notes = [
            e
            for e in events
            if (
                isinstance(e, NoteEvent)
                or isinstance(e, dict)
                and e.get("type") == "note"
            )
        ]
        numbers = [
            e["note_number"] if isinstance(e, dict) else e.note_number for e in notes
        ]
        octaves = [n // 12 - 1 for n in numbers]
        summary.append(
            {
                "channel": name,
                "note_count": len(notes),
                "octave_range": [min(octaves, default=4), max(octaves, default=4)],
                "duration_ticks": total_ticks,
            }
        )
    return summary
