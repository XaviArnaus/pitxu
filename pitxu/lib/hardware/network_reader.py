import logging
import platform
from subprocess import run

logger = logging.getLogger(__name__)


class NetworkReader:
    """
    Reads the network state: the default interface and the WiFi networks.

    What can't be read returns None.
    """

    COMMAND_TIMEOUT_SECONDS: int = 10

    @staticmethod
    def default_interface() -> dict | None:
        """
        Name, IP, netmask, broadcast and MAC of the default network interface, or None if there is none.
        """
        try:
            import ifcfg

            data = ifcfg.default_interface()
            if data is None:
                return None
            return {
                "name": data.get("name"),
                "ip": data.get("inet"),
                "netmask": data.get("netmask"),
                "broadcast": data.get("broadcast"),
                "mac": data.get("ether"),
            }
        except Exception as e:
            logger.debug(f"Could not read the default network interface: {e}")
            return None

    @staticmethod
    def wifi_networks() -> list[dict] | None:
        """
        The WiFi networks seen by the device: SSID, security and signal (Linux), or only the SSID (Windows).
        An empty list on a platform without support. None if the platform tool failed.

        On macOS it returns a placeholder network, as there is no tool that gives it without extra permissions.
        """
        system = platform.system().lower()

        if system == "linux":
            # Use nmcli to get WiFi networks
            output = NetworkReader._run(["nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL", "dev", "wifi"])
            if output is None:
                return None
            networks = []
            for line in output.strip().split("\n"):
                parts = line.split(":")
                if len(parts) >= 3:
                    networks.append({"ssid": parts[0], "security": parts[1], "signal": parts[2]})
            return networks

        if system == "windows":
            # Use netsh to get WiFi networks
            output = NetworkReader._run(["netsh", "WLAN", "show", "interfaces"])
            if output is None:
                return None
            networks = []
            for line in output.split("\n"):
                if "SSID" in line and "BSSID" not in line:
                    networks.append({"ssid": line.split(":")[1].strip()})
            return networks

        if system == "darwin":
            return [{"ssid": "Mocked WiFi Network", "security": "WPA2", "signal": "80"}]

        # Unsupported OS for WiFi scanning
        return []

    # ---- Internals ----

    @staticmethod
    def _run(command: list[str]) -> str | None:
        try:
            result = run(command, capture_output=True, timeout=NetworkReader.COMMAND_TIMEOUT_SECONDS)
            if result.returncode != 0:
                logger.debug(f"[{' '.join(command)}] failed ({result.returncode}): {result.stderr.decode(errors='replace').strip()}")
                return None
            return result.stdout.decode(errors="replace")
        except Exception as e:
            logger.debug(f"[{' '.join(command)}] could not run: {e}")
            return None
