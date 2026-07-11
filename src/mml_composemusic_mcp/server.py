# MCP server exposing compose_mml tool.

import argparse
from pathlib import Path

from fastmcp import FastMCP

from .ir import ErrorCode, ErrorDetail, NoteSequence
from .lexer import tokenize
from .parser_ppmck import parse_ppmck
from .parser_pyxel import parse_pyxel
from .synthesizer import build_channel_summary, synthesize, write_wav
from .templates import get_template

mcp = FastMCP("mml-composemusic-mcp")
OUTPUT_DIR = Path("./data")


def _is_error(errors: list[ErrorDetail]) -> bool:
    return any(e.severity == "error" for e in errors)


def _split_errors(errors: list[ErrorDetail]) -> tuple[list[dict], list[dict]]:
    errs = [e.to_dict() for e in errors if e.severity == "error"]
    warns = [e.to_dict() for e in errors if e.severity == "warning"]
    return errs, warns


def _parse_mml(mml: str, mode: str) -> tuple[dict, list[ErrorDetail]]:
    tokens = tokenize(mml, mode)
    if mode == "ppmck":
        note_sequence, errors = parse_ppmck(mml, tokens)
    elif mode == "pyxel":
        note_sequence, errors = parse_pyxel(mml, tokens)
    else:
        errors = [
            ErrorDetail(
                code=ErrorCode.VALIDATION_INVALID_MODE,
                line=0,
                column=0,
                message=f"未知のモード '{mode}' です。",
                severity="error",
                hint="mode は 'ppmck' または 'pyxel' を指定してください。",
            )
        ]
        note_sequence = None
    return (note_sequence.to_dict() if note_sequence else None), errors


@mcp.tool()
def compose_mml(
    action: str,
    mml: str = "",
    mode: str = "",
    template: str = "basic",
    sample_rate: int = 44100,
    normalize: bool = True,
) -> dict:
    """Compose, validate, or generate templates for retro chiptune-style MML."""
    if action == "template":
        if mode not in ("ppmck", "pyxel"):
            mode = "ppmck"
        if template not in ("basic", "melody", "chord", "drum", "empty"):
            template = "basic"
        mml_text, description = get_template(mode, template)
        return {"mml": mml_text, "description": description}

    if action in ("compose", "validate"):
        if not mml or not mode:
            return {
                "success": False,
                "valid": False,
                "note_sequence": None,
                "validation": {
                    "errors": [
                        {
                            "code": ErrorCode.VALIDATION_MISSING_PARAMETER.value,
                            "line": 0,
                            "column": 0,
                            "message": "mml と mode は compose/validate の必須パラメータです。",
                            "severity": "error",
                            "hint": "mml に MML 文字列、mode に 'ppmck' または 'pyxel' を指定してください。",
                        }
                    ],
                    "warnings": [],
                },
            }
        try:
            note_sequence_dict, errors = _parse_mml(mml, mode)
            errors_list, warnings_list = _split_errors(errors)
            if action == "validate":
                return {
                    "valid": not _is_error(errors),
                    "errors": errors_list,
                    "warnings": warnings_list,
                    "note_sequence": note_sequence_dict,
                    "channel_summary": build_channel_summary(note_sequence_dict)
                    if note_sequence_dict
                    else [],
                }
            # compose
            if _is_error(errors):
                return {
                    "success": False,
                    "wav_path": None,
                    "duration_sec": 0,
                    "note_sequence": note_sequence_dict,
                    "validation": {"errors": errors_list, "warnings": warnings_list},
                }

            ns = _dict_to_note_sequence(note_sequence_dict)
            try:
                wave_data, duration, synth_errors = synthesize(
                    ns, mode, sample_rate, normalize
                )
            except Exception as exc:
                return {
                    "success": False,
                    "wav_path": None,
                    "duration_sec": 0,
                    "note_sequence": note_sequence_dict,
                    "validation": {
                        "errors": [
                            {
                                "code": ErrorCode.SYSTEM_SYNTHESIS_FAILED.value,
                                "line": 0,
                                "column": 0,
                                "message": f"音声合成中にエラーが発生しました: {exc}",
                                "severity": "error",
                                "hint": "MMLの内容を確認の上、再度お試しください。問題が続く場合は、短いMMLから試してください。",
                            }
                        ],
                        "warnings": warnings_list,
                    },
                }
            errors.extend(synth_errors)
            errors_list, warnings_list = _split_errors(errors)
            if _is_error(errors):
                return {
                    "success": False,
                    "wav_path": None,
                    "duration_sec": 0,
                    "note_sequence": note_sequence_dict,
                    "validation": {"errors": errors_list, "warnings": warnings_list},
                }
            wav_path = OUTPUT_DIR / "output.wav"
            wav_errors = write_wav(wav_path, wave_data, sample_rate)
            errors.extend(wav_errors)
            errors_list, warnings_list = _split_errors(errors)
            return {
                "success": not _is_error(errors),
                "wav_path": str(wav_path) if not _is_error(errors) else None,
                "duration_sec": duration,
                "note_sequence": note_sequence_dict,
                "validation": {"errors": errors_list, "warnings": warnings_list},
            }
        except Exception as exc:
            return {
                "success": False,
                "wav_path": None,
                "duration_sec": 0,
                "note_sequence": None,
                "validation": {
                    "errors": [
                        {
                            "code": ErrorCode.SYSTEM_INTERNAL_ERROR.value,
                            "line": 0,
                            "column": 0,
                            "message": f"内部エラーが発生しました: {exc}",
                            "severity": "error",
                            "hint": "MMLの内容を確認の上、再度お試しください。",
                        }
                    ],
                    "warnings": [],
                },
            }

    return {
        "success": False,
        "validation": {
            "errors": [
                {
                    "code": ErrorCode.VALIDATION_INVALID_ACTION.value,
                    "line": 0,
                    "column": 0,
                    "message": f"未知の action '{action}' です。",
                    "severity": "error",
                    "hint": "action は 'compose', 'validate', 'template' のいずれかを指定してください。",
                }
            ],
            "warnings": [],
        },
    }


