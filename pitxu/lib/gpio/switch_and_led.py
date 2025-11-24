from pitxu.lib.abstract.pyxavi import PyXavi
from pyxavi import Config, Dictionary
from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from definitions import SHARED_GPIO_BUTTON_GREEN_STATE, SHARED_GPIO_LED_BLUE_STATE

from gpiozero import LED, Button


class SwitchAndLed(PyXavi):
    '''
    Class to manage a GPIO switch and an LED

    The switch can be used to trigger actions, and the LED can be used to indicate status.
    '''

    STATE_MUTE_SWITCH = "mute_switch"

    _shared_memory: SharedMemoryManager = None

    _blue_led: LED = None
    _green_button: Button = None

    _states: dict[str, bool] = {
        STATE_MUTE_SWITCH: False
    }

    def __init__(self, config: Config, params: Dictionary):
        super(SwitchAndLed,self).init_pyxavi(config=config, params=params)
        # Initialization code for GPIO switch and LED would go here
        self.initialize()
        self._xlog.info("SwitchAndLed initialized")
    
    def initialize(self):

        # The blue LED
        self._blue_led = LED(int(self._xconfig.get("gpio.led_blue_pin")))

        # If True (the default), the GPIO pin will be pulled high by default. 
        #   In this case, connect the other side of the button to ground. 
        # If False, the GPIO pin will be pulled low by default. 
        #   In this case, connect the other side of the button to 3V3.
        #
        # To get the current value, use `self._green_button.is_pressed`
        self._green_button = Button(int(self._xconfig.get("gpio.button_green_pin")), pull_up=True)

        self._xlog.info("Switch and Led: Loading GPIO state from Shared Memory")
        self._shared_memory = SharedMemoryManager(config=self._xconfig, params=self._xparams)
        self._shared_memory.initialize_existing_shared_memory_gpio_buttons()
        self._shared_memory.initialize_existing_shared_memory_gpio_leds()

        # Let's just reset generally the Switches and LEDs to off at startup
        self._shared_memory.write_shared_memory_gpio_button(SHARED_GPIO_BUTTON_GREEN_STATE, False)
        self.set_led_blue_off()

        self._xlog.info("Done Initializing Switch and Led")
    
    def is_mute_switch_on(self) -> bool:
        '''
        Just to know the current state of the mute switch
        '''
        return self._states[self.STATE_MUTE_SWITCH]

    def update_mute_switch_state_if_pressed(self) -> bool:
        '''
        To be called to check the state of the mute switch.
        '''
        is_pressed = not self._green_button.is_pressed
        if is_pressed:
            self._states[self.STATE_MUTE_SWITCH] = True
            self._shared_memory.write_shared_memory_gpio_button(SHARED_GPIO_BUTTON_GREEN_STATE, True)
            self.set_led_blue_on()
        else:
            self._states[self.STATE_MUTE_SWITCH] = False
            self._shared_memory.write_shared_memory_gpio_button(SHARED_GPIO_BUTTON_GREEN_STATE, False)
            self.set_led_blue_off()
        return is_pressed

    def set_led_blue_on(self):
        self._blue_led.on()
        self._shared_memory.write_shared_memory_gpio_led(SHARED_GPIO_LED_BLUE_STATE, True)

    def set_led_blue_off(self):
        self._blue_led.off()
        self._shared_memory.write_shared_memory_gpio_led(SHARED_GPIO_LED_BLUE_STATE, False)