from __future__ import annotations

class Point:

    x: int = None
    y: int = None

    DEFAULT_MAX_X = 250
    DEFAULT_MAX_Y = 155

    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def equals_to(self, point):
        return True if self.x == point.x and self.y == point.y else False
    
    def is_greater_or_equal_than(self, point) -> bool:
        return True if self.x >= point.x and self.y >= point.y else False
    
    def to_image_point(self) -> tuple:
        return (self.x, self.y)
    
    def is_valid(self, display_size: Point = None) -> bool:
        min_x = 0
        min_y = 0
        max_x = display_size.x if display_size else self.DEFAULT_MAX_X
        max_y = display_size.y if display_size else self.DEFAULT_MAX_Y
        return True if self.x >= min_x and \
                        self.x <= max_x and \
                        self.y >= min_y and \
                        self.y <= max_y \
                    else False
    
    def __repr__(self):
        return "(" + str(self.x) + "," + str(self.y) + ")"
