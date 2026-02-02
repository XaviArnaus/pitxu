import os
from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.framebuffer import Framebuffer  # pytorinox
from pitxu.lib.abstract.device import Device

from pitxu.lib.objects.point import Point
from PIL import Image
import numpy as np

class FramebufferScreen(PyXavi, Device):
    """
    Driver for DSI LCDs by using the Linux framebuffer.

    Thanx to: 
    - https://raspi.muth.org/framebuffer.html
    - https://gist.github.com/Quasimondo/e47a5be0c2fa9a3ef80c433e3ee2aead

    To explore:
    - https://stackoverflow.com/questions/76358117/draw-to-different-linux-framebuffers-with-python
    """

    # LCD Waveshare 5" DSI + Toucnhscreen
    LCD_WIDTH = 800
    LCD_HEIGHT = 480

    framebuffer_screen: Framebuffer = None

    use_horizontal: int = 0
    user_screen_size: Point = None

    def __init__(self, config: Config, params: Dictionary):
        super(FramebufferScreen, self).init_pyxavi(config=config, params=params)

        # Initialize framebuffer
        self.framebuffer_screen = Framebuffer(0)  # for /dev/fb0

        # Another approach to explore: write directly into the framebuffer device
        # https://gist.github.com/Quasimondo/e47a5be0c2fa9a3ef80c433e3ee2aead
        # this is the frambuffer for analog video output - note that this is a 16 bit RGB
        # other setups will likely have a different format and dimensions which you can check with
        # fbset -fb /dev/fb0 
        # self.framebuffer_screen = np.memmap('/dev/fb0', dtype='uint16',mode='w+', shape=(576,720))

        # Initialize numpy
        self.np=np

    def _init_display(self):
        # this turns off the cursor blink:
        os.system("TERM=linux setterm -foreground black -clear all >/dev/tty0")
    
    def _reset_lcd(self):
        pass

    def close(self):
        # turn on the cursor again:    
        os.system("TERM=linux setterm -foreground white -clear all >/dev/tty0")
    
    def clear(self):
        # # Paint the entire screen black
        # self.fill_screen(0)
        self._flush_image_to_device(Image.new("RGBA", (self.LCD_WIDTH, self.LCD_HEIGHT), "black"))
        pass

    def display(self, image: Image.Image):

        original_width, original_height = image.size

        # # We work with images in landscape but apparently the screen is in portrait
        # image = image.rotate(90, expand=True)
        # original_width, original_height = image.size

        # Ensure that the image fits into the screen. Otherwise, preprocess it.
        # if not Point(original_width, original_height).equals_to(self.user_screen_size):
        if not Point(original_width, original_height).equals_to(Point(self.LCD_WIDTH, self.LCD_HEIGHT)):
            image = self._preprocess_image(image)
            original_width, original_height = image.size
        
        # The framebuffer appears to be in BGR, not in RGB. So, we need to convert the image.
        # We assume here that the image is already in RGB format, because we set it in config.
        r, g, b, a = image.split()
        image = Image.merge("RGBA", (b, g, r, a))

        # Finally, send the data to the device
        self._flush_image_to_device(image)

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess the image to fit the screen size by resizing and cropping while maintaining aspect ratio.
        """
        screen_width, screen_height = self.LCD_WIDTH, self.LCD_HEIGHT
        original_width, original_height = image.size
        aspect_ratio = original_width / original_height
        screen_aspect_ratio = screen_width / screen_height

        if aspect_ratio > screen_aspect_ratio:
            new_height = screen_height
            new_width = int(new_height * aspect_ratio)
            resized_img = image.resize((new_width, new_height))
            offset_x = (new_width - screen_width) // 2
            cropped_img = resized_img.crop(
                (offset_x, 0, offset_x + screen_width, screen_height))
        else:
            new_width = screen_width
            new_height = int(new_width / aspect_ratio)
            resized_img = image.resize((new_width, new_height))
            offset_y = (new_height - screen_height) // 2
            cropped_img = resized_img.crop(
                (0, offset_y, screen_width, offset_y + screen_height))
        
        return cropped_img
    
    def _flush_image_to_device(self, image: Image.Image, x=0, y=0):
        self.framebuffer_screen.show(image)

        # # Note: If performance is terrible, consider using numpy to write directly to the framebuffer device.
        
        # Alternative approach untested (Copilot code)
        # So, the framebuffer_screen is a numpy memmap array of shape (height, width), when assigning a value to it,
        # it fills/flushes the entire screen with that value.
        # Therefore, first we need to convert the received image to the appropriate format (16-bit RGB565)
        # Then, we can assign the converted data to the framebuffer_screen array.
        # Convert image to RGB565 format
        # image = image.convert("RGB")
        # rgb_array = np.array(image)
        # r = (rgb_array[:, :, 0] >> 3).astype(np.uint16)
        # g = (rgb_array[:, :, 1] >> 2).astype(np.uint16)
        # b = (rgb_array[:, :, 2] >> 3).astype(np.uint16)
        # rgb565_array = (r << 11) | (g << 5) | b
        # self.framebuffer_screen[:] = rgb565_array





    
    # def set_backlight(self, brightness):
    #     if self.backlight_mode:  # 如果是 PWM 模式
    #         if self.backlight_pwm is None:
    #             self.backlight_pwm = GPIO.PWM(self.LED_PIN, 1000)
    #             self.backlight_pwm.start(100)
    #         if 0 <= brightness <= 100:
    #             duty_cycle = 100 - brightness
    #             self.backlight_pwm.ChangeDutyCycle(duty_cycle)
    #     else:  # 如果是简单开关模式
    #         if brightness == 0:
    #             GPIO.output(self.LED_PIN, GPIO.HIGH)  # 关闭背光
    #         else:
    #             GPIO.output(self.LED_PIN, GPIO.LOW)  # 打开背光

    # def set_backlight_mode(self, mode):
    #     """
    #     Set the backlight mode
    #     :param mode: True uses PWM to adjust brightness, False uses simple switch control
    #     """
    #     if mode == self.backlight_mode:
    #         return  # Mode has not changed, no need to operate

    #     if mode:  # Switch to PWM mode
    #         self.backlight_pwm = GPIO.PWM(self.LED_PIN, 1000)
    #         self.backlight_pwm.start(100)
    #     else:  # Switch to simple switch mode
    #         if self.backlight_pwm is not None:
    #             self.backlight_pwm.stop()
    #             self.backlight_pwm = None
    #         GPIO.output(self.LED_PIN, GPIO.HIGH)  # Ensure backlight is on
    #     self.backlight_mode = mode


        
