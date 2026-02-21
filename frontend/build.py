"""Static site generator for CommonTrace frontend.

Reads seed_traces.json and generates a Wikipedia-style static site
with individual trace pages, tag pages, and a searchable index.
"""

import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markdown import markdown
from pygments.formatters import HtmlFormatter


SEED_TRACES_PATH = Path("seed_traces.json")
TEMPLATES_DIR = Path("templates")
STATIC_DIR = Path("static")
OUT_DIR = Path("_site")

# Primary languages/frameworks for homepage stats
TOP_LANGUAGES = [
    "python", "typescript", "javascript", "react", "fastapi", "next.js",
    "docker", "postgresql", "redis", "vue", "go", "rust",
]


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9\s-]", "", title.lower().strip())
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug[:80].rstrip("-")


def render_md(text: str) -> str:
    return markdown(
        text,
        extensions=["fenced_code", "codehilite", "tables"],
        extension_configs={
            "codehilite": {"css_class": "highlight", "guess_lang": False}
        },
    )


def find_related(trace: dict, all_traces: list[dict], limit: int = 5) -> list[dict]:
    my_tags = set(trace["tags"])
    scored = []
    for other in all_traces:
        if other["slug"] == trace["slug"]:
            continue
        overlap = len(my_tags & set(other["tags"]))
        if overlap > 0:
            scored.append((overlap, other))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:limit]]


def build():
    # Load traces
    traces = json.loads(SEED_TRACES_PATH.read_text())
    print(f"Loaded {len(traces)} traces")

    # Enrich traces
    for trace in traces:
        trace["slug"] = slugify(trace["title"])
        trace["context_html"] = render_md(trace["context"])
        trace["solution_html"] = render_md(trace["solution"])

    # Build tag index
    tag_index = defaultdict(list)
    tag_counts = Counter()
    for trace in traces:
        for tag in trace["tags"]:
            tag_index[tag].append(trace)
            tag_counts[tag] += 1

    all_tags_sorted = tag_counts.most_common()

    # Detect top languages present in tags
    top_languages = [lang for lang in TOP_LANGUAGES if lang in tag_counts]

    # Jinja2 setup
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
    env.globals["all_tags"] = all_tags_sorted
    env.globals["total_traces"] = len(traces)

    # Pygments CSS (light theme for Wikipedia-style)
    formatter = HtmlFormatter(style="friendly")
    pygments_css = formatter.get_style_defs(".highlight")

    # Clean output
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    # Generate homepage
    home_tpl = env.get_template("home.html")
    (OUT_DIR / "index.html").write_text(
        home_tpl.render(
            recent_traces=traces[:10],
            top_languages=top_languages,
            page_title="CommonTrace — The AI Knowledge Base",
        )
    )
    print("Generated homepage")

    # Generate browse/all traces page
    browse_tpl = env.get_template("index.html")
    browse_dir = OUT_DIR / "browse"
    browse_dir.mkdir(parents=True, exist_ok=True)
    (browse_dir / "index.html").write_text(
        browse_tpl.render(traces=traces, page_title="All traces — CommonTrace")
    )
    print("Generated browse page")

    # Generate individual trace pages
    trace_tpl = env.get_template("trace.html")
    for trace in traces:
        trace_dir = OUT_DIR / "trace" / trace["slug"]
        trace_dir.mkdir(parents=True, exist_ok=True)
        related = find_related(trace, traces)
        (trace_dir / "index.html").write_text(
            trace_tpl.render(
                trace=trace,
                related_traces=related,
                page_title=f"{trace['title']} — CommonTrace",
            )
        )
    print(f"Generated {len(traces)} trace pages")

    # Generate tag pages
    tag_tpl = env.get_template("tag.html")
    for tag, tag_traces in tag_index.items():
        tag_dir = OUT_DIR / "tag" / tag
        tag_dir.mkdir(parents=True, exist_ok=True)
        (tag_dir / "index.html").write_text(
            tag_tpl.render(
                tag=tag,
                traces=tag_traces,
                page_title=f"{tag} — CommonTrace",
            )
        )
    print(f"Generated {len(tag_index)} tag pages")

    # Generate about page
    about_tpl = env.get_template("about.html")
    about_dir = OUT_DIR / "about"
    about_dir.mkdir(parents=True, exist_ok=True)
    (about_dir / "index.html").write_text(
        about_tpl.render(page_title="About — CommonTrace")
    )
    print("Generated about page")

    # Static assets
    static_out = OUT_DIR / "static"
    static_out.mkdir(parents=True, exist_ok=True)
    (static_out / "highlight.css").write_text(pygments_css)

    # Copy static files
    for f in STATIC_DIR.iterdir():
        if f.is_file():
            shutil.copy(f, static_out / f.name)

    print(f"Build complete: {OUT_DIR}/")


if __name__ == "__main__":
    build()
