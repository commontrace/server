# Frontend — Static Site

## Tech Stack

- Python `build.py` → Jinja2 templates → static HTML
- nginx Alpine serves both `commontrace.org` and `docs.commontrace.org` via server_name routing
- 9 languages: en, fr, zh, es, pt, de, ja, ar, hi

## Design Direction

- **Wikipedia/community-project aesthetic** — NOT dark tech startup
- Light theme default, dark theme available (toggle)
- Content-first, warm, readable typography
- Animated canvas hero (neural network particles) — KEEP
- Real contribution metrics and community signals

### Anti-patterns (user rejected)
- No gradient text, no parallax, no staggered reveals on content pages
- No glassmorphism, no excessive shadows
- No "super deep tech AI futuristic dark shit"

### Inspiration
Wikipedia, MDN, OpenCollective, Svelte docs, 11ty, Linux Foundation

## Build Pipeline

```bash
python3 build.py  # generates static HTML from Jinja2 templates
# nginx serves the output
```
