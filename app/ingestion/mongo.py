from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterable


def mongo_enabled() -> bool:
    return bool(os.getenv("MONGODB_URI"))

