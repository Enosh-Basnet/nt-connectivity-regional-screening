"""NT Connectivity Regional Screening - Streamlit prototype.

Run from the repository root:
    python3 -m pip install -r requirements.txt
    streamlit run app.py

The app reads the CSVs written by data/script.ipynb (data/output/) and
recalculates the trial score live from the weights chosen in the sidebar.
It never changes the source data.
"""

from __future__ import annotations

import html
import io
import zipfile
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# --------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "data" / "output"
MASTER_CSV = OUTPUT_DIR / "nt_sa2_master.csv"
COMMUNITY_CSV = OUTPUT_DIR / "community_regional_context.csv"
INCLUSION_CSV = OUTPUT_DIR / "digital_inclusion_context.csv"

TRIAL_WEIGHTS = {"50/50": 0.50, "60/40": 0.60, "70/30": 0.70}  # mobile share
BASELINE = "60/40"
TOP_N = 5

MOBILE_COLOUR = "#2a6f97"
NBN_COLOUR = "#e67e22"
MUTED = "#b8c2cc"

CAVEAT = (
    "This is a **regional screening tool**. A high SA2 score is a prompt for "
    "further investigation, not a community-level investment decision. Scores "
    "use SA2-level availability percentages; they do not measure speed, "
    "reliability, affordability or the experience of any named community."
)

st.set_page_config(
    page_title="NT Connectivity Regional Screening",
    page_icon="📶",
    layout="wide",
)


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    master = pd.read_csv(MASTER_CSV, dtype={"sa2_code": str})
    community = pd.read_csv(COMMUNITY_CSV, dtype={"sa2_code": str})
    inclusion = pd.read_csv(INCLUSION_CSV) if INCLUSION_CSV.exists() else None
    return master, community, inclusion


@st.cache_data
def build_candidates(master: pd.DataFrame, community: pd.DataFrame) -> pd.DataFrame:
    """Candidate SA2s = SA2s containing at least one mapped BushTel record
    (same project selection rule as the notebook)."""
    counts = community.groupby("sa2_code", as_index=False).agg(
        mapped_records=("bushtel_id", "nunique"),
        major_records=("community_type", lambda s: int((s == "Major").sum())),
        minor_records=("community_type", lambda s: int((s == "Minor").sum())),
        name_matches_2022=("historical_listed_2022", "sum"),
    )
    cand = master.merge(counts, on="sa2_code", how="inner", validate="one_to_one")
    cand["mobile_premises_gap"] = 100 - cand["mobile_premises_pct"]
    cand["nbn_fixed_gap"] = 100 - cand["nbn_fixed_premises_pct"]
    cand["name_matches_2022"] = cand["name_matches_2022"].astype(int)
    return cand


def score(cand: pd.DataFrame, mobile_w: float) -> pd.DataFrame:
    """Weighted gap score and competition ranking (ties share a rank)."""
    out = cand.copy()
    nbn_w = 1 - mobile_w
    out["mobile_component"] = (mobile_w * out["mobile_premises_gap"]).round(1)
    out["nbn_component"] = (nbn_w * out["nbn_fixed_gap"]).round(1)
    out["score"] = (mobile_w * out["mobile_premises_gap"] + nbn_w * out["nbn_fixed_gap"]).round(1)
    out["rank"] = out["score"].rank(ascending=False, method="min").astype(int)
    return out.sort_values(["rank", "sa2_name"]).reset_index(drop=True)


def weight_label(mobile_w: float) -> str:
    m = round(mobile_w * 100)
    return f"{m}/{100 - m}"


