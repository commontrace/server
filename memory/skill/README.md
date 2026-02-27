# Skill — Claude Code Plugin

## Hook Pipeline

```
session_start.py → detect project context, search CommonTrace, write bridge files
user_prompt.py   → count user turns, record timestamps, periodic flush (every 10 turns)
post_tool_use.py → record events, detect knowledge candidates, handle all 6 MCP tools
stop.py          → score importance, prompt for contribution, persist to SQLite, telemetry
```

## Hooked MCP Tools (6 total)

All routed through `post_tool_use.py main()`:
- `get_trace` → cache trace + record consumption + mark_trace_used
- `contribute_trace` → record locally + auto-dedup + supersession
- `amend_trace` → update both local_knowledge and discovered_knowledge
- `search_traces` → cache all results to discovered_knowledge
- `vote_trace` → update both discovered and local (upvote boosts recall)

## Knowledge Detection Patterns (16 total)

| Weight | Pattern | Signal |
|--------|---------|--------|
| 3.0 | error_resolution | error → code change → successful verification |
| 2.5 | security_hardening | security file changes after errors |
| 2.5 | user_correction | same file edited before and after user message |
| 2.5 | approach_reversal | Write to file previously Edit-ed 3+ times |
| 2.0 | test_fix_cycle | test fails → code fix → test passes |
| 2.0 | dependency_resolution | package manager errors → config fix → success |
| 2.0 | config_discovery | config changes that resolved errors |
| 2.0 | novelty_encounter | new language/domain in this project |
| 2.0 | infra_discovery | infrastructure file changes after errors |
| 2.0 | migration_pattern | 5+ files across dirs + config changes |
| 2.0 | research_then_implement | search/fetch then code with no errors |
| 1.5 | generation_effect | solved without any external knowledge |
| 1.5 | cross_file_breadth | changes spanning 3+ directories |
| 1.5 | iteration_depth | same file edited 3+ times (scales to 2.0) |
| 1.5 | workaround | research + errors + changes |
| 1.0 | temporal_investment | long session with sustained activity |

Temporal proximity compounding (synaptic tagging): patterns near high-signal events get 0-30% boost. Threshold >= 4.0 triggers contribution prompt.

## Persistent Local Store (SQLite)

`~/.commontrace/local.db` — 9 tables, self-migrating schema:

| Table | Purpose |
|-------|---------|
| projects | working directory → language/framework mapping |
| sessions | per-session stats (errors, resolutions, contributions) |
| entities | accumulated language/framework/domain with Jaro-Winkler dedup (0.88) |
| events | migrated JSONL events (incremental with offset tracking) |
| error_signatures | fuzzy signatures for recurrence detection |
| trigger_feedback | which triggers led to trace consumption (reinforcement) |
| local_knowledge | contributed traces with temperature, decay, half-life, evergreen, bi-temporal |
| discovered_knowledge | cached traces from others (search results, get_trace responses) |
| session_insights | top pattern + score per session for recall |
| error_resolutions | error signature → fix files + command pairing |

## Memory Architecture (DroidClaw/OpenClaw-inspired)

- **Temperature**: HOT/WARM/COOL/COLD/FROZEN — score-based from decay (>=0.7/0.4/0.1/<0.1/180d+)
- **Decay**: Ebbinghaus with logarithmic stability — `effective_hl = base_hl * (1 + 1.5 * ln(recall_count + 1))`
- **Evergreen**: Tags (security, algorithm, invariant) or patterns (security_hardening) exempt from decay
- **Half-lives**: Pattern-aware — workaround=60d, dependency=90d, config=180d, infra=730d
- **Spreading activation**: Multi-hop BFS (4 hops, 0.85 decay) via tag overlap
- **Search**: BM25 over title+context+solution+tags, blended with decay
- **Ranking**: MMR diversity reranking (lambda=0.7, Jaccard on tags+title tokens)
- **Bi-temporal**: valid_from/valid_to — superseded knowledge retains history
- **Entity dedup**: Jaro-Winkler (0.88 threshold) — prevents "react" vs "reactjs" fragmentation

## Trigger System (5 types)

| Trigger | Cooldown | What fires it |
|---------|----------|---------------|
| bash_error | 30s | Non-zero exit code or stderr |
| error_recurrence | 60s | Fuzzy match to previous session's error signature |
| pre_code | 180s | Writing a new file (file doesn't exist yet) |
| domain_entry | 120s | First time using a language in this project |
| pre_research | 120s | WebSearch — checks local BM25 before API |

All cooldowns scale via adaptive feedback: >=40% conversion → 0.5x cooldown, <5% after 20+ firings → 3x cooldown.

## Error Resolution Cascade (4 levels)

1. Local error_resolutions table (no API call)
2. Discovered knowledge cache (BM25 over cached external traces)
3. Cross-session error_signatures (fuzzy Jaccard match)
4. CommonTrace API search (last resort)

## Response Format Handling

MCP tool responses may arrive as dict or JSON string. `_parse_tool_response()` handles both formats.
