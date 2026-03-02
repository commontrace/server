# Phase 7: Hook Pipeline Simplification - Research

**Researched:** 2026-03-02
**Domain:** Claude Code hook pipeline (Python, JSONL bridge files, SQLite)
**Confidence:** HIGH — all findings are from direct code inspection of the live files

## Summary

Phase 7 simplifies the hook pipeline so hooks build context for the agent rather than making decisions on its behalf. The primary architectural shift is threefold: (1) session_start injects a compact pointer-only context block under 1500 chars, (2) post_tool_use becomes a pure JSONL writer with no SQLite writes during sessions, and (3) stop.py becomes the single SQLite persistence point and switches from threshold-gated prompting to agent-assessed prompting.

All changes are confined to three files — `session_start.py`, `post_tool_use.py`, and `stop.py`. No changes to `user_prompt.py`, `session_state.py`, or `local_store.py` are required. The 13 public functions in local_store.py are sufficient for the new batch-persist pattern in stop.py without modification.

The most significant design shift is HOOK-05: removing the `IMPORTANCE_THRESHOLD = 4.0` gate. Instead of the hook deciding whether the session was important enough, the hook presents structural metadata and the agent assesses relevance. This requires careful attention to avoid prompt noise (contribution prompts on every trivial session).

**Primary recommendation:** Decompose into three sequential tasks — session_start (HOOK-01), post_tool_use (HOOK-02), stop.py (HOOK-03 + HOOK-04 + HOOK-05) — in that order, since stop.py depends on the new JSONL files post_tool_use will write.

## Standard Stack

No new libraries are introduced. Phase 7 uses the existing skill stack exclusively.

### Core
| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| Python 3 stdlib | 3.x | json, pathlib, time, os | Zero-dependency constraint for skill hooks |
| JSONL files | — | Session bridge files in /tmp/commontrace-sessions/{session_id}/ | Established pattern from Phase 6; atomic appends on Linux |
| SQLite (local_store.py) | — | Persistent cross-session working memory | Already in place from Phase 6 redesign |

### No New Dependencies

The `session_state.append_event()` and `read_events()` functions in `session_state.py` already handle all JSONL I/O. The five new JSONL file names (`triggers.jsonl`, `search_results.jsonl`, `trace_consumed.jsonl`, `votes.jsonl`) follow exactly the same pattern as existing files (`errors.jsonl`, `changes.jsonl`, etc.).

**No installation required.** This phase is pure refactoring within existing files.

## Architecture Patterns

### Current vs. Target Hook Architecture

```
CURRENT (Phase 6 state):

session_start.py
  └─ SQLite write: ensure_project, start_session
  └─ SQLite read: get_cached_traces, get_project_context, get_trigger_effectiveness
  └─ Writes bridge files: project_id, context_fingerprint.json, trigger_stats.json
  └─ API call: search_traces (with context)
  └─ Output: additionalContext (title + context[:100] + solution[:150] per trace)

post_tool_use.py (PROBLEM: SQLite writes during session)
  └─ SQLite write: record_trigger (via _record_trigger_safe)
  └─ SQLite write: record_error_signature (via _check_error_recurrence)
  └─ SQLite write: record_trace_consumed, mark_trace_used_v2, cache_trace_pointer
  └─ SQLite write: record_trace_vote_v2
  └─ SQLite read: get_project_context (in _check_domain_entry — OK)
  └─ JSONL writes: errors, resolutions, changes, research, contributions, candidates

stop.py
  └─ Reads JSONL files
  └─ compute_importance() → score
  └─ if score >= 4.0: block with contribution prompt (GATES on score)
  └─ _persist_session(): end_session + prune_stale_cache

TARGET (Phase 7):

session_start.py (unchanged SQLite pattern)
  └─ SQLite write: ensure_project, start_session (unchanged)
  └─ SQLite read: get_cached_traces, get_project_context, get_trigger_effectiveness
  └─ Writes bridge files: unchanged
  └─ API call: search_traces (unchanged)
  └─ Output: COMPACT additionalContext under 1500 chars (pointer format only)

post_tool_use.py (JSONL-only writes)
  └─ SQLite read: get_project_context in _check_domain_entry (SELECT, unchanged)
  └─ JSONL writes: errors, resolutions, changes, research, candidates (existing)
  └─ JSONL writes: triggers.jsonl (new — replaces _record_trigger_safe SQLite)
  └─ JSONL writes: search_results.jsonl (new — replaces handle_search_results SQLite)
  └─ JSONL writes: trace_consumed.jsonl (new — replaces handle_trace_consumption SQLite)
  └─ JSONL writes: votes.jsonl (new — replaces handle_vote SQLite)
  └─ contributions.jsonl already captures trace_id (handle_contribution: remove SQLite)

stop.py
  └─ Reads ALL JSONL files (existing + 4 new)
  └─ compute_importance() → metadata only (NOT a gate)
  └─ if candidates exist: present structural context, agent decides
  └─ _persist_session(): batch-persist new JSONL data + end_session + prune_stale_cache
```

