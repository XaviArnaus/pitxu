from pyxavi import Config, Dictionary, TerminalColor, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi

from definitions import ROOT_DIR

import time, json, os

class Test(PyXavi):

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Test, self).init_pyxavi(config=config, params=params)
    
    # -------- The tests themselves --------

    def test_eink_multiline(self):
        try:
            from pitxu.lib.eink.eink import EinkDisplay
            from pitxu.lib.canvas.macros import Macros
            from pitxu.lib.canvas.canvas import Canvas

            # Instantiating

            # Delegate the run to Main
            self._xlog.debug("Testing eInk display multiline text")
            eink = EinkDisplay(config=self._xconfig, params=self._xparams)
            macros = Macros(config=self._xconfig, params=self._xparams)
            macros.arbitrary_text_with_icon(
                display = eink, 
                text = "This is a test", 
                icon = "⚠️", 
                font_size = Canvas.FONT_SIZE_BIG, 
                header = "Single Line Test", 
                font_header_size = Canvas.FONT_SIZE_BIG)
            self._xlog.debug("Pausing 2 seconds to let it show")
            time.sleep(2)
            macros.arbitrary_text_with_icon(
                display = eink, 
                text = "This is a test of multiline text rendering on the eInk display.", 
                icon = "⚠️", 
                font_size = Canvas.FONT_SIZE_BIG, 
                header = "Multiline Test", 
                font_header_size = Canvas.FONT_SIZE_BIG)
            self._xlog.debug("Pausing 2 seconds to let it show")
            time.sleep(2)
            self._xlog.debug("Clearing eInk display")
            eink.clear()
            self._xlog.info("End of work.")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack())

    def test_matrix(self):
        try:
            from pitxu.lib.matrix_led import Max7219

            # Delegate the run to Main
            self._xlog.debug("Testing LED Matrix display")
            Max7219(config=self._xconfig, params=self._xparams).test()
            self._xlog.debug("Pausing 2 seconds to let it show")
            time.sleep(2)
            self._xlog.info("End of work.")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack())

    def test_lcd(self):
        try:
            from pitxu.lib.lcd.st7789 import ST7789
            from pitxu.lib.objects.point import Point
            from pitxu.lib.objects.rectangle import Rectangle
            from pitxu.lib.canvas.canvas import Canvas
            from PIL import ImageFont, ImageDraw, Image
            # from pitxu.lib.canvas.macros import Macros as CanvasMacros

            expected_screen_size = Point(280, 240)

            # Delegate the run to Main
            self._xlog.debug("Testing LCD display")
            lcd = ST7789(config=self._xconfig, params=self._xparams.merge(Dictionary({"screen_size": expected_screen_size})))
            self._xlog.debug("Drawing a white cross over black background...")
            lcd.draw_line(0, 0, lcd.LCD_WIDTH - 1, lcd.LCD_HEIGHT - 1, color=0xFFFF)  # Diagonal line
            lcd.draw_line(0, lcd.LCD_HEIGHT - 1, lcd.LCD_WIDTH - 1, 0, color=0xFFFF)  # Diagonal line
            self._xlog.debug("Pausing 2 seconds to let it show")
            time.sleep(2)
            
            for text in ["Without\nCanvas class", "With\nCanvas class"]:

                # Clear screen
                lcd.fill_screen(0)

                # Prepare the classes
                self._xlog.debug(f"Drawing {text}...")
                if text == "Without\nCanvas class":
                    image = Image.new("RGB", expected_screen_size.to_image_point(), "black")
                    draw = ImageDraw.Draw(image)
                else:
                    canvas = Canvas(config=self._xconfig, params=self._xparams.merge(Dictionary({"screen_size": expected_screen_size})))
                    draw = canvas.get_canvas()

                colors = ["red", "green", "blue", "yellow", "purple"]
                for i in range(5):
                    draw.rectangle(
                        xy=Rectangle(
                            Point(i * 10, i * 10),
                            Point(expected_screen_size.x - (i * 10), expected_screen_size.y - (i * 10))
                        ).to_image_rectangle(),
                        fill=colors[i]
                    )
                draw.text(
                    xy=Point(expected_screen_size.x / 2, expected_screen_size.y / 2).to_image_point(),
                    text=text,
                    font=ImageFont.truetype(os.path.join(ROOT_DIR, "pitxu", "lib", "canvas", "fonts", "Font_with_emojis.ttc"), 25),
                    fill="white",
                    anchor="mm",
                    align="center")
                
                if text == "With\nCanvas class":
                    image = canvas.get_image()

                lcd.draw_image(image)
                self._xlog.debug("Pausing 2 seconds to let it show")
                time.sleep(2)

            # Clear screen
            lcd.fill_screen(0)
            self._xlog.info("End of work.")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack()) 

    def test_mouth_in_lcd(self):
        try:
            from pitxu.lib.lcd.device_wrapper import DeviceWrapper
            from pitxu.lib.canvas.canvas import Canvas
            from pitxu.lib.canvas.macros import Macros
            from pitxu.lib.objects.point import Point

            MODE_IN_USE = "paint" # Valid values: "paint", "direct"

            expected_screen_size = Point(280, 240)

            # Delegate the run to Main
            self._xlog.debug("Testing the KITT mouth as LEDs in the LCD display")
            parameters = parameters.merge(Dictionary({
                "screen_size": expected_screen_size,
                "device_config_prefix": "lcd"
            }))
            device = DeviceWrapper(config=self._xconfig, params=parameters)
            parameters.set("device", device)
            canvas = Canvas(config=self._xconfig, params=parameters)
            parameters.set("canvas", canvas)
            macros = Macros(config=self._xconfig, params=parameters)
            parameters.set("macros", macros)
            
            if MODE_IN_USE == "direct":
                self._xlog.debug("Using direct mode to draw KITT mouth while speaking...")
                # Direct mode, no painter
                for i in range(0,2):
                    macros.kitt_speaking_effect(0,0,2,4, 0.01)
            else:
                from pitxu.lib.canvas.painter import Painter
                from pitxu.lib.canvas.painter_commands import BackgroundComm

                painter = Painter(config=self._xconfig, params=parameters)

                self._xlog.debug("Using painter mode to draw KITT mouth while speaking...")
                # Painter mode

                # Setting what to show and start the painting loop
                painter.set_background_interaction(BackgroundComm.SPEAKING, parameter={
                    "col_1": 0,
                    "col_2": 0,
                    "col_3": 2,
                    "col_4": 4,
                })
                painter.start_or_resume_paint()

                # Emulating now some time until the speaker is not busy anymore
                self._xlog.debug("Emulating KITT mouth while speaking for 0.5 seconds...")
                time.sleep(0.5)

                # Reached here? Stop the painting
                painter.stop()

                # We could have done a close, that stops and cleans up.
                painter.close()

            # Clear screen
            device.clear()
            self._xlog.info("End of work.")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack())

    def test_thinking_in_lcd(self):
        try:
            from pitxu.lib.lcd.device_wrapper import DeviceWrapper
            from pitxu.lib.canvas.canvas import Canvas
            from pitxu.lib.canvas.macros import Macros
            from pitxu.lib.objects.point import Point

            expected_screen_size = Point(280, 240)

            # Delegate the run to Main
            self._xlog.debug("Testing the KITT mouth as LEDs in the LCD display")
            parameters = self._xparams.merge(Dictionary({
                "screen_size": expected_screen_size
            }))
            device = DeviceWrapper(config=self._xconfig, params=parameters)
            parameters.set("device", device)
            canvas = Canvas(config=self._xconfig, params=parameters)
            parameters.set("canvas", canvas)
            macros = Macros(config=self._xconfig, params=parameters)

            for i in range(0,5):
                macros.kitt_horizontal_effect()

            # Clear screen
            device.clear()
            self._xlog.info("End of work.")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack()) 

    def test_email(self):
        
        try:
            # Delegate the run to Main
            from pitxu.lib.command.services.mail import ServiceMail
            mail_service = ServiceMail(config=self._xconfig, params=self._xparams)
            subject = "Test Email from Pitxu"
            body = "This is a test email sent from the Pitxu application."
            if mail_service.send_email(subject=subject, body=body):
                self._xlog.info("Email sent successfully.")
            else:
                self._xlog.error("Failed to send email.")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack())

    def test_print(self):

        try:
            # Delegate the run to Main
            from pitxu.lib.command.services.print import ServicePrint
            print_service = ServicePrint(config=self._xconfig, params=self._xparams)
            subject = "Test Print from Pitxu"
            body = f"{subject}\n\nThis is a test print sent from the Pitxu application."
            if print_service.print(text=body):
                self._xlog.info("Print sent successfully.")
            else:
                self._xlog.error("Failed to send print.")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack())

    def test_lists(self):
        try:
            from pitxu.lib.utils.lists import Lists
            lists = Lists(config=self._xconfig, params=self._xparams)

            # Create list
            list_name = "Test List"
            test_list = lists.create_list(list_name=list_name)
            if not test_list:
                self._xlog.error("Failed to create test list.")
                return
            self._xlog.info(f"List created successfully: {json.dumps(test_list, indent=2)}")
            
            # Add items
            lists.add_entry(list_name, "First entry")
            lists.add_entry(list_name, "Second entry")
            self._xlog.info(f"2 entries added successfully to the list [{list_name}]: {json.dumps(test_list, indent=2)}")

            # Get items
            element_2 = lists.get_entry(list_name, position=2)
            if not element_2:
                self._xlog.error("Failed to retrieve entry")
                return
            self._xlog.info(f"Entry retrieved successfully: {json.dumps(element_2, indent=2)}")

            # Update item
            updated_element_1 = lists.update_entry(list_name, position=1, new_text="Updated first entry")
            if not updated_element_1:
                self._xlog.error("Failed to retrieve updated entry")
                return
            self._xlog.info(f"Entry updated successfully: {json.dumps(updated_element_1, indent=2)}")

            # Delete item
            deleted_element_1 = lists.delete_entry(list_name, position=1)
            if not deleted_element_1:
                self._xlog.error("Failed to delete entry.")
                return
            self._xlog.info(f"Entry deleted successfully: {json.dumps(deleted_element_1, indent=2)}")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack())
    
    def test_fans(self):
        try:

            INITIAL_HZ = 100
            waiting_time = 4

            # Delegate the run to Main
            self._xlog.debug("Testing fans control")
            from rpi_hardware_pwm import HardwarePWM
            from pitxu.lib.gpio.fans import FanConfig
            from subprocess import check_output

            fan_configs: list[FanConfig] = self._xconfig.get("gpio.fans.devices", [])
            for fan_config_data in fan_configs:
                fan_config = FanConfig.from_dict(fan_config_data)
                self._xlog.debug(f"Testing PWM fan '{fan_config.name}' as: \n{json.dumps(fan_config.to_dict(), indent=2)}")
                pwm=HardwarePWM(
                    fan_config.pwm_channel,
                    INITIAL_HZ,
                    chip=fan_config.pwm_chip) #channel 0 1 2 3 for GPIO12 13 18 19 respectively
                pwm.change_duty_cycle(0)
                pwm.change_frequency(fan_config.pwm_frequency)
                pwm.start(100)
                self._xlog.debug("System PWM setup: \n" + check_output("sudo cat /sys/kernel/debug/pwm", shell=True).decode())
                self._xlog.debug(f"Fan should be at 100% speed for {waiting_time} seconds")
                time.sleep(waiting_time)
                pwm.change_duty_cycle(0.5/10)
                self._xlog.debug("System PWM setup: \n" + check_output("sudo cat /sys/kernel/debug/pwm", shell=True).decode())
                self._xlog.debug(f"Fan should be at 50% speed for {waiting_time} seconds")
                time.sleep(waiting_time)
                pwm.change_frequency(25_000)
                self._xlog.debug("System PWM setup: \n" + check_output("sudo cat /sys/kernel/debug/pwm", shell=True).decode())
                self._xlog.debug(f"Fan should be at 50% speed but with 25KHz frequency for {waiting_time} seconds")
                time.sleep(waiting_time)
                pwm.stop()
            self._xlog.info("End of work.")
        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack())
