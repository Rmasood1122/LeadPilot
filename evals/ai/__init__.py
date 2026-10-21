"""AI evals: golden sets, graders and gating for every model touchpoint.

Extends the release gate in evals/ (run_evals.py -> promote.py) rather than
building a second one: the offline mode runs inside the offline pytest suite
(tests/test_ai_evals.py), so a regression there fails `full_suite_pass_rate`
like any other test. The live mode (evals/ai/live_eval.py) is opt-in, needs a
real key, never runs in CI and stops at a spend ceiling.

Layout:
  framework.py   specs, replay client, runner, metrics, gating rules
  graders.py     code-based graders (preferred) and the model-judge interface
  context.py     an in-memory database and seed helpers for adapters
  adapters.py    one function per touchpoint: case input -> the app's output
  golden/*.yaml  one golden set per touchpoint
  baseline.json  recorded baseline per touchpoint (offline now; live pending)

Program: docs/program/STAR_VICTORAE.md Phase 2.
"""
