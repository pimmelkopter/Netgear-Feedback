##services/interfaces.py##
from typing import Protocol

class SwitchMonitorInterface(Protocol):
    def is_connected(self) -> bool:
        ...
    
    def get_uptime(self) -> float:
        ...

class HotspotServiceInterface(Protocol):
    def is_active(self) -> bool:
        ...