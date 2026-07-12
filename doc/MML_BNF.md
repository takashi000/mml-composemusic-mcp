# MML 構文規則（BNF）

> 本ドキュメントは `mml-composemusic-mcp` がサポートする MML の構文を BNF（Backus-Naur Form）で定義する。
> 対象モード: `ppmck`（PPMCK インスパイア形式）と `pyxel`（Pyxel MML 準拠）。

---

## 1. 共通字句要素

```bnf
/* 基本文字 */
<digit>       ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
<number>      ::= <digit>+

/* 音符名（Lexer で正規化: ppmck は小文字、pyxel は大文字 → 内部は小文字） */
<note_name>   ::= "c" | "d" | "e" | "f" | "g" | "a" | "b"

/* 変化記号 */
<sharp>       ::= "+" | "#"
<flat>        ::= "-"
<accidental>  ::= <sharp> | <flat>

/* 音長 */
<dot>         ::= "."
<length>      ::= <number> <dot>*
              | /* 省略時: デフォルト音長を使用 */

/* オクターブ */
<octave_up>   ::= ">"
<octave_down> ::= "<"

/* タイ・スラー */
<tie>         ::= "&"

/* リピート */
<repeat_start>::= "["
<repeat_end>  ::= "]" <number>?

/* 小節線 */
<bar>         ::= "|"

/* 改行・空白 */
<whitespace>  ::= " " | "\t" | "\r" | "\n"
```

---

## 2. ppmck モード

### 2.1 全体構造

```bnf
<ppmck_mml>       ::= <ppmck_header>* <ppmck_track>*

<ppmck_header>    ::= "#" <header_key> <header_value>?
<header_key>      ::= "TITLE" | "COMPOSER" | "PROGRAMER" | "OCTAVE-REV"
                    | "INCLUDE" | "EX-DISKFM" | "EX-NAMCO106" | "BANK-CHANGE"
                    | "EFFECT-INCLUDE"
<header_value>    ::= "\"" <string> "\""

<ppmck_track>     ::= <track_header> <ppmck_statement>*
<track_header>    ::= "A" | "B" | "T" | "N" | "L"
```

### 2.2 ステートメント

```bnf
<ppmck_statement> ::= <note>
                    | <rest>
                    | <octave_cmd>
                    | <length_cmd>
                    | <volume_cmd>
                    | <duty_cmd>
                    | <quantize_cmd>
                    | <tempo_cmd>
                    | <tie_cmd>
                    | <slur_cmd>
                    | <ppmck_ext_cmd>
                    | <repeat_start>
                    | <repeat_end>
                    | <bar>
                    | <comment>
                    | <newline>

<note>            ::= <note_name> <accidental>? <length>
<rest>            ::= "r" <length>

<octave_cmd>      ::= "o" <number>          /* o0 〜 o7 */
                    | <octave_up>
                    | <octave_down>

<length_cmd>      ::= "l" <number>          /* l1 〜 l192 */
<volume_cmd>      ::= "v" <number>          /* v0 〜 v15 */

<duty_cmd>        ::= "@" <number>          /* @0 〜 @3, Pulse系のみ */
<quantize_cmd>    ::= "q" <number>          /* q1 〜 q8 */
<tempo_cmd>       ::= "t" <number>          /* t1 〜 */

<tie_cmd>         ::= "^" (<note> | <number>)
<slur_cmd>        ::= "&" (<note> | <rest> | <number>)

<comment>         ::= ";" <string_to_eol>
```

### 2.3 合成拡張コマンド

