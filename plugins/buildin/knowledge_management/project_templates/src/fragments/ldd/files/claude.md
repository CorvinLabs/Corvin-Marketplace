## LDD (loss-driven development)

LDD is always on in CorvinOS. For a non-trivial change: run the E2E first and capture the loss signal, argue the strongest counter-case before a recommendation (`dialectical-reasoning`), find the structural origin of a bug before fixing it (`root-cause-by-layer`), and update the docs in the same change (`docs-as-definition-of-done`). A unit test that calls a function directly does not prove that anything calls it.
