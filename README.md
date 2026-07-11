# mml-composemusic-mcp

MML (Music Macro Language) を使った作曲支援 MCP サーバー向け Python パッケージ。

## 開発環境

- Python 3.14+
- 依存管理: [uv](https://docs.astral.sh/uv/)

## セットアップ

```bash
uv sync
```

## 主要コマンド

```bash
# テスト実行
uv run pytest

# リンター・フォーマッタ実行
uv run ruff check .
uv run ruff format .

# 依存追加
uv add <package>

# 開発依存追加
uv add --dev <package>
```

## ディレクトリ構成

```
src/     # ソースコード
tests/   # テストコード
doc/     # ドキュメント