"""License / compatibility / flagged-source knowledge base.

The knowledge base is *data*, not code: it lives in editable YAML under
``config/`` so the community can extend it. This module loads it and exposes the
classification and compatibility queries the risk analyzer depends on.
"""

from .kb import PolicyKB, LicenseInfo, Compatibility  # noqa: F401
