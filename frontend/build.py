"""Static site generator for CommonTrace frontend.

Reads seed_traces.json and generates a static site
with individual trace pages, tag pages, and a searchable index.
Supports i18n: generates localized versions for each language.
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
TRANSLATIONS_PATH = Path("translations.json")
TEMPLATES_DIR = Path("templates")
STATIC_DIR = Path("static")
OUT_DIR = Path("_site")

SUPPORTED_LANGS = ["en", "fr", "zh", "es", "pt", "de", "ja"]
DEFAULT_LANG = "en"

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


def load_translations() -> dict:
    """Load translations from JSON file."""
    if TRANSLATIONS_PATH.exists():
        return json.loads(TRANSLATIONS_PATH.read_text())
    # Fallback: return empty dict, English strings are hardcoded in templates
    return {}


def make_translator(translations: dict, lang: str):
    """Create a translation function for a specific language."""
    lang_strings = translations.get(lang, {})
    en_strings = translations.get("en", {})

    def t(key: str, **kwargs) -> str:
        # Use None sentinel to distinguish missing keys from empty strings
        text = lang_strings.get(key)
        if text is None:
            text = en_strings.get(key)
        if text is None:
            text = key
        if kwargs:
            for k, v in kwargs.items():
                text = text.replace("{" + k + "}", str(v))
        return text

    return t


def make_url_helper(lang: str):
    """Create a URL helper that prepends language prefix for non-default langs."""
    if lang == DEFAULT_LANG:
        return lambda path: path
    prefix = f"/{lang}"
    return lambda path: f"{prefix}{path}"


def build():
    # Load traces
    traces = json.loads(SEED_TRACES_PATH.read_text())
    print(f"Loaded {len(traces)} traces")

    # Load translations
    translations = load_translations()
    print(f"Loaded translations for: {', '.join(translations.keys()) or 'none'}")

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

    # Pygments CSS (light theme)
    formatter = HtmlFormatter(style="friendly")
    pygments_css = formatter.get_style_defs(".highlight")

    # Clean output
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    # Static assets (shared across all languages)
    static_out = OUT_DIR / "static"
    static_out.mkdir(parents=True, exist_ok=True)
    (static_out / "highlight.css").write_text(pygments_css)

    # Copy static files
    for f in STATIC_DIR.iterdir():
        if f.is_file():
            shutil.copy(f, static_out / f.name)

    # Determine which languages to build
    langs_to_build = [lang for lang in SUPPORTED_LANGS if lang in translations]
    if DEFAULT_LANG not in langs_to_build:
        langs_to_build.insert(0, DEFAULT_LANG)

    # Build each language version
    for lang in langs_to_build:
        t = make_translator(translations, lang)
        url = make_url_helper(lang)

        # Jinja2 setup (fresh env per language for globals)
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False
        )
        env.globals["all_tags"] = all_tags_sorted
        env.globals["total_traces"] = len(traces)
        env.globals["t"] = t
        env.globals["url"] = url
        env.globals["lang"] = lang
        env.globals["supported_langs"] = SUPPORTED_LANGS
        env.globals["default_lang"] = DEFAULT_LANG

        # Output directory: root for English, /{lang}/ for others
        lang_out = OUT_DIR if lang == DEFAULT_LANG else OUT_DIR / lang
        lang_out.mkdir(parents=True, exist_ok=True)

        # Generate homepage
        home_tpl = env.get_template("home.html")
        (lang_out / "index.html").write_text(
            home_tpl.render(
                recent_traces=traces[:10],
                top_languages=top_languages,
                page_title=f"CommonTrace — {t('nav.subtitle')}",
            )
        )

        # Generate browse/all traces page
        browse_tpl = env.get_template("index.html")
        browse_dir = lang_out / "browse"
        browse_dir.mkdir(parents=True, exist_ok=True)
        (browse_dir / "index.html").write_text(
            browse_tpl.render(
                traces=traces,
                page_title=f"{t('browse.title')} — CommonTrace",
            )
        )

        # Generate individual trace pages
        trace_tpl = env.get_template("trace.html")
        for trace in traces:
            trace_dir = lang_out / "trace" / trace["slug"]
            trace_dir.mkdir(parents=True, exist_ok=True)
            related = find_related(trace, traces)
            (trace_dir / "index.html").write_text(
                trace_tpl.render(
                    trace=trace,
                    related_traces=related,
                    page_title=f"{trace['title']} — CommonTrace",
                )
            )

        # Generate tag pages
        tag_tpl = env.get_template("tag.html")
        for tag, tag_traces in tag_index.items():
            tag_dir = lang_out / "tag" / tag
            tag_dir.mkdir(parents=True, exist_ok=True)
            (tag_dir / "index.html").write_text(
                tag_tpl.render(
                    tag=tag,
                    traces=tag_traces,
                    page_title=f"{tag} — CommonTrace",
                )
            )

        # Generate about page
        about_tpl = env.get_template("about.html")
        about_dir = lang_out / "about"
        about_dir.mkdir(parents=True, exist_ok=True)
        (about_dir / "index.html").write_text(
            about_tpl.render(page_title=f"{t('about.title')} — CommonTrace")
        )

        print(f"Generated [{lang}]: homepage, browse, {len(traces)} traces, {len(tag_index)} tags, about")

    print(f"Build complete: {OUT_DIR}/")


if __name__ == "__main__":
    build()
