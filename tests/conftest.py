# tests/conftest.py
"""Pytest configuration and shared fixtures."""

import pytest
import sys
from pathlib import Path

# Ensure pop package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
