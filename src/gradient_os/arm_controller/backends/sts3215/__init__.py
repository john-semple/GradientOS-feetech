# backends/sts3215/__init__.py
#
# Feetech STS3215 (SCS/STS protocol) servo backend for GradientOS.
# This module provides hardware control for Feetech STS3215 serial bus servos.

from .driver import STS3215Backend
from . import protocol
from . import config

__all__ = ['STS3215Backend', 'protocol', 'config']