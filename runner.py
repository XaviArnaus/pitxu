import os, time
from dotenv import load_dotenv
import importlib.metadata
import sounddevice
import asyncio
import logging
import json

from pyxavi.terminal_color import TerminalColor
from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary
from pyxavi.debugger import full_stack

from pitxu.lib.utils.config_loader import ConfigLoader

from definitions import ROOT_DIR, CONFIG_DIR

from pitxu.main import Main


def load_environment():
    """
    Loads the environment

    This means to load the environment vars from the .env file and also
    any other parameter related to the environment.
    """
    load_dotenv()


def load_logger(config: Config, loglevel: int = None) -> logging:

    if loglevel is not None:
        # Lets first merge the config with the new value
        logger_config = config.get("logger")
        logger_config["loglevel"] = loglevel
        logger_config["stdout"]["active"] = True
        config.merge_from_dict(parameters={"logger": logger_config})

    return Logger(config=config, base_path=ROOT_DIR).get_logger()

def run():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        logger.debug("Starting Main run")
        main = Main(config=config, params=parameters)
        asyncio.run(main.run())
        logger.info("End of the Main run")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack()) 

def clear_displays():
    try:
        from pitxu.lib.eink import EinkDisplay
        from pitxu.lib.matrix_led import Max7219
        from pitxu.lib.lcd.st7789 import ST7789
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        try:
            logger.debug("Clearing eInk display")
            EinkDisplay(config=config, params=parameters).clear()
        except Exception as e:
            logger.warning(f"Could not clear eInk display: {str(e)}")
        try:
            logger.debug("Clearing LED Matrix display")
            Max7219(config=config, params=parameters).clear()
        except Exception as e:
            logger.warning(f"Could not clear LED Matrix display: {str(e)}")
        try:
            logger.debug("Clearing LCD display")
            ST7789(config=config, params=parameters).clear()
        except Exception as e:
            logger.warning(f"Could not clear LCD display: {str(e)}")
        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def test_eink_multiline():
    try:
        from pitxu.lib.eink import EinkDisplay, Macros
        from pitxu.lib.canvas.canvas import Canvas

        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        logger.debug("Testing eInk display multiline text")
        eink = EinkDisplay(config=config, params=parameters)
        macros = Macros(config=config, params=parameters)
        macros.arbitrary_text_with_icon(
            display = eink, 
            text = "This is a test", 
            icon = "⚠️", 
            font_size = Canvas.FONT_SIZE_BIG, 
            header = "Single Line Test", 
            font_header_size = Canvas.FONT_SIZE_BIG)
        logger.debug("Pausing 2 seconds to let it show")
        time.sleep(2)
        macros.arbitrary_text_with_icon(
            display = eink, 
            text = "This is a test of multiline text rendering on the eInk display.", 
            icon = "⚠️", 
            font_size = Canvas.FONT_SIZE_BIG, 
            header = "Multiline Test", 
            font_header_size = Canvas.FONT_SIZE_BIG)
        logger.debug("Pausing 2 seconds to let it show")
        time.sleep(2)
        logger.debug("Clearing eInk display")
        eink.clear()
        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def test_matrix():
    try:
        from pitxu.lib.matrix_led import Max7219

        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        logger.debug("Testing LED Matrix display")
        Max7219(config=config, params=parameters).test()
        logger.debug("Pausing 2 seconds to let it show")
        time.sleep(2)
        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def test_lcd():
    try:
        from pitxu.lib.lcd.st7789 import ST7789
        from pitxu.lib.objects.point import Point
        from pitxu.lib.objects.rectangle import Rectangle
        from pitxu.lib.canvas.canvas import Canvas
        from PIL import ImageFont, ImageDraw, Image
        # from pitxu.lib.canvas.macros import Macros as CanvasMacros

        # Instantiating
        config, logger, parameters = _initialize()

        expected_screen_size = Point(280, 240)

        # Delegate the run to Main
        logger.debug("Testing LCD display")
        lcd = ST7789(config=config, params=parameters.merge(Dictionary({"screen_size": expected_screen_size})))
        logger.debug("Drawing a white cross over black background...")
        lcd.draw_line(0, 0, lcd.LCD_WIDTH - 1, lcd.LCD_HEIGHT - 1, color=0xFFFF)  # Diagonal line
        lcd.draw_line(0, lcd.LCD_HEIGHT - 1, lcd.LCD_WIDTH - 1, 0, color=0xFFFF)  # Diagonal line
        logger.debug("Pausing 2 seconds to let it show")
        time.sleep(2)
        
        for text in ["Without\nCanvas class", "With\nCanvas class"]:

            # Clear screen
            lcd.fill_screen(0)

            # Prepare the classes
            logger.debug(f"Drawing {text}...")
            if text == "Without\nCanvas class":
                image = Image.new("RGB", expected_screen_size.to_image_point(), "black")
                draw = ImageDraw.Draw(image)
            else:
                canvas = Canvas(config=config, params=parameters.merge(Dictionary({"screen_size": expected_screen_size})))
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
            logger.debug("Pausing 2 seconds to let it show")
            time.sleep(2)

        # Clear screen
        lcd.fill_screen(0)
        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack()) 

