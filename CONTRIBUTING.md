# Contributing

1. Python 3.14 and Home Assistant 2026.10: `pip install -r requirements_test.txt`.
2. `ruff check . && ruff format --check . && python -m pytest tests -q`.
3. Tests must mock Jackett and qBittorrent (`aioclient_mock`). Never use real credentials, hosts,
   magnets or live downloads/deletions in tests, fixtures or CI. Use example/documentation hosts.
4. Behaviour that touches permissions, selections, deletion or writes needs tests for both the
   allowed and the denied path (including forged or mismatched identity).
5. Keep secrets, URLs and magnets out of exceptions, logs, diagnostics and tool output.
6. Update `CHANGELOG.md` and the translations (`strings.json`, `translations/en.json`, `de.json`; a test checks they match).

CI also runs hassfest and HACS validation on GitHub.
