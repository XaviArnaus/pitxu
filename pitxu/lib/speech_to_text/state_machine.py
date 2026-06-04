from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

class TrascriptionState:
    """
    This class is used to keep track of the current state of the transcription, to be able to apply some logic based on it.
    """
    IDLE = "IDLE"
    START_CONTEXT = "START_CONTEXT"
    ONGOING_PROCESS_CHUNK = "ONGOING_PROCESS_CHUNK"
    LEFTOVER_CHUNK_PROCESSING = "LEFTOVER_CHUNK_PROCESSING"
    REQUESTED_TRANSCRIPTION = "REQUESTED_TRANSCRIPTION"
    FINAL_TRANSCRIPTION = "FINAL_TRANSCRIPTION"
    DONE = "DONE"

class SttStateMachine(PyXavi):

    # Holds the current state of the transcription process.
    current_state: str = TrascriptionState.IDLE

    # Defines FROM -> TO allowed state transitions. This is used to validate that the state transitions are correct, and to apply some logic based on the current state.
    allowed_state_transitions = {
        # Clean start: from IDLE to START_CONTEXT
        TrascriptionState.IDLE: [TrascriptionState.START_CONTEXT],
        # Normal flow: from START_CONTEXT to ONGOING_PROCESS_CHUNK
        TrascriptionState.START_CONTEXT: [TrascriptionState.ONGOING_PROCESS_CHUNK],
        # From ONGOING_PROCESS_CHUNK we can either receive more chunks to process, which keeps us in the same state, 
        #   or we can receive the end of stream signal (None chunk), which means that we have finished processing the current set of chunks 
        #   and we can move to the next state, LEFTOVER_CHUNK_PROCESSING, where we will process the leftover chunks in the queue while waiting for the transcription result. 
        #   We can also receive the end of stream signal directly as REQUESTED_TRANSCRIPTION state, if we receive a very short audio input.
        TrascriptionState.ONGOING_PROCESS_CHUNK: [TrascriptionState.ONGOING_PROCESS_CHUNK, TrascriptionState.LEFTOVER_CHUNK_PROCESSING, TrascriptionState.REQUESTED_TRANSCRIPTION],
        # From LEFTOVER_CHUNK_PROCESSING we can not receive more chunks to process, so we can only head to REQUESTED_TRANSCRIPTION.
        TrascriptionState.LEFTOVER_CHUNK_PROCESSING: [TrascriptionState.REQUESTED_TRANSCRIPTION],
        # From REQUESTED_TRANSCRIPTION we can only move to receiving the transcription result, which is FINAL_TRANSCRIPTION.
        TrascriptionState.REQUESTED_TRANSCRIPTION: [TrascriptionState.FINAL_TRANSCRIPTION],
        # From FINAL_TRANSCRIPTION we can move to DONE when there was an actual transcription, or IDLE if there was no transcription (empty result).
        TrascriptionState.FINAL_TRANSCRIPTION: [TrascriptionState.DONE, TrascriptionState.IDLE],
        # From DONE we can only move to IDLE. This transition represents that we STT triggered the Main's callback.
        TrascriptionState.DONE: [TrascriptionState.IDLE]
    }

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(SttStateMachine, self).init_pyxavi(config=config, params=params)

        # self._xlog.debug("Initializing STT State Machine")

        # self._log_debug("STT State Machine initialization complete")
    
    def is_expected_current_state(self, expected_state: TrascriptionState) -> bool:
        """
        Validates if the given state equals the current state. 
        """
        return self.is_expected_current_states([expected_state])
    
    def is_expected_current_states(self, expected_states: list[TrascriptionState], where_am_i: str = None) -> bool:
        """
        Validates if the current state is one of the expected states.

        Args:
            expected_states (list[TrascriptionState]): The list of expected states to validate against.
            where_am_i (str, optional): A string to indicate where this validation is being called from, to provide more context in the logs. Defaults to None. Commented as logging is useless.
        Returns:
            bool: True if the current state is one of the expected states, False otherwise.
        """
        if self.current_state not in expected_states:
            #where_am_i = f"[{where_am_i}]" if where_am_i else ""
            #self._xlog.error(f"👁️‍🗨️ {where_am_i} Invalid state: {self.current_state}. Expected one of: {expected_states}.")
            return False
        return True
    
    def transition_to(self, new_state: TrascriptionState, expected_current_states: list[TrascriptionState] = None) -> bool:
        """
        Transitions the state machine to a new state if the transition is valid.
        """
        if expected_current_states and not self.is_expected_current_states(expected_current_states):
            self._xlog.error(f"👁️‍🗨️ Invalid expected current states: {expected_current_states}")
            return False
        
        if new_state not in self.allowed_state_transitions:
            self._xlog.error(f"👁️‍🗨️ Invalid new state: {new_state}")
            return False

        if new_state not in self.allowed_state_transitions[self.current_state]:
            self._xlog.error(f"👁️‍🗨️ Invalid state transition from {self.current_state} to {new_state}")
            return False

        self._xlog.debug(f"👁️‍🗨️ Transitioning from {self.current_state} to {new_state}")
        self.current_state = new_state
        return True
    
    def get_transcription_state(self) -> str:
        """
        Returns the current state of the transcription process.
        """
        return self.current_state
    
    def reset(self):
        """
        Resets the state machine to the IDLE state.
        """
        self._xlog.debug("👁️‍🗨️ Resetting STT State Machine to IDLE state")
        self.current_state = TrascriptionState.IDLE