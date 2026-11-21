#!/usr/bin/env python3
"""リーマン ζ 関数の位相図(偏角を色で表した図)を画像にする。2 種類を出力する。

  band … 図 1 の上段。横が t = Im s(0 〜 60)、縦が σ = Re s(上が大きい。2.5 〜 −8)。
  hero … 巻頭の図版。複素平面のふつうの向きで、横が σ(−56 〜 4)、縦が t(下が 0、上が 40)。
         臨界線 Re s = 1/2 は右寄りの縦線になり、零点がその上に縦に並ぶ。

どちらも縦横の縮尺は同じ(等角)。色は ζ(s) の偏角 φ だけで決める(絶対値は使わない)。
墨・藍・朱の 3 色刷りに見立ててある。

  φ = 0    (正の実数)   … 紙の色(何も刷らない)
  φ = +π/2 (+i の向き) … 藍
  φ = ±π   (負の実数)   … 墨(暗い紙面では白)
  φ = −π/2 (−i の向き) … 朱

明るさは cos φ の単調な関数、色みは |sin φ| に比例させてあり、一周して元に戻る。
零点では 4 色すべてが 1 点に集まる。明るい紙面用と暗い紙面用の 2 枚ずつを出力する。

画像は「紙の上のインク」として書き出す。紙の色のところは完全に透明で、色の濃いところほど不透明になる
(紙の色の上に重ねると、ちょうど上の配色になる)。紙の地模様が、刷りの薄いところでは透けて見える。
Re s が大きい側の端は、さらに透明へぼかしてある。

外部ライブラリは Pillow だけ(数値計算は倍精度の複素数演算)。
  * Re s ≥ 1/2 … Euler–Maclaurin の和公式で直接計算
  * Re s < 1/2 … 関数等式 ζ(s) = 2^s π^{s−1} sin(πs/2) Γ(1−s) ζ(1−s) で右半平面の値から求める
    (左半平面で和公式を直接使うと、大きな値どうしの打ち消しで桁落ちするため)
検算: 既知の特殊値、scripts/gen_zeta_figure.py の実装との一致、文献値の零点。

使い方: python3 -I scripts/gen_zeta_phase.py site/src/assets [band|hero|all]
        python3 -I scripts/gen_zeta_phase.py --palette             # 紙面で使う色コードを表示
"""
import cmath
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_zeta_figure as ref  # noqa: E402  (同じディレクトリにある、図 1 下段用の実装)

N_TERMS = 48                     # Euler–Maclaurin で直接足す項数(|s| < 2πN で補正項が収束する)
SUPERSAMPLE = 2                  # 計算はこの倍率で行い、縮小して滑らかにする
LN2, LNPI, HALF_PI = math.log(2.0), math.log(math.pi), math.pi / 2

# 図の範囲。fade: Re s がこの範囲で 不透明 → 透明
BAND = {"t": (0.0, 60.0), "sigma": (-8.0, 2.5), "fade": (1.5, 2.5), "px_per_unit": 30}
HERO = {"t": (0.0, 40.0), "sigma": (-56.0, 4.0), "fade": (1.5, 4.0), "px_per_unit": 20}

# 色(OKLCH)。紙の色はサイトの CSS(site/src/styles/global.css の --paper)と同じ値にする。
HUE_AI, HUE_SHU = 262.0, 38.0
THEMES = {
    # paper: 紙の色(φ = 0)、far: φ = π での明るさ、ai / shu: φ = ±π/2 での(明るさ, 彩度)
    "light": {"paper": (0xFB, 0xFA, 0xF6), "far": 0.20, "ai": (0.47, 0.170), "shu": (0.62, 0.190)},
    "dark": {"paper": (0x10, 0x14, 0x1C), "far": 0.94, "ai": (0.64, 0.150), "shu": (0.68, 0.175)},
}


def srgb_to_oklab(rgb):
    lin = []
    for v in rgb:
        v /= 255
        lin.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = lin
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def oklab_to_srgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    out = []
    for v in rgb:
        v = min(1.0, max(0.0, v))
        v = 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
        out.append(int(round(255 * v)))
    return tuple(out)


