ErrorDetail に `code`（機械処理用のエラーコード）を追加して、エラー種類ごとにメッセージテンプレートとhintを規定します。大きく **構文エラー** と **システムエラー** の2種に分けます。

---

## ErrorDetail 構造（改訂）

```
{
  code: string,               # エラーコード（機械処理用、LLMがパターン認識可能）
  line: int,                  # 行番号
  column: int,                # 列番号
  message: string,            # エラーメッセージ（プレースホルダ展開済み）
  severity: "error" | "warning",
  hint: string,               # LLM向けの修正ヒント
  context: string             # 該当箇所の周辺テキスト（任意）
}
```

> `code` を追加しました。LLMは `code` を見てエラーパターンを分類し、`hint` に従って修正できます。`context` は該当行のテキスト前後を切り出したもので、LLMが位置を特定しやすくなります。

---

## エラーコード仕様

### 構文エラー（SYNTAX_*）

LLMがMML記述を修正する対象。`hint` に具体的な修正例を含める。

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
| `SYNTAX_NOTE_OUT_OF_RANGE` | MIDI音番号が0-127を逸脱 | `音高が範囲外です（MIDI音番号 {note_number}）。オクターブ {octave} の音符 '{note}' は生成できません。` | `オクターブを調整してください。有効範囲: o{min_oct}〜o{max_oct}。` | warning（クランプ） |
| `SYNTAX_CHANNEL_MISMATCH` | チャンネルに不適切なコマンド | `チャンネル '{channel}' で '{command}' は使用できません。` | `{channel_description}。コマンドを削除するか、適切なチャンネルに移動してください。` | warning（無視） |
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

---

### システムエラー（SYSTEM_*）

LLMの修正対象外。内部処理の失敗。`hint` は空または「再試行してください」程度。

| code | trigger | message テンプレート | hint | severity |
|---|---|---|---|---|
| `SYSTEM_SYNTHESIS_FAILED` | 音声合成中のnumpy演算エラー等 | `音声合成中にエラーが発生しました: {detail}` | `MMLの内容を確認の上、再度お試しください。問題が続く場合は、短いMMLから試してください。` | error |
| `SYSTEM_WAV_WRITE_FAILED` | WAVファイル出力の失敗 | `WAVファイルの出力に失敗しました: {detail}` | `しばらく待ってから再度お試しください。` | error |
| `SYSTEM_INTERNAL_ERROR` | 予期しない例外 | `内部エラーが発生しました: {detail}` | `MMLの内容を確認の上、再度お試しください。` | error |

> システムエラーは `compose` actionでのみ発生しうる。`validate` / `template` actionでは構文エラー以外は返らない設計。

---

### エラーレスポンスの実例

#### 構文エラーの例（LLMが修正可能）

```json
{
  "code": "SYNTAX_UNTERMINATED_REPEAT",
  "line": 5,
  "column": 18,
  "message": "リピート '[' に対応する ']' が見つかりません。",
  "severity": "error",
  "hint": "] を追加してリピートを閉じてください。回数指定（例: ]2）も可能です。",
  "context": "  [ c d e f | g a b > c"
}
```

LLMはこれを見て、「5行目の `[` に `]` を追加すればいい」と判断できる。

#### 値範囲外の例

```json
{
  "code": "SYNTAX_VALUE_OUT_OF_RANGE",
  "line": 2,
  "column": 7,
  "message": "'v' の値 20 は範囲外です。有効範囲: 0〜15。",
  "severity": "error",
  "hint": "例: v15 のように指定してください。",
  "context": "A t150 l8 o4 v20 q2"
}
```

#### システムエラーの例

```json
{
  "code": "SYSTEM_SYNTHESIS_FAILED",
  "line": 0,
  "column": 0,
  "message": "音声合成中にエラーが発生しました: frequency calculation overflow at note_number 135",
  "severity": "error",
  "hint": "MMLの内容を確認の上、再度お試しください。問題が続く場合は、短いMMLから試してください。",
  "context": ""
}
```

---

### エラー発生時のcompose_mml戻り値（改訂）

```
compose action で ERROR がある場合:

{
  success: false,
  wav_path: null,              # WAVは生成しない
  duration_sec: 0,
  note_sequence: null,          # 解析途中で停止した場合はnull
  validation: {
    errors: [ErrorDetail, ...], # 構文エラー・システムエラー
    warnings: [ErrorDetail, ...] # warningはerrorsとは別に格納
  }
}
```

> warnings も ErrorDetail 構造で返す（severity = "warning"）。LLMは warnings を見て「修正しなくても動くが、改善できる」ことを把握できる。

---

これで、エラーまわりの仕様を規定しました。構文エラーは14種類、システムエラーは3種類。LLMが `code` を見てパターン認識し、`hint` に従って修正できる構造になっています。
