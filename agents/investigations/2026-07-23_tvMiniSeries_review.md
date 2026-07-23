# DQ Review: titleType: tvMiniSeries

**Date**: 2026-07-23
**Reviewer**: AI Agent (Claude Code / dqm-review) — independent session
**Investigation reviewed**: local-agents/investigations/2026-07-23_tvMiniSeries.md

---

## Overall Verdict

**OVERALL: ENDORSE-WITH-CAVEATS**

**One-line summary**: Core verdict (NO ACTION NEEDED) is correct and most SQL logic is sound, but the "accelerated continuation of a 12-year trend" framing is factually wrong for the driver genres, and the pipeline lag claim about the numerator is not supported by data.

---

## Finding-by-Finding Assessment

### Finding 1: Two compounding effects drive the flag — numerator up +33.6%, denominator down -7.1%
- **Assessment**: CONFIRMED
- **SQL logic**: Query 1 correctly replicates the flagged metric using the same `basics JOIN ratings` join. The replication is faithful.
- **Result interpretation**: Correct — 1,412→1,887 tvMiniSeries and 66,745→62,037 total are accurate.
- **Alternative explanation**: None; the arithmetic is unambiguous.

---

### Finding 2: Denominator shrinkage is pipeline lag — tvEpisode is the main driver
- **Assessment**: CONFIRMED
- **SQL logic**: Query 2 correctly identifies the breakdown by titleType. tvEpisode at -3,294 titles is the dominant driver of the -4,708 denominator drop.
- **Result interpretation**: Correct. Pipeline lag explanation for other types (tvEpisode, short, tvSeries declining while tvMiniSeries grows) is well-supported.
- **Alternative explanation**: None stronger — pipeline lag is the established mechanism for why current-year denominator shrinks, and the pattern (every type except tvMiniSeries declining) is consistent with it.

---

### Finding 3: Drama (+147%) and Romance (+297%) are the genre drivers; this is "accelerated continuation of a 12-year trend"
- **Assessment**: PLAUSIBLE for the genre identification, DISPUTED for the trend characterisation
- **SQL logic**: Query 3 correctly identifies Drama and Romance as the drivers. The avg_votes as a proxy for engagement level is reasonable but not definitive.
- **Result interpretation**: The genre identification is correct. The "accelerated continuation of a 12-year trend" framing is **wrong**. Challenge Query 1 (below) shows Drama and Romance were FLAT or DECLINING from 2021-2023, then exploded in 2024. This is a **structural step-change**, not an acceleration. The 12-year trend in the overall tvMiniSeries share is gradual; the 2024 Drama/Romance surge is discontinuous and unexplained by any prior trajectory.
- **Alternative explanation**: The step-change could indicate a specific data submission event (e.g., a major Asian streaming platform bulk-registering its 2024 catalog on IMDB), rather than organic industry growth. The Analyst did not investigate this possibility.

---

### Finding 4: Growth is entirely in the micro-engagement long tail — popular titles unchanged at 3
- **Assessment**: CONFIRMED
- **SQL logic**: Query 4 correctly segments by vote bucket and compares 2023 vs 2024. The micro_under100 bucket (+344, +182%) vs popular_10kplus unchanged at 3 is valid.
- **Result interpretation**: Correct. The blockbuster-skew hypothesis is effectively ruled out. The finding that entire growth is concentrated in low-engagement content is robust.
- **Alternative explanation**: The very low vote counts (micro_under100 dominates) are consistent with both organic international long-tail growth AND a one-time bulk registration event. The Analyst correctly identifies the low-engagement pattern but cannot distinguish between these two causes from vote counts alone.

---

### Finding 5: Pipeline lag will inflate the 2024 denominator when data matures, implying the tvMiniSeries % will recalculate lower
- **Assessment**: NEEDS-RECHECK
- **SQL logic**: The Analyst correctly notes that unrated tvEpisode/short/tvSeries titles will eventually accumulate votes and grow the denominator.
- **Result interpretation**: Partially correct for the denominator. **Critically incorrect for the numerator.** The Analyst implies the numerator is also suppressed by pipeline lag — this is not supported. Challenge Query 2 (below) shows that tvMiniSeries pct_rated in 2024 is **46.2%**, the HIGHEST in four years (vs 40.2% in 2023, 39.3% in 2022). Pipeline lag is not suppressing the tvMiniSeries count — these titles are accumulating ratings at an above-average rate. The 2024 unrated tvMiniSeries pool (2,199 titles) will also grow the numerator as data matures. The net directional effect on the percentage is uncertain, not clearly "will recalculate lower."

---

## Independent Challenge Queries

### Challenge 1: Are Drama/Romance genre trends genuinely a gradual acceleration, or a 2024 step-change?

**Why**: The Analyst characterises 2024 as "accelerated continuation of a 12-year trend." If true, we should see steady growth 2021→2022→2023→2024 in Drama/Romance. If it is a step-change, the pattern will be flat then jump.

```sql
SELECT b.startYear, b.genres, COUNT(*) as cnt
FROM basics b JOIN ratings r USING (tconst)
WHERE b.titleType = 'tvMiniSeries'
  AND b.startYear IN (2021, 2022, 2023, 2024)
  AND b.genres IN ('Drama','Romance')
GROUP BY b.startYear, b.genres
ORDER BY b.startYear, cnt DESC
```

