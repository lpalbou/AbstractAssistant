# 1045 — Orb CI presentation sampling

Original full CI39250011911:80/81 passed; the return snapshot already matched the final
sphere, so the intermediate-frame assertion failed. All new automation/update UI cases passed.

The revised fixture uses a two-second animation through the production component; normal app
calls retain the650ms default. Original intermediate-frame and reversal difference assertions
remain. Explicit production-artwork samples at0.7→0.35→0.65 also prove the reverse geometry at
both rendered sizes. Comparison images are reduced to view resolution, avoiding millions of
unoptimized byte operations on the UI thread between animation frames. Endpoints, return and
Reduced Motion checks remain. No visual thresholds are relaxed and no test is skipped.

Local revised orb suite plus new automation/update UI:6/6 pass, zero skipped/failed. Package
suite251/251 passes, including retry occurrence identity. Sampled images were visually inspected.
The final full hosted suite is required before upload; no failing candidate was offered for
approval. Production styling and default timing, Framework/server and other Watch work unchanged.

Final hosted39257198880:81/81 passed, zero skipped or failed. Verified126.1 candidate remains at the human upload gate. Full summary: full-ci-native.json.
