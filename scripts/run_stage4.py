"""Stage 4: EU white space ranking (S4).

Usage:
    python -m scripts.run_stage4
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core_pipeline import white_space

FIG = Path("docs/figs")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    f = white_space.run()
    show = f[["imports_eur_m", "kr_share", "cn_share", "growth_25_23", "agm_share_2025",
              "cars_total_m", "cars_ge10_m", "share_age_ge10", "score_balanced",
              "rank_balanced", "rank_demand_led", "rank_headroom_led", "rank_spread"]].copy()
    for c in ["kr_share", "cn_share", "growth_25_23", "agm_share_2025", "share_age_ge10"]:
        show[c] = (show[c] * 100).round(1)
    show["imports_eur_m"] = show["imports_eur_m"].round(0)
    show["cars_total_m"] = show["cars_total_m"].round(1)
    show["cars_ge10_m"] = show["cars_ge10_m"].round(1)
    print("S4 EU white space (shares and growth in %, imports EUR M avg 2024-25, cars M):")
    print(show.to_string())
    stable = f[f["rank_spread"] <= 2].head(8).index.tolist()
    print(f"\nTop candidates stable across weight sets (rank spread <= 2): {stable}")

    fig, ax = plt.subplots(figsize=(8, 5.5))
    sz = (f["cars_ge10_m"].clip(lower=0.2) * 25)
    ax.scatter(f["share_age_ge10"] * 100, f["kr_share"] * 100, s=sz, alpha=0.6, color="#4c72b0", edgecolor="k", lw=0.5)
    for c, r in f.iterrows():
        ax.annotate(c, (r["share_age_ge10"] * 100, r["kr_share"] * 100), fontsize=8, ha="center", va="center")
    ax.axhline(f["kr_share"].median() * 100, color="gray", ls=":", lw=0.8)
    ax.axvline(f["share_age_ge10"].median() * 100, color="gray", ls=":", lw=0.8)
    ax.set_xlabel("passenger cars aged 10y+ (% of parc)")
    ax.set_ylabel("Korean share of CN 8507 10 imports (%, 2024-25)")
    ax.set_title("EU white space: bubble = cars aged 10y+ (M)")
    fig.tight_layout()
    fig.savefig(FIG / "s4_white_space.png", dpi=120)
    plt.close(fig)
    print(f"\nfigure: {FIG}/s4_white_space.png")


if __name__ == "__main__":
    main()