**Result:**
```
startYear  genres   cnt
2021       Drama    169
2021       Romance  39
2022       Drama    151
2022       Romance  35
2023       Drama    164
2023       Romance  58
2024       Drama    405
2024       Romance  230
```

**Finding**: **The "accelerated continuation" framing is incorrect.** Drama was flat/declining 2021-2023 (169→151→164) and Romance was similarly flat (39→35→58). The 2024 values (405 Drama, 230 Romance) represent a **sudden discontinuous jump with no prior acceleration signal**. This is a structural step-change, not a continuation. The Analyst's root cause narrative should be revised: the 2024 surge is a novel event requiring further investigation, not predictable from the 12-year trend.

---

### Challenge 2: Does pipeline lag suppress the tvMiniSeries numerator (pct_rated trend)?

**Why**: The Analyst claims pipeline lag is a secondary driver. If it affects all types equally, it should suppress tvMiniSeries rated counts too (lower pct_rated in 2024 vs prior years). If tvMiniSeries is immune, the numerator growth is entirely organic and may not "recalculate lower" when 2024 matures.

```sql
SELECT b.startYear,
       COUNT(*) AS total_in_basics,
       COUNT(r.tconst) AS has_ratings,
       COUNT(*) - COUNT(r.tconst) AS unrated,
       ROUND(100.0 * COUNT(r.tconst) / COUNT(*), 1) AS pct_rated
FROM basics b
LEFT JOIN ratings r USING (tconst)
WHERE b.titleType = 'tvMiniSeries'
  AND b.startYear BETWEEN 2021 AND 2024
GROUP BY b.startYear
ORDER BY b.startYear
```

**Result:**
```
startYear  total_in_basics  has_ratings  unrated  pct_rated
2021       4136             1383         2753     33.4
2022       3831             1504         2327     39.3
2023       3516             1412         2104     40.2
2024       4086             1887         2199     46.2
```

**Finding**: **Pipeline lag is NOT suppressing the tvMiniSeries numerator.** The pct_rated for tvMiniSeries has risen every year: 33.4% → 39.3% → 40.2% → 46.2%. In 2024, nearly half of all registered tvMiniSeries already have ratings — the highest rate in four years. This is the opposite of what pipeline lag would predict. It suggests the 2024 Drama/Romance titles are actively viewed and voted on despite being low-engagement by absolute vote count. The 2,199 unrated 2024 tvMiniSeries will increase the numerator further as they accumulate votes, partially offsetting the denominator recovery. The Analyst's claim that the % "will likely recalculate lower" is uncertain and may be wrong in direction.

---

## Gaps and Missed Checks

- [ ] **Did not verify the genre trend by year 2021-2023.** The Analyst cited a "12-year trend" without checking whether Drama/Romance specifically showed any growth in recent years. They did not. This is a material characterisation error.
- [ ] **Did not run any of the three VERIFY queries before assigning HIGH confidence.** VERIFY query 3 (the pct_rated check) was among the suggested queries — if the Analyst had run it, the pipeline lag numerator claim would have been caught before finalising.
- [ ] **Did not test the bulk registration hypothesis.** If a single platform submitted thousands of titles in 2024, this could be detectable by looking at tconst ranges (IMDB assigns sequential IDs), or by checking whether Drama/Romance tvMiniSeries submissions cluster by date. The Analyst dismissed this scenario without evidence.
- [ ] **Confidence rating of HIGH is not fully supported.** Two of the five findings have material caveats (genre trend characterisation, pipeline lag numerator claim). MEDIUM-HIGH would be more accurate.

---

## Recommendation

**ENDORSE-WITH-CAVEATS**: The core verdict (NO ACTION NEEDED) stands. The DQ check flagged a real and explainable phenomenon. No data integrity issues were found. The investigation can be presented to the business team with the following amendments before finalisation:

1. **Replace "accelerated continuation of a 12-year trend"** with "discontinuous step-change in 2024 for Drama/Romance genres that was not present in 2021-2023." The overall tvMiniSeries share grew gradually for 12 years, but the 2024 Drama/Romance surge specifically is a novel structural break.

2. **Remove or qualify the claim that "tvMiniSeries % will likely recalculate lower when 2024 data matures."** The pct_rated for tvMiniSeries is rising (now 46.2%, highest on record), meaning the numerator will also grow as unrated 2024 titles accumulate votes. The net directional effect on the final percentage is uncertain.

3. **Lower confidence from HIGH to MEDIUM-HIGH** to reflect the unresolved question of WHY 2024 specifically caused such a dramatic step-change. The known explanation (international long-tail content) is plausible but not proven — a bulk registration event could produce the same signal.

The recommended fence recalibration after 2024 matures is sound and endorsed without modification.

---

## Banking Compliance Note

This review was produced by an AI agent operating independently of the original investigation. It reduces but does not eliminate the risk of misinterpretation. A qualified human analyst must review both the investigation and this review before any operational decision or escalation. Specifically: the unresolved "bulk registration vs organic growth" question should be assessed by someone with access to IMDB submission metadata or industry knowledge about 2024 Asian streaming catalog events, which neither agent had access to.
