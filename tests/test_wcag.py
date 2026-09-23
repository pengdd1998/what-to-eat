
def test_wcag_contrast():
    """P0-2 回归锚：昼/夜两片全部前景/背景组合过 WCAG AA（≥4.5:1 正文级）。"""
    from app import style_tokens as st

    def lum(hexc):
        r, g, b = [int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = f(r), f(g), f(b)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def cr(a, b):
        la, lb = sorted([lum(a), lum(b)], reverse=True)
        return (la + 0.05) / (lb + 0.05)

    for theme, toks in st.TOKENS.items():
        pairs = [
            ("主钮 黄底/墨字", toks["y"], toks["y-ink"], 4.5),
            ("正文 墨字/底", toks["ink-1"], toks["bg-0"], 4.5),
            ("次级 淡墨/底", toks["ink-2"], toks["bg-0"], 4.5),
        ]
        for name, fg, bg, floor in pairs:
            ratio = cr(fg, bg)
            assert ratio >= floor, f"{theme} {name} {ratio:.2f}:{1} < {floor}:1"
