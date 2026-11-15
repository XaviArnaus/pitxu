"""
Stateless hardware readers, grouped by topic.

They are meant to be extractable into an external library:
    - Static methods only, no instances, no held resources (no GPIO claims, no open I2C buses).
      The only memory is the psutil process cache of SystemReader, needed to measure CPU usage between calls.
    - No dependency on the application (no PyXavi, no config, no shared memory).
      Whatever they need comes as an argument. They only use the standard `logging` module.
    - They never raise on a failed read: they return None. What "unknown" means
      for the application (-1, "N/A"...) is decided by the caller.
    - They don't check the platform unless the way to read changes with it. If the tool or the file is not there,
      the read just fails and returns None.
"""
from .alsa_mixer import AlsaMixer
from .network_reader import NetworkReader
from .power_reader import PowerReader
from .system_reader import SystemReader
from .thermal_reader import ThermalReader

__all__ = ["AlsaMixer", "NetworkReader", "PowerReader", "SystemReader", "ThermalReader"]
