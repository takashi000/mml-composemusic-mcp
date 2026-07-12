# mml-composemusic-mcp

LLMにMMLを書かせ、レトロゲーム機風の音楽をWAVとして生成するMCPサーバです。

Pulse 2ch、Triangle 1ch、Noise 1chの構成を持つ簡易2A03 APU風シンセサイザーを内蔵しています。MCPクライアントから単一の`compose_mml`ツールを呼び出すことで、作曲、検証、作例テンプレートの取得まで行えます。

> [!IMPORTANT]
> `ppmck`と`pyxel`は、このプロジェクトが受理するMML構文モードの名前です。オリジナルのPPMCK/mckcやPyxelとの完全な互換性は保証しません。

## 主な機能

- MMLを解析し、モノラル16-bit PCMのWAVファイルを生成
- 構文・値域・チャンネル適合性を合成前に検証
- Pulse1、Pulse2、Triangle、Noiseの4チャンネルに対応
- ppmck風の小文字MMLと、Pyxel風の大文字MMLに対応
- 音量・音色エンベロープ、ビブラート、LFO、グライド、スイープなどを合成へ反映
- LLMがコピーして改変できる8種類の作例テンプレートを収録
- stdio、HTTP、SSE、Streamable HTTPトランスポートに対応

## サンプルデータ

実際にLLMを使用してこのMCPツールで作曲させてみたサンプルデータです。
ppmck版
- [音声](samples/ppmck/output.wav)
- [mml](samples/ppmck/output.mml)

pyxel版
- [音声](samples/pyxel/output.wav)
- [mml](samples/pyxel/output.mml)

## 必要環境

