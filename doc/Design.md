# レトロチップ音源作曲MCPサーバ — 統合設計書

> 作成日: 2026-07-11 | 更新日: 2026-07-12 | ステータス: **現行実装準拠**

---

## 1. 概要

### 1.1 目的

LLMがMML（Music Macro Language）を記述することで、レトロチップ音源（2A03 APU）のAPU音源をエミュレートした音楽を作曲・再生できるMCPサーバを設計・実装する。

### 1.2 設計目標

| 目標 | 内容 |
|---|---|
| **LLMフレンドリ** | LLMが生成しやすいMML構文、明確なエラーメッセージ |
| **2モード対応** | `ppmck`モード（クラシックAPU準拠）と`pyxel`モード（Pyxel準拠）を切り替え可能 |
| **正確な音源エミュレーション** | NTSC 2A03 timer、段階波形、Noise LFSR、Sweep、非線形ミキサを再現 |
| **拡張性** | 共通AST・IRによりモード別の構文と音声合成を分離 |
| **単一ツール** | `compose_mml` の1ツールで作曲・検証・テンプレート生成を完結 |

### 1.3 スコープ

| 対象 | 内容 |
|---|---|
| 実装範囲 | Pulse1 / Pulse2 / Triangle / Noiseの4ch MML解析、WAV合成、バリデーション、テンプレート生成 |
| 構文拡張 | Pyxel `@ENV` / `@VIB` / `@GLI`、ppmck `@v` / `@@` / `@MP` / `@EP` / `@EN` / `D` / `s` / `v+` / `v-` / `^` をIR v2から合成へ反映 |
| 対象外 | GUI / Webフロントエンド、DPCM、NSF出力、未定義のppmck拡張構文 |

### 1.4 技術スタック

| 項目 | 選定 | 理由 |
|---|---|---|
| 実装言語 | Python 3.14 | FastMCP対応、numpyで音声合成、LLM親和性 |
| MCP SDK | FastMCP >= 2.1.0 | 優良SDK |
| 音声合成 | numpy >= 2.0.0 | 波形生成の数値計算 |
| 音声出力 | 標準ライブラリ wave | WAV形式、外部依存なし |
| テスト | pytest, Hypothesis, ruff | 単体・生成テスト、リント、フォーマット |

---

## 2. システム全体アーキテクチャ

### 2.1 全体構成

```
┌──────────────────────────────────────────────────────────┐
│                     LLM Client (Claude等)                 │
│                  ┌──────────────────┐                    │
│                  │   compose_mml    │                    │
│                  └────────┬─────────┘                    │
└───────────────────────────┼─────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────┐
│                    MCP Server Layer                       │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │                 Tool Dispatcher                       │ │
│  │   action パラメータで動作を切り替え                      │ │
│  │   (compose / validate / template)                     │ │
│  └──────────────────┬───────────────────────────────────┘ │
│                     │                                      │
│  ┌──────────────────┴───────────────────────────────────┐ │
│  │              MML Parser Pipeline                       │ │
│  │                                                        │ │
│  │  ┌─────────┐     ┌──────────────┐     ┌────────────┐ │ │
│  │  │  Lexer   │────▶│   Parser     │────▶│    AST     │ │ │
│  │  │ (共通)   │     │(ppmck/pyxel) │     │  (共通)    │ │ │
│  │  └─────────┘     └──────────────┘     └─────┬──────┘ │ │
│  │                                              │         │ │
│  │  ┌───────────────────────────────────────────┘         │ │
│  │  │           SemanticAnalyzer                         │ │
│  │  │     (ppmck/pyxel) ──▶ NoteSequence IR              │ │
│  │  └────────────────────────────────────────────────────│ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                  │          │
│  ┌───────────────────────────────────────────────┴────────┐ │
│  │              APU Synthesis Engine                      │ │
│  │                                                        │ │
│  │  ┌────────┐  ┌────────┐  ┌──────────┐  ┌───────────┐  │ │
│  │  │ Pulse1 │  │ Pulse2 │  │ Triangle │  │  Noise    │  │ │
│  │  └───┬────┘  └───┬────┘  └────┬─────┘  └─────┬─────┘  │ │
│  │      └───────────┴───────────┴───────────────┘         │ │
│  │                    │                                   │ │
│  │              ┌─────┴─────┐                            │ │
│  │              │  Mixer     │                            │ │
│  │              │ (4ch→WAV)  │                            │ │
│  │              └───────────┘                            │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### 2.2 処理パイプライン

```
MML文字列
  │
  ▼