def test_mouth_in_lcd():
    try:
        from pitxu.lib.lcd.device_wrapper import DeviceWrapper
        from pitxu.lib.canvas.canvas import Canvas
        from pitxu.lib.canvas.macros import Macros
        from pitxu.lib.objects.point import Point

        MODE_IN_USE = "paint" # Valid values: "paint", "direct"

        # Instantiating
        config, logger, parameters = _initialize()

        expected_screen_size = Point(280, 240)

        # Delegate the run to Main
        logger.debug("Testing the KITT mouth as LEDs in the LCD display")
        parameters = parameters.merge(Dictionary({
            "screen_size": expected_screen_size,
            "device_config_prefix": "lcd"
        }))
        device = DeviceWrapper(config=config, params=parameters)
        parameters.set("device", device)
        canvas = Canvas(config=config, params=parameters)
        parameters.set("canvas", canvas)
        macros = Macros(config=config, params=parameters)
        parameters.set("macros", macros)
        
        if MODE_IN_USE == "direct":
            logger.debug("Using direct mode to draw KITT mouth while speaking...")
            # Direct mode, no painter
            for i in range(0,2):
                macros.kitt_speaking_effect(0,0,2,4, 0.01)
        else:
            from pitxu.lib.canvas.painter import Painter
            from pitxu.lib.canvas.painter_commands import BackgroundComm

            painter = Painter(config=config, params=parameters)

            logger.debug("Using painter mode to draw KITT mouth while speaking...")
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
            logger.debug("Emulating KITT mouth while speaking for 0.5 seconds...")
            time.sleep(0.5)

            # Reached here? Stop the painting
            painter.stop()

            # We could have done a close, that stops and cleans up.
            painter.close()

        # Clear screen
        device.clear()
        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def test_thinking_in_lcd():
    try:
        from pitxu.lib.lcd.device_wrapper import DeviceWrapper
        from pitxu.lib.canvas.canvas import Canvas
        from pitxu.lib.canvas.macros import Macros
        from pitxu.lib.objects.point import Point

        # Instantiating
        config, logger, parameters = _initialize()

        expected_screen_size = Point(280, 240)

        # Delegate the run to Main
        logger.debug("Testing the KITT mouth as LEDs in the LCD display")
        parameters = parameters.merge(Dictionary({"screen_size": expected_screen_size}))
        device = DeviceWrapper(config=config, params=parameters)
        parameters.set("device", device)
        canvas = Canvas(config=config, params=parameters)
        parameters.set("canvas", canvas)
        macros = Macros(config=config, params=parameters)

        for i in range(0,5):
            macros.kitt_horizontal_effect()

        # Clear screen
        device.clear()
        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack()) 

def query_sound_devices():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        logger.debug("Querying SoundDevice")
        print()
        print(sounddevice.query_devices())
        print()
        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack()) 

# def test_sound_out():
#     try:
#         # Instantiating
#         config, logger, parameters = _initialize()

#         # Delegate the run to Main
#         logger.debug("Testing SoundDevice")
        
#         import soundfile as sf
#         import sounddevice as sd
#         import threading

#         def _play(sound):
#             event =threading.Event()

