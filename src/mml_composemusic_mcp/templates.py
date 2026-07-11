# MML template generators for both modes.

TEMPLATES = {
    "ppmck": {
        "basic": '#TITLE "Basic Song"\n#COMPOSER "LLM"\n\nA t120 l8 o4 v15 q2\n  c d e f | g a b > c\n\nB l8 o3 v12 q1\n  e g b r | e g b r\n\nT l4 o3 v7\n  c2 g2 e2 c2\n\nN l8 v10\n  c r c r | c r c r\n',
        "melody": '#TITLE "Melody Lead"\n#COMPOSER "LLM"\n\nA t120 l8 o5 v15 q2\n  c e g e | d f a f | e g b g | c4 r4\n\nB l8 o4 v10 q1\n  c e g e | c e g e | d f a f | c4 r4\n\nT l4 o3 v7\n  c2 g2 | a2 f2 | g2 d2 | c2 r2\n\nN l8 v8\n  c r c r | c r c r | c r c r | c r c r\n',
        "chord": '#TITLE "Chord Backing"\n#COMPOSER "LLM"\n\nA t120 l4 o4 v12 q2\n  c e g c | f a > c f | g b > d g | c e g c\n\nB l4 o4 v12 q1\n  e g b e | f a > c f | d g b d | e g b e\n\nT l2 o3 v7\n  c2 | f2 | g2 | c2\n\nN l8 v8\n  r c r c | r c r c | r c r c | r c r c\n',
        "drum": '#TITLE "Drum Beat"\n#COMPOSER "LLM"\n\nA t120 l8 o4 v15 q2\n  c r e r | g r e r | c r e r | g r c r\n\nB l8 o3 v12 q1\n  e r g r | e r g r | e r g r | e r g r\n\nT l4 o2 v7\n  c2 c2 | c2 c2 | c2 c2 | c2 c2\n\nN l16 v10\n  c r c r c r c r | c r c r c r c r\n  c r c r c r c r | c r c r c r c r\n',
        "empty": '#TITLE "Empty Template"\n#COMPOSER "LLM"\n\nA t120 l4 o4 v15 q2\n  \n\nB l4 o3 v12 q1\n  \n\nT l4 o3 v7\n  \n\nN l4 v10\n  \n',
    },
    "pyxel": {
        "basic": "0: T120 L8 O4 V100 @1\n   C D E F | G A B >C\n\n1: L8 O3 V80 @2\n   E G B R | E G B R\n\n2: L4 O3 V60\n   C2 G2 E2 C2\n\n3: L8 V80\n   C R C R | C R C R\n",
        "melody": "0: T120 L8 O5 V100 @1\n   C E G E | D F A F | E G B G | C4 R4\n\n1: L8 O4 V80 @2\n   C E G E | C E G E | D F A F | C4 R4\n\n2: L4 O3 V60\n   C2 G2 | A2 F2 | G2 D2 | C2 R2\n\n3: L8 V70\n   C R C R | C R C R | C R C R | C R C R\n",
        "chord": "0: T120 L4 O4 V90 @1\n   C E G C | F A >C F | G B >D G | C E G C\n\n1: L4 O4 V90 @2\n   E G B E | F A >C F | D G B D | E G B E\n\n2: L2 O3 V60\n   C2 | F2 | G2 | C2\n\n3: L8 V70\n   R C R C | R C R C | R C R C | R C R C\n",
        "drum": "0: T120 L8 O4 V100 @1\n   C R E R | G R E R | C R E R | G R C R\n\n1: L8 O3 V80 @2\n   E R G R | E R G R | E R G R | E R G R\n\n2: L4 O2 V60\n   C2 C2 | C2 C2 | C2 C2 | C2 C2\n\n3: L16 V80\n   C R C R C R C R | C R C R C R C R\n   C R C R C R C R | C R C R C R C R\n",
        "empty": "0: T120 L4 O4 V100 @1\n   \n\n1: L4 O3 V80 @2\n   \n\n2: L4 O3 V60\n   \n\n3: L4 V80\n   \n",
    },
}

DESCRIPTIONS = {
    "basic": "基本的な4ch構成（メロディ+和音+ベース+リズム）",
    "melody": "メロディ重視（Pulse1主旋律、他は伴奏最小限）",
    "chord": "コード伴奏重視（Pulse2で和音、Triangleでベース）",
    "drum": "リズム重視（Noise中心のビートパターン）",
    "empty": "各チャンネルのヘッダーのみ（空のテンプレート）",
}


def get_template(mode: str, template: str) -> tuple[str, str]:
    mml = TEMPLATES[mode][template]
    desc = DESCRIPTIONS[template]
    return mml, desc
