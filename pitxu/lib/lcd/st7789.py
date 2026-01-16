from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.objects.point import Point
from PIL import Image

import RPi.GPIO as GPIO
import spidev
import time

class ST7789(PyXavi):
    """
    Driver for the ST7789 display controller.

    It has been stripped out from the original WhisPlay library so that it only initializes
    and controls the ST7789 display, without any other extra functionality. This way, we
    can integrate it better into our per-module architecture.
    """

    # LCD 参数
    LCD_WIDTH = 240
    LCD_HEIGHT = 280
    CornerHeight = 20  # The pixels occupied by the fillet height
    DC_PIN = 13
    RST_PIN = 7
    LED_PIN = 15

    backlight_mode: bool = True  # True uses PWM to adjust brightness, False uses simple switch control
    backlight_pwm = None  # Object for PWM control of backlight brightness
    spi: spidev.SpiDev = None

    use_horizontal: int = 0
    user_screen_size: Point = None

    def __init__(self, config: Config, params: Dictionary):
        super(ST7789, self).init_pyxavi(config=config, params=params)

        # Getting the screen size in order.
        if params.key_exists("screen_size"):
            self.user_screen_size = params.get("screen_size")
            # If the sizes are the same as the default device ones
            if self.user_screen_size.equals_to(Point(self.LCD_WIDTH, self.LCD_HEIGHT)):
                self.use_horizontal = 0 if self.user_screen_size.y > self.user_screen_size.x else 1
                self._xlog.debug(f"Given screen size of {self.user_screen_size} equals device's {Point(self.LCD_WIDTH, self.LCD_HEIGHT)} -> " +\
                                 ("vertical" if self.use_horizontal == 0 else "horizontal"))
            # If the sizes are the transposed as the default device ones
            elif self.user_screen_size.equals_to(Point(self.LCD_HEIGHT, self.LCD_WIDTH)):
                self.use_horizontal = 1 if self.user_screen_size.x > self.user_screen_size.y else 0
                self._xlog.debug(f"Given screen size of {self.user_screen_size} transposed device's {Point(self.LCD_WIDTH, self.LCD_HEIGHT)} -> " +\
                                 ("vertical" if self.use_horizontal == 0 else "horizontal"))
            # The sizes actually do not actually fit, and this is not allowed
            else:
                self._xlog.error(f"Given screen size of {self.user_screen_size} does not match device's {Point(self.LCD_WIDTH, self.LCD_HEIGHT)}, even transposed. Aborting.")
                raise ValueError
        else:
            self._xlog.warning(f"Didn't receive 'screen_size' from params, taking the default ones from the driver: {self.LCD_WIDTH}x{self.LCD_HEIGHT}")
            self.user_screen_size = Point(self.LCD_WIDTH, self.LCD_HEIGHT)
            self.use_horizontal = 0

        # Initialize GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(True)
        GPIO.setup([self.DC_PIN, self.RST_PIN, self.LED_PIN], GPIO.OUT)
        GPIO.output(self.LED_PIN, GPIO.LOW)  # Enable backlight

        # Initialize SPI
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 100_000_000
        self.spi.mode = 0b00
    
        self.previous_frame = None
        self._detect_raspberry_pi_version()
        self.set_backlight(self._xconfig.get("lcd.brightness", 50))
        self._reset_lcd()
        # self._init_display(self.use_horizontal)
        self._init_display()
        self.fill_screen(0)
    
    def set_backlight(self, brightness):
        if self.backlight_mode:  # 如果是 PWM 模式
            if self.backlight_pwm is None:
                self.backlight_pwm = GPIO.PWM(self.LED_PIN, 1000)
                self.backlight_pwm.start(100)
            if 0 <= brightness <= 100:
                duty_cycle = 100 - brightness
                self.backlight_pwm.ChangeDutyCycle(duty_cycle)
        else:  # 如果是简单开关模式
            if brightness == 0:
                GPIO.output(self.LED_PIN, GPIO.HIGH)  # 关闭背光
            else:
                GPIO.output(self.LED_PIN, GPIO.LOW)  # 打开背光

    def set_backlight_mode(self, mode):
        """
        Set the backlight mode
        :param mode: True uses PWM to adjust brightness, False uses simple switch control
        """
        if mode == self.backlight_mode:
            return  # Mode has not changed, no need to operate

        if mode:  # Switch to PWM mode
            self.backlight_pwm = GPIO.PWM(self.LED_PIN, 1000)
            self.backlight_pwm.start(100)
        else:  # Switch to simple switch mode
            if self.backlight_pwm is not None:
                self.backlight_pwm.stop()
                self.backlight_pwm = None
            GPIO.output(self.LED_PIN, GPIO.HIGH)  # Ensure backlight is on
        self.backlight_mode = mode

    def _reset_lcd(self):
        GPIO.output(self.RST_PIN, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(self.RST_PIN, GPIO.LOW)
        time.sleep(0.1)
        GPIO.output(self.RST_PIN, GPIO.HIGH)
        time.sleep(0.12)

    def _init_display(self, use_horizontal=0):
        self._send_command(0x11)
        time.sleep(0.12)
        # USE_HORIZONTAL = 1
        USE_HORIZONTAL = use_horizontal if use_horizontal in [0,1,2,3] else 1
        direction = {0: 0x00, 1: 0xC0, 2: 0x70,
                     3: 0xA0}.get(USE_HORIZONTAL, 0x00)
        self._send_command(0x36, direction)
        self._send_command(0x3A, 0x05)
        self._send_command(0xB2, 0x0C, 0x0C, 0x00, 0x33, 0x33)
        self._send_command(0xB7, 0x35)
        self._send_command(0xBB, 0x32)
        self._send_command(0xC2, 0x01)
        self._send_command(0xC3, 0x15)
        self._send_command(0xC4, 0x20)
        self._send_command(0xC6, 0x0F)
        self._send_command(0xD0, 0xA4, 0xA1)
        self._send_command(
            0xE0,
            0xD0,
            0x08,
            0x0E,
            0x09,
            0x09,
            0x05,
            0x31,
            0x33,
            0x48,
            0x17,
            0x14,
            0x15,
            0x31,
            0x34,
        )
        self._send_command(
            0xE1,
            0xD0,
            0x08,
            0x0E,
            0x09,
            0x09,
            0x15,
            0x31,
            0x33,
            0x48,
            0x17,
            0x14,
            0x15,
            0x31,
            0x34,
        )
        self._send_command(0x21)
        self._send_command(0x29)

    def _send_command(self, cmd, *args):
        GPIO.output(self.DC_PIN, GPIO.LOW)
        self.spi.xfer2([cmd])
        if args:
            GPIO.output(self.DC_PIN, GPIO.HIGH)
            self._send_data(list(args))

    def _send_data(self, data):
        GPIO.output(self.DC_PIN, GPIO.HIGH)
        
        try:
            self.spi.writebytes2(data)
        except AttributeError:
            max_chunk = 4096
            for i in range(0, len(data), max_chunk):
                self.spi.writebytes(data[i : i + max_chunk])

    # # def set_window(self, x0, y0, x1, y1, use_horizontal=0):
    # def set_window(self, x0, y0, x1, y1, use_horizontal=3):
    #     if use_horizontal in (0, 1):
    #         self._send_command(0x2A, x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)
    #         self._send_command(
    #             0x2B, (y0 + 20) >> 8, (y0 + 20) & 0xFF, (y1 +
    #                                                      20) >> 8, (y1 + 20) & 0xFF
    #         )
    #     elif use_horizontal in (2, 3):
    #         self._send_command(
    #             0x2A, (x0 + 20) >> 8, (x0 + 20) & 0xFF, (x1 +
    #                                                      20) >> 8, (x1 + 20) & 0xFF
    #         )
    #         self._send_command(0x2B, y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)
    #     self._send_command(0x2C)
    
    def set_window(self, x0, y0, x1, y1, use_horizontal=0):
        use_horizontal = self.use_horizontal
        if use_horizontal in (0, 1):
            self._send_command(
                0x2A,
                x0 >> 8,
                x0 & 0xFF,
                x1 >> 8,
                x1 & 0xFF)  # Here Waveshare sends x1 - 1, but WhisPlay does it in the draw_image() method when calling set_window()
            self._send_command(
                0x2B,
                # Adding 20 to y0 and y1 to account for the corner height offset
                # If I remove it, the image is drawn shifted up by 20 pixels
                (y0 + 20) >> 8,
                (y0 + 20) & 0xFF,
                (y1 + 20) >> 8,
                (y1 + 20) & 0xFF  # Here Waveshare sends y1 - 1, but WhisPlay does it in the draw_image() method when calling set_window()
                # (y0) >> 8,
                # (y0) & 0xFF,
                # (y1) >> 8,
                # (y1) & 0xFF  # Here Waveshare sends y1 - 1, but WhisPlay does it in the draw_image() method when calling set_window()
            )
        elif use_horizontal in (2, 3):
            self._send_command(
                0x2A,
                (x0 + 20) >> 8,
                (x0 + 20) & 0xFF,
                (x1 + 20) >> 8,
                (x1 + 20) & 0xFF
            )
            self._send_command(
                0x2B,
                y0 >> 8,
                y0 & 0xFF,
                y1 >> 8,
                y1 & 0xFF
            )
        self._send_command(0x2C)

    def draw_pixel(self, x, y, color):
        if x >= self.LCD_WIDTH or y >= self.LCD_HEIGHT:
            return
        self.set_window(x, y, x, y)
        self._send_data([(color >> 8) & 0xFF, color & 0xFF])

    def draw_line(self, x0, y0, x1, y1, color):
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        while True:
            self.draw_pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def fill_screen(self, color):
        self.set_window(0, 0, self.LCD_WIDTH - 1, self.LCD_HEIGHT - 1)
        buffer = []
        high = (color >> 8) & 0xFF
        low = color & 0xFF
        for _ in range(self.LCD_WIDTH * self.LCD_HEIGHT):
            buffer.extend([high, low])
        self._send_data(buffer)
    
    def draw_image(self, image: Image.Image):

        original_width, original_height = image.size
        self._xlog.debug(f"Received image of size {original_width}x{original_height} to draw")

        # # We work with images in landscape but apparently the screen is in portrait
        image = image.rotate(90)
        original_width, original_height = image.size
        self._xlog.debug(f"Rotated image so now size is {original_width}x{original_height}")

        # Ensure that the image fits into the screen. Otherwise, preprocess it.
        # if not Point(original_width, original_height).equals_to(self.user_screen_size):
        if not Point(original_width, original_height).equals_to(Point(self.LCD_WIDTH, self.LCD_HEIGHT)):
            image = self._preprocess_image(image)
            original_width, original_height = image.size
            self._xlog.debug(f"Preprocessed to size {original_width}x{original_height}")

        # Now get the actual data that we'll send to the device
        pixel_data = self._convert_image_to_pixel_data_array(image)

        # Finally, send the data to the device
        self._xlog.debug(f"Flushing image of size {original_width}x{original_height} to device")
        self._flush_pixel_data_to_device(0, 0, original_width, original_height, pixel_data)

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess the image to fit the screen size by resizing and cropping while maintaining aspect ratio.
        """
        screen_width, screen_height = self.LCD_WIDTH, self.LCD_HEIGHT
        img_width, img_height = image.size

        # Calculate the scaling factor to maintain aspect ratio
        scale_factor = max(screen_width / img_width, screen_height / img_height)

        # Resize the image with the scaling factor
        new_width = int(img_width * scale_factor)
        new_height = int(img_height * scale_factor)
        resized_img = image.resize((new_width, new_height))

        # Calculate cropping box to center the image
        offset_x = (new_width - screen_width) // 2
        offset_y = (new_height - screen_height) // 2

        # Crop the image to fit screen size
        cropped_img = resized_img.crop(
            (offset_x, offset_y, offset_x + screen_width, offset_y + screen_height))

        return cropped_img

    def _convert_image_to_pixel_data_array(self, image: Image.Image) -> bytearray:
        original_width, original_height = image.size
        pixel_data = []
        for y in range(original_height):
            for x in range(original_width):
                r, g, b = image.getpixel((x, y))
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                pixel_data.extend([(rgb565 >> 8) & 0xFF, rgb565 & 0xFF])

        return pixel_data

    def _flush_pixel_data_to_device(self, x, y, width, height, pixel_data):
        self._xlog.debug(f"Drawing image at ({x}, {y}) with size {width}x{height} over a screen of {self.LCD_WIDTH}x{self.LCD_HEIGHT}")
        if (x + width > self.LCD_WIDTH) or (y + height > self.LCD_HEIGHT):
            self._xlog.error("The image size is beyond the range of the screen")
            raise ValueError("The image size is beyond the range of the screen")
        self.set_window(x, y, x + width - 1, y + height - 1)
        self._send_data(pixel_data)
    
    def _detect_raspberry_pi_version(self):
        """
        Detect the Raspberry Pi hardware version and set the backlight mode according to the version
        """
        try:
            with open("/proc/cpuinfo", "r") as f:
                lines = f.readlines()
                model_name = None
                for line in lines:
                    if line.startswith("Model"):
                        model_name = line.strip().split(":")[1].strip()
                        break
                if model_name:
                    if "Zero" in model_name and "2" not in model_name:
                        # 如果是 Zero 或 Zero W
                        self.backlight_mode = False  # Use simple switch mode
                    else:
                        # 其他型号（如 Zero 2 W, 3B, 4B 等）
                        self.backlight_mode = True  # Use PWM mode
                        self._xlog.debug(f"Detected hardware: {model_name}, Backlight mode: {'PWM' if self.backlight_mode else 'Simple Switch'}")
                else:
                    self._xlog.warning("Model name not found in /proc/cpuinfo")
                    self.backlight_mode = True  # Use PWM mode by default
        except Exception as e:
            self._xlog.error(f"Error detecting hardware version: {e}")
            self.backlight_mode = True  # Use PWM mode by default


        