def oklch_to_srgb(L, C, h_deg):
    h = math.radians(h_deg)
    return oklab_to_srgb(L, C * math.cos(h), C * math.sin(h))


AI_AB = (math.cos(math.radians(HUE_AI)), math.sin(math.radians(HUE_AI)))
SHU_AB = (math.cos(math.radians(HUE_SHU)), math.sin(math.radians(HUE_SHU)))


def make_phase_color(theme):
    """位相 → sRGB。φ = 0 でちょうど紙の色、φ = π で far、φ = ±π/2 で藍・朱になる。

    明るさは cos φ の 2 次式 L = a + b cos φ + c cos²φ(3 点を通り、cos φ について単調)。
    """
    th = THEMES[theme]
    pl, pa, pb = srgb_to_oklab(th["paper"])
    far = th["far"]
    b_coef = (pl - far) / 2
    sides = []
    for (l_flank, chroma), ab in ((th["ai"], AI_AB), (th["shu"], SHU_AB)):
        c_coef = (pl + far) / 2 - l_flank
        assert abs(2 * c_coef) < abs(b_coef), "明るさが cos φ について単調でない"
        sides.append((l_flank, c_coef, chroma, ab))

    def color(phi):
        cs, sn = math.cos(phi), math.sin(phi)
        l_flank, c_coef, chroma, ab = sides[0] if sn >= 0 else sides[1]
        L = l_flank + b_coef * cs + c_coef * cs * cs
        k = chroma * abs(sn)
        a, b = k * ab[0], k * ab[1]
        if cs > 0:
            w = cs ** 4 * (1 - abs(sn))      # φ = 0 の近くだけ、紙のわずかな色みへ寄せる
            a, b = a + (pa - a) * w, b + (pb - b) * w
        return oklab_to_srgb(L, a, b)

    return color


def as_ink(target, paper):
    """紙の色 paper の上に重ねると target になる、いちばん透明な (R, G, B, A) を返す。

    ブラウザの合成と同じく、sRGB の値のまま 紙 × (1 − α) + インク × α で考える。
    """
    # 明るい紙ではインクは紙を暗くするだけ、暗い紙では明るくするだけ、とする。
    # (ごく淡い藍で青だけが紙より明るくなる、といった画素が不透明になって地模様を隠すのを防ぐ)
    if sum(paper) > 382:
        target = tuple(min(t, p) for t, p in zip(target, paper))
    else:
        target = tuple(max(t, p) for t, p in zip(target, paper))
    alpha = 0.0
    for t, p in zip(target, paper):
        if t < p:
            alpha = max(alpha, (p - t) / p)
        elif t > p:
            alpha = max(alpha, (t - p) / (255 - p))
    if alpha < 1 / 510:
        return (paper[0], paper[1], paper[2], 0.0)
    ink = tuple(min(255.0, max(0.0, p + (t - p) / alpha)) for t, p in zip(target, paper))
    return ink + (alpha,)


def hexrgb(c):
    return "#%02x%02x%02x" % c


def em_column(t, sigmas, pows):
    """Euler–Maclaurin。t を固定して、各 σ(≥ 1/2 を想定)での ζ(σ + it) を返す。pows[i][n-1] = n^{-σ_i}。"""
    n_terms = N_TERMS
    b = [cmath.exp(complex(0.0, -t * math.log(n))) for n in range(1, n_terms + 1)]   # n^{-it}
    nn = n_terms * n_terms
    out = []
    for sig, a in zip(sigmas, pows):
        s = complex(sig, t)
        total = 0j
        for x, y in zip(a, b):
            total += x * y
        q = a[-1] * b[-1]                       # N^{-s}
        total -= 0.5 * q                        # 最後の項は 1/2 だけ
        total += n_terms * q / (s - 1)
        term = s * q / n_terms
        fact = 2.0
        for k, bern in enumerate(ref.BERNOULLI, start=1):
            total += bern / fact * term
            term *= (s + 2 * k - 1) * (s + 2 * k) / nn
            fact *= (2 * k + 1) * (2 * k + 2)
        out.append(total)
    return out


