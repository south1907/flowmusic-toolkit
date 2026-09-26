# Contributing

Thank you for contributing to Google Flow Music Local API.

## Development setup

```bash
make install-dev
make check
```

Use `make format` before opening a pull request. Keep changes focused and add
tests for new behavior or bug fixes.

## Pull requests

- Open an issue first for large behavioral or architectural changes.
- Keep the public request contract prompt-first and document breaking changes.
- Never commit browser sessions, bearer tokens, cookies, generated audio, or
  local SQLite databases.
- Confirm both the API and extension continue to work with the signed-in
  browser-session architecture.

## Bug reports

Use the bug-report form and provide sanitized logs, your operating system,
Python version, and Chrome version. Never include credentials or session data.

