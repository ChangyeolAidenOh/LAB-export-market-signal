"""Stage 2: S1 pass-through and S2 origin shift, with H2-H5 verdicts.

Usage:
    python -m scripts.run_stage2
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from core_pipeline import origin_shift, pass_through

FIG = Path("docs/figs")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)

    pt = pass_through.run()
    price = pt[pt["target"] == "usd_per_kg"].set_index("series")
    print("S1 pass-through of lead price into export unit price (USD/kg), by destination:")
    cols = ["n", "cpt0", "cpt3", "cpt3_se", "cpt3_p", "cpt6", "cpt6_p", "peak_lag", "fx_beta", "r2"]
    print(price[cols].round(3).to_string())
    vol = pt[pt["target"] == "kg"].set_index("series")
    print("\nS1 lead price -> volume (kg), should be insignificant:")
    print(vol[["cpt6", "cpt6_se", "cpt6_p", "r2"]].round(3).to_string())
    v1 = pass_through.verdicts(pt)
    print(f"\nH4 (pass-through differs by market): spread={v1['H4_spread_pp']}pp, "
          f"sig markets={v1['H4_n_sig']}/5 -> {'SUPPORTED' if v1['H4'] else 'REJECTED'}")
    print(f"H5 (lead moves value not volume): insignificant volume in {v1['H5_n_insig_volume']}/5 -> "
          f"{'SUPPORTED' if v1['H5'] else 'REJECTED'}")

    fig, ax = plt.subplots(figsize=(7, 3.5))
    p5 = price.loc[["US", "JP", "AU", "GB", "CA"]]
    ax.bar(p5.index, p5["cpt3"], yerr=1.96 * p5["cpt3_se"], color="#4c72b0", capsize=4)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("CPT(3): cumulative pass-through, 3 months")
    ax.set_title("Lead price -> export unit price (USD/kg), by destination")
    fig.tight_layout()
    fig.savefig(FIG / "s1_pass_through.png", dpi=120)
    plt.close(fig)

    tbl, monthly, v2 = origin_shift.run()
    print("\nS2 US imports HTS 8507.10.0060 by origin: share (value) pre vs post Apr-2025")
    show = tbl[["share_val_pre", "share_val_post", "share_val_2026ytd", "delta_val_pp",
                "delta_qty_pp", "usd_per_unit_pre", "usd_per_unit_post"]].copy()
    for c in ["share_val_pre", "share_val_post", "share_val_2026ytd"]:
        show[c] = (show[c] * 100).round(1)
    print(show.round(1).to_string())
    print(f"\nH2 (total flat +/-10%, Korea share down >1sd): total post/pre={v2['H2_total_post_over_pre']}, "
          f"Korea share drop={v2['H2_korea_share_drop_sd']} sd -> {'SUPPORTED' if v2['H2'] else 'REJECTED'}")
    print(f"H3 (top gainer = Mexico): top gainer={v2['H3_top_gainer']} -> {'SUPPORTED' if v2['H3'] else 'REJECTED'}")

    sh = monthly["share_val"].rolling(3).mean().dropna()
    order = [c for c in ["Korea", "Mexico", "Germany", "Japan", "Malaysia", "Vietnam", "China", "Other"] if c in sh.columns]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.stackplot(sh.index, [sh[c] for c in order], labels=order, alpha=0.9)
    ax.axvline(pd.Timestamp("2025-04-01"), color="k", lw=1)
    ax.set_ylim(0, 1)
    ax.set_title("US imports HTS 8507.10.0060: origin share of customs value (3m MA)")
    ax.legend(loc="upper left", fontsize=7, ncol=4)
    fig.tight_layout()
    fig.savefig(FIG / "s2_origin_share.png", dpi=120)
    plt.close(fig)

    lvl = monthly["share_qty"]
    print(f"\nfigures: {FIG}/s1_pass_through.png, {FIG}/s2_origin_share.png")


if __name__ == "__main__":
    main()
