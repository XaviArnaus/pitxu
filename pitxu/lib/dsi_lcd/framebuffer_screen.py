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

    Thanx to: https://raspi.muth.org/framebuffer.html
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
        # buffer = Image.new(mode="RGB", size=self.framebuffer_screen.size)
        # draw = ImageDraw.Draw(buffer)
        # cx = self.framebuffer_screen.size[0] // 2
        # cy = self.framebuffer_screen.size[1] // 2
        # draw.rectangle((cx - 10, cy -10, cx + 10,  cy + 10), "white") 
        # self.framebuffer_screen.show(buffer)

        # Initialize numpy
        self.np=np
    
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

    def _reset_lcd(self):
        pass
    
    def clear(self):
        # # Paint the entire screen black
        # self.fill_screen(0)
        pass

    def _init_display(self, use_horizontal=0):
        pass
    
    def display(self, image: Image.Image):

        # original_width, original_height = image.size

        # # We work with images in landscape but apparently the screen is in portrait
        # image = image.rotate(90, expand=True)
        # original_width, original_height = image.size

        # # Ensure that the image fits into the screen. Otherwise, preprocess it.
        # # if not Point(original_width, original_height).equals_to(self.user_screen_size):
        # if not Point(original_width, original_height).equals_to(Point(self.LCD_WIDTH, self.LCD_HEIGHT)):
        #     image = self._preprocess_image(image)
        #     original_width, original_height = image.size

        # Finally, send the data to the device
        self._flush_image_to_device(image)

    # def _preprocess_image(self, image: Image.Image) -> Image.Image:
    #     """
    #     Preprocess the image to fit the screen size by resizing and cropping while maintaining aspect ratio.
    #     """
    #     screen_width, screen_height = self.LCD_WIDTH, self.LCD_HEIGHT
    #     original_width, original_height = image.size
    #     aspect_ratio = original_width / original_height
    #     screen_aspect_ratio = screen_width / screen_height

    #     if aspect_ratio > screen_aspect_ratio:
    #         new_height = screen_height
    #         new_width = int(new_height * aspect_ratio)
    #         resized_img = image.resize((new_width, new_height))
    #         offset_x = (new_width - screen_width) // 2
    #         cropped_img = resized_img.crop(
    #             (offset_x, 0, offset_x + screen_width, screen_height))
    #     else:
    #         new_width = screen_width
    #         new_height = int(new_width / aspect_ratio)
    #         resized_img = image.resize((new_width, new_height))
    #         offset_y = (new_height - screen_height) // 2
    #         cropped_img = resized_img.crop(
    #             (0, offset_y, screen_width, offset_y + screen_height))
        
    #     return cropped_img
    
    def _flush_image_to_device(self, image: Image.Image, x=0, y=0):
        self.framebuffer_screen.show(image)


        
