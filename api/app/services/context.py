"""Context service for contextual knowledge convergence.

Builds structured context fingerprints from trace metadata and tags,
converts them to embeddable strings, and computes alignment scores
between fingerprints for context-aware search boosting and vote weighting.
"""

from typing import Optional

from app.services.enrichment import detect_framework, detect_language

# OS detection patterns in tags and metadata
_OS_TAGS = {"linux", "macos", "windows", "ubuntu", "debian", "centos", "alpine"}

# Package manager detection
_PKG_MANAGERS = {"pip", "npm", "yarn", "pnpm", "cargo", "go", "bun", "poetry", "conda"}

# Runtime detection
_RUNTIMES = {"node", "deno", "bun", "cpython", "pypy", "jvm", "dotnet"}

# Environment detection
_ENVIRONMENTS = {"docker", "kubernetes", "serverless", "lambda", "vercel", "railway", "heroku"}

# Field weights for alignment scoring
_FIELD_WEIGHTS: dict[str, float] = {
    "language": 0.3,
    "framework": 0.25,
    "os": 0.15,
    "package_manager": 0.1,
    "runtime": 0.1,
    "environment": 0.1,
}


def build_context_fingerprint(
    metadata_json: Optional[dict], tags: list[str]
) -> Optional[dict]:
    """Extract structured context from metadata and tags.

    Returns dict with keys: language, framework, os, environment,
    package_manager, runtime. Missing fields are omitted (not null-filled).
    Returns None if no context can be extracted.
    """
    meta = metadata_json or {}
    tag_set = {t.lower() for t in tags}
    solution_text = ""

    fingerprint: dict[str, str] = {}

    # Language: from metadata first, then tags
    lang = meta.get("language")
    if not lang:
        # Check tags for language hints
        for t in tag_set:
            if t in {"python", "javascript", "typescript", "rust", "go", "java", "ruby", "php", "c", "cpp", "csharp", "swift", "kotlin"}:
                lang = t
                break
    if lang:
        fingerprint["language"] = lang

    # Framework: from metadata first, then tags
    fw = meta.get("framework")
    if not fw:
        for t in tag_set:
            if t in {"fastapi", "django", "flask", "react", "vue", "next", "express", "rails", "spring", "sqlalchemy", "laravel", "svelte", "angular", "nestjs"}:
                fw = t
                break
    if fw:
        fingerprint["framework"] = fw

    # OS: from metadata or tags
    os_val = meta.get("os")
    if not os_val:
        for t in tag_set:
            if t in _OS_TAGS:
                os_val = t
                break
    if os_val:
        fingerprint["os"] = os_val

    # Package manager: from metadata or tags
    pkg = meta.get("package_manager")
    if not pkg:
        for t in tag_set:
            if t in _PKG_MANAGERS:
                pkg = t
                break
    if pkg:
        fingerprint["package_manager"] = pkg

    # Runtime: from metadata or tags
    rt = meta.get("runtime")
    if not rt:
        for t in tag_set:
            if t in _RUNTIMES:
                rt = t
                break
    if rt:
        fingerprint["runtime"] = rt

    # Environment: from metadata or tags
    env = meta.get("environment")
    if not env:
        for t in tag_set:
            if t in _ENVIRONMENTS:
                env = t
                break
    if env:
        fingerprint["environment"] = env

    return fingerprint if fingerprint else None


def build_context_string(fingerprint: dict) -> str:
    """Convert fingerprint dict to embeddable text.

    Example: "language:python framework:fastapi os:linux package_manager:pip"
    """
    parts = []
    for key in ("language", "framework", "os", "package_manager", "runtime", "environment"):
        if key in fingerprint:
            parts.append(f"{key}:{fingerprint[key]}")
    return " ".join(parts)


def compute_context_alignment(fp_a: dict, fp_b: dict) -> float:
    """Weighted Jaccard-like similarity between two fingerprints.

    Returns 0.0-1.0. Only fields present in at least one fingerprint
    contribute to the score. Weight per field defined in _FIELD_WEIGHTS.
    """
    if not fp_a or not fp_b:
        return 0.0

    matched_weight = 0.0
    total_weight = 0.0

    for field, weight in _FIELD_WEIGHTS.items():
        val_a = fp_a.get(field)
        val_b = fp_b.get(field)

        # Only score fields present in at least one fingerprint
        if val_a is None and val_b is None:
            continue

        total_weight += weight

        if val_a is not None and val_b is not None and val_a == val_b:
            matched_weight += weight

    if total_weight == 0.0:
        return 0.0

    return matched_weight / total_weight
