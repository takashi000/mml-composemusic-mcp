全部確定ですね。設計書に反映して、確定版を出します。メモリにも保存しておきます。はい、記録も残りました。それでは確定版の設計書を出しますね。

---

# ファミコン音源作曲MCPサーバ — 仕様・基本設計書（確定版）

> 作成日: 2026-07-11 | ステータス: **確定**（実装前）

---

## 1. 概要

### 1.1 目的

LLMがMML（Music Macro Language）を記述することで、ファミコン（NES）のAPU音源をエミュレートした音楽を作曲・再生できるMCPサーバを設計する。

### 1.2 設計目標

| 目標 | 内容 |
|---|---|
| **LLMフレンドリ** | LLMが生成しやすいMML構文、明確なエラーメッセージ |
| **2モード対応** | `ppmck`モード（FC準拠）と`pyxel`モード（Pyxel準拠）を切り替え可能 |
| **正確な音源エミュレーション** | NES APU 4チャンネルの特性を忠実に再現 |
| **拡張性** | DPCM、エンベロープ等の第2段階機能を前提とした設計 |
| **単一ツール** | compose_mml の1ツールで作曲・検証・テンプレート生成を完結 |

### 1.3 スコープ外

- 実装コードの作成
- DPCMチャンネル（第2段階）
- NSFファイル出力（第2段階で検討）
- GUI / Webフロントエンド

### 1.4 技術スタック

| 項目 | 選定 | 理由 |
|---|---|---|
| 実装言語 | Python | FastMCP対応、numpyで音声合成、LLM親和性 |
| MCP SDK | FastMCP | 優良SDK |
| 音声合成 | numpy | 波形生成の数値計算 |
| 音声出力 | 標準ライブラリ wave | WAV形式、外部依存なし |

---

## 2. システム全体アーキテクチャ

### 2.1 全体構成

```
┌──────────────────────────────────────────────────────────┐
│                     LLM Client (Claude等)                 │
│                  ┌──────────────────┐                      │
│                  │   compose_mml    │                      │
│                  └────────┬─────────┘                      │
└───────────────────────────┼───────────────────────────────┘
                            │
┌───────────────────────────┴───────────────────────────────┐
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
│  │  ┌─────────┐     ┌──────────────┐     ┌────────────┐  │ │
│  │  │  Lexer   │────▶│   Parser     │────▶│NoteSequence│  │ │
│  │  │ (共通)   │     │(ppmck/pyxel) │     │   (共通IR) │  │ │
│  │  └─────────┘     └──────────────┘     └─────┬──────┘  │ │
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

1. **Lexer**: MML文字列をトークン列に変換。両モード共通のトークン定義を持ち、大文字/小文字の正規化を行う
2. **Parser**: トークン列を構文解析し、NoteSequence（中間表現）を生成。ppmckとpyxelで別のパーサーを使用
3. **Synthesizer**: NoteSequenceを入力として、numpyでAPU各チャンネルの波形を合成し、WAV形式で出力

---

## 3. MCPツール仕様

### 3.1 ツール一覧

| ツール名 | 機能 |
|---|---|
| `compose_mml` | MMLの作曲・コンパイル・検証・テンプレート生成を統合した単一ツール |

### 3.2 `compose_mml` 詳細仕様

#### パラメータ

| パラメータ | 型 | required | 説明 |
|---|---|---|---|
| `action` | string | yes | 動作モード: `"compose"` / `"validate"` / `"template"` |
| `mml` | string | compose/validate時 | MML文字列 |
| `mode` | string | compose/validate時 | `"ppmck"` / `"pyxel"` |
| `template` | string | template時 | テンプレート種別: `"basic"` / `"melody"` / `"chord"` / `"drum"` / `"empty"` |
| `sample_rate` | int | no | 出力サンプリング周波数 (default: 44100) |
| `normalize` | bool | no | 出力のノーマライズ (default: true) |

#### action別の動作と戻り値

**`action: "compose"`** — MMLをコンパイルしてWAVを生成

```
入力: mml, mode, (sample_rate, normalize)

戻り値:
{
  success: bool,
  wav_path: string,           # 生成されたWAVファイルパス
  duration_sec: float,        # 演奏時間
  note_sequence: object,      # NoteSequence IR
  validation: {               # コンパイル時に内包される検証結果
    errors: [ErrorDetail],
    warnings: [string]
  }
}
```

> composeは必ず検証を内包する。エラーがあればWAVは生成せず、検証結果のみ返す。

**`action: "validate"`** — MMLの構文チェックのみ（音声生成なし）

```
入力: mml, mode

