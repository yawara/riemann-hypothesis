#!/usr/bin/env python3
"""レポート冒頭の図版用に、臨界線上のリーマン ζ 関数を数値計算する。

  Z(t) = e^{iθ(t)} ζ(1/2 + it)      (Hardy の Z 関数。t が実数なら実数値)

Z(t) の零点は ζ(1/2 + it) の零点、すなわち臨界線 Re s = 1/2 上の非自明な零点に一致する。
外部ライブラリは使わず、倍精度の複素数演算だけで計算する:

  * ζ(s)  … Euler–Maclaurin の和公式(N = 60 項 + Bernoulli 補正 12 項)
  * θ(t)  … Lanczos 近似による log Γ(1/4 + it/2) の虚部 − (t/2) log π

検算として、求めた零点を文献値(小数 6 桁)と照合する。

使い方: python3 -I scripts/gen_zeta_figure.py > verification/zeta-figure.json
"""
import cmath
import json
import math
import sys

T_MAX = 60.0
STEP = 0.05

# Bernoulli 数 B_2, B_4, ..., B_24
BERNOULLI = [1 / 6, -1 / 30, 1 / 42, -1 / 30, 5 / 66, -691 / 2730, 7 / 6, -3617 / 510,
             43867 / 798, -174611 / 330, 854513 / 138, -236364091 / 2730]

# Lanczos 近似 (g = 7, n = 9)
LANCZOS_G = 7.0
LANCZOS = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
           -176.61502916214059, 12.507343278686905, -0.13857109526572012,
           9.9843695780195716e-6, 1.5056327351493116e-7]


def zeta(s, n_terms=60):
    """Euler–Maclaurin による ζ(s)。Re s > -20 程度、|Im s| <= 100 程度で十分な精度。"""
    total = 0j
    for n in range(1, n_terms):
        total += cmath.exp(-s * math.log(n))
    ln_n = math.log(n_terms)
    total += cmath.exp((1 - s) * ln_n) / (s - 1)
    total += 0.5 * cmath.exp(-s * ln_n)
    # Σ_k B_{2k}/(2k)! · s(s+1)…(s+2k-2) · N^{-s-2k+1}
    term = s * cmath.exp((-s - 1) * ln_n)        # k = 1: s · N^{-s-1}
    fact = 2.0                                    # (2k)!
    for k, b in enumerate(BERNOULLI, start=1):
        total += b / fact * term
        # k → k+1: 掛ける (s+2k-1)(s+2k) / N^2、階乗は (2k+1)(2k+2) 倍
        term *= (s + 2 * k - 1) * (s + 2 * k) / (n_terms * n_terms)
        fact *= (2 * k + 1) * (2 * k + 2)
    return total


def log_gamma(z):
    """Lanczos 近似による log Γ(z)(Re z > 0)。虚部は 2π の整数倍だけ不定だが、ここでは問題ない。"""
    z = z - 1
    x = LANCZOS[0]
    for i in range(1, len(LANCZOS)):
        x += LANCZOS[i] / (z + i)
    t = z + LANCZOS_G + 0.5
    return 0.5 * math.log(2 * math.pi) + (z + 0.5) * cmath.log(t) - t + cmath.log(x)


def theta(t):
    """Riemann–Siegel θ 関数。"""
    return log_gamma(complex(0.25, t / 2)).imag - (t / 2) * math.log(math.pi)


def hardy_z(t):
    return (cmath.exp(1j * theta(t)) * zeta(complex(0.5, t))).real


def bisect(a, b, tol=1e-10):
    fa, fb = hardy_z(a), hardy_z(b)
    assert fa * fb < 0
    while b - a > tol:
        m = 0.5 * (a + b)
        fm = hardy_z(m)
        if fa * fm <= 0:
            b, fb = m, fm
        else:
            a, fa = m, fm
    return 0.5 * (a + b)


# 文献値(非自明な零点の虚部、小数 6 桁)。Odlyzko の表などで広く知られている値。
KNOWN_ZEROS = [14.134725, 21.022040, 25.010858, 30.424876, 32.935062, 37.586178, 40.918719,
               43.327073, 48.005151, 49.773832, 52.970321, 56.446248, 59.347044]


def main():
    n = int(round(T_MAX / STEP))
    ts = [i * STEP for i in range(n + 1)]
    zs = [hardy_z(t) for t in ts]

    zeros = []
    for i in range(n):
        if zs[i] == 0 or zs[i] * zs[i + 1] < 0:
            zeros.append(bisect(ts[i], ts[i + 1]))

    # 検算
    assert len(zeros) == len(KNOWN_ZEROS), (len(zeros), zeros)
    max_err = max(abs(a - b) for a, b in zip(zeros, KNOWN_ZEROS))
    assert max_err < 1e-6, max_err
    # ζ(1/2) = -1.4603545088...、ζ(2) = π²/6 でも検算
    assert abs(zeta(0.5 + 0j).real - (-1.4603545088095868)) < 1e-10
    assert abs(zeta(2 + 0j).real - math.pi ** 2 / 6) < 1e-12

    out = {
        "t_max": T_MAX,
        "step": STEP,
        "z": [round(v, 4) for v in zs],
        "zeros": [round(v, 6) for v in zeros],
        "z_min": round(min(zs), 4),
        "z_max": round(max(zs), 4),
        "max_abs_error_vs_known_zeros": max_err,
    }
    json.dump(out, sys.stdout)
    print()
    print(f"zeros={len(zeros)} max_err={max_err:.2e} z_range=[{min(zs):.3f}, {max(zs):.3f}] Z(0)={zs[0]:.6f}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
