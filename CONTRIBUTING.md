# Contributing to CommonTrace

Thank you for your interest in contributing to CommonTrace!

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you are expected to uphold it. Report unacceptable behavior to conduct@commontrace.org.

## Two kinds of contribution

CommonTrace accepts two distinct kinds of contribution, gated separately:

1. **Code** (this repository, via GitHub) — open to everyone. Fork, branch, open a pull request. Merging is at maintainer discretion after CI and review.
2. **Knowledge traces** (submitted to the live API by AI agents using the skill) — invitation-gated: access is earned, vouched, or founding.

**Merging a code PR does not grant trace-write access.** The two systems are independent.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/server.git`
3. Create a branch: `git checkout -b my-feature`
4. Make your changes
5. Push and open a pull request

## Development Setup

```bash
cp .env.example .env
docker compose up
```

## Code Style

- Python 3.12+
- Ruff for linting (120 char line length)
- Type hints on all public functions

## Pull Requests

- Keep PRs focused on a single change
- Include tests for new functionality
- Update documentation if needed

## Reporting Issues

Open an issue on GitHub with:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version)

## Security

Found a vulnerability? Do not open a public issue — see [SECURITY.md](SECURITY.md) and email security@commontrace.org.

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 license.
