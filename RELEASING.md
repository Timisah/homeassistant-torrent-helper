# Releasing

Installation is through HACS as a **custom repository** (no default-catalogue listing is claimed).
HACS installs the repository contents of the chosen release/tag, so no zip asset is needed and
`hacs.json` has no `zip_release`.

1. Update `version` in `custom_components/torrent_tools/manifest.json` and `pyproject.toml`
   (a test checks they agree) and `CHANGELOG.md`.
2. All CI jobs green (lint, tests, hassfest, HACS).
3. Complete the [acceptance checklist](docs/acceptance-checklist.md) on a test setup.
4. Tag `vX.Y.Z` (must equal the manifest version). The `Release (draft)` workflow creates a **draft** release.
5. The repository owner reviews the draft and decides whether to publish it. Do not publish before review.