# --------------------------------------------------------------------------
# Export helpers
# --------------------------------------------------------------------------
RANKING_EXPORT_COLS = {
    "rank": "rank",
    "sa2_code": "sa2_code",
    "sa2_name": "sa2_name",
    "score": "score",
    "mobile_premises_pct": "mobile_premises_pct",
    "mobile_premises_gap": "mobile_premises_gap",
    "nbn_fixed_premises_pct": "nbn_fixed_premises_pct",
    "nbn_fixed_gap": "nbn_fixed_gap",
    "mobile_area_pct": "mobile_area_pct_context",
    "nbn_satellite_premises_pct": "nbn_satellite_premises_pct_context",
    "population_2025": "sa2_population_2025_context",
    "area_km2": "sa2_area_km2",
    "mapped_records": "mapped_bushtel_records",
    "name_matches_2022": "direct_2022_name_matches",
}


def ranking_export(ranked: pd.DataFrame, mobile_w: float) -> pd.DataFrame:
    out = ranked[list(RANKING_EXPORT_COLS)].rename(columns=RANKING_EXPORT_COLS)
    out.insert(3, "weights_mobile_nbn", weight_label(mobile_w))
    return out


def community_export(community: pd.DataFrame, ranked: pd.DataFrame, mobile_w: float) -> pd.DataFrame:
    reg = ranked[["sa2_code", "rank", "score"]].rename(
        columns={"rank": "sa2_rank", "score": "sa2_score"}
    )
    out = community.merge(reg, on="sa2_code", how="left")
    out["weights_mobile_nbn"] = weight_label(mobile_w)
    out["direct_2022_name_match"] = out["historical_listed_2022"].map({True: "Yes", False: "No"})
    cols = [
        "sa2_rank", "sa2_name", "sa2_code", "sa2_score", "weights_mobile_nbn",
        "community", "community_type", "bushtel_id", "latitude", "longitude",
        "direct_2022_name_match", "historical_site_name", "provider_2022",
        "aliases", "bushtel_profile_url",
    ]
    return out[cols].sort_values(["sa2_rank", "sa2_name", "community"]).reset_index(drop=True)


