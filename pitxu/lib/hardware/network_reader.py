import logging
import platform
import re
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
    def connected_wifi() -> dict | None:
        """
        The WiFi network that the device is connected to, or None if it is not connected (or can't be read).
        """
        networks = NetworkReader.wifi_networks()
        if not networks:
            return None
        return next((network for network in networks if network.get("in_use")), None)

    @staticmethod
    def wifi_networks() -> list[dict] | None:
        """
        The WiFi networks seen by the device, strongest first (Linux): SSID, security, signal, and in_use,
        that is True for the network that we are connected to. Only the connected one on Windows.
        An empty list on a platform without support. None if the platform tool failed.

        Beware: the list is NOT the connection. The first one is the strongest, not the connected one.

        On macOS it returns a placeholder network, as there is no tool that gives it without extra permissions.
        """
        system = platform.system().lower()

        if system == "linux":
            # Use nmcli to get WiFi networks. IN-USE is "*" for the network that we are connected to.
            output = NetworkReader._run(["nmcli", "-t", "-f", "IN-USE,SSID,SECURITY,SIGNAL", "dev", "wifi"])
            if output is None:
                return None
            networks = []
            for line in output.strip().split("\n"):
                parts = NetworkReader._split_terse(line)
                if len(parts) >= 4:
                    networks.append({"ssid": parts[1], "security": parts[2], "signal": parts[3], "in_use": parts[0].strip() == "*"})
            return networks

        if system == "windows":
            # netsh only lists the interfaces, with the network that each one is connected to.
            output = NetworkReader._run(["netsh", "WLAN", "show", "interfaces"])
            if output is None:
                return None
            networks = []
            for line in output.split("\n"):
                if "SSID" in line and "BSSID" not in line:
                    networks.append({"ssid": line.split(":")[1].strip(), "in_use": True})
            return networks

        if system == "darwin":
            return [{"ssid": "Mocked WiFi Network", "security": "WPA2", "signal": "80", "in_use": True}]

        # Unsupported OS for WiFi scanning
        return []

    # ---- Internals ----

    @staticmethod
    def _split_terse(line: str) -> list[str]:
        """
        Splits a line of `nmcli -t`, where the fields are separated by ":" and a ":" inside a field is escaped as "\\:".
        """
        return [part.replace("\\:", ":").replace("\\\\", "\\") for part in re.split(r"(?<!\\):", line)]

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
