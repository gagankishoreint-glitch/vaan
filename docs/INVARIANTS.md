# INVARIANTS -> ENFORCEMENT MAP

Each invariant from the brief, where it is enforced, and what would catch a violation.

| # | Invariant | In-process guard (development) | File-level checker (authority) | Test |
|---|---|---|---|---|
| 1 | Exactly one terminal event per request | `RequestScope.terminal` raises `TerminalEventAlreadyEmitted`; `_terminal_emitted` is set before the emit, so a concurrent second call cannot race through | `check_events.py` I1 | `test_exactly_one_terminal`, `test_concurrent_terminals_exactly_one`, `test_double_terminal_fails` |
| 2 | No attempt starts after the terminal event | `RequestScope.attempt_start` raises | I2 (file order, with `t_mono` as secondary) | `test_no_attempt_after_terminal`, `test_attempt_after_terminal_fails`, `test_attempt_after_terminal_caught_by_order_without_timestamps` |
| 3 | No bucket goes negative | P5: `Budget.take()` asserts post-state >= 0; check-and-take with no await between | I3 `budget.update.remaining_after >= 0` | `test_negative_bucket_fails` + P5 unit test |
| 4 | waiting + working + retrying ~= total | `RequestScope.finish` is the only exit, so the three parts come from one place | I4 with `observability.latency_sum_tolerance_s` | `test_latency_sum_mismatch_fails_and_within_tolerance_passes`, `test_retry_sleep_without_totals_fails` |
| 5 | `send_reply` accepts only `VerifiedAnswer | NoEvidence | PassagesOnly` | `contracts.is_reply()` is the single test; P5/P6 `send_reply` asserts it | I5 permitted reply types | `test_is_reply_is_the_h1_gate`, `test_unpermitted_reply_fails` |
| 6 | No tokens consumed after abandonment | P7: cancel the task, then assert no `attempt.*` follows | I6 tokens after `request.abandoned` | `test_tokens_after_abandon_fail` |
| 7 | Every cited chunk_id exists; every quote is a verbatim substring | P6 `verify.py`: code check before any LLM check | `scripts/check_citations.py` (lands with P2 chunks) | P6 |
| 9 | (new, D-008) `backend` is run scope, `attempt_backend` is attempt scope | `ReservedFieldError` on any collision with the envelope | I7 | `test_reserved_field_collision_raises`, 4 `I7` cases |
| 8 | `VerifiedAnswer` only via `mint_verified()`, only from `pipeline/verify.py` | `__post_init__` raises unless `_minted` | **AST lint** over `relay/` | `test_mint_verified_only_called_from_verify_module`, `test_direct_construction_rejected` |

## Rules -> enforcement

| Rule | How it is kept |
|---|---|
| 7 (monotonic through Clock) | `test_no_direct_time_monotonic_outside_clock`, `test_no_asyncio_sleep_outside_clock` |
| 8 (never swallow CancelledError, never block the loop) | `test_no_bare_except_in_package` (bare `except:` and `except BaseException`), `test_emit_does_not_block_caller`, `test_cancelled_sleep_propagates` |
| 4 (no magic numbers) | `test_no_hardcoded_model_or_url_in_package`, `test_require_refuses_null`, `test_no_orphan_tbd_comments` |
| 1 (contracts are leaves) | `test_contracts_module_is_a_leaf` |

## Honest gaps

- Invariant 3, 6, 7 are **not yet enforceable** because the code they guard does not exist.
  The checker already accepts and validates the event shapes they will emit, so a violation
  shows up as a checker failure on the first run that does it, not in review.
- Invariant 5 depends on every send path calling `is_reply()`. That is a convention until
  P6 adds the assertion inside `send_reply`. Listed as a risk.
- `test_no_direct_time_monotonic_outside_clock` is a text scan, not an AST walk, so a call
  split across lines could slip past. Accepted: the alternative is a full dataflow analysis,
  and the cost of a miss is a wrong duration in one event, caught by I4.
