"""Synthetic ML-project generator, cached metadata fixtures and loaders.

Everything the Provenant pipeline needs to run end-to-end offline lives here:

* :mod:`provenant.data.specs` — declarative specifications of the synthetic
  projects; each spec *is* the ground truth it is scored against.
* :mod:`provenant.data.generate` — renders each spec into a realistic ML
  project (configs, scripts, notebooks, placeholder artifacts), writes a
  per-project cached-metadata fixture, and emits the ground-truth BOM.
* ``fixtures/metadata_store.yaml`` — cached, point-in-time metadata records for
  the real public identifiers referenced by the bundled real-style examples, so
  resolution of those projects also runs fully offline.

No model weights or datasets are redistributed: components are referenced by
identifier/hash only, and local "artifacts" are zero-information placeholder
files whose *names* carry the signal discovery keys on.
"""
