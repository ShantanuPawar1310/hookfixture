"""Local, provider-neutral webhook fixture generation. No network operations."""

from .core import Delivery, Scenario, Summary, create_scenario, load_events, verify_scenario, write_scenario

__version__ = "0.1.0"
__all__ = [
    "Delivery", "Scenario", "Summary", "create_scenario", "load_events",
    "verify_scenario", "write_scenario",
]