```bnf
<ppmck_ext_cmd>  ::= <relative_volume_cmd>
                    | <detune_cmd>
                    | <sweep_cmd>
                    | <vol_envelope_def>
                    | <vol_envelope_use>
                    | <duty_envelope_def>
                    | <duty_envelope_use>
                    | <lfo_def>
                    | <lfo_use>
                    | <lfo_off>
                    | <pitch_env_def>
                    | <pitch_env_use>
                    | <pitch_env_off>
                    | <note_env_def>
                    | <note_env_use>
                    | <note_env_off>

<relative_volume_cmd>
                  ::= "v+" <number>?        /* 1 〜 15 */
                    | "v-" <number>?        /* 1 〜 15 */

<detune_cmd>      ::= "D" <signed_number>  /* -127 〜 126 */
<sweep_cmd>       ::= "s" <number> "," <signed_number>

<vol_envelope_def>::= "@v" <number> "=" "{" <number_list> "|" <number_list>? "}"
<vol_envelope_use>::= "@v" <number>

<duty_envelope_def>::= "@" <number> "=" "{" <number_list> "|" <number_list>? "}"
<duty_envelope_use>::= "@@" <number>

<lfo_def>        ::= "@MP" <number> "=" "{" <number> "," <number> "," <number> "," <number> "}"
<lfo_use>        ::= "MP" <number>
<lfo_off>        ::= "MPOF"

<pitch_env_def>   ::= "@EP" <number> "=" "{" <signed_number_list> "|" <signed_number_list>? "}"
<pitch_env_use>   ::= "EP" <number>
<pitch_env_off>   ::= "EPOF"

<note_env_def>    ::= "@EN" <number> "=" "{" <signed_number_list> "|" <signed_number_list>? "}"
<note_env_use>    ::= "EN" <number>
<note_env_off>   ::= "ENOF"

<signed_number>   ::= ("+" | "-")? <number>
<number_list>     ::= <number> (","? <number>)*
<signed_number_list> ::= <signed_number> (","? <signed_number>)*
```

### 2.4 将来予定コマンド（現在の受理文法には含めない）

以下は設計予約であり、現在は構文エラーになる。実装時に受理文法へ移す。

```bnf
<ppmck_stage2>    ::= <count_length>
                    | <section_repeat>
                    | <transpose_cmd>
                    | <noise_mode_cmd>

<count_length>    ::= <note_name> <accidental>? "%" <number>

<section_repeat>  ::= "[" <ppmck_statement>+ "]" <number>?

<transpose_cmd>   ::= "K" <number>
<noise_mode_cmd>  ::= "m" <number>
```


---

## 3. pyxel モード

### 3.1 全体構造

```bnf
<pyxel_mml>       ::= <pyxel_track>*

<pyxel_track>     ::= <pyxel_track_header> <pyxel_statement>*
<pyxel_track_header>
                  ::= <number> ":"        /* 0: 1: 2: 3: */
```

### 3.2 ステートメント

```bnf
<pyxel_statement> ::= <note>
                    | <rest>
                    | <octave_cmd>
                    | <length_cmd>
                    | <volume_cmd>
                    | <gate_cmd>
                    | <tone_cmd>
                    | <tempo_cmd>
                    | <transpose_cmd>
                    | <detune_cmd>
                    | <tie_cmd>
                    | <repeat_start>
                    | <repeat_end>
                    | <bar>
                    | <ext_cmd>
                    | <newline>

<note>            ::= <note_name> <accidental>? <length>
<rest>            ::= "R" <length>

<octave_cmd>      ::= "O" <number>          /* O0 〜 O7 */
                    | <octave_up>
                    | <octave_down>

<length_cmd>      ::= "L" <number>          /* L1 〜 L192 */
<volume_cmd>      ::= "V" <number>          /* V0 〜 V127 */
<gate_cmd>        ::= "Q" <number>          /* Q0 〜 Q100 */
<tone_cmd>        ::= "@" <number>          /* @0 〜 @3, Pulse系のみ有効 */
<tempo_cmd>       ::= "T" <number>          /* T1 〜 */
<signed_number>   ::= ("+" | "-")? <number>
<transpose_cmd>   ::= "K" <signed_number>   /* 半音単位 */
<detune_cmd>      ::= "Y" <signed_number>   /* セント単位 */

<tie_cmd>         ::= <tie> (<note> | <rest> | <number>)
```

### 3.3 合成拡張コマンド

