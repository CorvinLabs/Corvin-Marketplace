# Experiments

One folder per experiment: `docs/data/experiments/<slug>/` with the raw data and a `MANIFEST.sha256`.
Raw data is not an entity type; the entities that frame it are:

1. `kb new idea --title "..."` - the question.
2. `kb new plan --title "EXP-<slug>: ..." --link derived_from=IDEA-0001` - the PREREGISTRATION. Commit it BEFORE the first data point; never edit it afterwards, amend with a dated note.
3. Collect the data into `docs/data/experiments/<slug>/`, write `MANIFEST.sha256`.
4. `kb new note --title "EXP-<slug> result" --link derived_from=PLAN-0001 --link evidence=repo:<project>/docs/data/experiments/<slug>` - the result, negative results included.
