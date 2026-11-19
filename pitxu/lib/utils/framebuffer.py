#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Framebuffer helper that makes lots of simpifying assumptions

bits_per_pixel    assumed memory layout
16                rgb565
24                rgb
32                argb

https://github.com/robertmuth/Pytorinox/blob/master/framebuffer.py

"""

import os

from PIL import Image


def _read_and_convert_to_ints(filename):
    with open(filename, "r") as fp:
        content = fp.read()
        tokens = content.strip().split(",")
        return [int(t) for t in tokens if t]


def _converter_argb(image: Image):
    return bytes([x for r, g, b in image.getdata() for x in (255, r, g, b)])


def _converter_rgb565(image: Image):
    return bytes([x for r, g, b in image.getdata()
                  for x in ((g & 0x1c) << 3 | (b >> 3), r & 0xf8 | (g >> 3))])


def _converter_1_argb(image: Image):
    return bytes([x for p in image.getdata()
                  for x in (255, p, p, p)])


def _converter_1_rgb(image: Image):
    return bytes([x for p in image.getdata()
                  for x in (p, p, p)])


def _converter_1_rgb565(image: Image):
    return bytes([(255 if x else 0) for p in image.getdata()
                  for x in (p, p)])


def _converter_rgba_rgb565_numpy(image: Image):
    import numpy
    flat = numpy.frombuffer(image.tobytes(), dtype=numpy.uint32)
    # note,  this is assumes little endian byteorder and results in
    # the following packing of an integer:
    # bits 0-7: red, 8-15: green, 16-23: blue, 24-31: alpha
    flat = ((flat & 0xf8) << 8) | ((flat & 0xfc00) >> 5) | ((flat & 0xf80000) >> 19)
    return flat.astype(numpy.uint16).tobytes()


def _converter_no_change(image: Image):
    return image.tobytes()


def _converter_rgba_bgra(image: Image):
    # The channels are swapped by the packer of PIL, in the same pass that makes the bytes.
    return image.tobytes("raw", "BGRA")

# anything that does not use numpy is hopelessly slow
_CONVERTER = {
    ("RGBA", 16): _converter_rgba_rgb565_numpy,
    ("RGB", 16): _converter_rgb565,
    ("RGB", 24): _converter_no_change,
    ("RGB", 32): _converter_argb,
    ("RGBA", 32): _converter_no_change,
    # note numpy does not work well with mode="1" images as
    # image.tobytes() loses pixel color info
    ("1", 16): _converter_1_rgb565,
    ("1", 24): _converter_1_rgb,
    ("1", 32): _converter_1_argb,
}


class Framebuffer(object):

    def __init__(self, device_no: int):
        self.path = f"/dev/fb{device_no}"
        config_dir = f"/sys/class/graphics/fb{device_no}"
        self.size = tuple(_read_and_convert_to_ints(
            config_dir + "/virtual_size"))
        self.stride = _read_and_convert_to_ints(config_dir + "/stride")[0]
        self.bits_per_pixel = _read_and_convert_to_ints(
            config_dir + "/bits_per_pixel")[0]
        assert self.stride == self.bits_per_pixel // 8 * self.size[0]
        # The device is opened on the first frame and kept open: opening it for every frame is a waste.
        self._fd: int | None = None

    def __str__(self):
        args = (self.path, self.size, self.stride, self.bits_per_pixel)
        return "%s  size:%s  stride:%s  bits_per_pixel:%s" % args

    # Note: performance is terrible even for medium resolutions without numpy, see _CONVERTER.
    def show(self, image: Image, swap_red_blue: bool = False):
        """
        Writes the whole image to the device.

        Args:
            swap_red_blue: The image is RGBA but the device wants BGRA (32 bits per pixel). The swap is done while
                converting, so the caller does not need to make copies of the image to swap the channels.
        """
        if swap_red_blue and (image.mode, self.bits_per_pixel) == ("RGBA", 32):
            converter = _converter_rgba_bgra
        else:
            converter = _CONVERTER[(image.mode, self.bits_per_pixel)]
        assert image.size == self.size
        self._write(converter(image))

    def show_region(self, image: Image, box: tuple[int, int, int, int], swap_red_blue: bool = False):
        """
        Writes only a rectangle of the image to the device: box is (left, top, right, bottom), right and bottom excluded.
        The rows of the rectangle are written one by one at their place, so what is outside of it is not touched.
        Only for the format that the DSI screen has (RGBA image, 32 bits per pixel). With any other, it writes the whole image.
        """
        if (image.mode, self.bits_per_pixel) != ("RGBA", 32):
            self.show(image, swap_red_blue=swap_red_blue)
            return
        assert image.size == self.size

        left, top, right, bottom = box
        left, top = max(0, left), max(0, top)
        right, bottom = min(self.size[0], right), min(self.size[1], bottom)
        if right <= left or bottom <= top:
            return

        data = image.crop((left, top, right, bottom)).tobytes("raw", "BGRA" if swap_red_blue else "RGBA")
        bytes_per_pixel = self.bits_per_pixel // 8
        row_bytes = (right - left) * bytes_per_pixel
        if left == 0 and right == self.size[0]:
            # Full rows are contiguous in the device: one write.
            self._write(data, top * self.stride)
            return
        view = memoryview(data)
        for row in range(bottom - top):
            self._write(view[row * row_bytes:(row + 1) * row_bytes], (top + row) * self.stride + left * bytes_per_pixel)

    def _write(self, data: bytes, offset: int = 0):
        """ Writes the bytes at the offset of the device, over the connection that is kept open. """
        for attempt in range(2):
            try:
                if self._fd is None:
                    self._fd = os.open(self.path, os.O_WRONLY)
                view = memoryview(data)
                written = 0
                while written < len(view):
                    written += os.pwrite(self._fd, view[written:], offset + written)
                return
            except OSError:
                # The device may have been reset: one more try with a fresh connection, then it is a real error.
                self.close()
                if attempt == 1:
                    raise

    def close(self):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def on(self):
        pass

    def off(self):
        pass