戻り値:
{
  valid: bool,
  errors: [ErrorDetail],
  note_sequence: object,      # 解析成功時のみ
  channel_summary: [           # チャンネル別サマリー
    { channel: string, note_count: int, octave_range: [int,int], duration_ticks: int }
  ]
}
```

**`action: "template"`** — MMLテンプレートを生成

```
入力: mode, template

戻り値:
{
  mml: string,                # テンプレートMML文字列
  description: string          # テンプレートの説明
}
```

#### ErrorDetail 構造

```
{
  line: int,
  column: int,
  message: string,
  severity: "error" | "warning",
  hint: string                # 修正のヒント（任意）
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

- 両モード（ppmck / pyxel）のパーサが共通で出力する
- 後段のSynthesizerはNoteSequenceのみを見れば動く（MMLの文法を知らない）
- JSON互換の構造体で表現し、MCPレスポンスに直接埋め込める

### 4.2 時間解像度

```
1拍（4分音符） = 192 ticks
```

- 192は 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96 で割り切れる
- 3連符、16分音符、32分音符など主要な分割に対応
- pyxelモードのtick（1 tick = 4分音符の1/48）と整合: 192 / 48 = 4

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

```
NoteEvent = {
  type: "note",
  tick_position: int,       # 絶対開始位置
  duration: int,            # 音長（ticks）
  note_number: int,         # MIDI音番号 (69 = A4 = 440Hz)
  velocity: int,            # 音量 (0-15, Triangleはppmckで無視、pyxelで有効)
  duty: int,                # デューティ比 (0-3, Pulseのみ)
  gate_time: float          # ゲートタイム割合 0.0-1.0
}

RestEvent = {
  type: "rest",
  tick_position: int,
  duration: int
}

VolumeEvent = {
  type: "volume",
  tick_position: int,
  value: int                # 0-15（pyxelは0-127から正規化）
}

DutyEvent = {
  type: "duty",
  tick_position: int,
  value: int                # 0-3
}

TempoEvent = {
  type: "tempo",
  tick_position: int,
  bpm: int
}

RepeatEvent = {
  type: "repeat",
  start_tick: int,
  end_tick: int,
  repeat_count: int          # 0 = 無限
}
```

#### 拡張イベント（第2段階実装、第1段階は保持のみ）

```
EnvelopeEvent = {
  type: "envelope",
  tick_position: int,
  slot: int,                    # 1-15 (0はOFF)
  points: [                     # 定義内容（切り替えのみの場合は空）
    { target_volume: int, duration_ticks: int }
  ]
}

VibratoEvent = {
  type: "vibrato",
  tick_position: int,
  slot: int,                    # 1-15 (0はOFF)
  params: {                     # 定義内容（切り替えのみの場合は空）
    delay_ticks: int,
    period_ticks: int,
    depth_cents: int
  }
}

GlideEvent = {
  type: "glide",
  tick_position: int,
  slot: int,                    # 1-15 (0はOFF)
  params: {                     # 定義内容（切り替えのみの場合は空）
    initial_offset_cents: int,
    duration_ticks: int
  }
}
```

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

> **pyxelモードの `@` コマンド処理（確定）**: `@` はPulseチャンネルでのみデューティ比として有効。Triangle・Noiseチャンネルでは無視する。トラック番号と `@` が矛盾する場合、トラック番号を優先し、`@` は警告の上無視。

| 状況 | 処理 |
|---|---|
| トラック0(Pulse1) + `@1`(Square) | ✅ 正常。デューティ比50%として扱う |
| トラック0(Pulse1) + `@0`(Triangle) | ⚠️ 警告。チャンネルはPulse1のまま、`@0`は無視 |
| トラック2(Triangle) + `@1`(Square) | ⚠️ 警告。チャンネルはTriangleのまま、`@1`は無視 |
| トラック3(Noise) + `@0`(Triangle) | ⚠️ 警告。チャンネルはNoiseのまま、`@0`は無視 |

#### Noiseチャンネルの note_number → period マッピング（確定）

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

## 5. MMLパーサ基本設計

### 5.1 Lexer（共通）

両モードの字句解析を統一。モードごとに大文字/小文字を正規化した後にトークン化する。

**主なトークン種別:**

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
| タイ/スラー | `&` | |
| リピート | `[`, `]` + 数値 (pyxel) | |
| 小節線 | `\|` | 視覚用、再生に影響しない |
| トラック識別 | ppmck: `A`/`B`/`T`/`N`/`L`, pyxel: `数字:` | |
| ヘッダー | `#` で始まる行 (ppmck) | |
| コメント | `;` 以降行末 (ppmck) | |

**モード別正規化:**

- ppmck: 音符・コマンドは小文字に正規化、`#` 行はヘッダー、`;` 以降はコメント
- pyxel: 音符・コマンドは大文字に正規化、`数字:` はトラックヘッダー

### 5.2 Parser（モード別）

#### ppmckパーサ

- トラックヘッダー `A`/`B`/`T`/`N` でチャンネルを決定
- `L` は全体ループフラグ
- `#TITLE` 等のヘッダーはメタ情報として保持
- デフォルト値: octave=4, volume=15, length=4, duty=2
- Triangleチャンネルでは `v` コマンドを無視（警告なし）
- タイ(`&`)で同音高を結合
- 第2段階: エンベロープ(`@v`), スイープ(`s`), 区間ループ(`[...]`), トランスポーズ(`K`), ノイズモード(`m`)

#### pyxelパーサ

- トラック番号 `0:`〜`3:` でチャンネルを決定
- `@` コマンドはPulseチャンネルでのみデューティ比として有効。他チャンネルでは警告して無視
- デフォルト値: octave=4, volume=100, length=4, gate=80, tone=0
- 音量 `V0`〜`V127` → IR内部で 0〜15 に正規化
- ゲートタイム `Q0`〜`Q100` → gate_time 0.0〜1.0
- リピート `[...]N` を展開（ネスト対応、省略時無限）
- タイ `&` は同音高=タイ、異音高=レガート、音長のみ=音長延長
- `@ENV`/`@VIB`/`@GLI`: NoteSequenceにイベントとして保持。第1段階は合成に反映しない
- `K`(トランスポーズ): note_numberに加算
- `Y`(ディチューン): note_numberの小数部として保持

### 5.3 エラーハンドリング

| カテゴリ | 例 | severity |
|---|---|---|
| 構文エラー | 不正なトークン、未終端のリピート | error |
| 範囲エラー | オクターブ範囲外、音量範囲外 | error または warning |
| チャンネルエラー | Triangleへの `q` コマンド、Noiseへの音高指定(ppmck) | warning（無視して継続） |
| 音域エラー | MIDI音番号0-127を逸脱 | warning（クランプ） |
| 参照エラー | 未定義エンベロープ/ビブラート参照 | error |
| 未サポート | `@ENV`/`@VIB`/`@GLI`（第1段階） | warning（「第1段階では未サポート、無視されます」） |

**回復戦略:**
- ERROR時: そのトークンで解析を停止し、エラーを返す
- WARNING時: 警告を記録しつつ、妥当な値にクランプして処理を継続
- compose actionでは、ERRORがある場合WAVを生成せず検証結果のみ返す

---

## 6. APU音声合成エンジン基本設計

### 6.1 NES APU ハードウェア仕様

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

- **波形**: 矩形波、4種のデューティ比（12.5%, 25%, 50%, 75%）
- **周波数**: `output_freq = CPU_clock / (16 * (wavelength + 1))`、wavelengthは11bit (0-2047)
- **音量**: 4-bit (0-15) または decay envelope
- **スイープ**: 第2段階で対応。`Wavelength ± (Wavelength >> S)` のピッチ変動

#### Triangle チャンネル

- **波形**: 32段階三角波（0→15→0の階段状）
- **音量**: 制御なし（固定振幅）
  - **ppmckモード**: `v` コマンドを無視、振幅は固定最大値
  - **pyxelモード**: `V` の値を振幅スケールとして適用。`V0`=無音、`V127`=最大振幅
  - NoteSequenceは両モードで `velocity` を保持するが、ppmckモードのSynthesizerはそれを無視する
- **周波数**: `output_freq = CPU_clock / (32 * (wavelength + 1))`

#### Noise チャンネル

- **波形**: 15-bit LFSR（Linear Feedback Shift Register）による擬似乱数
- **音量**: 4-bit (0-15)
- **周期**: 4-bit period register (0-15) + mode flag (0=long 32767samples, 1=short 93samples)
- **マッピング（確定）**:
  - **ppmckモード**: 音高不使用。すべて `period=8, mode=0`（中域デフォルト）。音長と音量のみ反映
  - **pyxelモード**: `period = clamp(15 - floor(note_number / 8), 0, 15)`, `mode = 1 if period >= 13 else 0`

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
  │      第2段階: NES非線形ミキシングテーブル
  │
  └─ 4. ノーマライズ → 16bit PCM → WAV出力
```

### 6.3 ミキシング仕様

| 項目 | 第1段階（線形） | 第2段階（FC実機風） |
|---|---|---|
| 方式 | 単純平均 `(ch1+ch2+ch3+ch4)/4` | NES非線形ミキシング |
| クリッピング | -1.0 ~ 1.0 でクランプ | 実機と同様の段階的ミックス |
| ノーマライズ | 有効時ピークを-1.0に正規化 | 無効化可能 |

> FC実機の非線形ミキシング: `output = 95.88 - (8128 / (sum_of_active_channels + 1))`。第2段階で実装。

---

## 7. 2モード比較サマリー

| 項目 | ppmckモード | pyxelモード |
|---|---|---|
| **大文字/小文字** | 小文字 `c d e` | 大文字 `C D E` |
| **コマンド** | `o` `l` `v` `t` `q` | `O` `L` `V` `T` `Q` `@` `K` `Y` |
| **チャンネル指定** | `A` `B` `T` `N`（文字） | `0:`〜`3:`（番号）+ `@` 音色 |
| **チャンネル数** | 4ch（DPCM第2段階） | 4ch（DPCM非対応） |
| **音量範囲** | 0-15（FC準拠） | 0-127 |
| **デューティ比** | `q0`〜`q3` で4種 | `@1`(50%), `@2`(25%) の2種のみ（Pulse系のみ有効） |
| **ゲートタイム** | 第2段階で検討 | `Q0`〜`Q100`（default 80） |
| **Triangle音量** | 無視（FC仕様） | 設定可（Pyxel仕様、振幅スケールとして適用） |
| **Noise音高** | 不使用（period=8固定） | note_number → period マッピング |
| **エンベロープ** | `@v`（第2段階） | `@ENV` スロット定義+切替（第1段階は保持のみ） |
| **ビブラート** | 第3段階 | `@VIB` スロット定義+切替（第1段階は保持のみ） |
| **ピッチスライド** | `s` スイープ（第2段階） | `@GLI` スロット定義+切替（第1段階は保持のみ） |
| **トランスポーズ** | `K`（第2段階） | `K`（半音単位） |
| **リピート** | `L`（全体）, `[...]`（第2段階） | `[...]`（回数指定、省略時無限、ネスト対応） |
| **タイ** | `c4&c4` のみ | `C4&C4` または `C4&16`（音長のみ可） |
| **コメント** | `;` | 公式記載なし |
| **ヘッダー** | `#TITLE` 等 | なし |

---

## 8. 確定事項一覧

| # | 項目 | 決定内容 |
|---|---|---|
| 1 | pyxel `@` とトラック番号の矛盾 | トラック番号優先。`@` はPulse系のみデューティ比として有効、他チャンネルでは警告して無視 |
| 2 | Noise note_number → period マッピング | ppmck: `period=8, mode=0` 固定。pyxel: `period = clamp(15 - floor(nn/8), 0, 15)`, `mode = 1 if period >= 13 else 0` |
| 3 | pyxel Triangle音量 | ppmck: 無視（固定振幅）。pyxel: 振幅スケールとして適用。NoteSequenceは両モードでvelocity保持 |
| 4 | 出力フォーマット | WAV確定。NSFは第2段階 |
| 5 | `@ENV`/`@VIB`/`@GLI` IR表現 | EnvelopeEvent/VibratoEvent/GlideEvent の3種を定義。第1段階は保持のみ、合成無視、validateでWARNING |
| 6 | 非線形ミキシング | 第2段階で実装。第1段階は線形ミキシング |

---

以上が確定版の仕様・基本設計書です。

……全部揃いましたね。6つあった未決定事項が全部決まって、表の最後が「確定」で埋まったのを見ると、なんだか安心します。設計書はこれで完成です。実装に入るときに、この書類があれば迷わないはずです。

何か足りないところや直したいところがあれば、いつでも言ってくださいね。