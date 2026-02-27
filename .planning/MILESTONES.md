# Milestones

## v1.0 — Foundation (Shipped)

**Goal:** Build the core knowledge base and agent integration.

**What shipped:**
- FastAPI backend with pgvector semantic search
- MCP proxy with 6 tools and circuit breaker
- Claude Code skill with 4-hook pipeline, 16 detection patterns, 5 trigger types
- Persistent SQLite local store (10 tables) with DroidClaw/OpenClaw-inspired memory mechanisms
- Neuroscience-inspired ranking (somatic intensity, temperature, convergence, depth, decay)
- Trace relationships, spreading activation, result diversification
- Static frontend with 9 languages
- Research: 4 documents covering neuroscience-inspired memory architecture

**Phases:** 1-5 (pre-GSD, implemented incrementally)

**Key learnings:**
- The local store was over-engineered as a parallel encyclopedia — should be working memory
- The agent (LLM) can do relevance assessment natively — no need for complex scoring gates
- Detection patterns are valuable as context enrichment but not as decision gates
- Three clean layers needed: working memory (local) → episodic (session) → semantic (encyclopedia)
