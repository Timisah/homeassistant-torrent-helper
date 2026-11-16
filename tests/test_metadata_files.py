"""Static consistency of manifest, translations, services and HACS files."""

import json
from pathlib import Path

import yaml

from custom_components.torrent_tools.operations import OPERATIONS

ROOT = Path(__file__).parent.parent
COMP = ROOT / "custom_components" / "torrent_tools"


def keys(node, prefix=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from keys(v, f"{prefix}/{k}")
    else:
        yield prefix


def test_translations_have_identical_keys():
    en = set(keys(json.loads((COMP / "translations" / "en.json").read_text())))
    de = set(keys(json.loads((COMP / "translations" / "de.json").read_text())))
    strings = set(keys(json.loads((COMP / "strings.json").read_text())))
    assert en == de == strings
    assert not any(
        not v
        for v in json.loads((COMP / "translations" / "de.json").read_text())["config"][
            "error"
        ].values()
    )


def test_services_yaml_matches_schemas_and_translations():
    services = yaml.safe_load((COMP / "services.yaml").read_text())
    tr = json.loads((COMP / "translations" / "en.json").read_text())["services"]
    assert set(services) == set(OPERATIONS) == set(tr)
    for name, op in OPERATIONS.items():
        schema_fields = {str(k) for k in op.schema.schema}
        assert set(services[name]["fields"]) == schema_fields == set(tr[name]["fields"]), name


def test_manifest_and_hacs():
    manifest = json.loads((COMP / "manifest.json").read_text())
    assert manifest["domain"] == "torrent_tools" and manifest["single_config_entry"] is True
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert f'version = "{manifest["version"]}"' in pyproject
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert (
        hacs["name"] == "Torrent Tools" and "zip_release" not in hacs
    )  # install from repo contents
    assert (COMP / "icons.json").exists()
