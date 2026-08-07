"""The event semantic layer (M5): raw game events -> ExperienceEvent.

Raw events arrive from the `/events` WebSocket. `SemanticMapper` interprets
them into `ExperienceEvent`s (interaction facts only) and `EventCollector`
persists those facts through an injected memory backend while a run is
active.
"""

from .collector import EventCollector
from .mapper import SemanticMapper

__all__ = ["EventCollector", "SemanticMapper"]