### Pattern 1: Compact Pointer Format (HOOK-01)

**What:** session_start emits trace pointers (title + ID only), not content previews.
**When to use:** Any time a trace reference is injected into additionalContext.
**Character budget:**
```
Project: python/fastapi (3rd session)            ~40 chars
1. [Trace Title Here Up To 80 Chars]  (abc123-...) ~130 chars
2. [Second Trace Title]  (def456-...)              ~130 chars
3. [Third Trace Title]  (ghi789-...)               ~130 chars
Use search_traces before solving. Contribute via contribute_trace. ~80 chars
─────────────────────────────────────────────────────────────────
Total: ~510 chars  (target: under 1500)
```

**Example:**
```python
# Source: direct code inspection of session_start.py

def format_result(result: dict) -> str:
    """Compact pointer: title (truncated) + trace ID only."""
    title = result.get("title", "Untitled")[:80]
    trace_id = result.get("id", "")
    return f"[{title}]  ({trace_id})"

def build_additional_context(project_info: str, traces: list[str],
                              instruction: str) -> str:
    parts = []
    if project_info:
        parts.append(project_info)
    if traces:
        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(traces))
        parts.append(numbered)
    parts.append(instruction)
    ctx = "\n".join(parts)
    # Safety cap
    if len(ctx) > 1500:
        ctx = ctx[:1497] + "..."
    return ctx
```

### Pattern 2: JSONL-Only post_tool_use (HOOK-02)

**What:** Every SQLite write in post_tool_use becomes a JSONL append. stop.py reads and persists at session end.
**When to use:** Any new event that was previously going to SQLite during session.

**New JSONL files:**
```python
# Source: direct code inspection of post_tool_use.py + session_state.py

# triggers.jsonl (replaces _record_trigger_safe SQLite call)
append_event(state_dir, "triggers.jsonl", {
    "trigger_name": trigger_name,
    # "t" added automatically by append_event
})

# search_results.jsonl (replaces handle_search_results SQLite call)
for r in results[:5]:
    trace_id = r.get("id", "")
    title = r.get("title", "")
    if trace_id and title:
        append_event(state_dir, "search_results.jsonl", {
            "trace_id": trace_id,
            "title": title[:120],
            "source": "search",
        })

# trace_consumed.jsonl (replaces handle_trace_consumption SQLite calls)
append_event(state_dir, "trace_consumed.jsonl", {
    "trace_id": trace_id,
    "title": title,  # from tool_response if available
    "source": "get_trace",
})

# votes.jsonl (replaces handle_vote SQLite call)
append_event(state_dir, "votes.jsonl", {
    "trace_id": trace_id,
    "vote_type": vote_type,  # "up" or "down"
})
```

### Pattern 3: Batch Persist in stop.py (HOOK-03)

**What:** stop.py reads all new JSONL files and persists to SQLite in correct order.
**When to use:** In `_persist_session()`, after computing stats.

**Order matters:** Triggers must be inserted before trace consumptions are matched.

