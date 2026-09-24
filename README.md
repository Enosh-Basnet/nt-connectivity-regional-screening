# NT Connectivity Regional Screening

A Python data project for the CDU IT Code Fair Data Innovation Challenge. It combines Northern Territory (NT) connectivity indicators, regional population data, and a geographic community lookup to identify **SA2 regions for further connectivity investigation**.

The original project question is: *Which remote NT communities should be prioritised for connectivity investment, and can a data-driven Connectivity Priority Index identify the areas of greatest need?* The available coverage measurements are reported for **Statistical Areas Level 2 (SA2s)**, not for individual communities. This prototype therefore ranks regional coverage gaps and lists communities to investigate within those regions. It does not produce an investment ranking of communities.

## What the analysis produces

- A clean NT dataset containing 68 SA2s with coverage and 2025 population fields.
- A reference view of 96 BushTel Major/Minor communities mapped to 16 of those SA2s.
- A trial score for the 16 SA2s, plus 50/50 and 70/30 weight comparisons.
- An audit of direct name matches against a separate 2022 mobile-sites list.
- Regional charts and an optional interactive chart of communities nested within SA2s.

The 16 candidate SA2s were selected because at least one mapped BushTel Major/Minor community falls inside each one. **This is not an official ABS classification of 16 remote SA2s.**

## Data sources

