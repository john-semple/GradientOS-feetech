# backends/hls3950/__init__.py
#
# Feetech HLS3950 (FT-SCS protocol) servo backend for GradientOS.
# This module provides hardware control for Feetech HLS3950 serial bus servos.

from .driver import HLS3950Backend
from . import protocol
from . import config

__all__ = ['HLS3950Backend', 'protocol', 'config']