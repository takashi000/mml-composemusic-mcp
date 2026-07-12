# MML template generators for both modes.

TEMPLATES = {
    "ppmck": {
        "basic": '#TITLE "Basic Song"\n#COMPOSER "LLM"\n\nA t120 l8 o4 v15 @2\n  c d e f | g a b > c\n\nB l8 o3 v12 @1\n  e g b r | e g b r\n\nT l4 o3 v7\n  c2 g2 e2 c2\n\nN l8 v10\n  c r c r | c r c r\n',
        "melody": '#TITLE "Melody Lead"\n#COMPOSER "LLM"\n\nA t120 l8 o5 v15 @2\n  c e g e | d f a f | e g b g | c4 r4\n\nB l8 o4 v10 @1\n  c e g e | c e g e | d f a f | c4 r4\n\nT l4 o3 v7\n  c2 g2 | a2 f2 | g2 d2 | c2 r2\n\nN l8 v8\n  c r c r | c r c r | c r c r | c r c r\n',
        "chord": '#TITLE "Chord Backing"\n#COMPOSER "LLM"\n\nA t120 l4 o4 v12 @2\n  c e g c | f a > c f | g b > d g | c e g c\n\nB l4 o4 v12 @1\n  e g b e | f a > c f | d g b d | e g b e\n\nT l2 o3 v7\n  c2 | f2 | g2 | c2\n\nN l8 v8\n  r c r c | r c r c | r c r c | r c r c\n',
        "drum": '#TITLE "Drum Beat"\n#COMPOSER "LLM"\n\nA t120 l8 o4 v15 @2\n  c r e r | g r e r | c r e r | g r c r\n\nB l8 o3 v12 @1\n  e r g r | e r g r | e r g r | e r g r\n\nT l4 o2 v7\n  c2 c2 | c2 c2 | c2 c2 | c2 c2\n\nN l16 v10\n  c r c r c r c r | c r c r c r c r\n  c r c r c r c r | c r c r c r c r\n',
        "empty": '#TITLE "Empty Template"\n#COMPOSER "LLM"\n\nA t120 l4 o4 v15 @2\n  r1\n\nB l4 o3 v12 @1\n  r1\n\nT l4 o3 v7\n  r1\n\nN l4 v10\n  r1\n',
        "expressive_lead": '#TITLE "Expressive Lead"\n#COMPOSER "LLM"\n\n; Define reusable volume and duty envelopes before the tracks.\n@v1={15,12,9|7,9}\n@0={2,1|2,3}\n\nA t132 l8 o5 v15 q7 @v1 @@0\n  c e g >c | <b g e c | v-3 d f a >d | v+3 <c4 r4\n\nB l8 o4 v10 @1\n  c r g r | e r g r | d r a r | e4 r4\n\nT l4 o3 v7\n  c2 e2 | d2 c2\n\nN l8 v9\n  c r c c | c r c r | c r c c | c r c r\n',
        "vibrato_lead": '#TITLE "Vibrato Lead"\n#COMPOSER "LLM"\n\n; MP adds cyclic vibrato; EP adds a one-shot upward pitch shape.\n@MP1={12,16,18,0}\n@EP1={40,20,0|10,0}\n\nA t116 l8 o5 v15 @2 D-6 MP1\n  c4 e4 | g2 MPOF | EP1 a4 g4 | EPOF D0 e2\n\nB l8 o4 v10 @1 D6\n  c e g e | c e g e | f a >c <a | g b >d <b\n\nT l4 o3 v7\n  c2 g2 | f2 g2\n\nN l8 v8\n  c r c r | c r c r | c r c r | c r c r\n',
        "pitch_motion": '#TITLE "Pitch Motion"\n#COMPOSER "LLM"\n\n; EN creates a rapid arpeggio; sweep bends Pulse pitch over time.\n@EN1={0,4,7|12,7,4}\n\nA t144 l8 o4 v15 @2 EN1\n  c2 g2 | ENOF s2,3 >c2 <g2 | s0,-2 c1\n\nB l8 o3 v11 @1\n  c c g g | a a g4 | f f e e | d d c4\n\nT l4 o2 v7\n  c2 g2 | a2 f2 | c1\n\nN l8 v10\n  c r c c | c r c r | c r c c | c c c r\n',
    },
    "pyxel": {
        "basic": "0: T120 L8 O4 V100 @1\n   C D E F | G A B >C\n\n1: L8 O3 V80 @2\n   E G B R | E G B R\n\n2: L4 O3 V60\n   C2 G2 E2 C2\n\n3: L8 V80\n   C R C R | C R C R\n",
        "melody": "0: T120 L8 O5 V100 @1\n   C E G E | D F A F | E G B G | C4 R4\n\n1: L8 O4 V80 @2\n   C E G E | C E G E | D F A F | C4 R4\n\n2: L4 O3 V60\n   C2 G2 | A2 F2 | G2 D2 | C2 R2\n\n3: L8 V70\n   C R C R | C R C R | C R C R | C R C R\n",
        "chord": "0: T120 L4 O4 V90 @1\n   C E G C | F A >C F | G B >D G | C E G C\n\n1: L4 O4 V90 @2\n   E G B E | F A >C F | D G B D | E G B E\n\n2: L2 O3 V60\n   C2 | F2 | G2 | C2\n\n3: L8 V70\n   R C R C | R C R C | R C R C | R C R C\n",
        "drum": "0: T120 L8 O4 V100 @1\n   C R E R | G R E R | C R E R | G R C R\n\n1: L8 O3 V80 @2\n   E R G R | E R G R | E R G R | E R G R\n\n2: L4 O2 V60\n   C2 C2 | C2 C2 | C2 C2 | C2 C2\n\n3: L16 V80\n   C R C R C R C R | C R C R C R C R\n   C R C R C R C R | C R C R C R C R\n",
        "empty": "0: T120 L4 O4 V100 @1\n   R1\n\n1: L4 O3 V80 @2\n   R1\n\n2: L4 O3 V60\n   R1\n\n3: L4 V80\n   R1\n",
        "expressive_lead": "0: T132 L8 O5 V110 Q90 @1 @ENV1 110 24 80 24 45 48\n   C E G >C | <B G E C | @ENV0 D F A >D | <C4 R4\n\n1: L8 O4 V75 @2\n   C R G R | E R G R | D R A R | E4 R4\n\n2: L4 O3 V60\n   C2 E2 | D2 C2\n\n3: L8 V75\n   C R C C | C R C R | C R C C | C R C R\n",
        "vibrato_lead": "0: T116 L8 O5 V110 @1 Y-6 @VIB1 12 16 18\n   C4 E4 | G2 @VIB0 | @VIB1 A4 G4 | @VIB0 Y0 E2\n\n1: L8 O4 V75 @2 Y6\n   C E G E | C E G E | F A >C <A | G B >D <B\n\n2: L4 O3 V60\n   C2 G2 | F2 G2\n\n3: L8 V70\n   C R C R | C R C R | C R C R | C R C R\n",
        "pitch_motion": "0: T144 L8 O4 V110 @2 @GLI1 700 48\n   C2 G2 | @GLI0 K12 C2 K0 G2 | @GLI1 C1\n\n1: L8 O3 V80 @1\n   C C G G | A A G4 | F F E E | D D C4\n\n2: L4 O2 V60\n   C2 G2 | A2 F2 | C1\n\n3: L8 V80\n   C R C C | C R C R | C R C C | C C C R\n",
    },
}

DESCRIPTIONS = {
    "basic": "基本的な4ch構成（メロディ+和音+ベース+リズム）",
    "melody": "メロディ重視（Pulse1主旋律、他は伴奏最小限）",
    "chord": "コード伴奏重視（Pulse2で和音、Triangleでベース）",
    "drum": "リズム重視（Noise中心のビートパターン）",
    "empty": "各チャンネルのヘッダーのみ（空のテンプレート）",
    "expressive_lead": "音量・音色エンベロープで表情を付けるリード",
    "vibrato_lead": "ビブラート・ピッチ変化・デチューンを使うリード",
    "pitch_motion": "アルペジオ・スイープ・グライドによる大きな音程変化",
}


def get_template(mode: str, template: str) -> tuple[str, str]:
    mml = TEMPLATES[mode][template]
    desc = DESCRIPTIONS[template]
    return mml, desc
