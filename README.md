# mml-composemusic-mcp

レトロチップ音源（2A03 APU）風のMMLをLLMに作曲させるためのMCPサーバです。

`compose_mml` という1つのツールで、MMLの**作曲（WAV生成）**、**構文検証**、**テンプレート生成**を行えます。

---

## 目次

1. [機能概要](#機能概要)
2. [動作環境](#動作環境)
3. [インストール](#インストール)
4. [MCPクライアントへの登録](#mcpクライアントへの登録)
5. [ツールの使い方](#ツールの使い方)
6. [MML形式](#mml形式)
7. [テスト・開発](#テスト開発)
8. [ディレクトリ構成](#ディレクトリ構成)
9. [ライセンス](#ライセンス)

---

## 機能概要

| 機能 | 説明 |
|---|---|
| `compose` | MMLを解析し、レトロAPU風の矩形波/三角波/ノイズでWAVファイルを生成する |
| `validate` | MMLの構文を検証し、エラー・警告・チャンネル概要を返す |
| `template` | `ppmck` / `pyxel` 用のテンプレートMMLを生成する |

### 対応MML形式

| モード | 特徴 |
|---|---|
| `ppmck` | PPMCKインスパイアのクラシックAPU準拠形式。小文字コマンド、`A`/`B`/`T`/`N` トラック |
| `pyxel` | Pyxel MML準拠形式。大文字コマンド、`0:`〜`3:` トラック、リピート・ゲートタイム対応 |

---

## 動作環境

- Python 3.14 以上
- [uv](https://docs.astral.sh/uv/)（推奨）
- 依存パッケージ: `fastmcp`, `numpy`

---

## インストール

### 1. リポジトリをクローンまたは配置

```bash
cd C:\\path\\to\\mml-composemusic-mcp
```

### 2. 依存関係をインストール

`uv` を使う場合:

```bash
uv sync
```

`pip` を使う場合:

```bash
pip install -e .
```

### 3. 起動確認

```bash
uv run mml-composemusic-mcp --help
```

以下のように表示されればOKです。

```
usage: mml-composemusic-mcp [-h] [--output-dir OUTPUT_DIR]
       [--transport {stdio,http,sse,streamable-http}] [--host HOST] [--port PORT]
```

---

## MCPクライアントへの登録

### Claude Desktop の場合

1. 設定ファイルを開きます。

   | OS | パス |
   |---|---|
   | Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
   | macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

2. `mcpServers` に以下を追加します。

   ```json
   {
     "mcpServers": {
       "mml-composemusic": {
         "command": "uv",
         "args": [
           "run",
           "--project",
           "C:\\path\\to\\mml-composemusic-mcp",
           "mml-composemusic-mcp",
           "--output-dir",
           "C:\\path\\to\\mml-composemusic-mcp\\data"
         ]
       }
     }
   }
   ```

3. Claude Desktop を再起動します。

### 設定ファイル例

[`doc/mcp-client-config-example.json`](doc/mcp-client-config-example.json) に設定例があります。必要に応じてコピーしてください。

### トランスポートの選択

| トランスポート | 用途 | 設定方法 |
|---|---|---|
| `stdio` | 標準的なMCPクライアント接続（デフォルト） | `command`/`args` で指定 |
| `http` | HTTPエンドポイント | `--transport http` で起動後、`url` で接続 |
| `sse` | Server-Sent Events | `--transport sse` で起動後、`url` で接続 |
| `streamable-http` | Streamable HTTP | `--transport streamable-http` で起動 |

#### SSEで使う場合の例

```bash
uv run mml-composemusic-mcp --transport sse --port 8080 --output-dir ./data
```

```json
{
  "mcpServers": {
    "mml-composemusic": {
      "url": "http://127.0.0.1:8080/sse"
    }
  }
}
```

### 注意点

- `--output-dir` は相対パスでも動きますが、MCPクライアントの作業ディレクトリが不定なため、**絶対パスを推奨**します。
- 初回起動時は `uv` が依存関係を解決するため、少し時間がかかることがあります。

---

## ツールの使い方

### ツール名

`compose_mml`

### 引数

| 引数名 | 型 | 必須 | デフォルト | 説明 |
|---|---|---|---|---|
| `action` | string | yes | — | `compose`, `validate`, `template` のいずれか |
| `mml` | string | compose/validate時 | `""` | MMLソース文字列 |
| `mode` | string | compose/validate時 | `""` | `ppmck` または `pyxel` |
| `template` | string | template時 | `"basic"` | `basic`, `melody`, `chord`, `drum`, `empty` |
| `sample_rate` | integer | no | `44100` | 出力WAVのサンプリングレート（Hz） |
| `normalize` | boolean | no | `true` | 出力振幅を正規化するか |

### action=`compose` — WAVを生成

```json
{
  "action": "compose",
  "mml": "0: T120 L8 O4 V100 @1\n   C D E F | G A B >C",
  "mode": "pyxel",
  "sample_rate": 44100,
  "normalize": true
}
```

#### 戻り値

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

- `success` が `false` の場合、`wav_path` は `null` になります。
- エラーがある場合は `validation.errors` に詳細なエラー情報が入ります。

### action=`validate` — 構文チェック

```json
{
  "action": "validate",
  "mml": "A t120 l8 o4 v15 q2\n  c d e f",
  "mode": "ppmck"
}
```

#### 戻り値

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

### action=`template` — テンプレート生成

```json
{
  "action": "template",
  "mode": "pyxel",
  "template": "basic"
}
```

#### 戻り値

```json
{
  "mml": "0: T120 L8 O4 V100 @1\n   C D E F | ...",
  "description": "基本的な4ch構成（メロディ+和音+ベース+リズム）"
}
```

### テンプレート種別

| テンプレート | 内容 |
|---|---|
| `basic` | 基本的な4ch構成（メロディ+和音+ベース+リズム） |
| `melody` | メロディ重視（Pulse1主旋律、他は伴奏最小限） |
| `chord` | コード伴奏重視（Pulse2で和音、Triangleでベース） |
| `drum` | リズム重視（Noise中心のビートパターン） |
| `empty` | 各チャンネルのヘッダーのみ（空のテンプレート） |

---

## MML形式

### ppmck 形式の例

```
#TITLE "My Song"
#COMPOSER "LLM"

A t150 l8 o4 v15 q2
  c d e f | g a b > c

B l8 o3 v12 q1
  c r g r c r g r

T l4 o3 v7
  c2 c2 g2 g2

N l8 v10
  r c r c r c r c
```

### pyxel 形式の例

```
0: T150 L8 O4 V100 @1
   C D E F G A B >C

1: L8 O3 V80 @2
   E G B R E G B R

2: L4 O3 V60
   C2 G2 E2 C2

3: L8 V80
   C R C R C R C R
```

### 詳細仕様

詳細なMMLコマンド仕様、IR構造、エラーコードは [`doc/Design.md`](doc/Design.md) を参照してください。

---

## テスト・開発

### テスト実行

```bash
uv run pytest
```

### リント・フォーマット

```bash
uv run ruff check .
uv run ruff format .
```

### 手動でサーバを起動

```bash
uv run mml-composemusic-mcp --output-dir ./data
```

または:

```bash
uv run python -m mml_composemusic_mcp.server --output-dir ./data
```

---

## ディレクトリ構成

```
.
├── doc/                          # 設計書・設定例
│   ├── Design.md                 # 統合設計書
│   ├── mcp.md                    # MCPツールスキーマ
│   └── mcp-client-config-example.json  # MCPクライアント設定例
├── src/mml_composemusic_mcp/     # ソースコード
│   ├── server.py                 # MCPサーバ
│   ├── lexer.py                  # MML字句解析
│   ├── parser_ppmck.py           # ppmckパーサ
│   ├── parser_pyxel.py           # pyxelパーサ
│   ├── parser_base.py            # パーサ共通処理
│   ├── ir.py                     # 中間表現・エラー型
│   ├── synthesizer.py            # APU風合成・WAV出力
│   └── templates.py              # テンプレート
├── tests/                        # テスト
├── README.md                     # このファイル
└── pyproject.toml                # プロジェクト設定
```

---

## ライセンス

MIT