| Input file | Source and level | Role in this project |
| --- | --- | --- |
| `SA2 Coverage Indicators(1).xlsx` | [Australian Government Digital Connectivity Indicators](https://catalogue.data.infrastructure.gov.au/dataset/digital-connectivity-indicators-maps-lga-sa2-suas); SA2 percentages | Mobile premises and area availability; NBN fixed and satellite premises availability |
| `32180DS0001_2024-25(1).xlsx` | [ABS Regional population, 2024–25](https://www.abs.gov.au/statistics/people/population/regional-population/latest-release), Table 7; SA2 | 2025 estimated resident population, area, and population density |
| `mobile-coverage-all-sites(1).xlsx` | [NT Government mobile coverage in remote areas, 2022](https://data.nt.gov.au/dataset/mobile-phone-coverage-in-remote-areas-of-the-nt); listed sites | Historical context and direct community-name matching only |
| `FN-home(1).xlsx` | [First Nations Digital Inclusion Dashboard](https://dashboard.digitalinclusionindex.org.au/FirstNations/Remote/); broad geographic summaries | NT, Remote, and Very Remote context only |
| `NT_Community_SA2_Reference.xlsx` | Supplied geographic lookup based on [BushTel community profiles](https://bushtel.nt.gov.au/profile) and [ABS ASGS Edition 3 SA2 digital boundaries](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/digital-boundary-files) | Maps BushTel community coordinates to containing SA2 codes; see its **Method and sources** sheet |

The geographic lookup was prepared separately **with AI assistance**. It is an input to the Python analysis, not an output derived from the four original spreadsheets. It includes BushTel IDs, coordinates, aliases, SA2 assignments, and source notes. The lookup contains 59 Major and 37 Minor records (96 total); this selection should not be described as an official list of 76 communities. Its documented coordinate comparison used BushTel GDA94 coordinates with GDA2020 SA2 boundaries without a datum transformation, so points near boundaries merit an additional check.

## How the data is processed

1. Read the four source workbooks and check their sheets and fields.
2. Keep the 68 NT SA2 records from the coverage workbook, using SA2 codes beginning with `7`; check missing values, duplicates, and percentage ranges.
3. Extract 2025 SA2 population and geographic fields from ABS Table 7.
4. Join coverage to population on the **nine-digit SA2 code**; all 68 codes match, with no duplicate keys or SA2 name disagreements.
5. Join the supplied BushTel-to-SA2 lookup to the regional dataset; all 96 entries match an SA2, covering 16 distinct SA2s.
6. Compare cleaned community names with the 2022 mobile list. The full lookup has 59 direct name matches and 37 without a direct match. A nonmatch may reflect a different name or absence from a historical list; it **does not prove lack of mobile coverage**.
7. Calculate trial regional gap scores and compare their ranks under three weights.

The 2022 file includes 148 rows labelled `COMMUNITY`, as well as other site types. The name-match count is descriptive context and does not enter the score. The digital inclusion summary is also contextual and is never copied onto individual SA2 or community rows as if measured there.

## Trial SA2 scoring method

The score uses two **SA2-level availability gaps**, each measured in percentage points:

```text
mobile_premises_gap = 100 - mobile_premises_pct
nbn_fixed_gap       = 100 - nbn_fixed_premises_pct

trial_score_60_40 = 0.60 × mobile_premises_gap
                  + 0.40 × nbn_fixed_gap
```

Higher values mean a larger combined *regional availability gap* for these two technologies. The 60/40 choice is a trial assumption, not a validated policy weight. The same data are tested with 50/50 and 70/30 weights. `mobile_area_pct`, NBN satellite availability, SA2 population, the 2022 name-match flag, and the digital inclusion summaries are displayed or discussed as context; they are **not components** of this score.

NBN fixed availability describes the fixed NBN technology category, not all ways a premise might obtain internet. In 13 of the 16 candidate SA2s, its reported availability is 0%, so this component does little to separate most of the regions. Their relative ordering mainly follows the mobile premises gap. A high score is a prompt to investigate, not proof that every community in that SA2 has poor connectivity.

## Trial results

| Regional rank | SA2 | 60/40 trial score | Mapped BushTel communities |
| ---: | --- | ---: | ---: |
| 1 | Victoria River | 65.8 | 7 |
| 2 | Barkly | 62.8 | 9 |
| 3 | Tanami | 59.2 | 8 |
| 4 | Sandover – Plenty | 58.0 | 10 |
| 5 | West Arnhem | 56.2 | 6 |

These five SA2s contain **40 mapped communities to investigate**. Among those 40, 23 have a direct cleaned-name match in the 2022 mobile-sites file; the remaining 17 require further checking. The five leading SA2s retain their order under the three trial weights. That observation does not validate the score or identify individual community needs.

## Reproduce the analysis

An example local layout is:

```text
nt-connectivity-regional-screening/
├── README.md
└── data/
    ├── NT_connectivity_wrangling_walkthrough.py
    ├── SA2 Coverage Indicators(1).xlsx
    ├── 32180DS0001_2024-25(1).xlsx
    ├── mobile-coverage-all-sites(1).xlsx
    ├── FN-home(1).xlsx
    ├── NT_Community_SA2_Reference.xlsx
    └── output/                         # created when the script runs
```

The walkthrough also accepts the four raw workbooks in a `data/` folder beside the script. Install its dependencies in your Python environment:

```bash
python3 -m pip install pandas openpyxl
python3 data/NT_connectivity_wrangling_walkthrough.py
```

The supplied walkthrough sections **1–9** create `nt_sa2_master.csv`, `community_regional_context.csv`, and `digital_inclusion_context.csv` in the script's `output/` directory. The **trial ranking and charts are from subsequent VS Code analysis cells**. Commit those later cells in the repository as a saved notebook or script so someone else can regenerate `trial_sa2_regional_screening.csv` and the charts. The charts use Matplotlib; the optional hover-label chart uses Plotly (`python3 -m pip install matplotlib plotly`). Run the completed notebook or script from a fresh kernel to check that all cells work in order.

The trial regional CSV has one row per candidate SA2, including the gap components, three scores, mapped-community counts, and direct 2022 name-match counts. The community CSV repeats SA2 values alongside community identifiers for **context**; its regional percentages and regional population are not community measurements.

## Interpretation and limitations

- **Geography:** SA2s can span large areas and include places with very different local conditions. A community's containing SA2 score is not that community's score. Katherine is also among the 16 selected SA2s because of mapped communities, demonstrating why this set should not be called a formal remoteness classification.
- **Meaning of coverage:** The government indicators estimate the share of premises or land area where a technology is available. They do not measure service use, cost, actual speed, reliability, indoor reception, or experience at any named community.
- **Timing:** The data sources have different reference dates. The NT mobile-sites file describes sites listed in 2022; a missing direct name match is not a current no-service finding.
- **Population:** The 2025 ABS population represents the entire SA2. It cannot be used as the population of a mapped BushTel community or the number of residents lacking service.
- **Technology:** Zero NBN fixed availability does not mean zero broadband availability. Satellite is reported separately and is not the same service type as NBN fixed.
- **Inclusion:** NT, Remote, and Very Remote inclusion scores are broad summaries and cannot be assigned to individual communities or SA2s.
- **Decision status:** The index weights are exploratory. Community-level investment decisions need current local coverage evidence and input on reliability, affordability, demand, and proposed solutions.

## Next step

Use the top-ranked **regions** to decide where to conduct community-level checks. Record what is known for each community, validate local service conditions with current sources and people on the ground, then revise the indicators and weights before making an investment recommendation.

## AI assistance

AI assistance was used to prepare the BushTel-to-SA2 geographic reference workbook and to help draft the Python walkthrough and explanatory text. The student ran the wrangling and scoring steps, reviewed join counts and outputs, and is responsible for checking the analysis and describing AI use accurately in the Code Fair submission.