#             def callback(outdata, frames, time, status):
#                 data = wf.buffer_read(frames, dtype='float32')
#                 if len(outdata) > len(data):
#                     outdata[:len(data)] = data
#                     outdata[len(data):] = b'\x00' * (len(outdata) - len(data))
#                     raise sd.CallbackStop
#                 else:
#                     outdata[:] = data

#             with sf.SoundFile(sound) as wf:
#                 stream = sd.RawOutputStream(samplerate=wf.samplerate,
#                                             channels=wf.channels,
#                                             callback=callback,
#                                             blocksize=1024,
#                                             finished_callback=event.set)
#                 with stream:
#                     event.wait()

#         def _playsound(sound):
#             new_thread = threading.Thread(target=_play, args=(sound,))
#             new_thread.start()

#         _playsound('sounds_file.wav')


#         logger.info("End of work.")

#     except RuntimeError as e:
#         print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
#     except Exception:
#         print(full_stack()) 

def battery_status():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        from pitxu.lib.ups.ups import UPS
        ups = UPS(config=config, params=parameters)
        voltage, capacity = ups.read_voltage_and_capacity()
        pld_state = ups.get_pld_state()
        logger.info(f"Battery voltage: {voltage:.2f} V")
        logger.info(f"Battery capacity: {capacity:.2f} %")
        logger.info(f"Power Loss/Adapter Failure State: {'FAIL' if pld_state == 0 else 'OK'}")
        logger.info("End of work.")
        ups.close()

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def send_email():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        from pitxu.lib.command.services.mail import ServiceMail
        mail_service = ServiceMail(config=config, params=parameters)
        subject = "Test Email from Pitxu"
        body = "This is a test email sent from the Pitxu application."
        if mail_service.send_email(subject=subject, body=body):
            logger.info("Email sent successfully.")
        else:
            logger.error("Failed to send email.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def send_to_printer():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        from pitxu.lib.command.services.print import ServicePrint
        print_service = ServicePrint(config=config, params=parameters)
        subject = "Test Print from Pitxu"
        body = f"{subject}\n\nThis is a test print sent from the Pitxu application."
        if print_service.print(text=body):
            logger.info("Print sent successfully.")
        else:
            logger.error("Failed to send print.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def test_lists():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        from pitxu.lib.utils.lists import Lists
        lists = Lists(config=config, params=parameters)
        
        # Create list
        list_name = "Test List"
        test_list = lists.create_list(list_name=list_name)
        if not test_list:
            logger.error("Failed to create test list.")
            return
        logger.info(f"List created successfully: {json.dumps(test_list, indent=2)}")
        
        # Add items
        lists.add_entry(list_name, "First entry")
        lists.add_entry(list_name, "Second entry")
        logger.info(f"2 entries added successfully to the list [{list_name}]: {json.dumps(test_list, indent=2)}")

        # Get items
        element_2 = lists.get_entry(list_name, position=2)
        if not element_2:
            logger.error("Failed to retrieve entry")
            return
        logger.info(f"Entry retrieved successfully: {json.dumps(element_2, indent=2)}")

        # Update item
        updated_element_1 = lists.update_entry(list_name, position=1, new_text="Updated first entry")
        if not updated_element_1:
            logger.error("Failed to retrieve updated entry")
            return
        logger.info(f"Entry updated successfully: {json.dumps(updated_element_1, indent=2)}")

        # Delete item
        deleted_element_1 = lists.delete_entry(list_name, position=1)
        if not deleted_element_1:
            logger.error("Failed to delete entry.")
            return
        logger.info(f"Entry deleted successfully: {json.dumps(deleted_element_1, indent=2)}")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def _initialize() -> tuple[Config, Logger, Dictionary]:
    load_environment()
    config = ConfigLoader.load_config_files()
    logger = load_logger(config=config)
    parameters = Dictionary({
        "base_path": ROOT_DIR,
        "api_key": os.getenv("API_KEY", None),
        "mail": {
            "user_address": os.getenv("EMAIL_USERADDRESS", None),
            "user_name": os.getenv("EMAIL_USERNAME", None),
            "password": os.getenv("EMAIL_PASSWORD", None),
        },
        "app_version": importlib.metadata.version('pitxu')
    })

    return config, logger, parameters

if __name__ == '__main__':
    run()