- Python 3.14以上
- [uv](https://docs.astral.sh/uv/)（推奨）

## セットアップ

リポジトリを取得し、プロジェクトのディレクトリで依存関係をインストールします。

```bash
uv sync
uv run mml-composemusic-mcp --help
```

pipを使う場合は、仮想環境内で次のようにインストールできます。

```bash
python -m pip install -e .
mml-composemusic-mcp --help
```

## MCPクライアントへの登録

標準入出力で起動する設定例です。`C:\path\to\mml-composemusic-mcp`と出力先を実際の絶対パスへ置き換えてください。

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

`--output-dir`を省略した場合は、サーバの作業ディレクトリにある`./data`へ出力します。MCPクライアントによって作業ディレクトリが異なるため、通常は絶対パスの指定を推奨します。

HTTP系トランスポートで手動起動する場合は、次のオプションを利用できます。

```bash
uv run mml-composemusic-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8080 \
  --output-dir ./data
```

利用可能な`--transport`は`stdio`（デフォルト）、`http`、`sse`、`streamable-http`です。HTTP側の接続URLは、使用するFastMCPとMCPクライアントのトランスポート設定に合わせてください。

## LLMからの使い方

公開されるツールは`compose_mml`の1つです。基本的には、テンプレートを取得して編集し、検証してから合成します。

1. `action: "template"`で作例を取得する
2. 作りたい曲に合わせてLLMがMMLを書き換える
3. `action: "validate"`でエラーと警告を確認する
4. 問題がなければ`action: "compose"`でWAVを生成する

MCPクライアントでは、たとえば次のように依頼できます。

> pyxelモードのvibrato_leadテンプレートを参考に、テンポ150の明るい8小節のボス戦BGMを作ってください。まずvalidateし、問題を直してからcomposeしてください。

### `compose_mml`の引数

| 引数 | 型 | 使用するaction | デフォルト | 説明 |
|---|---|---|---|---|
| `action` | string | すべて | 必須 | `template`、`validate`、`compose` |
| `mode` | string | すべて | `""` | `ppmck`または`pyxel` |
| `mml` | string | validate/compose | `""` | 検証・合成するMML |
| `template` | string | template | `"basic"` | 取得するテンプレート名 |
| `sample_rate` | integer | compose | `44100` | WAVのサンプリング周波数 |
| `normalize` | boolean | compose | `true` | 合成後に振幅を正規化するか |

未知の`mode`をtemplateで指定した場合は`ppmck`、未知のテンプレート名を指定した場合は`basic`へフォールバックします。validate/composeでは`mml`と`mode`が必須です。

### テンプレートを取得する

```json
{
  "action": "template",
  "mode": "pyxel",
  "template": "vibrato_lead"
}
```

| テンプレート | 用途 |
|---|---|
| `basic` | メロディ、伴奏、ベース、リズムの基本4ch構成 |
| `melody` | Pulse1の主旋律を中心にした構成 |
| `chord` | Pulseのコード伴奏とTriangleベースを中心にした構成 |
| `drum` | Noiseのビートを中心にした構成 |
| `empty` | 各チャンネルを休符だけにした最小構成 |
| `expressive_lead` | 音量・音色エンベロープを使うリード |
| `vibrato_lead` | ビブラート、ピッチ変化、デチューンを使うリード |
| `pitch_motion` | アルペジオ、スイープ、グライドを使う効果的な音程変化 |

テンプレートは両モードに用意され、同じ目的を各モード固有のコマンドで表現します。

### MMLを検証する

```json
{
  "action": "validate",
  "mode": "ppmck",
  "mml": "A t120 l8 o4 v15 q7 @2\n  c d e f | g a b >c"
}
```

`valid`、`errors`、`warnings`に加え、解析済みの`note_sequence`とチャンネルごとの`channel_summary`を返します。エラーには行・列、原因、修正ヒントが含まれます。

### WAVを生成する

```json
{
  "action": "compose",
  "mode": "pyxel",
  "mml": "0: T120 L8 O4 V100 Q90 @1\n   C D E F | G A B >C",
  "sample_rate": 44100,
  "normalize": true
}
```

成功時は`success: true`、`wav_path`、`duration_sec`、解析済みの`note_sequence`を返します。指定した出力ディレクトリの下に生成時刻を表す`YYYYMMDD_HHMMSS_mmm`ディレクトリを作り、`output.wav`と、合成に使用したMML原文の`output.mml`を保存します。

`wav_path`はMCPサーバが動作しているマシン上のローカルパスです。リモートのHTTPサーバとして運用する場合、このツール自体はWAVのダウンロード配信を行いません。

## MMLの書き方

### チャンネル対応

| 音源 | ppmck | pyxel | 特徴 |
|---|---|---|---|
| Pulse1 | `A` | `0:` | デューティ比を変更できる矩形波 |
| Pulse2 | `B` | `1:` | デューティ比を変更できる矩形波 |
| Triangle | `T` | `2:` | 主にベース向けの三角波 |
| Noise | `N` | `3:` | ドラムや効果音向けのノイズ |
| Loop | `L` | — | ppmckのループトラック |

ppmckは音符と基本コマンドに小文字、pyxelは大文字を使います。

### ppmckモード

```mml
#TITLE "My Song"
#COMPOSER "LLM"

A t150 l8 o4 v15 q7 @2
  c d e f | g a b >c

B l8 o3 v11 @1
  c r g r | c r g r

T l4 o2 v7
  c2 g2 | a2 f2

N l8 v10
  c r c c | c r c r
```

主な拡張機能:

- `D`: セント単位のデチューン
- `s`: Pulseハードウェアスイープ
- `v+` / `v-`: 相対音量
- `@v` / `@@`: 音量・デューティエンベロープ
- `@MP` / `MP` / `MPOF`: LFOの定義・適用・解除
- `@EP` / `EP` / `EPOF`: ピッチエンベロープ
- `@EN` / `EN` / `ENOF`: 高速アルペジオ向けノートエンベロープ
- `^`: タイ、`&`: スラー

### pyxelモード

```mml
0: T150 L8 O4 V110 Q90 @1
   C D E F | G A B >C

1: L8 O3 V80 @2
   C R G R | C R G R

2: L4 O2 V60
   C2 G2 | A2 F2

3: L8 V80
   C R C C | C R C R
```

主な拡張機能:

- `K`: 半音単位のトランスポーズ
- `Y`: セント単位のデチューン
- `@ENV`: 音量エンベロープ
- `@VIB`: ビブラート
- `@GLI`: グライド
- `[...]N`: 回数付きリピート
- `&`: スラー

値域や正確な文法は[MML構文規則](doc/MML_BNF.md)、MCPの入出力は[MCPツール仕様](doc/mcp.md)、内部構造は[設計書](doc/Design.md)を参照してください。

## 現在の制約

- DPCM、NSF出力、GUI、Webプレイヤーはありません。
- 実機や既存ドライバの音を厳密に再現するエミュレーターではありません。
- Pulse専用コマンドをTriangleやNoiseへ指定すると、エラーまたは警告になります。
- ppmckの区間リピートなど、設計上予約されていても未実装の構文があります。
- pyxelの無限リピートは安全のため有限回で打ち切られ、警告が返る場合があります。

## 開発

```bash
# 全テスト
uv run pytest

# lint
uv run ruff check .

# format
uv run ruff format .

# stdioサーバを手動起動
uv run mml-composemusic-mcp --output-dir ./data
```

受理するMML文法を変更する場合は、実装・テストと合わせて`doc/MML_BNF.md`を更新してください。

## ライセンス

MIT