```python
# Source: direct analysis of local_store.py trigger_feedback pairing logic

def _persist_session(data: dict, state_dir: Path) -> None:
    conn = _get_conn()
    session_id = data.get("session_id") or str(os.getppid())
    project_id = _read_project_id(state_dir)

    # 1. Insert trigger fires (in timestamp order so pairing works)
    triggers = read_events(state_dir, "triggers.jsonl")
    for t in sorted(triggers, key=lambda x: x.get("t", 0)):
        record_trigger(conn, session_id, t["trigger_name"])

    # 2. Match trace consumptions to trigger fires
    consumed = read_events(state_dir, "trace_consumed.jsonl")
    for c in sorted(consumed, key=lambda x: x.get("t", 0)):
        record_trace_consumed(conn, session_id, c["trace_id"])
        if project_id and c.get("title"):
            cache_trace_pointer(conn, c["trace_id"], project_id,
                                c["title"], source=c.get("source", "get_trace"))

    # 3. Cache search result pointers
    search_results = read_events(state_dir, "search_results.jsonl")
    seen_trace_ids = set()
    for r in search_results:
        trace_id = r.get("trace_id", "")
        if trace_id and trace_id not in seen_trace_ids:
            seen_trace_ids.add(trace_id)
            cache_trace_pointer(conn, trace_id, project_id,
                                r.get("title", "")[:120],
                                source=r.get("source", "search"))

    # 4. Record votes
    votes = read_events(state_dir, "votes.jsonl")
    for v in votes:
        record_trace_vote_v2(conn, v["trace_id"], v["vote_type"])

    # 5. Record error signatures
    errors = read_events(state_dir, "errors.jsonl")
    if project_id:
        for e in errors:
            if e.get("sig"):  # sig field added by post_tool_use
                record_error_signature(conn, project_id, e["sig"])

    # 6. Session stats + pruning (existing)
    contributions = read_events(state_dir, "contributions.jsonl")
    score, top_pattern, _ = compute_importance(state_dir)
    end_session(conn, session_id, {
        "error_count": len(errors),
        "resolution_count": len(read_events(state_dir, "resolutions.jsonl")),
        "contribution_count": len(contributions),
    }, top_pattern=top_pattern, importance_score=score)
    prune_stale_cache(conn)
    conn.close()
```

### Pattern 4: Agent-Assessed Contribution Prompt (HOOK-05)

**What:** Present structural session context; the agent decides relevance. No numeric threshold.
**When to use:** When `candidates.jsonl` has at least one entry at session end.

```python
# Source: direct analysis of stop.py _build_prompt() and main()

# OLD gate (to remove):
# if score < IMPORTANCE_THRESHOLD:  # 4.0
#     return

# NEW gate (candidates-based):
candidates = read_events(state_dir, "candidates.jsonl")
if not candidates:
    return  # No patterns detected — skip contribution prompt

# NEW prompt style (structural facts, agent decides):
def _build_prompt(candidates, errors, changes, research, state_dir) -> str:
    patterns = list({c.get("pattern") for c in candidates})
    n_errors = len(errors)
    n_files = len({c.get("file", "") for c in changes if c.get("file")})
    n_research = len(research)

    summary_parts = []
    if n_errors:
        summary_parts.append(f"{n_errors} error(s) encountered")
    if n_files:
        summary_parts.append(f"{n_files} file(s) changed")
    if n_research:
        summary_parts.append(f"{n_research} research event(s)")

    summary = ", ".join(summary_parts) if summary_parts else "activity detected"
    patterns_str = ", ".join(p.replace("_", " ") for p in patterns)

    # metadata_json hint for contribute_trace (unchanged from current)
    metadata_hint = _build_metadata_hint(...)

    return (
        f"Session: {summary}. "
        f"Patterns detected: {patterns_str}. "
        f"Consider contributing to CommonTrace if this session contained "
        f"reusable knowledge. Use contribute_trace or continue. "
        f"{metadata_hint}"
    )
```

### Anti-Patterns to Avoid

- **Removing the `_check_domain_entry()` SQLite read:** `get_project_context()` is a SELECT only, not a write. HOOK-02 prohibits writes only. Keep this read.
- **Inserting trigger_feedback AFTER trace_consumed events:** `record_trace_consumed()` matches against existing unfulfilled trigger_feedback rows. Must insert triggers first.
- **Not truncating API result titles in format_result:** Current `format_result()` in session_start does NOT truncate the title field. Titles can be up to 200 chars (API max). Always truncate to 80 in the new compact format.
- **Removing compute_importance() entirely:** HOOK-04 says patterns produce metadata, not scoring gates. `compute_importance()` is still useful for assembling metadata (top pattern, evidence dict) to pass to `end_session()` and the prompt. Remove the gate, not the function.
- **Caching contributed traces differently than searched traces:** Contributed traces should also go into search_results.jsonl (or contributions.jsonl should be read by the batch persist and cached). Otherwise contributions are never cached locally.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe JSONL appends | Custom file locking | `append_event()` in session_state.py | Already handles atomic appends on Linux for short lines |
| Character counting for context | Custom truncation | Simple `len(ctx) > 1500` check + `[:1497] + "..."` | One-liner; no library needed |
| Trigger-to-consumption pairing | Complex matching algorithm | Sort by timestamp + `record_trace_consumed()` finds most recent unfulfilled trigger | local_store.py already has this logic |
| Batch SQLite inserts | Custom transaction management | Call existing local_store functions in a loop inside one connection | `_get_conn()` returns connection; caller holds it open across all inserts |

