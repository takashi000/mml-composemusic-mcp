# mml-composemusic-mcp

ファミコン音源（2A03 APU）風のMMLをLLMに作曲させるためのMCPサーバ。

## 機能

- `compose_mml` ツールを提供
- ppmck 形式と pyxel 形式のMMLを解析・合成
- MIDIノート番号に変換後、NES APU風の矩形波/三角波/ノイズでWAV出力
- バリデーション、テンプレート生成に対応

## ツール引数

| 引数 | 説明 |
|------|------|
| `action` | `compose`, `validate`, `template` のいずれか |
| `mml` | MML文字列（compose/validate時必須） |
| `mode` | `ppmck` または `pyxel`（compose/validate時必須） |
| `template` | `basic`, `melody`, `chord`, `drum`, `empty`（action=template時） |
| `sample_rate` | WAV出力サンプリングレート（デフォルト44100） |
| `normalize` | 出力振幅の正規化（デフォルトtrue） |

## 実行

```bash
uv run mml-composemusic-mcp --output-dir ./data
```

または

```bash
uv run python -m mml_composemusic_mcp.server --output-dir ./data
```

## テスト

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

## ディレクトリ構成

- `src/mml_composemusic_mcp/`
  - `server.py` - MCPサーバ
  - `lexer.py` - MML字句解析
  - `parser_ppmck.py`, `parser_pyxel.py` - 構文解析
  - `ir.py` - 中間表現・エラー型
  - `synthesizer.py` - APU風合成・WAV出力
  - `templates.py` - テンプレート
- `tests/` - テスト
- `doc/` - 設計書
