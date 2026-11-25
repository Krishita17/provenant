"""Shared fixtures. Synthetic projects are generated into a temp dir per session
so the tests never depend on committed, regenerable artifacts."""

import os
import sys

import pytest

# Make the src layout importable when pytest's pythonpath config is not applied.
_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(_SRC))

from provenant.data.generate import generate  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def synthetic_base(tmp_path_factory):
    base = tmp_path_factory.mktemp("provenant_examples")
    generate(str(base), seed=7)
    return str(base)


@pytest.fixture(scope="session")
def synthetic_projects(synthetic_base):
    root = os.path.join(synthetic_base, "synthetic")
    return sorted(os.path.join(root, d) for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))


def project(synthetic_base, name):
    return os.path.join(synthetic_base, "synthetic", name)
