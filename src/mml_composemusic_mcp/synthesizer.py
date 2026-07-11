"""Retro APU-style synthesizer: NoteSequence -> WAV."""

import wave
from math import floor
from pathlib import Path

import numpy as np

from .ir import (
    DutyEvent,
    ErrorCode,
    ErrorDetail,
    NoteEvent,
    NoteSequence,
    RestEvent,
    TempoEvent,
    VolumeEvent,
)

CPU_CLOCK = 1_789_772.5
SAMPLE_RATE_DEFAULT = 44100


def midi_to_freq(note_number: int) -> float:
    return 440.0 * 2.0 ** ((note_number - 69) / 12.0)


def noise_period_to_rate(period: int, mode: int, sample_rate: int) -> float:
    # Retro noise: rate = CPU_CLOCK / (NTSC divider for period)
    # Approximate using pyxel mapping described in design
    dividers = [
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
    ]
    div = dividers[period & 0x0F]
    # Long mode (0) vs short mode (1) affects LFSR length, not frequency divider
    return CPU_CLOCK / div


class ChannelSynthesizer:
    def __init__(
        self, channel_type: str, sample_rate: int = SAMPLE_RATE_DEFAULT
    ) -> None:
        self.channel_type = channel_type
        self.sample_rate = sample_rate
        self.wave = np.zeros(0, dtype=np.float64)

    def render(
        self,
        events: list,
        total_ticks: int,
        bpm: int,
        mode: str,
    ) -> np.ndarray:
        seconds = tick_to_second(total_ticks, bpm)
        length = int(seconds * self.sample_rate)
        self.wave = np.zeros(length, dtype=np.float64)
        last_velocity = 15 if self.channel_type != "triangle" else 15
        last_duty = 2
        for event in events:
            if isinstance(event, VolumeEvent):
                last_velocity = event.value
                continue
            if isinstance(event, DutyEvent):
                last_duty = event.value
                continue
            if isinstance(event, TempoEvent):
                bpm = event.bpm
                continue
            if not isinstance(event, (NoteEvent, RestEvent)):
                continue
            start_sample = int(
                tick_to_second(event.tick_position, bpm) * self.sample_rate
            )
            end_tick = event.tick_position + event.duration
            end_sample = min(
                int(tick_to_second(end_tick, bpm) * self.sample_rate), length
            )
            if start_sample >= length or end_sample <= start_sample:
                continue
            if isinstance(event, RestEvent):
                continue
            self._render_note(
                start_sample,
                end_sample,
                event,
                last_velocity,
                last_duty,
                mode,
            )
        return self.wave

    def _render_note(
        self,
        start: int,
        end: int,
        event: NoteEvent,
        velocity: int,
        duty: int,
        mode: str,
    ) -> None:
        duration_samples = end - start
        if duration_samples <= 0:
            return
        if self.channel_type == "noise":
            self._render_noise(start, end, event, velocity, mode)
            return
        if self.channel_type == "triangle":
            self._render_triangle(start, end, event, velocity, mode)
            return
        self._render_pulse(start, end, event, velocity, duty)

    def _render_pulse(
        self,
        start: int,
        end: int,
        event: NoteEvent,
        velocity: int,
        duty: int,
    ) -> None:
        freq = midi_to_freq(event.note_number)
        if freq <= 0:
            return
        phase_inc = freq / self.sample_rate
        duty_cycle = {0: 0.125, 1: 0.25, 2: 0.5, 3: 0.75}.get(duty, 0.5)
        samples = np.arange(end - start)
        phase = (samples * phase_inc) % 1.0
        waveform = np.where(phase < duty_cycle, 1.0, -1.0)
        amp = velocity / 15.0
        gate = max(0.0, min(1.0, event.gate_time))
        if gate < 1.0:
            gate_sample = int((end - start) * gate)
            if gate_sample < len(waveform):
                waveform[gate_sample:] = 0.0
        self.wave[start:end] += waveform * amp

    def _render_triangle(
        self,
        start: int,
        end: int,
        event: NoteEvent,
        velocity: int,
        mode: str,
    ) -> None:
        freq = midi_to_freq(event.note_number)
        if freq <= 0:
            return
        phase_inc = freq / self.sample_rate
        samples = np.arange(end - start)
        phase = (samples * phase_inc) % 1.0
        # 32-step triangle approximated by abs(phase*2-1)
        waveform = 2.0 * np.abs(phase * 2.0 - 1.0) - 1.0
        if mode == "pyxel":
            amp = velocity / 15.0
        else:
            amp = 1.0
        gate = max(0.0, min(1.0, event.gate_time))
        if gate < 1.0:
            gate_sample = int((end - start) * gate)
            if gate_sample < len(waveform):
                waveform[gate_sample:] = 0.0
        self.wave[start:end] += waveform * amp

    def _render_noise(
        self,
        start: int,
        end: int,
        event: NoteEvent,
        velocity: int,
        mode: str,
    ) -> None:
        if mode == "pyxel":
            period = max(0, min(15, 15 - floor(event.note_number / 8)))
            mode_flag = 1 if period >= 13 else 0
        else:
            period = 8
            mode_flag = 0
        rate = noise_period_to_rate(period, mode_flag, self.sample_rate)
        phase_inc = rate / self.sample_rate
        samples = np.arange(end - start)
        phase = (samples * phase_inc) % 1.0
        diff = np.diff(phase, prepend=0)
        transitions = diff < 0
        # LFSR-like pseudo-random toggling on each period rollover
        state = np.zeros(len(samples), dtype=np.int32)
        lfsr = 1
        for i in range(len(samples)):
            if transitions[i]:
                # feedback bit
                if mode_flag:
                    bit = (lfsr ^ (lfsr >> 6)) & 1
                    lfsr = ((lfsr >> 1) | (bit << 14)) & 0x7FFF
                else:
                    bit = (lfsr ^ (lfsr >> 1)) & 1
                    lfsr = ((lfsr >> 1) | (bit << 14)) & 0x7FFF
            state[i] = lfsr & 1
        waveform = np.where(state, 1.0, -1.0)
        amp = velocity / 15.0
        gate = max(0.0, min(1.0, event.gate_time))
        if gate < 1.0:
            gate_sample = int((end - start) * gate)
            if gate_sample < len(waveform):
                waveform[gate_sample:] = 0.0
        self.wave[start:end] += waveform * amp


