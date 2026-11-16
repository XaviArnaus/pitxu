from __future__ import annotations

class Size:

    width: int = None
    height: int = None

    DEFAULT_MAX_WIDTH = 250
    DEFAULT_MAX_HEIGHT = 155

    def __init__(self, width, height):
        self.width = width
        self.height = height
    
    def equals_to(self, size):
        return True if self.width == size.width and self.height == size.height else False
    
    def is_greater_or_equal_than(self, size) -> bool:
        return True if self.width >= size.width and self.height >= size.height else False
    
    def to_image_point(self) -> tuple:
        return (self.width, self.height)
    
    def is_valid(self, display_size: Size = None) -> bool:
        min_width = 0
        min_height = 0
        max_width = display_size.width if display_size else self.DEFAULT_MAX_WIDTH
        max_height = display_size.height if display_size else self.DEFAULT_MAX_HEIGHT
        return True if self.width >= min_width and \
                        self.width <= max_width and \
                        self.height >= min_height and \
                        self.height <= max_height \
                    else False
    
    def __repr__(self):
        return "(" + str(self.width) + "," + str(self.height) + ")"
