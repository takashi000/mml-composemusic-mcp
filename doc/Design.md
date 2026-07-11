# レトロチップ音源作曲MCPサーバ — 統合設計書

> 作成日: 2026-07-11 | ステータス: **実装済み（第1段階）**

---

## 1. 概要

### 1.1 目的

LLMがMML（Music Macro Language）を記述することで、レトロチップ音源（2A03 APU）のAPU音源をエミュレートした音楽を作曲・再生できるMCPサーバを設計・実装する。

### 1.2 設計目標

| 目標 | 内容 |
|---|---|
| **LLMフレンドリ** | LLMが生成しやすいMML構文、明確なエラーメッセージ |
| **2モード対応** | `ppmck`モード（クラシックAPU準拠）と`pyxel`モード（Pyxel準拠）を切り替え可能 |
| **正確な音源エミュレーション** | レトロAPU 4チャンネルの特性を忠実に再現 |
| **拡張性** | DPCM、エンベロープ等の第2段階機能を前提とした設計 |
| **単一ツール** | `compose_mml` の1ツールで作曲・検証・テンプレート生成を完結 |

### 1.3 スコープ

| 対象 | 内容 |
|---|---|
| 第1段階（実装済み） | 4ch MML解析、WAV合成、バリデーション、テンプレート生成、基本エラーコード |
| 第2段階（将来） | DPCMチャンネル、NSFファイル出力、クラシックAPU実機風非線形ミキシング、エンベロープ合成、区間ループ（ppmck） |
| 対象外 | GUI / Webフロントエンド |

### 1.4 技術スタック

| 項目 | 選定 | 理由 |
|---|---|---|
| 実装言語 | Python 3.14 | FastMCP対応、numpyで音声合成、LLM親和性 |
| MCP SDK | FastMCP >= 2.1.0 | 優良SDK |
| 音声合成 | numpy >= 2.0.0 | 波形生成の数値計算 |
| 音声出力 | 標準ライブラリ wave | WAV形式、外部依存なし |
| テスト | pytest, ruff | 単体テスト・リント・フォーマット |

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
│  │  │  Lexer   │────▶│   Parser     │────▶│NoteSequence│ │ │
│  │  │ (共通)   │     │(ppmck/pyxel) │     │   (共通IR) │ │ │
│  │  └─────────┘     └──────────────┘     └─────┬──────┘ │ │
│  └──────────────────────────────────────────────┼────────┘ │
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
[Lexer] ──トークン列──▶ [Parser] ──NoteSequence──▶ [Synthesizer] ──WAV
                          │
                     (validateの場合はここで停止)
                     (templateの場合はテンプレート文字列を返却)