def _dict_to_note_sequence(data: dict) -> NoteSequence:
    from .ir import (
        ChannelSequence,
        DutyEvent,
        EnvelopeEvent,
        GlideEvent,
        NoteEvent,
        NoteSequence,
        RepeatEvent,
        RestEvent,
        TempoEvent,
        VibratoEvent,
        VolumeEvent,
    )

    ns = NoteSequence(
        version=data["version"],
        bpm=data["bpm"],
        ticks_per_quarter=data["ticks_per_quarter"],
        channels={},
    )
    for name, ch_data in data["channels"].items():
        ch = ChannelSequence(
            channel_type=ch_data["channel_type"],
            events=[],
            total_ticks=ch_data["total_ticks"],
        )
        for ev in ch_data["events"]:
            ev_type = ev["type"]
            if ev_type == "note":
                ch.events.append(NoteEvent(**ev))
            elif ev_type == "rest":
                ch.events.append(RestEvent(**ev))
            elif ev_type == "volume":
                ch.events.append(VolumeEvent(**ev))
            elif ev_type == "duty":
                ch.events.append(DutyEvent(**ev))
            elif ev_type == "tempo":
                ch.events.append(TempoEvent(**ev))
            elif ev_type == "repeat":
                ch.events.append(RepeatEvent(**ev))
            elif ev_type == "envelope":
                ch.events.append(EnvelopeEvent(**ev))
            elif ev_type == "vibrato":
                ch.events.append(VibratoEvent(**ev))
            elif ev_type == "glide":
                ch.events.append(GlideEvent(**ev))
        ns.channels[name] = ch
    return ns


def main() -> None:
    parser = argparse.ArgumentParser(description="MML Compose MCP Server")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./data",
        help="Directory to store generated WAV files (default: ./data)",
    )
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "http", "sse", "streamable-http"],
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind for HTTP-based transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind for HTTP-based transports (default: 8080)",
    )
    args = parser.parse_args()
    global OUTPUT_DIR
    OUTPUT_DIR = Path(args.output_dir)
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport=args.transport,
            host=args.host,
            port=args.port,
        )


if __name__ == "__main__":
    main()