**Key insight:** The existing primitives (`append_event`, `read_events`, `session_state.py`, local_store.py's 13 functions) cover everything Phase 7 needs. The work is rewiring, not building.

## Common Pitfalls

### Pitfall 1: Trigger-Contribution Pairing Order
**What goes wrong:** stop.py batch-inserts trace consumptions before trigger fires, so `record_trace_consumed()` finds no trigger_feedback rows to update. Result: all trigger effectiveness stats show 0% conversion.
**Why it happens:** The JSONL files are read independently; it's easy to process `trace_consumed.jsonl` before `triggers.jsonl`.
**How to avoid:** Explicitly process triggers first in `_persist_session()`. Add a comment explaining the dependency.
**Warning signs:** trigger_effectiveness queries always return `consumed = 0` for sessions where traces were actually consumed.

### Pitfall 2: Contribution Prompt Noise (HOOK-05)
**What goes wrong:** Removing the 4.0 threshold means every session with any candidate triggers a blocking prompt — even short sessions where a research+implement candidate was detected from a single web search.
**Why it happens:** `research_then_implement` candidate is detected after any WebSearch followed by a Write, which is extremely common.
**How to avoid:** The candidates gate alone may be insufficient. Consider: require at least 2 distinct pattern types, or require at least 1 error event, or require minimum 2 user turns (already MIN_TURNS = 2 in current code — keep this).
**Warning signs:** Stop hook blocks on nearly every session.

### Pitfall 3: Missing Error Signature in errors.jsonl
**What goes wrong:** `_check_error_recurrence()` in post_tool_use currently computes `error_signature(error_text)` and writes it to SQLite. The new approach adds a `"sig"` field to the errors.jsonl event. If the sig field is missing (e.g., error_text is empty), stop.py silently skips signature recording.
**Why it happens:** `error_text` can be empty if only exit code was available (no stderr).
**How to avoid:** Guard with `if error_text: sig = error_signature(error_text)` before appending. Only add `"sig"` key when sig is non-empty.
**Warning signs:** `error_signatures` table grows empty; error recurrence detection never fires on second session.

### Pitfall 4: session_start Character Count Exceeds 1500
**What goes wrong:** API returns a trace with a very long title (up to 200 chars per API field), causing the compact format to exceed 1500 chars.
**Why it happens:** The new `format_result()` should truncate title to 80, but if truncation is forgotten in the contribution_recall section (which uses cached trace titles), overflow occurs.
**How to avoid:** Apply truncation everywhere a title is formatted. Add an explicit `len(additional_context) > 1500` assertion before printing. Truncate the full string as a safety net.
**Warning signs:** Claude Code's context window shows session_start injecting multi-paragraph blocks.

### Pitfall 5: SQLite Read in _check_domain_entry Mistakenly Removed
**What goes wrong:** A developer sees `_get_conn()` and `get_project_context()` in `_check_domain_entry()` and removes it thinking HOOK-02 requires zero SQLite access. Result: domain_entry trigger never fires (it needs to compare file language against project primary language from the projects table).
**Why it happens:** HOOK-02 says "no SQLite writes" but is sometimes read as "no SQLite at all."
**How to avoid:** HOOK-02 is explicit: "records events to JSONL bridge files only (no SQLite **writes**)." Reads are fine. Document this at the top of `_check_domain_entry()`.
**Warning signs:** domain_entry trigger never fires; novelty_encounter pattern never detected.

### Pitfall 6: Duplicate JSONL Entries for search_results
**What goes wrong:** `handle_search_results()` in post_tool_use writes up to 5 trace pointers to `search_results.jsonl` each time `search_traces` is called. Multiple calls to `search_traces` in one session create duplicate entries. stop.py caches all of them → `cache_trace_pointer()` upserts, so no corruption, but unnecessary work.
**How to avoid:** In stop.py batch loop, deduplicate by `trace_id` before calling `cache_trace_pointer()`. Use a `seen_trace_ids: set` as shown in the Pattern 3 example.
**Warning signs:** `trace_cache` table has many duplicate trace_id entries for the same project.

## Code Examples

### session_start.py: Compact Format with Character Guard

```python
# Source: direct analysis of session_start.py format_result() and main()

def format_result(result: dict) -> str:
    """Compact pointer: title (max 80 chars) + trace ID."""
    title = result.get("title", "Untitled")[:80]
    trace_id = result.get("id", "")
    return f"[{title}]  ({trace_id})"


# In main(), build additionalContext:
if results:
    formatted = [f"{i+1}. {format_result(r)}" for i, r in enumerate(results)]
    project_lang = context_dict.get("language", "") if context_dict else ""
    project_fw = context_dict.get("framework", "") if context_dict else ""
    project_sessions = context_dict.get("session_count", 1) if context_dict else 1
    project_label = project_lang
    if project_fw and project_fw != project_lang:
        project_label = f"{project_lang}/{project_fw}"

    additional_context = (
        f"Project: {project_label} ({project_sessions} session(s))\n"
        f"CommonTrace traces:\n" + "\n".join(formatted) + "\n"
        f"Use search_traces before solving. Contribute with contribute_trace."
    )
else:
    additional_context = (
        "Use search_traces before solving problems. "
        "Contribute solutions with contribute_trace."
    )

# Safety cap
if len(additional_context) > 1500:
    additional_context = additional_context[:1497] + "..."
```

### post_tool_use.py: _record_trigger_safe Replacement

```python
# Source: direct analysis of _record_trigger_safe() in post_tool_use.py

# OLD (remove this):
def _record_trigger_safe(state_dir: Path, trigger_name: str) -> None:
    try:
        from local_store import _get_conn, record_trigger
        session_id = state_dir.name
        conn = _get_conn()
        record_trigger(conn, session_id, trigger_name)
        conn.close()
    except Exception:
        pass

# NEW (replace with JSONL append):
def _record_trigger(state_dir: Path, trigger_name: str) -> None:
    """Record a trigger fire to JSONL. stop.py persists to SQLite at session end."""
    append_event(state_dir, "triggers.jsonl", {"trigger_name": trigger_name})
```

### post_tool_use.py: handle_trace_consumption Replacement

```python
# Source: direct analysis of handle_trace_consumption() in post_tool_use.py

def handle_trace_consumption(data: dict, state_dir: Path) -> None:
    """Handle get_trace: record consumption to JSONL. stop.py persists to SQLite."""
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return

    trace_id = tool_input.get("trace_id", "")
    if not trace_id:
        return

    # Get title from response if available (for cache)
    title = ""
    resp = _parse_tool_response(data)
    if resp:
        title = resp.get("title", "")

    append_event(state_dir, "trace_consumed.jsonl", {
        "trace_id": trace_id,
        "title": title[:120] if title else "",
        "source": "get_trace",
    })
```

### post_tool_use.py: Error Signature in JSONL

```python
# Source: direct analysis of _check_error_recurrence() in post_tool_use.py

def _record_error_sig(error_text: str, state_dir: Path) -> None:
    """Add error signature to the most recent error entry via separate file."""
    if not error_text:
        return
    try:
        from session_state import error_signature
        sig = error_signature(error_text)
        if sig:
            append_event(state_dir, "error_sigs.jsonl", {"sig": sig})
    except Exception:
        pass
```

Note: alternatively, add `"sig"` directly in `handle_bash()` when writing to `errors.jsonl`. The planner should decide which approach is cleaner. Adding `"sig"` to the existing `errors.jsonl` append avoids a sixth new file.

### stop.py: Agent-Assessed Contribution Prompt

```python
# Source: direct analysis of stop.py main() and _build_prompt()

# In main(), replace:
#   if score < IMPORTANCE_THRESHOLD:
#       return
# With:
candidates = read_events(state_dir, "candidates.jsonl")
if not candidates:
    return  # No structural patterns detected

# _build_prompt() produces structural context, not a judgment:
def _build_prompt(candidates, state_dir: Path) -> str:
    errors = read_events(state_dir, "errors.jsonl")
    changes = read_events(state_dir, "changes.jsonl")
    research = read_events(state_dir, "research.jsonl")

    patterns = list({c.get("pattern") for c in candidates})
    n_errors = len(errors)
    n_files = len({c.get("file", "") for c in changes if c.get("file")})

    summary_parts = []
    if n_errors:
        summary_parts.append(f"{n_errors} error(s)")
    if n_files:
        summary_parts.append(f"{n_files} file(s) changed")
    if research:
        summary_parts.append(f"{len(research)} research event(s)")
    summary = ", ".join(summary_parts) or "notable activity"

    patterns_str = ", ".join(p.replace("_", " ") for p in patterns)

    # metadata_json hint (unchanged from current — needed for somatic_intensity)
    # ... (keep existing metadata_parts building logic) ...

    return (
        f"Session: {summary}. Patterns: {patterns_str}. "
        f"If this session contains reusable knowledge, consider contributing. "
        f"Use contribute_trace or continue. {metadata_hint}"
    )
```

## State of the Art

| Old Approach | Current Approach | Phase 7 Target | Impact |
|--------------|-----------------|----------------|--------|
| Hook decides contribution importance | Score >= 4.0 gate | Agent assesses from structural metadata | Agent uses contextual judgment; hook provides facts |
| Full trace content in additionalContext | Title + context[:100] + solution[:150] per trace | Title[:80] + ID only (pointer) | 60-70% fewer chars; agent fetches full content via get_trace |
| SQLite writes distributed across session | Multiple writes in post_tool_use per event | Single batch-persist in stop.py | Reduces I/O contention; easier to reason about consistency |
| Real-time trigger-to-consumption pairing | Pairs immediately in post_tool_use | Timestamp-sorted batch matching in stop.py | Equivalent accuracy; simpler code path |

**The conceptual shift:** Phase 7 completes the "hooks as context-builders" pattern. Session_start gives the agent orientation. Post_tool_use captures structural signals. Stop presents what happened and asks the agent to decide. No hook makes value judgments — the agent is the intelligence.

## Open Questions

1. **Error signature storage approach**
   - What we know: `_check_error_recurrence()` currently computes `error_signature(error_text)` and writes to SQLite via `record_error_signature()`. This needs to move to JSONL.
   - What's unclear: Should the sig go into `errors.jsonl` as an additional field, or into a separate `error_sigs.jsonl` file? Adding to `errors.jsonl` avoids a new file but requires changing the append call in `handle_bash()`. Separate file keeps `handle_bash()` unchanged but adds file complexity.
   - Recommendation: Add `"sig"` field directly in `handle_bash()` errors.jsonl append (compute sig there). This keeps the sig co-located with its error, simplifies stop.py reading.

2. **Contribution prompt threshold for HOOK-05**
   - What we know: Removing the 4.0 gate means any candidate triggers prompting. `research_then_implement` is easily triggered (WebSearch + Write with no errors).
   - What's unclear: Will this produce unacceptable prompt noise in typical sessions?
   - Recommendation: Keep `MIN_TURNS = 2` check (already in stop.py). Consider additionally requiring at least one of: errors, changes to 2+ files, or a high-weight pattern (error_resolution, approach_reversal, user_correction). This preserves agent autonomy while filtering trivial sessions.

3. **Contributed trace local caching**
   - What we know: `handle_contribution()` currently writes `cache_trace_pointer()` to SQLite using the trace_id from the API response. When this moves to JSONL, contributions.jsonl already has the trace_id. But the title comes from `tool_input.get("title")` — this is available in post_tool_use.
   - What's unclear: Should contributions.jsonl be extended with a `"title"` field, or should stop.py cache contributed traces differently?
   - Recommendation: Extend contributions.jsonl to include `"title"` field from `tool_input`. stop.py reads contributions.jsonl and calls `cache_trace_pointer(conn, trace_id, project_id, title, source="contributed")` for each. Clean and consistent.

## Sources

### Primary (HIGH confidence)
- Direct code inspection of `/tmp/ct-skill/hooks/session_start.py` (344 lines, Phase 6 final)
- Direct code inspection of `/tmp/ct-skill/hooks/post_tool_use.py` (969 lines, Phase 6 final)
- Direct code inspection of `/tmp/ct-skill/hooks/stop.py` (754 lines, Phase 6 final)
- Direct code inspection of `/tmp/ct-skill/hooks/local_store.py` (435 lines, Phase 6 final)
- Direct code inspection of `/tmp/ct-skill/hooks/session_state.py` (148 lines, Phase 6 final)
- Direct code inspection of `/tmp/ct-skill/hooks/user_prompt.py` (138 lines, Phase 6 final)
- `/home/bitnami/commontrace/.planning/phases/06-local-store-redesign/06-VERIFICATION.md` — Phase 6 completion status (17/17 verified)
- `/home/bitnami/commontrace/.planning/phases/06-local-store-redesign/06-02-SUMMARY.md` — Phase 6 decisions and key changes
- `/home/bitnami/commontrace/.planning/REQUIREMENTS.md` — HOOK-01 through HOOK-05 requirements

### No External Sources Required
This phase is pure refactoring of known code. All findings are from direct inspection of the live skill files. No external library research needed.

## Metadata

**Confidence breakdown:**
- File-by-file change scope: HIGH — verified by code inspection
- New JSONL files needed: HIGH — derived from tracking all SQLite write call sites
- Trigger-pairing order dependency: HIGH — verified from local_store.py `record_trace_consumed()` SQL
- Character count analysis: HIGH — computed directly from format strings
- HOOK-05 prompt noise risk: MEDIUM — behavioral prediction, not code analysis

**Research date:** 2026-03-02
**Valid until:** Indefinite (internal codebase research, no external library dependencies)

---

## Implementation Checklist for Planner

When building the PLAN.md, ensure tasks cover:

**Task 1 — session_start.py (HOOK-01):**
- [ ] Rewrite `format_result()` to pointer format (title[:80] + ID only)
- [ ] Add project info line to additionalContext
- [ ] Add character count guard (`if len > 1500: truncate`)
- [ ] Verify: output under 1500 chars with 3 results and max-length titles
- [ ] Verify: syntax check passes

**Task 2 — post_tool_use.py (HOOK-02):**
- [ ] Replace `_record_trigger_safe()` with `append_event(state_dir, "triggers.jsonl", ...)`
- [ ] Add `"sig"` field to errors.jsonl append in `handle_bash()` (compute `error_signature(error_text)` there)
- [ ] Replace `handle_trace_consumption()` SQLite calls with `trace_consumed.jsonl` append
- [ ] Replace `handle_search_results()` SQLite calls with `search_results.jsonl` appends
- [ ] Replace `handle_vote()` SQLite calls with `votes.jsonl` append
- [ ] Remove `cache_trace_pointer()` from `handle_contribution()` (add title to contributions.jsonl instead)
- [ ] Keep `_check_domain_entry()` SQLite read (get_project_context is SELECT-only)
- [ ] Verify: zero `_get_conn()` calls that result in writes remain
- [ ] Verify: syntax check passes

**Task 3 — stop.py (HOOK-03 + HOOK-04 + HOOK-05):**
- [ ] `_persist_session()`: read `triggers.jsonl` → `record_trigger()` for each (in timestamp order)
- [ ] `_persist_session()`: read `trace_consumed.jsonl` → `record_trace_consumed()` + `cache_trace_pointer()` (after triggers)
- [ ] `_persist_session()`: read `search_results.jsonl` → `cache_trace_pointer()` (deduplicated by trace_id)
- [ ] `_persist_session()`: read `votes.jsonl` → `record_trace_vote_v2()`
- [ ] `_persist_session()`: read `errors.jsonl` (with sig field) or `error_sigs.jsonl` → `record_error_signature()`
- [ ] `_persist_session()`: read `contributions.jsonl` (with title field) → `cache_trace_pointer(source="contributed")`
- [ ] `main()`: remove `IMPORTANCE_THRESHOLD = 4.0` and `if score < IMPORTANCE_THRESHOLD: return`
- [ ] `main()`: add `candidates = read_events(state_dir, "candidates.jsonl")` gate
- [ ] `_build_prompt()`: rewrite to structural context + agent-decides framing
- [ ] Keep `compute_importance()` for metadata assembly (top_pattern + evidence for end_session)
- [ ] Keep post-contribution refinement logic unchanged
- [ ] Verify: syntax check passes
- [ ] Verify: no IMPORTANCE_THRESHOLD references remain
