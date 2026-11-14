import time


class LatencyTimeline:
    """
    Timestamps of the stages of one spoken interaction, and a readable breakdown of where the time went.

    It is meant to measure how long the user waits between finishing a sentence and hearing the answer.
    The marks are epoch seconds (time.time()), so a mark taken in another process (like the first audio written by Piper)
    can be added too, as long as it is passed through shared memory.

    Marks, in the order they normally happen:
        vad_end         The VAD decided the user finished speaking (it already waited `vad.release` seconds of silence).
        transcript      The final transcription arrived to Main.
        chatbot_start   Main starts the chatbot step (only when the Chatbot is called).
        llm_sent        The request is about to be sent to the Chatbot.
        llm_answer      The Chatbot answered.
        answer_ready    Main is ready to deliver the answer.
        say_start       Interaction.say() starts.
        speaker_sent    The SAY command is sent to the speaker (after waiting for the display).
        first_audio     Piper writes the first audio to the output stream (published through shared memory).
        say_end         The speech finished.

    Everything lives in the main process and is a class-level store, like System, so any class there can mark without wiring.
    """

    _marks: dict = {}

    @staticmethod
    def reset() -> None:
        LatencyTimeline._marks = {}

    @staticmethod
    def mark(name: str, timestamp: float = None) -> None:
        LatencyTimeline._marks[name] = timestamp if timestamp is not None else time.time()

    @staticmethod
    def elapsed(start: str, end: str) -> float | None:
        marks = LatencyTimeline._marks
        if start in marks and end in marks and marks[end] >= marks[start]:
            return marks[end] - marks[start]
        return None

    @staticmethod
    def breakdown(silence_wait_seconds: float = None) -> list[tuple[str, str]] | None:
        """
        The stages of the last interaction as (label, value) lines, ready for PyXavi.log_summary().
        None if the interaction did not start from a speech end.
        """
        if "vad_end" not in LatencyTimeline._marks:
            return None

        if "llm_sent" in LatencyTimeline._marks:
            stages = [
                ("STT final", "vad_end", "transcript"),
                ("Decision", "transcript", "chatbot_start"),
                ("Display + thinking", "chatbot_start", "llm_sent"),
                ("LLM", "llm_sent", "llm_answer"),
                ("Display after LLM", "llm_answer", "answer_ready"),
                ("Prepare say", "answer_ready", "say_start"),
            ]
        else:
            # Answers that don't call the Chatbot (only the trigger words, exit...).
            stages = [
                ("STT final", "vad_end", "transcript"),
                ("Decision + display", "transcript", "say_start"),
            ]
        stages += [
            ("Display wait in say", "say_start", "speaker_sent"),
            ("TTS to first audio", "speaker_sent", "first_audio"),
        ]

        lines = []
        for label, start, end in stages:
            elapsed = LatencyTimeline.elapsed(start, end)
            if elapsed is not None:
                lines.append((label, f"{elapsed:.2f} s"))

        total = LatencyTimeline.elapsed("vad_end", "first_audio")
        if total is None:
            lines.append(("First audio after VAD end", "not available"))
        else:
            lines.append(("First audio after VAD end", f"{total:.2f} s"))
            if silence_wait_seconds:
                lines.append(("VAD silence wait (release)", f"{float(silence_wait_seconds):.2f} s"))
                lines.append(("From when you stopped talking", f"~{total + float(silence_wait_seconds):.2f} s"))

        speaking = LatencyTimeline.elapsed("first_audio", "say_end")
        if speaking is not None:
            lines.append(("Speaking", f"{speaking:.1f} s"))

        return lines