def tick_to_second(tick: int, bpm: int, ticks_per_quarter: int = 192) -> float:
    quarter_seconds = 60.0 / bpm
    return tick * (quarter_seconds / ticks_per_quarter)


def synthesize(
    note_sequence: NoteSequence,
    mode: str,
    sample_rate: int = SAMPLE_RATE_DEFAULT,
    normalize: bool = True,
) -> tuple[np.ndarray, float, list[ErrorDetail]]:
    errors: list[ErrorDetail] = []
    total_ticks = max(ch.total_ticks for ch in note_sequence.channels.values())
    if total_ticks <= 0:
        return np.zeros(0, dtype=np.float64), 0.0, errors
    channels = []
    for _name, ch in note_sequence.channels.items():
        synth = ChannelSynthesizer(ch.channel_type, sample_rate)
        wave = synth.render(ch.events, total_ticks, note_sequence.bpm, mode)
        channels.append(wave)
    max_len = max(len(w) for w in channels)
    padded = [np.pad(w, (0, max_len - len(w)), mode="constant") for w in channels]
    mixed = np.mean(padded, axis=0)
    peak = np.max(np.abs(mixed))
    if normalize and peak > 0:
        mixed = mixed / peak
    mixed = np.clip(mixed, -1.0, 1.0)
    duration = max_len / sample_rate
    return mixed, duration, errors


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
                code=ErrorCode.SYSTEM_WAV_WRITE_FAILED,
                line=0,
                column=0,
                message=f"WAVファイルの出力に失敗しました: {exc}",
                severity="error",
                hint="しばらく待ってから再度お試しください。",
            )
        )
    return errors


def build_channel_summary(note_sequence: NoteSequence | dict) -> list[dict]:
    if isinstance(note_sequence, dict):
        channels = note_sequence["channels"]
    else:
        channels = note_sequence.channels
    summary = []
    for name, ch in channels.items():
        events = ch["events"] if isinstance(ch, dict) else ch.events
        total_ticks = ch["total_ticks"] if isinstance(ch, dict) else ch.total_ticks
        notes = [e for e in events if isinstance(e, NoteEvent)]
        if not notes:
            notes = [
                e for e in events if isinstance(e, dict) and e.get("type") == "note"
            ]
            octaves = [e["note_number"] // 12 - 1 for e in notes]
        else:
            octaves = [e.note_number // 12 - 1 for e in notes]
        summary.append(
            {
                "channel": name,
                "note_count": len(notes),
                "octave_range": [min(octaves, default=4), max(octaves, default=4)],
                "duration_ticks": total_ticks,
            }
        )
    return summary