```bnf
<ext_cmd>         ::= <env_cmd> | <vib_cmd> | <gli_cmd>

<env_cmd>         ::= "@ENV" <number> <env_def>?
<env_def>         ::= <number>+

<vib_cmd>         ::= "@VIB" <number> <vib_def>?
<vib_def>         ::= <number>+

<gli_cmd>         ::= "@GLI" <number> <gli_def>?
<gli_def>         ::= <number>+
```

---

## 4. トラック・チャンネル対応

| ppmck | pyxel | チャンネル | 種別 |
|---|---|---|---|
| `A` | `0:` | Pulse1 | 矩形波 |
| `B` | `1:` | Pulse2 | 矩形波 |
| `T` | `2:` | Triangle | 三角波 |
| `N` | `3:` | Noise | ノイズ |
| `L` | — | Loop | 全体ループ（ppmck のみ） |

---

## 5. 値範囲

| コマンド | モード | 有効範囲 | デフォルト | 備考 |
|---|---|---|---|---|
| `o` / `O` | 両方 | 0 〜 7 | 4 | |
| `l` / `L` | 両方 | 1 〜 192 | 4 | |
| `v` | ppmck | 0 〜 15 | 15 | |
| `V` | pyxel | 0 〜 127 | 100 | |
| `v+` / `v-` | ppmck | 1 〜 15 | 1 | 相対音量（0〜15へクランプ） |
| `@` | ppmck | 0 〜 3 | 2 | デューティ比（Pulse系のみ） |
| `@` | pyxel | 0 〜 3 | — | デューティ比（Pulse系のみ） |
| `q` | ppmck | 1 〜 8 | 8 | クオンタイズ（gate_time = value / 8） |
| `Q` | pyxel | 0 〜 100 | 80 | ゲートタイム（%） |
| `t` / `T` | 両方 | 1 〜 | 120 | |
| `D` | ppmck | -127 〜 126 | 0 | cent単位ディチューン |
| `s` | ppmck | speed 0〜7, depth ±1〜±7 | — | Pulseハードウェアスイープ |
| `@v` | ppmck | 0 〜 255 | — | 48 tick単位の音量エンベロープ |
| `@@` | ppmck | 0 〜 255 | — | 48 tick単位のデューティエンベロープ |
| `@MP` / `MP` / `MPOF` | ppmck | 0 〜 255 | — | 三角LFO |
| `@EP` / `EP` / `EPOF` | ppmck | 0 〜 255 | — | cent単位ピッチエンベロープ |
| `@EN` / `EN` / `ENOF` | ppmck | 0 〜 255 | — | 絶対半音オフセット列 |
| `K` | pyxel | -127 〜 127 | 0 | トランスポーズ（半音） |
| `Y` | pyxel | -127 〜 127 | 0 | ディチューン（セント） |

---

## 6. 備考

- 本 BNF は `mml-composemusic-mcp` の**サポート範囲**を定義するものであり、オリジナルの PPMCK や Pyxel の全機能を網羅するものではない。
- 第2段階予定コマンドは設計予約として記載するが、現在の受理文法には含めない。
- ppmck モード名は構文互換の識別子であり、拡張の挙動は本プロジェクト独自仕様である。PPMCK/mckc互換は保証しない。
- ppmck の列型エンベロープは1要素48 tickで、`|`以降を反復し、反復がなければ末尾値を保持する。`D`/`@EP`はcent、`@EN`は絶対半音、`@MP`は`delay,period,depth,0`である。
- pyxel の `@ENV` は`target,duration`組、`@VIB`は`delay,period,depth_cents`、`@GLI`は`initial_offset_cents,duration`である。slot 0は解除を表す。
- コマンド文字は ppmck では小文字、pyxel では大文字を使用する。音符・休符も同じ規則に従う。ただし ppmck の `D`（ディチューン）は大文字のみ受理する（小文字 `d` は音符）。
- `^` は ppmck モード専用のタイ、`&` は両モード共通のスラー（slur）として扱う。
- 詳細な実装アーキテクチャは [Design.md](Design.md) を参照。