[Lexer] ──トークン列──▶ [Parser] ──AST──▶ [SemanticAnalyzer] ──NoteSequence──▶ [Synthesizer] ──WAV
                           │                      │
                      構文エラー              意味エラー
                      (SyntaxError)          (SemanticError)
```

| ステップ | コンポーネント | 役割 | 検出するエラー |
|---|---|---|---|
| 1 | Lexer | MML文字列をトークン列に変換。両モード共通のトークン定義 | 不正文字（SyntaxError） |
| 2 | Parser | トークン列を構文解析し、ASTを生成。ppmckとpyxelで別のパーサー | 構文エラー（SyntaxError） |
| 3 | SemanticAnalyzer | ASTを検証・解釈し、NoteSequence（中間表現）を生成 | 意味エラー（SemanticError） |
| 4 | Synthesizer | NoteSequenceを入力として、numpyでAPU各チャンネルの波形を合成 | 実行時エラー（RuntimeError） |

---

## 3. MCPツール仕様

### 3.1 ツール一覧

| ツール名 | 機能 |
|---|---|
| `compose_mml` | MMLの作曲・コンパイル・検証・テンプレート生成を統合した単一ツール |

### 3.2 `compose_mml` 詳細仕様

#### パラメータ

| パラメータ | 型 | required | デフォルト | 説明 |
|---|---|---|---|---|
| `action` | string | yes | — | 動作モード: `"compose"` / `"validate"` / `"template"` |
| `mml` | string | compose/validate時 | `""` | MML文字列 |
| `mode` | string | compose/validate時 | `""` | `"ppmck"` / `"pyxel"` |
| `template` | string | template時 | `"basic"` | テンプレート種別: `"basic"` / `"melody"` / `"chord"` / `"drum"` / `"empty"` / `"expressive_lead"` / `"vibrato_lead"` / `"pitch_motion"` |
| `sample_rate` | int | no | `44100` | 出力サンプリング周波数（Hz） |
| `normalize` | bool | no | `true` | 出力振幅の正規化 |

#### action別の動作と戻り値

**`action: "compose"`** — MMLをコンパイルしてWAVを生成

```json
{
  "success": true,
  "wav_path": "./data/20260711_120000_123/output.wav",
  "duration_sec": 2.0,
  "note_sequence": { ... },
  "validation": {
    "errors": [],
    "warnings": []
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `success` | boolean | 合成・WAV出力が成功したか |
| `wav_path` | string \| null | 生成されたWAVファイルパス（失敗時はnull） |
| `duration_sec` | number | 生成された音声の長さ（秒） |
| `note_sequence` | object \| null | 中間表現（IR）のNoteSequence |
| `validation.errors` | array | エラーのリスト |
| `validation.warnings` | array | 警告のリスト |

> `compose` は必ず検証を内包する。エラーがあればWAVは生成せず、検証結果のみ返す。
>
> **出力構成**: 生成時刻を表す `YYYYMMDD_HHMMSS_mmm` ディレクトリを作成し、WAVを `output.wav`、合成元のMML原文をUTF-8の `output.mml` として出力する。MCPの戻り値には従来どおりWAVのパスだけを含める。

**`action: "validate"`** — MMLの構文チェックのみ（音声生成なし）

```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "note_sequence": { ... },
  "channel_summary": [
    {
      "channel": "Pulse1",
      "note_count": 4,
      "octave_range": [4, 5],
      "duration_ticks": 768
    }
  ]
}
```

**`action: "template"`** — MMLテンプレートを生成

```json
{
  "mml": "0: T120 L8 O4 V100 @1\n   C D E F | ...",
  "description": "基本的な4ch構成（メロディ+和音+ベース+リズム）"
}
```

### 3.3 テンプレート種別

| 種別 | 内容 |
|---|---|
| `basic` | 基本的な4ch構成（メロディ+和音+ベース+リズム） |
| `melody` | メロディ重視（Pulse1主旋律、他は伴奏最小限） |
| `chord` | コード伴奏重視（Pulse2で和音、Triangleでベース） |
| `drum` | リズム重視（Noise中心のビートパターン） |
| `empty` | 各チャンネルのヘッダーのみ（空のテンプレート） |

---

## 4. 中間表現: NoteSequence IR

### 4.1 設計方針

| 項目 | 内容 |
|---|---|
| 共通IR | 両モード（ppmck / pyxel）のSemanticAnalyzerが共通で出力する |
| 後段分離 | 後段のSynthesizerはNoteSequenceのみを見れば動く（MMLの文法を知らない） |
| JSON互換 | JSON互換の構造体で表現し、MCPレスポンスに直接埋め込める |

### 4.2 時間解像度

```
1拍（4分音符） = 192 ticks
```

### 4.3 データ構造

```
NoteSequence = {
  version: "1.0",
  bpm: int,
  ticks_per_quarter: 192,
  channels: {
    "Pulse1":   ChannelSequence,
    "Pulse2":   ChannelSequence,
    "Triangle": ChannelSequence,
    "Noise":    ChannelSequence
  }
}

ChannelSequence = {
  channel_type: "pulse" | "triangle" | "noise",
  events: [Event, ...],
  total_ticks: int
}

Event = NoteEvent | RestEvent | VolumeEvent | DutyEvent
      | TempoEvent | RepeatEvent | QuantizeEvent | DetuneEvent
      | SweepEvent | RelativeVolumeEvent
      | VolumeEnvelopeEvent | DutyEnvelopeEvent | LfoEvent
      | PitchEnvEvent | NoteEnvEvent
      | EnvelopeEvent | VibratoEvent | GlideEvent
```

各イベントは位置・音長・音高・音量など、合成とMCPレスポンスに必要な値を保持する。

---

## 5. MMLパーサ設計

### 5.1 4フェーズ分離

```
MML文字列
  │
  ▼
[Lexer] ──トークン列──▶ [Parser] ──AST──▶ [SemanticAnalyzer] ──NoteSequence IR
                           │                      │
                      SyntaxError            SemanticError
```

| フェーズ | 入力 | 出力 | エラー |
|---|---|---|---|
| Lexer | MML文字列 | トークン列 | 不正文字（SyntaxError） |
| Parser | トークン列 | AST | 構文エラー（SyntaxError） |
| SemanticAnalyzer | AST | NoteSequence IR | 意味エラー（SemanticError） |

### 5.2 Lexer（共通）

両モードでトークン型を共有し、モード別の字句規則でトークン化する。ppmckは小文字、Pyxelは大文字のコマンドを受理し、音名だけAST生成時に小文字へ正規化する。

#### 主なトークン種別

| カテゴリ | トークン | 備考 |
|---|---|---|
| 音符 | `c`-`b` (ppmck) / `C`-`B` (pyxel) | `+` / `#` / `-` は音名直後、音長より前 |
| 休符 | `r` / `R` | |
| オクターブ | `o`/`O` + 数値, `>`, `<` | |
| 音長 | `l`/`L` + 数値, 音符直後の数値, `.` | |
| 音量 | `v`/`V` + 数値 | |
| デューティ/音色 | `@`+数値(ppmck/pyxel), `q`+数値(ppmck クオンタイズ) | |
| テンポ | `t`/`T` + 数値 | |
| ゲートタイム | `q`+数値(ppmck 1-8), `Q` + 数値 (pyxel 0-100) | |
| トランスポーズ | `K` + 符号付き整数 (pyxel) | 例: `K-12`, `K+7` |
| ディチューン | `D` + 符号付き整数 (ppmck), `Y` + 符号付き整数 (pyxel) | 例: `D-10`, `Y-25` |
| 相対音量 | `v+` / `v-` (ppmck) | 0〜15へクランプして合成 |
| スイープ | `s`+数値,符号付き数値 (ppmck) | 2A03 Pulse sweepへ反映 |
| タイ | `^` (ppmck), `&` (両モード) | `^`はタイ、`&`はスラー |
| リピート | `[`, `]` + 数値, `\|` | 両モードで構造検証。ppmckのリピート内`\|`は終端分岐 |
| エンベロープ/LFO | `@v`/`@@`/`@MP`/`@EP`/`@EN` (ppmck), `@ENV`/`@VIB`/`@GLI` (pyxel) | IR v2定義表を参照して合成 |
| 小節線 | `\|` | 視覚用、再生に影響しない |
| トラック識別 | ppmck: `A`/`B`/`T`/`N`/`L`, pyxel: `0:`〜`3:` | |
| ヘッダー | `#` で始まる行 (ppmck) | |
| コメント | `;` 以降行末 (ppmck) | |
| 拡張コマンド | `@ENV`/`@VIB`/`@GLI` (pyxel) | 空白区切りの数値引数をIR v2へ保持して合成 |
| 不正文字 | `INVALID` | Parserが構文エラーとして報告 |

### 5.3 Parser（モード別）

Parserの責務は**トークン列から構造的に妥当なASTを生成すること**である。必須token、トップレベル順序、リピート対応、空定義を検証する。値範囲チェックやチャンネル適合性の判断は行わない。構文errorが1件でもあればSemanticAnalyzerへ進まない。

#### ppmckパーサ

- トラックヘッダー `A`/`B`/`T`/`N`/`L` を認識
- `#` ヘッダーを認識
- 各コマンドをASTノードに変換
- トップレベル順序を`headers → global definitions → tracks`として検証
- `L`を専用文法で解析し、`l`、休符、リピート、小節線以外を拒否
- リピートの開始・終端分岐・終了を`RepeatStartStmt`/`RepeatBreakStmt`/`RepeatEndStmt`として保持し、対応、分岐重複、ネストを検証
- タイ `^` / スラー `&` の結合対象をASTで保持
- `@v`/`@@`/`@MP`/`@EP`/`@EN` エンベロープ定義 `{...|...}` と使用をASTで保持

#### pyxelパーサ

- トラックヘッダー `0:`〜`3:` を認識
- `@ENV`/`@VIB`/`@GLI` のパラメータをASTノードに保持
- リピート `[...]N` の対応とネストを検証し、開始・終了をAST文として保持

### 5.4 SemanticAnalyzer（モード別）

SemanticAnalyzerの責務は**ASTを検証・解釈してNoteSequence IRを生成**する。

#### 共通処理

- 状態管理（`octave`, `velocity`, `duty`, `tick_position`）
- MIDI音番号変換
- tick計算
- タイ処理
- ppmck/pyxel共通のトランザクション型リピート展開（各トラック最大100,000イベント）
- 値範囲チェック
- 音域チェック

#### ppmck固有

- Triangle音量無視
- Noise音高無視
- `L`の時間軸から全チャンネル共通`loop_start`を算出し、4音声チャンネルへ`RepeatEvent(repeat_count=0)`を追加
- `@` = デューティ比、`q` = クオンタイズ（gate_time = value / 8）として解釈
- `^` タイを前の音符の音長延長として解釈
- `D`/`s`/`v+`/`v-`、各種エンベロープ/LFOを値域・チャンネル検証後にIRへ保持
- mckc型の`[前半|後半]N`を展開。回数省略時だけ2周期プレビューwarningを返す

#### pyxel固有

- 音量 `V0-V127` → `0-15` 正規化
- ゲートタイム `Q0-Q100` → `0.0-1.0`
- `@` コマンドのチャンネル適合性チェック
- `@ENV`/`@VIB`/`@GLI` のIR v2定義、選択、解除、合成
- 無限リピートの2周期プレビューwarning
- `&` スラーを前の音符の音長延長として解釈

---

## 6. 抽象構文木（AST）

### 6.1 設計方針

- **モード共通**: ppmck/pyxel両方を1つのASTノード型セットで表現
- **位置情報**: 全ノードに `line`, `column` を保持
- **構造保持**: リピート開始・終端分岐・終了とタイの結合対象を、意味解析可能な文列として保持

### 6.2 主要ASTノード

```python
@dataclass
class Program(ASTNode):
    tracks: list[Track]

@dataclass
class Track(ASTNode):
    track_id: str      # "A"/"B"/"T"/"N"/"L" or "0"-"3"
    channel: str       # "Pulse1"/"Pulse2"/"Triangle"/"Noise"/"Loop"
    mode: str          # "ppmck"/"pyxel"
    statements: list[Statement]
    headers: list[Header]

@dataclass
class NoteStmt(ASTNode):
    note_name: str     # "c"-"b"（正規化済み）
    accidental: int    # +1=sharp, -1=flat, 0=none
    length: int | None
    dots: int

@dataclass
class RestStmt(ASTNode):
    length: int | None
    dots: int

@dataclass
class OctaveStmt(ASTNode):
    value: int | None
    direction: str | None  # "up"/"down"

@dataclass
class LengthStmt(ASTNode):
    value: int

@dataclass
class VolumeStmt(ASTNode):
    value: int

@dataclass
class DutyStmt(ASTNode):
    value: int

@dataclass
class TempoStmt(ASTNode):
    value: int

@dataclass
class GateTimeStmt(ASTNode):
    value: int

@dataclass
class TransposeStmt(ASTNode):
    value: int

@dataclass
class DetuneStmt(ASTNode):
    value: int

@dataclass
class TieStmt(ASTNode):
    target: NoteStmt | RestStmt | int | None

@dataclass
class TieCmdStmt(ASTNode):
    target: NoteStmt | int | None

@dataclass
class QuantizeStmt(ASTNode):
    value: int

@dataclass
class DetuneCmdStmt(ASTNode):
    value: int

@dataclass
class RelativeVolumeStmt(ASTNode):
    up: bool
    value: int | None

@dataclass
class SweepStmt(ASTNode):
    x: int
    y: int

@dataclass
class VolumeEnvelopeUseStmt(ASTNode):
    slot: int

@dataclass
class VolumeEnvelopeDefStmt(ASTNode):
    slot: int
    values: list[int]
    loop: list[int] | None

@dataclass
class DutyEnvelopeUseStmt(ASTNode):
    slot: int

@dataclass
class DutyEnvelopeDefStmt(ASTNode):
    slot: int
    values: list[int]
    loop: list[int] | None

@dataclass
class LfoUseStmt(ASTNode):
    slot: int

@dataclass
class LfoDefStmt(ASTNode):
    slot: int
    params: list[int]

@dataclass
class LfoOffStmt(ASTNode):
    pass

@dataclass
class PitchEnvUseStmt(ASTNode):
    slot: int

@dataclass
class PitchEnvDefStmt(ASTNode):
    slot: int
    values: list[int]
    loop: list[int] | None

@dataclass
class PitchEnvOffStmt(ASTNode):
    pass

@dataclass
class NoteEnvUseStmt(ASTNode):
    slot: int

@dataclass
class NoteEnvDefStmt(ASTNode):
    slot: int
    values: list[int]
    loop: list[int] | None

@dataclass
class NoteEnvOffStmt(ASTNode):
    pass

@dataclass
class RepeatStartStmt(ASTNode):
    pass

@dataclass
class RepeatBreakStmt(ASTNode):
    pass  # ppmckの現在のリピート階層に属する終端分岐

@dataclass
class RepeatEndStmt(ASTNode):
    count: int | None  # None=無限

@dataclass
class BarStmt(ASTNode):
    pass

@dataclass
class ExtCmdStmt(ASTNode):
    cmd: str           # "ENV"/"VIB"/"GLI"
    slot: int
    params: list[int]
```

---

## 7. エラーハンドリング

### 7.1 エラー分類

```python
class ErrorPhase(Enum):
    LEXER = "lexer"
    SYNTAX = "syntax"
    SEMANTIC = "semantic"
    RUNTIME = "runtime"
    API = "api"
```

| 層 | コード接頭辞 | 発生フェーズ | 例 |
|---|---|---|---|
| **SyntaxError** | `SYNTAX_*` | Parser | 無効なトークン、未終端のリピート、不正なトラックヘッダー |
| **SemanticError** | `SEMANTIC_*` | SemanticAnalyzer | 値範囲外、チャンネル不適合、音域外、未定義参照 |
| **RuntimeError** | `RUNTIME_*` | Synthesizer | 音声合成失敗、WAV出力失敗、内部エラー |
| **APIError** | `VALIDATION_*` | Tool Dispatcher | パラメータ欠落、無効なmode/action |

### 7.2 ErrorDetail構造

```json
{
  "code": "SEMANTIC_VALUE_OUT_OF_RANGE",
  "phase": "semantic",
  "line": 1,
  "column": 5,
  "message": "'o' の値 9 は範囲外です。有効範囲: 0〜7。",
  "severity": "error",
  "hint": "例: o4 のように指定してください。",
  "context": "A t120 l8 o9 c"
}
```

### 7.3 回復戦略

| 状況 | 動作 |
|---|---|
| Parser ERROR時 | 同一フェーズ内で回復可能な位置まで読み進めて複数の診断を収集し、意味解析へは進まない |
| Semantic ERROR時 | 診断を収集し、不正な状態更新を行わず後続ASTの検証を継続 |
| WARNING時 | 警告を記録し、仕様で定めた無視・クランプ・有限回展開などの代替動作で継続 |
| compose action | ERRORがある場合WAVを生成せず検証結果のみ返す |

---

## 8. BNF文法（概要）

受理言語の正本は [MML_BNF.md](MML_BNF.md) とする。値を要求するコマンドで数値を省略した場合は既定値へ置換せず、`SYNTAX_INVALID_NUMBER`を返す。全トラックIDはモード内で一度だけ定義でき、ppmckヘッダーは既知のキーを用いてトラックより前に置き、値を指定する場合は二重引用符で囲む。

### 8.1 共通要素

```bnf
<note_name>   ::= "c" | "d" | "e" | "f" | "g" | "a" | "b"
<accidental>  ::= "+" | "#" | "-"
<length>      ::= <number> <dot>*
<octave_up>   ::= ">"
<octave_down> ::= "<"
<tie>         ::= "&"
```

### 8.2 ppmckモード

```bnf
<ppmck_mml>   ::= <ppmck_header>* <global_definition>* <ppmck_track>*
<ppmck_track> ::= <audio_track> | <loop_track>
<audio_track> ::= ("A" | "B" | "T" | "N") <ppmck_statement>*
<loop_track>  ::= "L" (<length_cmd> | <rest> | <loop_repeat> | <bar>)*
<ppmck_statement>
              ::= <note> | <rest> | <octave_cmd> | <length_cmd>
                | <volume_cmd> | <relative_volume_cmd> | <duty_cmd>
                | <quantize_cmd> | <tempo_cmd> | <tie_cmd> | <slur_cmd>
                | <detune_cmd> | <sweep_cmd>
                | <vol_envelope_def> | <vol_envelope_use>
                | <duty_envelope_def> | <duty_envelope_use>
                | <lfo_def> | <lfo_use> | <lfo_off>
                | <pitch_env_def> | <pitch_env_use> | <pitch_env_off>
                | <note_env_def> | <note_env_use> | <note_env_off>
                | <ppmck_repeat> | <bar>
<ppmck_repeat>::= "[" <ppmck_statement>* ("|" <ppmck_statement>*)? "]" <number>?
<loop_repeat> ::= "[" (<length_cmd> | <rest> | <loop_repeat>)*
                  ("|" (<length_cmd> | <rest> | <loop_repeat>)*)? "]" <number>?
```

### 8.3 pyxelモード

```bnf
<pyxel_mml>   ::= <pyxel_track>*
<pyxel_track> ::= <pyxel_track_header> <pyxel_statement>*
<pyxel_track_header>
              ::= "0:" | "1:" | "2:" | "3:"
<pyxel_statement>
              ::= <note> | <rest> | <octave_cmd> | <length_cmd>
                | <volume_cmd> | <gate_cmd> | <tone_cmd> | <tempo_cmd>
                | <transpose_cmd> | <detune_cmd> | <tie_cmd>
                | <pyxel_repeat> | <bar> | <ext_cmd>
<pyxel_repeat>::= "[" <pyxel_statement>* "]" <number>?
```

---

### 8.4 文法適合性の保証

BNFの各規則は Lexer → AST → IR/診断の一貫経路で検証する。`tests/test_mml_conformance.py`は、音符・休符・コマンド・トラック・ヘッダー・拡張コマンドについて正例、負例、境界値、位置情報を検査する。Hypothesisによる固定seedの生成テストで、有効音列のAST/IR保存と単一トークン破壊の非黙殺も確認する。

ppmckの将来予約構文は現在の受理言語に含めない。ppmck/pyxelの拡張はIR v2の共有定義表とチャンネル制御イベントへ変換して合成する。ppmckは構文モード名であり、PPMCK/mckcとのドライバ互換は保証しない。

## 9. APU音声合成エンジン

NoteSequence IRを入力としてPulse1、Pulse2、Triangle、Noiseを合成し、線形ミキシングと任意の正規化を経てWAVへ出力する。

---

## 10. MMLコマンド仕様

コマンド、値範囲、デフォルト値の完全な定義は [MML_BNF.md](MML_BNF.md) を参照する。設計書と実装で差異が生じた場合はBNFを受理言語の基準として監査し、実装変更と同時に適合テストを更新する。

---

## 11. 2モード比較サマリー

| 項目 | ppmckモード | pyxelモード |
|---|---|---|
| **大文字/小文字** | 小文字 `c d e`（`D` ディチューンは大文字のみ） | 大文字 `C D E` |
| **コマンド** | `o` `l` `v` `v+`/`v-` `t` `@` `q` `^` `&` `D` `s` | `O` `L` `V` `T` `Q` `@` `K` `Y` `&` |
| **チャンネル指定** | `A` `B` `T` `N`、制御用`L` | `0:`〜`3:`（番号） |
| **Parser** | `parser_ppmck.py` | `parser_pyxel.py` |
| **SemanticAnalyzer** | `semantic_ppmck.py` | `semantic_pyxel.py` |
| **音量範囲** | 0-15（クラシックAPU準拠） | 0-127 |
| **デューティ比** | `@0`〜`@3` で4種（Pulse系のみ） | `@0`〜`@3`（Pulse系のみ有効） |
| **クオンタイズ/ゲート** | `q1`〜`q8`（gate_time = value / 8） | `Q0`〜`Q100`（%） |
| **タイ/スラー** | `^` = タイ、`&` = スラー | `&` = スラー（タイなし） |
| **ディチューン** | `D-127`〜`D126`（セント） | `Y-127`〜`Y127`（セント） |
| **エンベロープ/LFO** | `@v`/`@@`/`@MP`/`@EP`/`@EN`（合成対応） | `@ENV`/`@VIB`/`@GLI`（合成対応） |
| **リピート** | `L`からloop_startを算出。`[...]N`と`[前半\|後半]N`をネスト展開 | `[...]N`をネスト展開 |

---

## 12. 確定事項一覧

| # | 項目 | 決定内容 |
|---|---|---|
| 1 | パーサーアーキテクチャ | Lexer → Parser → SemanticAnalyzer → Synthesizer の4フェーズ分離 |
| 2 | AST | モード共通ASTノード型セットを採用 |
| 3 | エラー分類 | SyntaxError / SemanticError / RuntimeError / APIError の4層分離 |
| 4 | BNF | [MML_BNF.md](MML_BNF.md) を受理言語の正本とし、適合テストで実装との一致を保証 |
| 5 | pyxel `@` とトラック番号の矛盾 | トラック番号優先。`@` はPulse系のみデューティ比として有効 |
| 6 | Noise note_number → period マッピング | ppmck: `period=8, mode=0` 固定。pyxel: マッピング式適用 |
| 7 | 出力構成 | `YYYYMMDD_HHMMSS_mmm/output.wav`, `YYYYMMDD_HHMMSS_mmm/output.mml` |
| 8 | リピート安全上限 | 各トラックの展開後イベント数は100,000件以下。超過時は展開前に意味error |

---

## 13. 実装状態

| カテゴリ | 実装内容 |
|---|---|
| MCPツール | `compose_mml`（compose/validate/template） |
| Lexer | ppmck/pyxel 両モード対応、共通トークン定義、INVALIDトークン。ppmck向けに `@v`/`@@`/`@MP`/`@EP`/`@EN`/`^`/`D`/`s`/`v+`/`v-` トークンを追加 |
| Parser | ppmck/pyxel 別Parser。必須token、トップレベル順序、case、リピート対応を検証し、ppmckの`RepeatBreakStmt`と専用L文法を構築 |
| SemanticAnalyzer | ppmck/pyxel別Analyzer、AST→IR変換。共通反復展開、事前イベント上限、値域→チャンネル→状態→IR順の検証、Lのloop_start算出を実装 |
| IR | NoteSequence、各種Event（Quantize/Detune/Sweep/RelativeVolume/VolumeEnvelope/DutyEnvelope/Lfo/PitchEnv/NoteEnv 等）、ErrorDetail（phase付き） |
| Synthesizer | Pulse/Triangle/Noise 4ch合成、線形ミキシング、WAV出力 |
| Templates | basic/melody/chord/drum/empty の5種 × 2モード。ppmckテンプレートは `@` でデューティ比を指定 |
| テスト | pytestの固定・統合テスト、Hypothesisの生成テスト、ruffによるリント/フォーマット |

---

以上が、レトロチップ音源作曲MCPサーバの統合設計書です。
