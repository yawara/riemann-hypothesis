#!/usr/bin/env python3
"""図 1 の上段: 臨界帯のまわりでのリーマン ζ 関数の位相図(偏角を色で表した図)を画像にする。

  横: t = Im s(0 〜 60)   縦: σ = Re s(上が大きい。2.5 〜 −8)   縦横の縮尺は同じ(等角)

色は ζ(s) の偏角 φ だけで決める(絶対値は使わない)。墨と藍と朱の 3 色刷りに見立ててある。

  φ = 0    (正の実数)   … 紙の色(何も刷らない)
  φ = +π/2 (+i の向き) … 藍
  φ = ±π   (負の実数)   … 墨(暗い紙面では白)
  φ = −π/2 (−i の向き) … 朱

明るさは cos φ、色みは |sin φ| に比例させてあり、一周して元に戻る。零点では 4 色すべてが 1 点に集まる。
明るい紙面用と暗い紙面用の 2 枚を出力する。上端(σ > 1.5)は紙に溶け込むよう透明にしてある。

外部ライブラリは Pillow だけ(数値計算は倍精度の複素数演算)。
  * Re s ≥ 1/2 … Euler–Maclaurin の和公式で直接計算
  * Re s < 1/2 … 関数等式 ζ(s) = 2^s π^{s−1} sin(πs/2) Γ(1−s) ζ(1−s) で右半平面の値から求める
    (左半平面で和公式を直接使うと、大きな値どうしの打ち消しで桁落ちするため)
検算: 既知の特殊値、scripts/gen_zeta_figure.py の実装との一致、文献値の零点。

使い方: python3 -I scripts/gen_zeta_phase.py site/src/assets     # zeta-phase-light.png / -dark.png を書き出す
        python3 -I scripts/gen_zeta_phase.py --palette             # 紙面で使う色コードを表示
"""
import cmath
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_zeta_figure as ref  # noqa: E402  (同じディレクトリにある、図 1 下段用の実装)

T_MIN, T_MAX = 0.0, 60.0
SIG_MIN, SIG_MAX = -8.0, 2.5
FADE_FROM, FADE_TO = 1.5, 2.5   # この σ の範囲で不透明 → 透明
PX_PER_UNIT = 30                 # 仕上がりの解像度(1 単位あたりのピクセル数。t と σ で同じ)
SUPERSAMPLE = 2                  # 計算はこの倍率で行い、縮小して滑らかにする
N_TERMS = 48                     # Euler–Maclaurin で直接足す項数(|s| < 2πN で補正項が収束する)

LN2, LNPI, HALF_PI = math.log(2.0), math.log(math.pi), math.pi / 2

