# Qualitative judge

The fixed version-1 rubric scores relevance, coherence and tone separately from factual/price checks. Anchors 1–5, opaque randomized IDs, absence of provider/token/length metadata, and an explicit anti-verbosity rule reduce biases; they do not eliminate judge bias. Batched scoring can create cross-candidate influence. Pairwise mode uses batches of two matched cases, compares their dimension scores, and randomizes presentation with a reproducible seed.

`python -m eval.judge.run --live --batch-size 4 --seed 42` uses the configured judge route and existing quota counters. It only judges real recordings with itineraries; it resumes by skipping existing judgments. `--pairwise` requires exactly matched two-candidate batches and fails on incompatible pairs. Judge usage consumes quota but is not included in agent per-trip token metrics.

After recording at least 20 itineraries:

```
python -m eval.judge.make_calibration_set
```

No synthetic calibration is allowed. Missing recordings produce `no recorded runs yet; run make eval-record first`; fewer than 20 also stop. The CSV is not overwritten. Fill `human_relevance`, `human_coherence`, `human_tone` with integers 1–5. Judge columns are blank during human review to reduce anchoring. Agreement reads judge scores from recorded files by ID, so score them before computing agreement:

```
python -m eval.judge.agreement
```

The report includes per-dimension sample sizes, Spearman rank correlation and Cohen's kappa for scores >=4 versus <4. Missing pairs are excluded, fewer than two pairs say not run, and constant inputs yield undefined (`None`) statistics. Low or negative agreement is reported unchanged. Calibration sampling is seeded, not a claim of population representativeness.

Judge output allowance scales with batch size using `evaluation.judge.output_tokens_per_itinerary` in models.yaml. `evaluation.judge.attempts` bounds invalid-JSON/schema retries; retries preserve the rubric and blinded order, and consume the normal provider quota. Partial or missing judgments are never accepted. Completed per-file judgments are saved atomically; a failed batch leaves human labels and earlier completed judgments unchanged. Rerun the same command to resume. These controls do not guarantee a provider will return valid JSON.