def offline_html(ranked: pd.DataFrame, comm: pd.DataFrame, mobile_w: float, stamp: str) -> str:
    """A small, script-free HTML report that opens in any browser offline."""
    wl = weight_label(mobile_w)
    esc = html.escape

    rank_rows = "".join(
        f"<tr{' class=top' if r['rank'] <= TOP_N else ''}>"
        f"<td>{r['rank']}</td><td>{esc(r['sa2_name'])}</td><td>{r['score']:.1f}</td>"
        f"<td>{r['mobile_premises_pct']}%</td><td>{r['nbn_fixed_premises_pct']}%</td>"
        f"<td>{r['mobile_area_pct']}%</td><td>{r['nbn_satellite_premises_pct']}%</td>"
        f"<td>{r['population_2025']:,}</td><td>{r['mapped_records']}</td>"
        f"<td>{r['name_matches_2022']}</td></tr>"
        for _, r in ranked.iterrows()
    )

    sections = []
    for _, r in ranked.iterrows():
        sub = comm[comm["sa2_code"] == r["sa2_code"]]
        items = "".join(
            f"<tr><td>{esc(c['community'])}</td><td>{esc(c['community_type'])}</td>"
            f"<td>{c['bushtel_id']}</td><td>{c['latitude']:.4f}, {c['longitude']:.4f}</td>"
            f"<td>{c['direct_2022_name_match']}</td></tr>"
            for _, c in sub.iterrows()
        )
        sections.append(
            f"<h3>#{r['rank']} {esc(r['sa2_name'])} "
            f"<small>score {r['score']:.1f} &middot; {len(sub)} mapped records</small></h3>"
            f"<table><tr><th>Record</th><th>Type</th><th>BushTel ID</th>"
            f"<th>Lat, lon (GDA94)</th><th>2022 name match</th></tr>{items}</table>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NT Connectivity Regional Screening - offline report</title>
<style>
 body{{font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#1d2733;background:#fff}}
 h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:18px;margin-top:28px}} h3{{font-size:15px;margin:20px 0 6px}}
 small{{color:#5b6773;font-weight:400}}
 .note{{background:#fff6e5;border-left:4px solid {NBN_COLOUR};padding:10px 12px;margin:12px 0}}
 table{{border-collapse:collapse;width:100%;margin:6px 0 12px}}
 th,td{{border-bottom:1px solid #e3e8ee;padding:5px 8px;text-align:left}}
 th{{background:#f3f6f9}} tr.top td{{background:#fdf1e4;font-weight:600}}
 code{{background:#f3f6f9;padding:1px 4px}}
 @media print{{.note{{break-inside:avoid}} h3{{break-after:avoid}}}}
</style></head><body>
<h1>NT Connectivity Regional Screening</h1>
<div><small>Offline export &middot; generated {esc(stamp)} &middot; weights mobile/NBN fixed = {wl}</small></div>
<div class="note"><b>Interpretation.</b> This is a regional screening output. A high SA2 score is a prompt
for further investigation, not a community-level investment decision. Availability percentages do not
measure speed, reliability, affordability or user experience. A missing 2022 name match is not evidence
of no current mobile service. SA2 population is for the whole SA2, not a mapped community.</div>
<h2>Method</h2>
<p><code>score = {mobile_w:.2f} &times; (100 &minus; mobile premises %) + {1 - mobile_w:.2f} &times; (100 &minus; NBN fixed premises %)</code>.
Candidate SA2s are the {len(ranked)} SA2s containing at least one mapped BushTel Major/Minor record
(a project selection rule, not an official classification). Mobile area %, NBN satellite % and population are context only.</p>
<h2>Regional ranking</h2>
<table><tr><th>Rank</th><th>SA2</th><th>Score</th><th>Mobile premises</th><th>NBN fixed</th>
<th>Mobile area*</th><th>NBN satellite*</th><th>SA2 pop. 2025*</th><th>Mapped records</th><th>2022 name matches</th></tr>
{rank_rows}</table>
<p><small>* Context only; not part of the score. Highlighted rows are the top {TOP_N} under these weights.</small></p>
<h2>Mapped BushTel records by SA2</h2>
{''.join(sections)}
<h2>Sources</h2>
<p><small>DITRDCA Digital Connectivity Indicators (SA2); ABS Regional population 2024&ndash;25, Table 7;
NT Government mobile sites list (2022, historical context only); BushTel community profiles via a
project-supplied SA2 lookup (GDA94 points vs GDA2020 SA2 boundaries, no datum transformation &mdash;
check records near boundaries).</small></p>
</body></html>"""


def offline_pack(ranked, comm_exp, rank_exp, mobile_w, stamp) -> bytes:
    wl = weight_label(mobile_w).replace("/", "-")
    readme = (
        "NT Connectivity Regional Screening - offline pack\n"
        f"Generated: {stamp}\nWeights (mobile / NBN fixed): {weight_label(mobile_w)}\n\n"
        "Files\n"
        "  report.html          open in any browser; no internet or scripts needed\n"
        "  sa2_ranking.csv      one row per candidate SA2 with score and indicators\n"
        "  bushtel_records.csv  one row per mapped BushTel record with its SA2 rank\n\n"
        "Interpretation\n"
        "  Regional screening only. A high SA2 score is a prompt for further\n"
        "  investigation, not a community-level investment decision. Columns ending\n"
        "  in _context are not part of the score. SA2 values repeated on community\n"
        "  rows are regional values, not community measurements.\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", readme)
        z.writestr("report.html", offline_html(ranked, comm_exp, mobile_w, stamp))
        z.writestr("sa2_ranking.csv", rank_exp.to_csv(index=False))
        z.writestr("bushtel_records.csv", comm_exp.to_csv(index=False))
    return buf.getvalue()


# --------------------------------------------------------------------------
# Load or explain what is missing
# --------------------------------------------------------------------------
missing = [p.name for p in (MASTER_CSV, COMMUNITY_CSV) if not p.exists()]
if missing:
    st.error(
        "Missing input files in `data/output/`: "
        + ", ".join(f"`{m}`" for m in missing)
        + ". Run `data/script.ipynb` from top to bottom first, then reload this page."
    )
    st.stop()

master, community, inclusion = load_data()
candidates = build_candidates(master, community)

# --------------------------------------------------------------------------
# Sidebar: weights
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Score weights")
    mobile_pct = st.slider(
        "Mobile premises gap weight (%)",
        min_value=0, max_value=100, value=60, step=5,
        help="The NBN fixed gap receives the remaining weight.",
    )
    mobile_w = mobile_pct / 100
    st.markdown(
        f"**Mobile {mobile_pct}% · NBN fixed {100 - mobile_pct}%**\n\n"
        f"score = **{mobile_w:.2f}** × mobile premises gap  \n"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;+ **{1 - mobile_w:.2f}** × NBN fixed gap\n\n"
        "where gap = 100 − reported availability %"
    )
    st.caption(
        "60/40 is the project's main trial; 50/50 and 70/30 are sensitivity checks. "
        "None of these is a validated policy weight."
    )
    st.divider()
    st.caption(
        f"Data: {len(master)} NT SA2s · {len(candidates)} candidate SA2s · "
        f"{community['bushtel_id'].nunique()} mapped BushTel records"
    )

ranked = score(candidates, mobile_w)
baseline = score(candidates, TRIAL_WEIGHTS[BASELINE])
ranked = ranked.merge(
    baseline[["sa2_code", "rank"]].rename(columns={"rank": "rank_baseline"}), on="sa2_code"
)
ranked["rank_change"] = ranked["rank_baseline"] - ranked["rank"]  # +ve = moved up

comm_exp = community_export(community, ranked, mobile_w)
rank_exp = ranking_export(ranked, mobile_w)
stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
file_tag = weight_label(mobile_w).replace("/", "-")

# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------
st.title("📶 NT Connectivity Regional Screening")
st.caption("CDU IT Code Fair 2026 · Data Innovation Challenge · DIC020")
st.info(CAVEAT)

top = ranked.iloc[0]
k1, k2, k3, k4 = st.columns(4)
k1.metric("NT SA2s in dataset", len(master))
k2.metric("Candidate SA2s", len(candidates), help="SA2s containing at least one mapped BushTel record")
k3.metric("Mapped BushTel records", community["bushtel_id"].nunique(),
          help=f"{(community.community_type == 'Major').sum()} Major, "
               f"{(community.community_type == 'Minor').sum()} Minor")
k4.metric(f"Highest gap score ({weight_label(mobile_w)}): {top['score']:.1f}", top["sa2_name"])

tab_rank, tab_sa2, tab_sens, tab_export, tab_about = st.tabs(
    ["Regional ranking", "Explore an SA2", "Weight sensitivity", "Export", "Method & limits"]
)

# --------------------------------------------------------------------------
# Tab 1: ranking
# --------------------------------------------------------------------------
with tab_rank:
    st.subheader(f"Candidate SA2s ranked by trial gap score (mobile/NBN fixed = {weight_label(mobile_w)})")

    long = ranked.melt(
        id_vars=["sa2_name", "rank", "score"],
        value_vars=["mobile_component", "nbn_component"],
        var_name="component", value_name="points",
    )
    long["component"] = long["component"].map(
        {"mobile_component": "Mobile premises gap", "nbn_component": "NBN fixed gap"}
    )
    long["label"] = "#" + long["rank"].astype(str) + "  " + long["sa2_name"]
    order = ("#" + ranked["rank"].astype(str) + "  " + ranked["sa2_name"]).tolist()

    bars = (
        alt.Chart(long)
        .mark_bar()
        .encode(
            y=alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=220)),
            x=alt.X("sum(points):Q", title="Weighted gap score (percentage points)",
                    scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("component:N", title=None,
                            scale=alt.Scale(domain=["Mobile premises gap", "NBN fixed gap"],
                                            range=[MOBILE_COLOUR, NBN_COLOUR]),
                            legend=alt.Legend(orient="top")),
            order=alt.Order("component:N"),
            tooltip=[alt.Tooltip("sa2_name:N", title="SA2"), "component:N",
                     alt.Tooltip("points:Q", title="Points", format=".1f"),
                     alt.Tooltip("score:Q", title="Total score", format=".1f")],
        )
    )
    totals = (
        alt.Chart(ranked.assign(label="#" + ranked["rank"].astype(str) + "  " + ranked["sa2_name"]))
        .mark_text(align="left", dx=4, fontWeight="bold")
        .encode(y=alt.Y("label:N", sort=order), x="score:Q", text=alt.Text("score:Q", format=".1f"))
    )
    st.altair_chart((bars + totals).properties(height=34 * len(ranked) + 40), width="stretch")

    n_zero = int((ranked["nbn_fixed_premises_pct"] == 0).sum())
    st.caption(
        f"Reported NBN fixed availability is 0% in {n_zero} of {len(ranked)} candidate SA2s, so the "
        "NBN component (orange) is identical for most regions and the ordering is driven mainly by "
        "the mobile premises gap. Zero NBN fixed does not mean zero broadband: satellite is reported "
        "separately."
    )

    def arrow(v: int) -> str:
        return "–" if v == 0 else (f"▲ {v}" if v > 0 else f"▼ {abs(v)}")

    table = ranked.assign(change=ranked["rank_change"].map(arrow))[
        ["rank", "sa2_name", "score", "change", "mobile_premises_pct", "nbn_fixed_premises_pct",
         "mobile_area_pct", "nbn_satellite_premises_pct", "population_2025", "mapped_records",
         "name_matches_2022"]
    ]
    st.dataframe(
        table,
        hide_index=True,
        height=35 * (len(table) + 1) + 3,
        width="stretch",
        column_config={
            "rank": st.column_config.NumberColumn("Rank", width="small"),
            "sa2_name": "SA2",
            "score": st.column_config.ProgressColumn("Score", format="%.1f", min_value=0, max_value=100),
            "change": st.column_config.TextColumn(f"vs {BASELINE}", help="Rank change against the 60/40 main trial"),
            "mobile_premises_pct": st.column_config.NumberColumn("Mobile premises %", format="%d%%"),
            "nbn_fixed_premises_pct": st.column_config.NumberColumn("NBN fixed %", format="%d%%"),
            "mobile_area_pct": st.column_config.NumberColumn("Mobile area %*", format="%d%%"),
            "nbn_satellite_premises_pct": st.column_config.NumberColumn("NBN satellite %*", format="%d%%"),
            "population_2025": st.column_config.NumberColumn("SA2 pop. 2025*", format="localized"),
            "mapped_records": st.column_config.NumberColumn("Mapped records"),
            "name_matches_2022": st.column_config.NumberColumn("2022 name matches"),
        },
    )
    st.caption("* Context only — not part of the score. Ties share a rank.")

# --------------------------------------------------------------------------
# Tab 2: SA2 explorer
# --------------------------------------------------------------------------
with tab_sa2:
    options = ranked["sa2_code"].tolist()
    names = dict(zip(ranked["sa2_code"], "#" + ranked["rank"].astype(str) + " " + ranked["sa2_name"]))
    code = st.selectbox("Select a candidate SA2", options, format_func=names.get)
    r = ranked.set_index("sa2_code").loc[code]
    recs = comm_exp[comm_exp["sa2_code"] == code]
    recs_view = recs.fillna({"provider_2022": "—", "aliases": "—", "historical_site_name": "—"})

    st.subheader(f"{r['sa2_name']}  ·  rank {r['rank']} of {len(ranked)}")

    c1, c2, c3 = st.columns(3)
    c1.metric(f"Trial score ({weight_label(mobile_w)})", f"{r['score']:.1f}")
    c2.metric("Mobile component", f"{r['mobile_component']:.1f}",
              help=f"{mobile_w:.2f} × {r['mobile_premises_gap']} pp gap")
    c3.metric("NBN fixed component", f"{r['nbn_component']:.1f}",
              help=f"{1 - mobile_w:.2f} × {r['nbn_fixed_gap']} pp gap")

    st.markdown("**Reported SA2 indicators**")
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Mobile premises", f"{r['mobile_premises_pct']}%", help="In score")
    i2.metric("NBN fixed premises", f"{r['nbn_fixed_premises_pct']}%", help="In score")
    i3.metric("Mobile area", f"{r['mobile_area_pct']}%", help="Context only")
    i4.metric("NBN satellite premises", f"{r['nbn_satellite_premises_pct']}%", help="Context only")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("SA2 population 2025", f"{r['population_2025']:,}", help="Whole SA2, not mapped communities")
    p2.metric("Area", f"{r['area_km2']:,.0f} km²")
    p3.metric("People per km²", f"{r['population_2025'] / r['area_km2']:.3f}")
    p4.metric("2022 name matches", f"{r['name_matches_2022']} of {r['mapped_records']}")

    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"**Mapped BushTel records ({len(recs)})**")
        st.dataframe(
            recs_view[["community", "community_type", "bushtel_id", "direct_2022_name_match",
                  "provider_2022", "aliases", "bushtel_profile_url"]],
            hide_index=True,
            width="stretch",
            column_config={
                "community": "Record",
                "community_type": "Type",
                "bushtel_id": st.column_config.NumberColumn("BushTel ID", format="%d"),
                "direct_2022_name_match": "2022 name match",
                "provider_2022": "2022 provider",
                "aliases": "Aliases",
                "bushtel_profile_url": st.column_config.LinkColumn("Profile", display_text="BushTel"),
            },
        )
        st.caption(
            "Community rows share their SA2's regional values; they are not community measurements. "
            "A 'No' name match may reflect a naming difference or the 2022 list's age — it is not "
            "evidence of no current mobile service."
        )
    with right:
        st.markdown("**Where the records sit** (no basemap, works offline)")
        pts = comm_exp.assign(selected=comm_exp["sa2_code"].eq(code).map({True: r["sa2_name"], False: "Other SA2s"}))
        loc = (
            alt.Chart(pts)
            .mark_circle(size=70, opacity=0.85, stroke="white", strokeWidth=0.5)
            .encode(
                x=alt.X("longitude:Q", scale=alt.Scale(domain=[129, 138.2]), title="Longitude"),
                y=alt.Y("latitude:Q", scale=alt.Scale(domain=[-26.2, -10.8]), title="Latitude"),
                color=alt.Color("selected:N", title=None,
                                scale=alt.Scale(domain=[r["sa2_name"], "Other SA2s"], range=[NBN_COLOUR, MUTED]),
                                legend=alt.Legend(orient="bottom")),
                order=alt.Order("selected:N", sort="ascending"),
                tooltip=["community:N", "community_type:N", "sa2_name:N",
                         alt.Tooltip("sa2_rank:Q", title="SA2 rank")],
            )
            .properties(height=420)
        )
        st.altair_chart(loc, width="stretch")
        st.caption("BushTel GDA94 points; check records near SA2 boundaries before operational use.")

    st.download_button(
        f"Download {r['sa2_name']} records (CSV)",
        recs.to_csv(index=False).encode(),
        file_name=f"sa2_{code}_{r['sa2_name'].replace(' ', '_')}_records_{file_tag}.csv",
        mime="text/csv",
    )

# --------------------------------------------------------------------------
# Tab 3: sensitivity
# --------------------------------------------------------------------------
with tab_sens:
    st.subheader("How much does the ranking depend on the weights?")
    sens = ranked[["sa2_code", "sa2_name"]].copy()
    cols = {}
    for label, w in TRIAL_WEIGHTS.items():
        s = score(candidates, w)[["sa2_code", "rank"]].rename(columns={"rank": f"Rank {label}"})
        sens = sens.merge(s, on="sa2_code")
        cols[f"Rank {label}"] = label
    current_col = f"Rank {weight_label(mobile_w)} (current)"
    sens = sens.merge(ranked[["sa2_code", "rank"]].rename(columns={"rank": current_col}), on="sa2_code")
    sens = sens.sort_values([current_col, "sa2_name"])
    if weight_label(mobile_w) in TRIAL_WEIGHTS:
        sens = sens.drop(columns=current_col)
    st.dataframe(sens.drop(columns="sa2_code").rename(columns={"sa2_name": "SA2"}),
                 hide_index=True, width="stretch", height=35 * (len(sens) + 1) + 3)

    tops = {label: score(candidates, w).head(TOP_N)["sa2_name"].tolist() for label, w in TRIAL_WEIGHTS.items()}
    same = all(t == tops[BASELINE] for t in tops.values())
    if same:
        st.success(f"The top {TOP_N} SA2s keep the same order under 50/50, 60/40 and 70/30: "
                   + ", ".join(tops[BASELINE]) + ".")
    else:
        st.warning("The top five changes across the three trial weights.")
    st.caption("Stable ranks are a sensitivity observation only; they do not validate the score.")

    # Rank across the full weight range
    sweep = pd.concat(
        [score(candidates, w / 100)[["sa2_name", "rank"]].assign(mobile_weight=w) for w in range(0, 101, 5)]
    )
    focus = ranked.head(TOP_N)["sa2_name"].tolist()
    sweep["group"] = sweep["sa2_name"].where(sweep["sa2_name"].isin(focus), "Other")
    base = alt.Chart(sweep).encode(
        x=alt.X("mobile_weight:Q", title="Mobile premises weight (%)", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("rank:Q", title="Rank", scale=alt.Scale(reverse=True, domain=[1, len(ranked)]),
                axis=alt.Axis(tickMinStep=1)),
        detail="sa2_name:N",
        tooltip=["sa2_name:N", "mobile_weight:Q", "rank:Q"],
    )
    other = base.transform_filter(alt.datum.group == "Other").mark_line(color=MUTED, strokeWidth=1)
    hi = base.transform_filter(alt.datum.group != "Other").mark_line(strokeWidth=2.5, point=True).encode(
        color=alt.Color("sa2_name:N", title=f"Current top {TOP_N}", sort=focus)
    )
    rule = alt.Chart(pd.DataFrame({"x": [mobile_pct]})).mark_rule(strokeDash=[4, 3], color="#555").encode(x="x:Q")
    st.markdown("**Rank of each SA2 across the whole weight range** (dashed line = current setting)")
    st.altair_chart((other + hi + rule).properties(height=380), width="stretch")
    st.caption(
        "At 0% mobile weight the score is only the NBN fixed gap, so the 13 SA2s with 0% NBN fixed tie. "
        "Rank changes happen mainly between SA2s whose mobile and NBN fixed gaps pull in opposite directions."
    )

# --------------------------------------------------------------------------
# Tab 4: export
# --------------------------------------------------------------------------
with tab_export:
    st.subheader("Take the results offline")
    st.markdown(
        f"Exports use the current weights (**mobile/NBN fixed = {weight_label(mobile_w)}**). "
        "The offline pack is a small zip that opens without internet access: a script-free HTML "
        "report you can print or email, plus the two CSVs and a README with the caveats."
    )
    pack = offline_pack(ranked, comm_exp, rank_exp, mobile_w, stamp)
    e1, e2, e3, e4 = st.columns(4)
    e1.download_button(
        f"Offline pack (.zip, {len(pack) / 1024:.0f} KB)", pack,
        file_name=f"nt_connectivity_offline_pack_{file_tag}.zip", mime="application/zip",
        type="primary", width="stretch",
    )
    e2.download_button(
        "Report only (.html)", offline_html(ranked, comm_exp, mobile_w, stamp).encode(),
        file_name=f"nt_connectivity_report_{file_tag}.html", mime="text/html",
        width="stretch",
    )
    e3.download_button(
        "SA2 ranking (.csv)", rank_exp.to_csv(index=False).encode(),
        file_name=f"sa2_ranking_{file_tag}.csv", mime="text/csv", width="stretch",
    )
    e4.download_button(
        "BushTel records (.csv)", comm_exp.to_csv(index=False).encode(),
        file_name=f"bushtel_records_{file_tag}.csv", mime="text/csv", width="stretch",
    )
    st.markdown("**Preview: SA2 ranking CSV**")
    st.dataframe(rank_exp, hide_index=True, width="stretch", height=35 * (len(rank_exp) + 1) + 3)

# --------------------------------------------------------------------------
# Tab 5: method and limitations
# --------------------------------------------------------------------------
with tab_about:
    st.subheader("Method")
    st.markdown(
        f"""
1. **Regional dataset** — {len(master)} NT SA2s from the Digital Connectivity Indicators, joined to
   ABS 2025 estimated resident population on the nine-digit SA2 code.
2. **Candidate SA2s** — the {len(candidates)} SA2s that contain at least one of the
   {community['bushtel_id'].nunique()} mapped BushTel Major/Minor records. This is a project selection
   rule, not an official remoteness classification (Katherine is included for this reason).
3. **Gaps** — `mobile gap = 100 − mobile premises %`, `NBN fixed gap = 100 − NBN fixed premises %`.
4. **Trial score** — weighted sum of the two gaps. 60/40 is the main trial; 50/50 and 70/30 are
   sensitivity checks. Mobile area %, NBN satellite %, population, 2022 name matches and digital
   inclusion summaries are **context only**.
"""
    )
    st.subheader("Limitations")
    st.markdown(
        """
- **SA2 aggregation** — an SA2 can cover a very large area with different local conditions.
- **Coverage meaning** — availability percentages do not measure speed, reliability, affordability,
  usage, indoor reception or user experience.
- **Different source dates** — the datasets have different reference periods.
- **Historical mobile list** — the 2022 list is context; a non-match is not proof of no current service.
- **Technology scope** — satellite is not in the score; zero NBN fixed ≠ zero broadband.
- **Population** — ABS population is for the whole SA2, not a mapped community.
- **Geography** — BushTel GDA94 points were compared with GDA2020 SA2 boundaries without a datum
  transformation; check records near boundaries.
- **Exploratory weights** — no weighting here is an official investment formula.
"""
    )
    if inclusion is not None:
        st.subheader("Broad digital inclusion context")
        st.caption("First Nations Digital Inclusion Dashboard summaries. These are broad geographic "
                   "summaries and are never assigned to individual SA2s or communities.")
        st.dataframe(
            inclusion.rename(columns={"geographic_summary": "Summary", "adii_score": "ADII score"}).round(1),
            hide_index=True,
        )
    st.subheader("Sources")
    st.markdown(
        """
- DITRDCA — [Digital Connectivity Indicators (LGA, SA2, SUAs)](https://catalogue.data.infrastructure.gov.au/dataset/digital-connectivity-indicators-maps-lga-sa2-suas)
- ABS — [Regional population, 2024–25](https://www.abs.gov.au/statistics/people/population/regional-population/2024-25)
- ABS — [ASGS Edition 3 digital boundary files](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/digital-boundary-files)
- NT Government — [BushTel community profiles](https://bushtel.nt.gov.au/)
- NT Government — [Mobile phone coverage in remote areas (2022)](https://data.nt.gov.au/dataset/mobile-phone-coverage-in-remote-areas-of-the-nt)
- ADII — [First Nations Digital Inclusion Dashboard](https://dashboard.digitalinclusionindex.org.au/FirstNations/Home/)
"""
    )