```

| ステップ | コンポーネント | 役割 |
|---|---|---|
| 1 | Lexer | MML文字列をトークン列に変換。両モード共通のトークン定義を持ち、大文字/小文字の正規化を行う |
| 2 | Parser | トークン列を構文解析し、NoteSequence（中間表現）を生成。ppmckとpyxelで別のパーサーを使用 |
| 3 | Synthesizer | NoteSequenceを入力として、numpyでAPU各チャンネルの波形を合成し、WAV形式で出力 |

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
| `template` | string | template時 | `"basic"` | テンプレート種別: `"basic"` / `"melody"` / `"chord"` / `"drum"` / `"empty"` |
| `sample_rate` | int | no | `44100` | 出力サンプリング周波数（Hz） |
| `normalize` | bool | no | `true` | 出力振幅の正規化 |

#### action別の動作と戻り値

**`action: "compose"`** — MMLをコンパイルしてWAVを生成

```json
{
  "success": true,
  "wav_path": "./data/output_20260711_120000_123.wav",
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
> **WAVファイル名**: 固定名 `output.wav` ではなく、生成時刻を含む `output_YYYYMMDD_HHMMSS_mmm.wav` 形式で出力される。これにより、複数回の `compose` 実行でファイルが上書きされるのを防ぐ。ミリ秒まで含めることで、短時間連続実行時のファイル名衝突も回避する。

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

| フィールド | 型 | 説明 |
|---|---|---|
| `valid` | boolean | MMLにerrorがないか |
| `errors` | array | エラーのリスト |
| `warnings` | array | 警告のリスト |
| `note_sequence` | object \| null | 中間表現（IR）のNoteSequence |
| `channel_summary` | array | チャンネルごとの統計情報 |

**`action: "template"`** — MMLテンプレートを生成

```json
{
  "mml": "0: T120 L8 O4 V100 @1\n   C D E F | ...",
  "description": "基本的な4ch構成（メロディ+和音+ベース+リズム）"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `mml` | string | 生成されたMMLテンプレート |
| `description` | string | テンプレートの説明 |

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
| 共通IR | 両モード（ppmck / pyxel）のパーサが共通で出力する |
| 後段分離 | 後段のSynthesizerはNoteSequenceのみを見れば動く（MMLの文法を知らない） |
| JSON互換 | JSON互換の構造体で表現し、MCPレスポンスに直接埋め込める |

### 4.2 時間解像度

```
1拍（4分音符） = 192 ticks
```

| 特徴 | 内容 |
|---|---|
| 192の理由 | 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96 で割り切れる |
| 対応リズム | 3連符、16分音符、32分音符など主要な分割に対応 |
| pyxel整合性 | pyxelモードのtick（1 tick = 4分音符の1/48）と整合: 192 / 48 = 4 |

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
      | TempoEvent | RepeatEvent
      | EnvelopeEvent | VibratoEvent | GlideEvent
```

#### 基本イベント

| イベント | フィールド | 型 | 説明 |
|---|---|---|---|
| `NoteEvent` | `type` | string | `"note"` |
| | `tick_position` | int | 絶対開始位置 |
| | `duration` | int | 音長（ticks） |
| | `note_number` | int | MIDI音番号 (69 = A4 = 440Hz) |
| | `velocity` | int | 音量 (0-15) |
| | `duty` | int | デューティ比 (0-3, Pulseのみ) |
| | `gate_time` | float | ゲートタイム割合 0.0-1.0 |
| | `detune_cents` | float | ディチューン（セント単位、pyxel Yコマンド） |
| `RestEvent` | `type` | string | `"rest"` |
| | `tick_position` | int | 絶対開始位置 |
| | `duration` | int | 音長（ticks） |
| `VolumeEvent` | `type` | string | `"volume"` |
| | `tick_position` | int | 絶対位置 |
| | `value` | int | 0-15（pyxelは0-127から正規化） |
| `DutyEvent` | `type` | string | `"duty"` |
| | `tick_position` | int | 絶対位置 |
| | `value` | int | 0-3 |
| `TempoEvent` | `type` | string | `"tempo"` |
| | `tick_position` | int | 絶対位置 |
| | `bpm` | int | テンポ |
| `RepeatEvent` | `type` | string | `"repeat"` |
| | `tick_position` | int | イベント位置 |
| | `start_tick` | int | リピート開始tick |
| | `end_tick` | int | リピート終了tick |
| | `repeat_count` | int | 0 = 無限 |
| | `duration` | int | リピート区間の長さ（ticks） |

#### 拡張イベント（第1段階は保持のみ、合成無視）

| イベント | フィールド | 型 | 説明 |
|---|---|---|---|
| `EnvelopeEvent` | `type` | string | `"envelope"` |
| | `tick_position` | int | 絶対位置 |
| | `slot` | int | 1-15 (0はOFF) |
| | `points` | list[dict] | `{target_volume, duration_ticks}` のリスト |
| `VibratoEvent` | `type` | string | `"vibrato"` |
| | `tick_position` | int | 絶対位置 |
| | `slot` | int | 1-15 (0はOFF) |
| | `params` | dict | `{delay_ticks, period_ticks, depth_cents}` |
| `GlideEvent` | `type` | string | `"glide"` |
| | `tick_position` | int | 絶対位置 |
| | `slot` | int | 1-15 (0はOFF) |
| | `params` | dict | `{initial_offset_cents, duration_ticks}` |

> 第1段階: パーサーはこれらをNoteSequenceに保持する。Synthesizerは無視。validateで「第1段階では未サポート、無視されます」とWARNING。

### 4.4 主要変換仕様

#### 音高変換

```
MIDI音番号 = (オクターブ + 1) * 12 + 音階オフセット + シャープ/フラット

音階オフセット: c=0, d=2, e=4, f=5, g=7, a=9, b=11

例: o4 a = 69 (A4 = 440Hz)
    o4 c = 60 (C4 = 中央C)
```

#### 音量正規化

| モード | MML表記 | IR内部値 | 備考 |
|---|---|---|---|
| ppmck | `v15` | 15 | 0-15そのまま |
| pyxel | `V100` | 12 | `round(100 / 127 * 15)` |

> NoteSequenceは両モードで `velocity` を保持する。ppmckモードのSynthesizerはTriangleの `velocity` を無視する。pyxelモードでは振幅スケールとして適用する。

#### チャンネル割り当て

| ppmck | pyxel | チャンネル | 備考 |
|---|---|---|---|
| `A` | `0:` | Pulse1 | 矩形波 |
| `B` | `1:` | Pulse2 | 矩形波 |
| `T` | `2:` | Triangle | 三角波 |
| `N` | `3:` | Noise | ノイズ |

#### pyxelモードの `@` コマンド処理

> `@` はPulseチャンネルでのみデューティ比として有効。Triangle・Noiseチャンネルでは無視する。トラック番号と `@` が矛盾する場合、トラック番号を優先し、`@` は警告の上無視。

| 状況 | 処理 |
|---|---|
| トラック0(Pulse1) + `@1`(Square) | ✅ 正常。デューティ比50%として扱う |
| トラック0(Pulse1) + `@2`(Pulse) | ✅ 正常。デューティ比25%として扱う |
| トラック0(Pulse1) + `@0`(Triangle) | ⚠️ 警告。チャンネルはPulse1のまま、`@0`は無視 |
| トラック2(Triangle) + `@1`(Square) | ⚠️ 警告。チャンネルはTriangleのまま、`@1`は無視 |
| トラック3(Noise) + `@0`(Triangle) | ⚠️ 警告。チャンネルはNoiseのまま、`@0`は無視 |
| トラック3(Noise) + `@3`(Noise) | ⚠️ 警告。チャンネルはNoiseのまま、`@3`は無視 |

#### Noiseチャンネルの note_number → period マッピング

| モード | 処理 |
|---|---|
| **ppmck** | 音高不使用。Noiseチャンネルの音符はすべて `period=8, mode=0`（中域デフォルト）。音長と音量のみ反映 |
| **pyxel** | note_number を noise period にマッピング |

pyxelモードのマッピング式:

```
period = clamp(15 - floor(note_number / 8), 0, 15)
mode   = 1 if period >= 13 else 0
```

| note_number | period | mode | 特徴 |
|---|---|---|---|
| 0（最低音） | 15 | 1 (short) | 最高ノイズ |
| 48（中域） | 9 | 0 (long) | 中域ノイズ |
| 96（高域） | 3 | 0 (long) | 低ノイズ |
| 120（最高音） | 0 | 0 (long) | 最低ノイズ |

---

## 5. MMLパーサ設計

### 5.1 Lexer（共通）

両モードの字句解析を統一。モードごとに大文字/小文字を正規化した後にトークン化する。

#### 主なトークン種別

| カテゴリ | トークン | 備考 |
|---|---|---|
| 音符 | `c`-`b` (ppmck) / `C`-`B` (pyxel) | 大文字小文字問わず判定 |
| 休符 | `r` / `R` | |
| オクターブ | `o`/`O` + 数値, `>`, `<` | |
| 音長 | `l`/`L` + 数値, 音符直後の数値, `.` | |
| 音量 | `v`/`V` + 数値 | |
| デューティ/音色 | `q`+数値(ppmck), `@`+数値(pyxel) | |
| テンポ | `t`/`T` + 数値 | |
| ゲートタイム | `Q` + 数値 (pyxel) | |
| トランスポーズ | `K` + 数値 (pyxel) | |
| ディチューン | `Y` + 数値 (pyxel) | |
| タイ/スラー | `&` | |
| リピート | `[`, `]` + 数値 (pyxel) | |
| 小節線 | `\|` | 視覚用、再生に影響しない |
| トラック識別 | ppmck: `A`/`B`/`T`/`N`/`L`, pyxel: `数字:` | |
| ヘッダー | `#` で始まる行 (ppmck) | |
| コメント | `;` 以降行末 (ppmck) | |
| 拡張コマンド | `@ENV`/`@VIB`/`@GLI` (pyxel) | 第1段階は保持のみ |

#### モード別正規化

| モード | 正規化ルール |
|---|---|
| ppmck | 音符・コマンドは小文字に正規化、`#` 行はヘッダー、`;` 以降はコメント |
| pyxel | 音符・コマンドは大文字に正規化、`数字:` はトラックヘッダー |

### 5.2 Parser（モード別）

#### ppmckパーサ

| 項目 | 内容 |
|---|---|
| トラックヘッダー | `A`/`B`/`T`/`N` でチャンネルを決定 |
| 全体ループ | `L` は全体ループフラグ。省略時は1回のみ再生 |
| メタ情報 | `#TITLE` 等のヘッダーはメタ情報として保持 |
| デフォルト値 | octave=4, volume=15, length=4, duty=2 |
| Triangle音量 | `v` コマンドを無視（警告なし） |
| タイ | `&` で同音高を結合。音長のみの指定も可 |
| 区間リピート | `[...]` は第2段階。現状はwarningで無視 |
| 第2段階予定 | エンベロープ(`@v`), スイープ(`s`), 区間ループ(`[...]`), トランスポーズ(`K`), ノイズモード(`m`) |

#### pyxelパーサ

| 項目 | 内容 |
|---|---|
| トラック番号 | `0:`〜`3:` でチャンネルを決定 |
| `@` コマンド | Pulseチャンネルでのみデューティ比として有効。他チャンネルでは警告して無視 |
| デフォルト値 | octave=4, volume=100, length=4, gate=80, duty=2 |
| 音量 | `V0`〜`V127` → IR内部で 0〜15 に正規化 |
| ゲートタイム | `Q0`〜`Q100` → gate_time 0.0〜1.0 |
| リピート | `[...]N` を展開（ネスト対応、省略時無限） |
| タイ | `&` は同音高=タイ、異音高=レガート、音長のみ=音長延長 |
| 拡張コマンド | `@ENV`/`@VIB`/`@GLI`: NoteSequenceにイベントとして保持。第1段階は合成に反映しない |
| トランスポーズ | `K`: note_numberに加算 |
| ディチューン | `Y`: note_numberの小数部として `detune_cents` に保持 |

#### リピート処理の違い

| モード | 記法 | 動作 |
|---|---|---|
| ppmck | `L` | 全体ループフラグ。最後にRepeatEventを追加 |
| ppmck | `[...]` | 第2段階。現状はwarningで無視 |
| pyxel | `[...]N` | 区間リピートを即座に展開。N省略時は無限（2回で打ち切りwarning） |
| pyxel | ネスト | 対応済み |

### 5.3 エラーハンドリング

| カテゴリ | 例 | severity |
|---|---|---|
| 構文エラー | 不正なトークン、未終端のリピート | error |
| 範囲エラー | オクターブ範囲外、音量範囲外 | error または warning |
| チャンネルエラー | Triangleへの `q` コマンド、Noiseへの音高指定(ppmck) | warning（無視して継続） |
| 音域エラー | MIDI音番号0-127を逸脱 | warning（クランプ） |
| 参照エラー | 未定義エンベロープ/ビブラート参照 | error |
| 未サポート | `@ENV`/`@VIB`/`@GLI`（第1段階） | warning（「第1段階では未サポート、無視されます」） |

#### 回復戦略

| 状況 | 動作 |
|---|---|
| ERROR時 | そのトークンで解析を停止し、エラーを返す |
| WARNING時 | 警告を記録しつつ、妥当な値にクランプして処理を継続 |
| compose action | ERRORがある場合WAVを生成せず検証結果のみ返す |

---

## 6. APU音声合成エンジン

### 6.1 レトロAPU ハードウェア仕様

#### 概要

| 項目 | 仕様 |
|---|---|
| CPUクロック (NTSC) | 1.7897725 MHz |
| フレームカウンタ | ~240Hz (envelope/length), ~60Hz (IRQ) |
| 出力 | 4チャンネル → ミキサー → DAC |
| サンプリングレート（本サーバ） | 44100 Hz（デフォルト、変更可） |

#### チャンネル一覧

| チャンネル | 種別 | レジスタ | MML対応 | 特徴 |
|---|---|---|---|---|
| Ch1 | Pulse 1 | $4000-$4003 | A / 0: | 矩形波、デューティ比4種、音量0-15、スイープ |
| Ch2 | Pulse 2 | $4004-$4007 | B / 1: | 矩形波、同上 |
| Ch3 | Triangle | $4008-$400B | T / 2: | 32段階三角波、音量固定、linear counter |
| Ch4 | Noise | $400C-$400F | N / 3: | LFSRノイズ、音量0-15、2周期モード |
| Ch5 | DMC | $4010-$4013 | — | 第2段階 |

#### Pulse チャンネル

| 項目 | 内容 |
|---|---|
| 波形 | 矩形波、4種のデューティ比（12.5%, 25%, 50%, 75%） |
| 周波数 | `output_freq = CPU_clock / (16 * (wavelength + 1))`、wavelengthは11bit (0-2047) |
| 音量 | 4-bit (0-15) または decay envelope |
| スイープ | 第2段階で対応。`Wavelength ± (Wavelength >> S)` のピッチ変動 |

#### Triangle チャンネル

| 項目 | 内容 |
|---|---|
| 波形 | 32段階三角波（0→15→0の階段状） |
| 音量 | 制御なし（固定振幅） |
| ppmckモード | `v` コマンドを無視、振幅は固定最大値 |
| pyxelモード | `V` の値を振幅スケールとして適用。`V0`=無音、`V127`=最大振幅 |
| 周波数 | `output_freq = CPU_clock / (32 * (wavelength + 1))` |

#### Noise チャンネル

| 項目 | 内容 |
|---|---|
| 波形 | 15-bit LFSR（Linear Feedback Shift Register）による擬似乱数 |
| 音量 | 4-bit (0-15) |
| 周期 | 4-bit period register (0-15) + mode flag (0=long 32767samples, 1=short 93samples) |
| ppmckモード | 音高不使用。すべて `period=8, mode=0`（中域デフォルト）。音長と音量のみ反映 |
| pyxelモード | `period = clamp(15 - floor(note_number / 8), 0, 15)`, `mode = 1 if period >= 13 else 0` |

### 6.2 合成フロー

```
NoteSequence
  │
  ├─ 1. テンポ変換: ticks → samples
  │      sample = tick × (60 / bpm) × (sample_rate / 192)
  │
  ├─ 2. チャンネルごとに波形生成（numpy）
  │      Pulse1, Pulse2: 矩形波（デューティ比パターン適用）
  │      Triangle: 32段階三角波（ppmck: 固定振幅, pyxel: velocityスケール）
  │      Noise: LFSRベース擬似乱数（ppmck: period=8固定, pyxel: マッピング式適用）
  │
  ├─ 3. ミキシング
  │      第1段階: 線形ミキシング (ch1+ch2+ch3+ch4)/4
  │      第2段階: レトロAPU非線形ミキシングテーブル
  │
  └─ 4. ノーマライズ → 16bit PCM → WAV出力
```

### 6.3 ミキシング仕様

| 項目 | 第1段階（線形） | 第2段階（クラシックAPU実機風） |
|---|---|---|
| 方式 | 単純平均 `(ch1+ch2+ch3+ch4)/4` | レトロAPU非線形ミキシング |
| クリッピング | -1.0 ~ 1.0 でクランプ | 実機と同様の段階的ミックス |
| ノーマライズ | 有効時ピークを-1.0に正規化 | 無効化可能 |

> クラシックAPU実機の非線形ミキシング: `output = 95.88 - (8128 / (sum_of_active_channels + 1))`。第2段階で実装。

---

## 7. MMLコマンド仕様

### 7.1 モード1: `ppmck` — PPMCKインスパイア独自形式

PPMCKの文法をベースにしつつ、不要な複雑さを排除した独自サブセット。LLMが生成しやすく、クラシックAPU音源の主要機能をカバーする。

#### 参考ドキュメント

| 内容 | URL |
|---|---|
| PPMCK mckc.txt（MMLコンパイラ仕様書） | https://github.com/munshkr/ppmck/blob/master/doc/mckc.txt |
| MCK Wiki MMLリファレンス | https://wikiwiki.jp/mck/MMLリファレンス |
| レトロAPUハードウェア仕様 (midi2nes) | https://github.com/matiaszanolli/midi2nes/blob/master/docs/NES_APU_REFERENCE.md |
| レトロAPU仕様 (problemkaputt.de ミラー) | https://github.com/RigleGit/nes-specs/blob/main/audioprocessingunitapu.md |

#### トラック構成例

```
#TITLE "My Song"
#COMPOSER "Luno"

A t150 l8 o4 v15 q2       # Pulse1
  c d e f | g a b > c

B l8 o3 v12 q1           # Pulse2
  c r g r c r g r

T l4 o3 v7               # Triangle（音量は無視、固定振幅）
  c2 c2 g2 g2

N l8 v10                 # Noise
  r c r c r c r c

L                        # 全体ループ（省略可）
```

#### トラックヘッダー

| 記法 | 意味 | 対象 | 備考 |
|---|---|---|---|
| `A` | Pulse1 チャンネル | — | 矩形波 |
| `B` | Pulse2 チャンネル | — | 矩形波 |
| `T` | Triangle チャンネル | — | 三角波、音量固定 |
| `N` | Noise チャンネル | — | ノイズ |
| `L` | 全体ループ | トラック末尾 | 省略時は1回のみ再生 |

#### 音高

| 記法 | 意味 | 備考 |
|---|---|---|
| `c` `d` `e` `f` `g` `a` `b` | ド レ ミ ファ ソ ラ シ | 小文字 |
| `c+` または `c#` | ド♯ | シャープ |
| `c-` | ド♭ | フラット |
| `o4` | オクターブ4（中央C基準） | `o0`〜`o7` |
| `>` | 1オクターブ上へ | 相対移動 |
| `<` | 1オクターブ下へ | 相対移動 |

> Noiseチャンネルでは音高は使わない（周波数はノイズテーブルで固定）

#### 音長

| 記法 | 意味 | 備考 |
|---|---|---|
| `l4` | デフォルト音長 = 4分音符 | トラック内で随時変更可 |
| `c4` | 4分音符のド | 音符の直後に数字 |
| `c8` | 8分音符のド | |
| `c1` | 全音符のド | |
| `c4.` | 付点4分音符 | +半分の長さ |
| `c4..` | 複付点4分音符 | +半分+半分の半分 |
| `r4` | 4分休符 | 休符にも音長指定可 |
| `c4&c4` | タイ | 同音高の音符を結合 |
| `c4&4` | 音長のみのタイ | 第1段階で対応 |

音長とテンポの関係: `4分音符の秒数 = 60 / BPM`

#### 音量

| 記法 | 意味 | 対象 | 備考 |
|---|---|---|---|
| `v15` | 音量15（最大） | A, B, N | 0-15、クラシックAPU準拠 |
| `v0` | 音量0（無音） | A, B, N | |

> Triangleチャンネルでは `v` は無視（ハードウェア仕様、音量制御なし）

#### デューティ比

| 記法 | 意味 | 対象 | 備考 |
|---|---|---|---|
| `q0` | 12.5% | A, B のみ | |
| `q1` | 25% | A, B のみ | |
| `q2` | 50% | A, B のみ | デフォルト |
| `q3` | 75% | A, B のみ | |

#### テンポ

| 記法 | 意味 | 備考 |
|---|---|---|
| `t120` | BPM 120 | 最初のトラックで指定、全体に適用 |

#### 区切り・フォーマット

| 記法 | 意味 |
|---|---|
| `\|` | 小節線（視覚用、再生には影響しない） |
| 改行 | トラック内の区切り（視覚用） |
| `#` 行 | ヘッダー・メタ情報 |
| 空行 | 無視 |
| `;` 以降 | コメント（行末まで無視） |

#### 第2段階で追加予定

| コマンド | 構文 | 内容 |
|---|---|---|
| カウント音長 | `c%48` | 全音符=192カウント基準 |
| エンベロープ定義 | `@v0 = { 15, 12, 8, 0 }` | 音量エンベロープ |
| エンベロープ指定 | `@v0` | 定義済みエンベロープ使用 |
| デューティ比音色 | `@0 = { 0, 1, \| 2 }` | 発音中のデューティ比変化 |
| スイープ | `s1,2` | ピッチスイープ（Pulseのみ） |
| 区間ループ | `[ c d \| e f ]2` | 指定回数繰り返し |
| トランスポーズ | `K2` | 全体キーシフト |
| ノイズモード | `m0` / `m1` | Noise ch: 0=ロング周期, 1=ショート周期 |

### 7.2 モード2: `pyxel` — Pyxel MML準拠形式

PyxelのMML仕様に準拠。Pyxelのサウンドシステムに合わせた記法。

#### 参考ドキュメント

| 内容 | URL |
|---|---|
| Pyxel Audio API (DeepWiki) | https://deepwiki.com/kitao/pyxel/5.3-audio-api |
| Pyxel MML Studio | https://kitao.github.io/pyxel/web/mml-studio/ |
| Pyxel MMLコマンドリファレンス | https://kitao.github.io/pyxel/docs/mml-commands.md |
| Pyxel GitHub（ソース） | https://github.com/kitao/pyxel |

#### トラック構成例

```
0: T150 L8 O4 V100 @1  # トラック0 (Pulse1)
   C D E F G A B >C

1: L8 O3 V80 @2        # トラック1 (Pulse2)
   E G B R E G B R

2: L4 O3 V60           # トラック2 (Triangle)
   C2 G2 E2 C2

3: L8 V80              # トラック3 (Noise)
   C R C R C R C R
```

#### 完全コマンド一覧

##### テンポ・音長・音量

| コマンド | 記法 | 意味 | 範囲 | デフォルト |
|---|---|---|---|---|
| テンポ | `T150` | BPM | 1- | 120 |
| デフォルト音長 | `L4` | n分音符。`L12`で8分3連符 | 1-192 | 4 |
| 音量 | `V100` | 音量 | **0-127** | 100 |
| ゲートタイム | `Q80` | ノート実発音割合(%)。100=隙間なし、0=無音 | 0-100 | 80 |

##### 音色・ピッチ

| コマンド | 記法 | 意味 | 範囲 | デフォルト |
|---|---|---|---|---|
| 音色（トーン） | `@1` | 波形タイプ。1:Square(50%) / 2:Pulse(25%) | 1-2（Pulse系のみ有効） | — |
| トランスポーズ | `K12` | 半音単位の移調。12で1オクターブ | — | 0 |
| ディチューン | `Y100` | セント単位の微調整。100で半音上、-100で半音下 | — | 0 |

##### 音高・オクターブ

| コマンド | 記法 | 意味 | 範囲 | デフォルト |
|---|---|---|---|---|
| 音符 | `C D E F G A B` | ドレミファソラシ | — | — |
| 音長指定 | `C4` `F16` | 音符の直後に音長 | 1-192 | `L`の値 |
| シャープ | `#` または `+` | 半音上 | — | — |
| フラット | `-` | 半音下 | — | — |
| 付点 | `.` | 音長を1.5倍。複数可 `C4..` | — | — |
| 休符 | `R` | 休符。`R8`のように音長指定可 | 1-192 | `L`の値 |
| オクターブ | `O4` | オクターブ指定。`O4`のA=440Hz | 0〜7 | 4 |
| 相対上 | `>` | 1オクターブ上（最大7） | — | — |
| 相対下 | `<` | 1オクターブ下（最小0） | — | — |
| タイ/スラー | `&` | 同音高=タイ、異音高=レガート。`C4&16` のように音長だけ指定も可 | — | — |

##### リピート

| コマンド | 記法 | 意味 | 範囲 |
|---|---|---|---|
| リピート開始 | `[` | 区間リピートの開始 | — |
| リピート終了 | `]2` | 区間リピートの終了。回数指定。省略時は**無限リピート**。**ネスト対応** | 1- |

##### エンベロープ `@ENV`

| 記法 | 意味 |
|---|---|
| `@ENV0` | エンベロープOFF |
| `@ENV1` | スロット1に切り替え |
| `@ENV1 30 20 100 50 0` | スロット1を定義して切り替え（簡易パース） |

> 本実装では `{...}` ブレース記法ではなく、フラットな数値列を簡易パースする。1 tick = 4分音符の1/48。スロット0は指定不可（OFF専用）。

##### ビブラート `@VIB`

| 記法 | 意味 |
|---|---|
| `@VIB0` | ビブラートOFF |
| `@VIB1` | スロット1に切り替え |
| `@VIB1 24 12 100` | スロット1を定義して切り替え（簡易パース） |

##### グライド（ピッチスライド）`@GLI`

| 記法 | 意味 |
|---|---|
| `@GLI0` | グライドOFF |
| `@GLI1` | スロット1に切り替え |
| `@GLI1 -100 24` | スロット1を定義して切り替え（簡易パース） |

---

## 8. エラー仕様

### 8.1 ErrorDetail 構造

```json
{
  "code": "SYNTAX_INVALID_TOKEN",
  "line": 1,
  "column": 5,
  "message": "無効な文字 'x' が見つかりました。",
  "severity": "error",
  "hint": "MMLコマンド（c,d,e,f,g,a,b,r,o,l,v,t,q など）を使用してください。",
  "context": "A t150 l8 o4 x c"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `code` | string | エラーコード（機械処理用、LLMがパターン認識可能） |
| `line` | integer | 発生行（1始まり。システム/APIエラー時は0） |
| `column` | integer | 発生列（1始まり。システム/APIエラー時は0） |
| `message` | string | 人間が読めるメッセージ |
| `severity` | string | `"error"` または `"warning"` |
| `hint` | string | LLM向けの修正ヒント |
| `context` | string | 該当行のコンテキスト |

> **注意**: `line` と `column` は **1始まり** です（最初の行・最初の列が1）。システムエラーやAPIレベルエラーなどで位置情報がない場合は `0` を使用します。

### 8.2 構文エラー（SYNTAX_*）

| code | trigger | message テンプレート | hint | severity |
|---|---|---|---|---|
| `SYNTAX_INVALID_TOKEN` | 解析不能な文字 | `無効な文字 '{char}' が見つかりました。` | `MMLコマンド（c,d,e,f,g,a,b,r,o,l,v,t,q など）を使用してください。` | error |
| `SYNTAX_INVALID_NUMBER` | 数値を期待した位置に数値以外 | `'{command}' の後に数値が必要です。` | `例: {command}{example} のように数値を指定してください。` | error |
| `SYNTAX_VALUE_OUT_OF_RANGE` | パラメータ値が許容範囲外 | `'{command}' の値 {value} は範囲外です。有効範囲: {min}〜{max}。` | `例: {command}{valid_example} のように指定してください。` | error または warning |
| `SYNTAX_UNEXPECTED_TOKEN` | 文脈に合わないトークン | `'{token}' はここでは使用できません。` | `期待される要素: {expected}。直前のコマンドを確認してください。` | error |
| `SYNTAX_UNTERMINATED_REPEAT` | `[` に対応する `]` がない | `リピート '[' に対応する ']' が見つかりません。` | `] を追加してリピートを閉じてください。回数指定（例: ]2）も可能です。` | error |
| `SYNTAX_UNMATCHED_REPEAT_END` | `]` に対応する `[` がない | `']' に対応する '[' が見つかりません。` | `直前の [ を確認するか、余分な ] を削除してください。` | error |
| `SYNTAX_UNTERMINATED_TIE` | `&` の後に音符がない | `タイ '&' の後に音符が見つかりません。` | `& の後に音符（例: {note_example}）を続けてください。音長のみ（例: &16）も可能です（pyxelモード）。` | error |
| `SYNTAX_INVALID_TRACK_HEADER` | 不正なトラックヘッダー | `無効なトラックヘッダー '{header}' です。` | ppmck: `A, B, T, N, L のいずれかを使用してください。` / pyxel: `0:, 1:, 2:, 3: のいずれかを使用してください。` | error |
| `SYNTAX_DUPLICATE_TRACK` | 同じトラックが複数回定義 | `トラック '{track}' が複数回定義されています。` | `各トラックは1回のみ定義できます。重複定義を削除してください。` | error |
| `SYNTAX_EMPTY_TRACK` | トラックに音符・休符がない | `トラック '{track}' に音符または休符がありません。` | `少なくとも1つの音符または休符を記述してください。` | error |
| `SYNTAX_NOTE_OUT_OF_RANGE` | MIDI音番号が0-127を逸脱 | `音高が範囲外です（MIDI音番号 {note_number}）。` | `オクターブを調整してください。有効範囲: o0〜o7。` | warning（クランプ） |
| `SYNTAX_CHANNEL_MISMATCH` | チャンネルに不適切なコマンド | `チャンネル '{channel}' で '{command}' は使用できません。` | `コマンドを削除するか、適切なチャンネルに移動してください。` | warning（無視） |
| `SYNTAX_UNTERMINATED_HEADER` | ppmck `#` ヘッダーの引用符が閉じていない | `ヘッダー '{header}' の引用符が閉じられていません。` | `二重引用符 " で値を閉じてください。例: #TITLE "My Song"` | error |
| `SYNTAX_UNDEFINED_REFERENCE` | 未定義のエンベロープ/ビブラート等を参照 | `'{ref_type}' '{ref_name}' は定義されていません。` | `使用前に定義してください。例: {definition_example}` | error |

#### チャンネル不適合の具体例（SYNTAX_CHANNEL_MISMATCH）

| 状況 | message | hint |
|---|---|---|
| Triangle + `q2` (ppmck) | `チャンネル 'Triangle' で 'q' は使用できません。` | `Triangleチャンネルはデューティ比を持ちません。q コマンドを削除してください。` |
| Triangle + `v10` (ppmck) | （警告なし、静かに無視） | — |
| Noise + `o4 c` (ppmck) | `チャンネル 'Noise' で音高指定は使用できません。` | `Noiseチャンネルでは音高ではなく音長と音量のみ指定してください。` |
| トラック2(Triangle) + `@1` (pyxel) | `チャンネル 'Triangle' で '@1' (Square) は使用できません。` | `トラック番号がチャンネルを決定します。@ コマンドを削除するか、Pulseチャンネル（0: または 1:）に移動してください。` |

#### 値範囲外の具体例（SYNTAX_VALUE_OUT_OF_RANGE）

| 状況 | message | hint | severity |
|---|---|---|---|
| `o9` (ppmck/pyxel) | `'o' の値 9 は範囲外です。有効範囲: 0〜7。` | `例: o4 のように指定してください。` | error |
| `v20` (ppmck) | `'v' の値 20 は範囲外です。有効範囲: 0〜15。` | `例: v15 のように指定してください。` | error |
| `V200` (pyxel) | `'V' の値 200 は範囲外です。有効範囲: 0〜127。` | `例: V100 のように指定してください。` | error |
| `l0` (両モード) | `'l' の値 0 は範囲外です。有効範囲: 1〜192。` | `例: l8 のように指定してください。` | error |
| `t0` (両モード) | `'t' の値 0 は範囲外です。有効範囲: 1以上。` | `例: t150 のように指定してください。` | error |

### 8.3 システムエラー（SYSTEM_*）

| code | trigger | message テンプレート | hint | severity |
|---|---|---|---|---|
| `SYSTEM_SYNTHESIS_FAILED` | 音声合成中のnumpy演算エラー等 | `音声合成中にエラーが発生しました: {detail}` | `MMLの内容を確認の上、再度お試しください。問題が続く場合は、短いMMLから試してください。` | error |
| `SYSTEM_WAV_WRITE_FAILED` | WAVファイル出力の失敗 | `WAVファイルの出力に失敗しました: {detail}` | `しばらく待ってから再度お試しください。` | error |
| `SYSTEM_INTERNAL_ERROR` | 予期しない例外 | `内部エラーが発生しました: {detail}` | `MMLの内容を確認の上、再度お試しください。` | error |

> システムエラーは `compose` actionでのみ発生しうる。`validate` / `template` actionでは構文エラー以外は返らない設計。

### 8.4 APIレベルエラー（VALIDATION_*）

| code | trigger | message テンプレート | hint | severity |
|---|---|---|---|---|
| `VALIDATION_MISSING_PARAMETER` | compose/validateで必須パラメータ(mml, mode)が欠落 | `mml と mode は compose/validate の必須パラメータです。` | `mml に MML 文字列、mode に 'ppmck' または 'pyxel' を指定してください。` | error |
| `VALIDATION_INVALID_MODE` | 未知のmodeが指定された | `未知のモード '{mode}' です。` | `mode は 'ppmck' または 'pyxel' を指定してください。` | error |
| `VALIDATION_INVALID_ACTION` | 未知のactionが指定された | `未知の action '{action}' です。` | `action は 'compose', 'validate', 'template' のいずれかを指定してください。` | error |

### 8.5 エラー発生時のcompose_mml戻り値

`compose` action で ERROR がある場合:

```json
{
  "success": false,
  "wav_path": null,
  "duration_sec": 0,
  "note_sequence": null,
  "validation": {
    "errors": [ErrorDetail, ...],
    "warnings": [ErrorDetail, ...]
  }
}
```

> warnings も ErrorDetail 構造で返す（severity = "warning"）。LLMは warnings を見て「修正しなくても動くが、改善できる」ことを把握できる。

---

## 9. 2モード比較サマリー

| 項目 | ppmckモード | pyxelモード |
|---|---|---|
| **大文字/小文字** | 小文字 `c d e` | 大文字 `C D E` |
| **コマンド** | `o` `l` `v` `t` `q` | `O` `L` `V` `T` `Q` `@` `K` `Y` |
| **チャンネル指定** | `A` `B` `T` `N`（文字） | `0:`〜`3:`（番号） |
| **チャンネル数** | 4ch（DPCM第2段階） | 4ch（DPCM非対応） |
| **音量範囲** | 0-15（クラシックAPU準拠） | 0-127 |
| **音量デフォルト** | 15 | 100 |
| **デューティ比** | `q0`〜`q3` で4種 | `@1`(50%), `@2`(25%) の2種のみ（Pulse系のみ有効） |
| **ゲートタイム** | 第2段階で検討 | `Q0`〜`Q100`（default 80） |
| **Triangle音量** | 無視（FC仕様） | 設定可（Pyxel仕様、振幅スケールとして適用） |
| **Noise音高** | 不使用（period=8固定） | note_number → period マッピング |
| **エンベロープ** | `@v`（第2段階） | `@ENV` スロット定義+切替（第1段階は保持のみ） |
| **ビブラート** | 第3段階 | `@VIB` スロット定義+切替（第1段階は保持のみ） |
| **ピッチスライド** | `s` スイープ（第2段階） | `@GLI` スロット定義+切替（第1段階は保持のみ） |
| **トランスポーズ** | `K`（第2段階） | `K`（半音単位） |
| **ディチューン** | 未対応 | `Y`（セント単位） |
| **リピート** | `L`（全体）, `[...]`（第2段階） | `[...]`（回数指定、省略時無限、ネスト対応） |
| **タイ** | `c4&c4` / `c4&4` | `C4&C4` または `C4&16`（音長のみ可） |
| **tick単位** | なし | 1 tick = 4分音符の1/48 |
| **コメント** | `;` | 公式記載なし |
| **ヘッダー** | `#TITLE` 等 | なし |

---

## 10. 確定事項一覧

| # | 項目 | 決定内容 |
|---|---|---|
| 1 | pyxel `@` とトラック番号の矛盾 | トラック番号優先。`@` はPulse系のみデューティ比として有効、他チャンネルでは警告して無視 |
| 2 | Noise note_number → period マッピング | ppmck: `period=8, mode=0` 固定。pyxel: `period = clamp(15 - floor(nn/8), 0, 15)`, `mode = 1 if period >= 13 else 0` |
| 3 | pyxel Triangle音量 | ppmck: 無視（固定振幅）。pyxel: 振幅スケールとして適用。NoteSequenceは両モードでvelocity保持 |
| 4 | 出力フォーマット | WAV確定。NSFは第2段階 |
| 5 | `@ENV`/`@VIB`/`@GLI` IR表現 | EnvelopeEvent/VibratoEvent/GlideEvent の3種を定義。第1段階は保持のみ、合成無視、validateでWARNING |
| 6 | 非線形ミキシング | 第2段階で実装。第1段階は線形ミキシング |
| 7 | ErrorDetail line/column | 1始まり。システム/APIエラー時は0 |
| 8 | pyxel 無限リピート | 省略時は2回で打ち切り、WARNINGを返す |
| 9 | pyxel `@ENV`/`@VIB`/`@GLI` パース | 第1段階は `{...}` ブレースではなくフラット数値列を簡易パース |
| 10 | WAVファイル名 | 固定名 `output.wav` から、生成時刻ベースの `output_YYYYMMDD_HHMMSS_mmm.wav` 形式に変更。毎回異なるファイル名で上書きを防止 |

---

## 11. 実装状態と今後の予定

### 11.1 第1段階実装済み機能

| カテゴリ | 実装内容 |
|---|---|
| MCPツール | `compose_mml`（compose/validate/template） |
| Lexer | ppmck/pyxel 両モード対応、共通トークン定義 |
| Parser | ppmckパーサ、pyxelパーサ、エラーハンドリング |
| IR | NoteSequence、各種Event、ErrorDetail、ErrorCode |
| Synthesizer | Pulse/Triangle/Noise 4ch合成、線形ミキシング、WAV出力 |
| Templates | basic/melody/chord/drum/empty の5種 × 2モード |
| CLI | `--output-dir`, `--transport`, `--host`, `--port` 対応 |
| テスト | pytestによる各種テスト、ruffによるリント/フォーマット |

### 11.2 第2段階予定機能

| カテゴリ | 予定内容 |
|---|---|
| DPCMチャンネル | 5ch目のDPCM対応 |
| NSF出力 | NSFファイル出力の検討 |
| 非線形ミキシング | クラシックAPU実機風ミキシングテーブル |
| エンベロープ合成 | `@v`(ppmck), `@ENV`(pyxel) の合成反映 |
| ppmck 区間リピート | `[...]` の展開 |
| ppmck スイープ | `s` コマンド |
| その他 | カウント音長、ノイズモード、トランスポーズ等 |

### 11.3 設計書と実装の差分

| 項目 | 設計書（旧） | 実装（最新） |
|---|---|---|
| `NoteEvent` | `detune_cents` なし | `detune_cents: float = 0.0` 追加 |
| `RepeatEvent` | `start_tick`, `end_tick`, `repeat_count` のみ | `tick_position`, `duration` も追加 |
| pyxel `@` コマンド | `@1`(50%), `@2`(25%) の2種 | 同じだが `@0`, `@3` は警告で拒否 |
| pyxel repeat | ネスト対応・省略時無限 | 実装済み、無限時は2回で打ち切り（warning） |
| ppmck repeat `[...]` | 第2段階 | 実装も第2段階（warning で無視） |
| pyxel `@ENV`/`@VIB`/`@GLI` | `{...}` ブレース記法 | 実装はフラット数値列で簡易パース |
| pyxel `Y`(ディチューン) | note_numberの小数部として保持 | `detune_cents` フィールドとして保持 |
| トランスポート | 設計書に記載なし | `stdio`/`http`/`sse`/`streamable-http` + CLI引数 |
| ErrorDetail line/column | 旧資料で表記揺れあり | 実装は1始まり（システムエラー時は0） |
| WAVファイル名 | 固定 `output.wav` | 可変 `output_YYYYMMDD_HHMMSS_mmm.wav`。生成時刻ベースで上書き防止 |

---

以上が、レトロチップ音源作曲MCPサーバの統合設計書です。