def chi(s):
    """関数等式の因子 χ(s) = 2^s π^{s−1} sin(πs/2) Γ(1−s)(Re s < 1 で使う)。"""
    return cmath.exp(s * LN2 + (s - 1) * LNPI + ref.log_gamma(1 - s)) * cmath.sin(HALF_PI * s)


def zeta_column(t, sigmas, pows_reflected):
    """各 σ での ζ(σ + it)。pows_reflected[i] は max(σ_i, 1 − σ_i) に対する n^{-σ'} の表。"""
    refl = [sig if sig >= 0.5 else 1 - sig for sig in sigmas]
    vals = em_column(t, refl, pows_reflected)
    out = []
    for sig, v in zip(sigmas, vals):
        if sig >= 0.5:
            out.append(v)
        else:
            out.append(chi(complex(sig, t)) * v.conjugate())     # ζ(1−s) = conj ζ((1−σ) + it)
    return out


def pow_table(sigmas):
    return [[n ** -(sig if sig >= 0.5 else 1 - sig) for n in range(1, N_TERMS + 1)] for sig in sigmas]


def zeta_point(s):
    return zeta_column(s.imag, [s.real], pow_table([s.real]))[0]


def self_check():
    # 特殊値(負の整数での値は関数等式の側を通る)
    assert abs(zeta_point(2 + 0j) - math.pi ** 2 / 6) < 1e-11
    assert abs(zeta_point(0.5 + 0j) + 1.4603545088095868) < 1e-11
    assert abs(zeta_point(1e-6 + 0j) + 0.5 + 0.9189385332e-6) < 1e-9      # ζ(0) = −1/2、ζ'(0) = −log√(2π)。s = 0 そのものは関数等式の極に当たる
    assert abs(zeta_point(-1 + 0j) + 1 / 12) < 1e-11
    assert abs(zeta_point(-3 + 0j) - 1 / 120) < 1e-11
    assert abs(zeta_point(-5 + 0j) + 1 / 252) < 1e-11
    assert abs(zeta_point(-7 + 0j) - 1 / 240) < 1e-11
    assert abs(zeta_point(-11 + 0j) - 691 / 32760) < 1e-11
    for k in (2, 4, 6, 8, 20, 40):
        v = zeta_point(complex(-k, 0))
        scale = abs(zeta_point(complex(-k + 1, 0)))
        assert abs(v) < 1e-11 * max(1.0, scale), (k, v)            # 自明な零点
    # 図 1 下段用の実装(N = 60 項の和公式を直接使う)との一致。その実装が桁落ちしない範囲で比べる
    worst = 0.0
    for sig in (-2.0, -1.0, 0.25, 0.5, 1.5, 2.5, 4.0):
        for t in (0.3, 7.0, 21.0, 44.4, 60.0):
            s = complex(sig, t)
            a, b = zeta_point(s), ref.zeta(s)
            worst = max(worst, abs(a - b) / abs(b))
    assert worst < 1e-7, worst      # 左半平面では比較相手(直接計算)の側が 1e-8 程度まで桁落ちする
    # 文献値の零点で |ζ| が十分小さい(零点の値は小数 6 桁なので 1e-5 程度が限界)
    zmax = max(abs(zeta_point(complex(0.5, g))) for g in ref.KNOWN_ZEROS)
    assert zmax < 2e-5, zmax
    return worst, zmax


def fade_alpha(sig, fade):
    x = min(1.0, max(0.0, (fade[1] - sig) / (fade[1] - fade[0])))
    return int(round(255 * x * x * (3 - 2 * x)))