# 色(OKLCH)。藍と朱は色相だけを決め、明るさは両者で同じにそろえる。
HUE_AI, CHROMA_AI = 262.0, 0.150
HUE_SHU, CHROMA_SHU = 38.0, 0.170
THEMES = {
    # paper: 紙の色(φ = 0)、l_far: φ = π での明るさ
    "light": {"paper": (0xFF, 0xFF, 0xFF), "l_far": 0.20},
    "dark": {"paper": (0x12, 0x14, 0x18), "l_far": 0.93},
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
    """位相 → sRGB。φ = 0 でちょうど紙の色になるよう、紙の色に寄せる。"""
    paper = THEMES[theme]["paper"]
    pl, pa, pb = srgb_to_oklab(paper)
    l_far = THEMES[theme]["l_far"]
    l_mid, l_amp = (pl + l_far) / 2, (pl - l_far) / 2

    def color(phi):
        cs, sn = math.cos(phi), math.sin(phi)
        L = l_mid + l_amp * cs
        if sn >= 0:
            a, b = CHROMA_AI * sn * AI_AB[0], CHROMA_AI * sn * AI_AB[1]
        else:
            a, b = CHROMA_SHU * -sn * SHU_AB[0], CHROMA_SHU * -sn * SHU_AB[1]
        if cs > 0:
            w = cs ** 4          # φ = 0 の近くだけ紙の色(わずかな色みを含む)へ寄せる
            a, b = a + (pa - a) * w * (1 - abs(sn)), b + (pb - b) * w * (1 - abs(sn))
        return oklab_to_srgb(L, a, b)

    return color


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
    for k in (2, 4, 6, 8):
        assert abs(zeta_point(complex(-k, 0))) < 1e-11            # 自明な零点
    # 図 1 下段用の実装(N = 60 項の和公式を直接使う)との一致。その実装が桁落ちしない範囲で比べる
    worst = 0.0
    for sig in (-2.0, -1.0, 0.25, 0.5, 1.5, 2.5):
        for t in (0.3, 7.0, 21.0, 44.4, 60.0):
            s = complex(sig, t)
            a, b = zeta_point(s), ref.zeta(s)
            worst = max(worst, abs(a - b) / abs(b))
    assert worst < 1e-7, worst      # 左半平面では比較相手(直接計算)の側が 1e-8 程度まで桁落ちする
    # 文献値の零点で |ζ| が十分小さい(零点の値は小数 6 桁なので 1e-5 程度が限界)
    zmax = max(abs(zeta_point(complex(0.5, g))) for g in ref.KNOWN_ZEROS)
    assert zmax < 2e-5, zmax
    return worst, zmax


def render(outdir):
    from PIL import Image

    worst, zmax = self_check()
    w = int(round((T_MAX - T_MIN) * PX_PER_UNIT)) * SUPERSAMPLE
    h = int(round((SIG_MAX - SIG_MIN) * PX_PER_UNIT)) * SUPERSAMPLE
    # 画素の中心で評価する。行 0 が上端(σ が最大)
    sigmas = [SIG_MAX - (i + 0.5) * (SIG_MAX - SIG_MIN) / h for i in range(h)]
    pows = pow_table(sigmas)
    alphas = []
    for sig in sigmas:
        x = min(1.0, max(0.0, (FADE_TO - sig) / (FADE_TO - FADE_FROM)))
        alphas.append(int(round(255 * x * x * (3 - 2 * x))))
    colors = {name: make_phase_color(name) for name in THEMES}
    images = {name: Image.new("RGBA", (w, h)) for name in THEMES}
    pixels = {name: im.load() for name, im in images.items()}
    for j in range(w):
        t = T_MIN + (j + 0.5) * (T_MAX - T_MIN) / w
        col = zeta_column(t, sigmas, pows)
        for i, v in enumerate(col):
            phi = cmath.phase(v)
            a = alphas[i]
            for name in THEMES:
                pixels[name][j, i] = colors[name](phi) + (a,)
        if j % 400 == 0:
            print(f"  列 {j}/{w}", file=sys.stderr, flush=True)
    os.makedirs(outdir, exist_ok=True)
    for name, im in images.items():
        if SUPERSAMPLE > 1:
            im = im.resize((w // SUPERSAMPLE, h // SUPERSAMPLE), Image.LANCZOS)
        path = os.path.join(outdir, f"zeta-phase-{name}.png")
        im.save(path, optimize=True)
        print(f"wrote {path}: {im.size[0]}x{im.size[1]}", file=sys.stderr)
    # 図の座標範囲。サイト側の描画(ZetaFigure.astro)がこの値で軸を合わせる
    with open(os.path.join(outdir, "zeta-phase.json"), "w", encoding="utf-8") as fh:
        json.dump({"tMin": T_MIN, "tMax": T_MAX, "sigMin": SIG_MIN, "sigMax": SIG_MAX,
                   "fadeFrom": FADE_FROM, "fadeTo": FADE_TO}, fh, separators=(",", ":"))
        fh.write("\n")
    print(f"t=[{T_MIN},{T_MAX}] sigma=[{SIG_MIN},{SIG_MAX}]  検算: 別実装との相対差 {worst:.1e}, "
          f"零点での |ζ| の最大 {zmax:.1e}", file=sys.stderr)


def palette():
    for theme in THEMES:
        c = make_phase_color(theme)
        print(f"位相図の 4 色({theme}):")
        for name, phi in (("紙  φ=0", 0.0), ("藍  φ=+π/2", math.pi / 2), ("遠  φ=π", math.pi), ("朱  φ=−π/2", -math.pi / 2)):
            print(f"  {name:12s} {hexrgb(c(phi))}")
    print("紙面用(同じ色相で、文字として読める濃さにしたもの):")
    for name, L, C, hue in (("藍(明るい地の文字)", 0.42, 0.130, HUE_AI), ("藍(暗い地の文字)", 0.78, 0.095, HUE_AI),
                             ("朱(明るい地の図)", 0.60, 0.185, HUE_SHU), ("朱(明るい地の文字)", 0.50, 0.165, HUE_SHU),
                             ("朱(暗い地)", 0.74, 0.150, HUE_SHU)):
        print(f"  {name:20s} {hexrgb(oklch_to_srgb(L, C, hue))}")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--palette":
        palette()
    elif len(sys.argv) == 2:
        render(sys.argv[1])
    else:
        sys.exit(__doc__)
