# Kickoff: Taupin, NASA Space Apps 2026, "Field Shift: Adapting Farms with NASA Data"

Track: judged sprint. Read on 2026-11-14.

## Scoring
- Human judges score 1 to 5 on each of five criteria: Impact, Creativity, Validity, Relevance, Presentation (source: https://www.spaceappschallenge.org/resources/judging-awards-guide/)
- Impact: "addressing either a minor or major problem"; a 5 "benefits a large audience" (source: https://www.spaceappschallenge.org/resources/judging-awards-guide/)
- Validity: "grounded in scientific principles", "ready for real-world implementation", "highly usable and user-friendly" (source: https://www.spaceappschallenge.org/resources/judging-awards-guide/)
- Relevance: "meaningfully integrates NASA data, utilizing it as a core component of the proposed solution rather than a superficial addition" (source: https://www.spaceappschallenge.org/resources/judging-awards-guide/)
- Presentation: "Judges evaluate the demo and full project to compute this score" (source: https://www.spaceappschallenge.org/resources/judging-awards-guide/)

## Test construction
- Judges read the project submission page and one demo: a slide deck of at most seven slides including title and intro, or a video of 30 seconds or less, in English, at a public link with no login; "the majority of judges' evaluation will be based on your project submission" (source: https://www.spaceappschallenge.org/resources/project-submission-guide/)
- Global awards need at least one NASA data source from the challenge Resources tab; every external resource is listed in the References field (source: https://www.spaceappschallenge.org/resources/judging-awards-guide/)

## Designer
- exposes: whether a team turns NASA data into a decision a farmer can act on this season
- obvious: a map dashboard of NASA layers with no decision, or a classifier demo with NASA data bolted on
- hypothesis: a per-field scouting plan (where to put bait traps, which days, what count means "no coated seed needed") scores higher on Impact and Validity than a risk table
- hypothesis: a 3D field whose colours come from NASA layers and a trained risk model reads as "NASA data is core" in a 30 second look; a satellite photo draped on a mesh does not
- hypothesis: a risk model with a held-out score on real bait-trap data scores higher on Validity than literature coefficients alone

## Test conditions
- A judge clones the repo and starts the app with the system Python (rebuild: run.sh)
- A judge drops a soil-insect photo and sees the map update or the photo go to the lab queue (rebuild: train/final_eval.py)
- A judge reads the 3D field and the trap plan built from NASA and soil layers (rebuild: src/taupin/bake.py)
- A judge reads the README numbers and checks them against the metrics file (rebuild: model/metrics.json)

## Bar
- bar: none (judged)
- deadline: 2026-11-16T04:59Z
