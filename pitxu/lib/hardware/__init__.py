"""
Stateless hardware readers, grouped by topic.

They are meant to be extractable into an external library:
    - Static methods only, no instances, no held resources (no GPIO claims, no open I2C buses).
    - No dependency on the application (no PyXavi, no config, no shared memory).
      Whatever they need comes as an argument. They only use the standard `logging` module.
    - They never raise on a failed read: they return None. What "unknown" means
      for the application (-1, "N/A"...) is decided by the caller.
    - They don't check the platform. If the tool or the file is not there, the read just fails and returns None.
"""
from .alsa_mixer import AlsaMixer
from .power_reader import PowerReader
from .thermal_reader import ThermalReader

__all__ = ["AlsaMixer", "PowerReader", "ThermalReader"]
