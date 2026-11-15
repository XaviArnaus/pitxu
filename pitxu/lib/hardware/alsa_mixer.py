import logging
import re
from subprocess import run

logger = logging.getLogger(__name__)


class AlsaMixer:
    """
    Reads and writes ALSA mixer controls through `amixer`.

    All values are the raw ones of the soundcard: any app-level policy (like an offset
    added to the output volume) belongs to the caller.
    Read functions return None when the value can't be read; write functions return True/False.
    """

    COMMAND_TIMEOUT_SECONDS: int = 5

    # Matches every [bracketed] group of an `amixer sget` line, e.g.
    #   "Mono: Capture 30 [48%] [14.25dB] [on]"  ->  ["48%", "14.25dB", "on"]
    _BRACKET_GROUPS = re.compile(r"\[([^\]]*)\]")

    @staticmethod
    def get_volume(control: str, channel: str = "Left") -> int | None:
        """
        Volume of a control as a percentage (0-100).

        Args:
            control: ALSA control name ("Speaker", "Master", "Mic", "Capture"...).
            channel: Channel line to parse: "Left" for stereo controls, "Mono" for mono ones.
        """
        groups = AlsaMixer._channel_groups(control, channel)
        if groups is None:
            return None
        for group in groups:
            if group.endswith("%"):
                try:
                    return int(group.rstrip("%").strip())
                except ValueError:
                    return None
        logger.debug(f"The control [{control}] has no volume on channel [{channel}].")
        return None

    @staticmethod
    def get_mute(control: str, channel: str = "Left") -> bool | None:
        """
        True if the control is muted, False if not, None if it can't be known.

        Some controls (like the WM8960 "Speaker") have a volume but no mute switch:
        there is no [on]/[off] in their output, and that is NOT the same as muted.
        """
        groups = AlsaMixer._channel_groups(control, channel)
        if groups is None:
            return None
        for group in groups:
            if group.lower() in ("on", "off"):
                return group.lower() == "off"
        logger.debug(f"The control [{control}] has no mute switch on channel [{channel}].")
        return None

    @staticmethod
    def set_volume(control: str, percent: int) -> bool:
        return AlsaMixer._run(["amixer", "set", control, f"{int(percent)}%"]) is not None

    @staticmethod
    def set_mute(control: str, mute: bool) -> bool:
        return AlsaMixer._run(["amixer", "set", control, "mute" if mute else "unmute"]) is not None

    # ---- Internals ----

    @staticmethod
    def _channel_groups(control: str, channel: str) -> list[str] | None:
        output = AlsaMixer._run(["amixer", "sget", control])
        if output is None:
            return None
        marker = f"{channel}:"
        for line in output.splitlines():
            if marker in line:
                return AlsaMixer._BRACKET_GROUPS.findall(line)
        logger.debug(f"No [{channel}] line in the output of the control [{control}].")
        return None

    @staticmethod
    def _run(command: list[str]) -> str | None:
        try:
            result = run(command, capture_output=True, timeout=AlsaMixer.COMMAND_TIMEOUT_SECONDS)
            if result.returncode != 0:
                logger.debug(f"[{' '.join(command)}] failed ({result.returncode}): {result.stderr.decode(errors='replace').strip()}")
                return None
            return result.stdout.decode(errors="replace")
        except Exception as e:
            logger.debug(f"[{' '.join(command)}] could not run: {e}")
            return None
