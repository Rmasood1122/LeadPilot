# Native agent cores

- `rust/`: `vectorae_native_rs` (PyO3, abi3): lead priority, follow-up timing, and the
  master supervisor. `cargo test` runs without Python (the bindings are the
  `python` feature, which maturin enables).
- `cpp/`: `vectorae_native_cpp` (C++17, pybind11, scikit-build-core): deliverability
  guard, reply triage, claim check. A plain CMake build runs the core's ctest.

See `docs/features/vectorae-agents.md`. Keep `app/agents/reference.py` in step with
any change here; `tests/test_agents_native_parity.py` enforces it.