def render(spec, name, outdir, t_axis):
    """t_axis = "x": 横が t・縦が σ(band)。t_axis = "y": 横が σ・縦が t で下が t の小さい側(hero)。"""
    from PIL import Image

    (t0, t1), (s0, s1) = spec["t"], spec["sigma"]
    ppu = spec["px_per_unit"] * SUPERSAMPLE
    nt, ns = int(round((t1 - t0) * ppu)), int(round((s1 - s0) * ppu))
    ts = [t0 + (j + 0.5) * (t1 - t0) / nt for j in range(nt)]
    w, h = (nt, ns) if t_axis == "x" else (ns, nt)
    if t_axis == "x":
        sigmas = [s1 - (i + 0.5) * (s1 - s0) / ns for i in range(ns)]     # 行 0 が上端(σ が最大)
    else:
        sigmas = [s0 + (i + 0.5) * (s1 - s0) / ns for i in range(ns)]     # 列 0 が左端(σ が最小)
    pows = pow_table(sigmas)
    fades = [fade_alpha(sig, spec["fade"]) / 255 for sig in sigmas]
    colors = {th: make_phase_color(th) for th in THEMES}
    papers = {th: THEMES[th]["paper"] for th in THEMES}
    # 縮小で縁がにじまないよう、α を掛けた値(RGBa)で持っておく
    images = {th: Image.new("RGBa", (w, h)) for th in THEMES}
    pixels = {th: im.load() for th, im in images.items()}
    for j, t in enumerate(ts):
        col = zeta_column(t, sigmas, pows)
        for i, v in enumerate(col):
            phi = cmath.phase(v)
            x, y = (j, i) if t_axis == "x" else (i, nt - 1 - j)
            for th in THEMES:
                r, g, b, a = as_ink(colors[th](phi), papers[th])
                a *= fades[i]
                pixels[th][x, y] = (int(round(r * a)), int(round(g * a)), int(round(b * a)), int(round(255 * a)))
        if j % 400 == 0:
            print(f"  {name}: {j}/{nt}", file=sys.stderr, flush=True)
    os.makedirs(outdir, exist_ok=True)
    for th, im in images.items():
        im = im.resize((w // SUPERSAMPLE, h // SUPERSAMPLE), Image.LANCZOS).convert("RGBA")
        path = os.path.join(outdir, f"zeta-{name}-{th}.png")
        im.save(path, optimize=True)
        print(f"wrote {path}: {im.size[0]}x{im.size[1]}", file=sys.stderr)
    # 図の座標範囲。サイト側の描画がこの値で軸や零点の位置を合わせる
    meta = {"tMin": t0, "tMax": t1, "sigMin": s0, "sigMax": s1, "fadeFrom": spec["fade"][0], "fadeTo": spec["fade"][1],
            "zeros": [g for g in ref.KNOWN_ZEROS if t0 <= g <= t1]}
    with open(os.path.join(outdir, f"zeta-{name}.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, separators=(",", ":"))
        fh.write("\n")


def palette():
    for theme in THEMES:
        c = make_phase_color(theme)
        print(f"位相図の 4 色({theme}):")
        for name, phi in (("紙  φ=0", 0.0), ("藍  φ=+π/2", math.pi / 2), ("遠  φ=π", math.pi), ("朱  φ=−π/2", -math.pi / 2)):
            print(f"  {name:12s} {hexrgb(c(phi))}")
    print("紙面用(同じ色相で、文字として読める濃さにしたもの):")
    for name, L, C, hue in (("藍(明るい地の文字)", 0.40, 0.140, HUE_AI), ("藍(暗い地の文字)", 0.78, 0.100, HUE_AI),
                             ("朱(明るい地の印)", 0.58, 0.200, HUE_SHU), ("朱(明るい地の文字)", 0.50, 0.170, HUE_SHU),
                             ("朱(暗い地)", 0.72, 0.160, HUE_SHU)):
        print(f"  {name:20s} {hexrgb(oklch_to_srgb(L, C, hue))}")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--palette":
        palette()
        return
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    outdir = sys.argv[1]
    what = sys.argv[2] if len(sys.argv) == 3 else "all"
    worst, zmax = self_check()
    print(f"検算: 別実装との相対差 {worst:.1e}, 零点での |ζ| の最大 {zmax:.1e}", file=sys.stderr)
    if what in ("band", "all"):
        render(BAND, "phase", outdir, "x")
    if what in ("hero", "all"):
        render(HERO, "hero", outdir, "y")


if __name__ == "__main__":
    main()
