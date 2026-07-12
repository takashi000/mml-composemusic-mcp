# MCP Server Tool Schema

本ドキュメントは `mml-composemusic-mcp` が提供するMCPツールのスキーマ定義です。

## ツール一覧

| ツール名 | 説明 |
|---------|------|
| `compose_mml` | レトロチップ音源風MMLの解析・合成・テンプレート生成を行う |

## `compose_mml`

### 概要

MML文字列を解析し、以下のいずれかの処理を実行します。

- `compose`: MMLをレトロAPU風音源で合成し、WAVファイルを出力する
- `validate`: MMLの構文を検証し、エラー・警告・チャンネル概要を返す
- `template`: 指定したモード用のテンプレートMMLを生成する

### 引数

| 引数名 | 型 | 必須 | デフォルト | 説明 |
|--------|-----|------|-----------|------|
| `action` | string | yes | - | `compose`, `validate`, `template` のいずれか |
| `mml` | string | compose/validate時 | `""` | MMLソース文字列 |
| `mode` | string | compose/validate時 | `""` | `ppmck` または `pyxel` |
| `template` | string | template時 | `"basic"` | `basic`, `melody`, `chord`, `drum`, `empty`, `expressive_lead`, `vibrato_lead`, `pitch_motion` |
| `sample_rate` | integer | no | `44100` | 出力WAVのサンプリングレート（Hz） |
| `normalize` | boolean | no | `true` | 出力振幅を正規化するか |

### 戻り値

#### action=`compose` の場合

```json
{
  "success": true,
  "wav_path": "./data/output.wav",
  "duration_sec": 2.0,
  "note_sequence": { ... },
  "validation": {
    "errors": [],
    "warnings": []
  }
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `success` | boolean | 合成・WAV出力が成功したか |
| `wav_path` | string \| null | 生成されたWAVファイルのパス（失敗時はnull） |
| `duration_sec` | number | 生成された音声の長さ（秒） |
| `note_sequence` | object \| null | 中間表現（IR）のNoteSequence |

`note_sequence`はIR v2で返される。曲全体で共有するエンベロープ/LFO定義は
`definitions`、選択・解除と演奏イベントは各`channels.*.events`に格納される。
`ppmck`は構文モード名であり、拡張コマンドのPPMCK/mckc互換を保証しない。
| `validation.errors` | array | エラーのリスト |
| `validation.warnings` | array | 警告のリスト |

#### action=`validate` の場合

```json
{
  "valid": true,
  "errors": [],
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
|-----------|-----|------|
| `valid` | boolean | MMLにerrorがないか |
| `errors` | array | エラーのリスト |
| `note_sequence` | object \| null | 中間表現（IR）のNoteSequence |
| `channel_summary` | array | チャンネルごとの統計情報 |

#### action=`template` の場合

```json
{
  "mml": "0: T120 L8 O4 V100 @1\n   C D E F | ...",
  "description": "基本的な4ch構成（メロディ+和音+ベース+リズム）"
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `mml` | string | 生成されたMMLテンプレート |
| `description` | string | テンプレートの説明 |

## エラー詳細

`errors` / `warnings` 配列の要素は以下の形式です。

```json
{
  "code": "SYNTAX_INVALID_TOKEN",
  "line": 1,
  "column": 5,
  "message": "未知のモード 'xyz' です。",
  "severity": "error",
  "hint": "mode は 'ppmck' または 'pyxel' を指定してください。",
  "context": ""
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `code` | string | エラーコード |
| `line` | integer | 発生行（0始まり） |
| `column` | integer | 発生列（0始まり） |
| `message` | string | 人間が読めるメッセージ |
| `severity` | string | `error` または `warning` |
| `hint` | string | 修正のヒント |
| `context` | string | 該当行のコンテキスト |

## サポートするMML形式

### ppmck

- トラック: `A`（Pulse1）、`B`（Pulse2）、`T`（Triangle）、`N`（Noise）
- コマンド例: `t120`（テンポ）、`l8`（音長）、`o4`（オクターブ）、`v15`（音量）、`q2`（デューティ）

### pyxel

- トラック: `0:`（Pulse1）、`1:`（Pulse2）、`2:`（Triangle）、`3:`（Noise）
- コマンド例: `T120`、`L8`、`O4`、`V100`、`@1`

## トランスポート

サーバ起動時に `--transport` で切り替え可能です。

| トランスポート | 用途 |
|---------------|------|
| `stdio` | 標準的なMCPクライアント接続（デフォルト） |
| `http` | HTTPエンドポイント |
| `sse` | Server-Sent Events |
| `streamable-http` | Streamable HTTP |

```bash
uv run mml-composemusic-mcp --transport sse --port 8080
```
