from pyxavi.config import Config
from .point import Point

class OffsetRectangle:

    OUTER = "outer"
    INNER = "inner"

class Rectangle:

    point_1: Point = None
    point_2: Point = None

    def __init__(self, point_1: Point, point_2: Point):
        self.point_1 = point_1
        self.point_2 = point_2
    
    # def with_offset(self, offset: int, direction: OffsetRectangle = OffsetRectangle.INNER):
    #     # The horizontal
    #     if self.point_1.x < self.point_2.x:
    #         if direction == OffsetRectangle.INNER:
    #             point_a_x = self.point_1.x + offset
    #             point_b_x = self.point_2.x - offset
    #             if point_a_x > self.point_2.x:
    #                 raise RuntimeError("Rectangle too small for such an INNER offset")
    #         else:
    #             point_a_x = self.point_1.x - offset
    #             point_b_x = self.point_2.x + offset
    #             if point_a_x < 0:
    #                 raise RuntimeError("Rectangle too big for such an OUTER offset")
    #     elif self.point_1.x > self.point_2.x:
    #         if direction == OffsetRectangle.INNER:
    #             point_a_x = self.point_1.x - offset
    #             point_b_x = self.point_2.x + offset
    #             if point_a_x < self.point_2.x:
    #                 raise RuntimeError("Rectangle too small for such an INNER offset")
    #         else:
    #             point_a_x = self.point_1.x + offset
    #             point_b_x = self.point_2.x - offset
    #             if point_b_x < 0:
    #                 raise RuntimeError("Rectangle too big for such an OUTER offset")
    #     elif self.point_1.x == self.point_2.x and direction == OffsetRectangle.INNER:
    #         raise RuntimeError("The X are the same, impossible for an INNER")

    #     # The vertical
    #     if self.point_1.y < self.point_2.y:
    #         if direction == OffsetRectangle.INNER:
    #             point_a_y = self.point_1.y + offset
    #             point_b_y = self.point_2.y - offset
    #             if point_a_y > self.point_2.y:
    #                 raise RuntimeError("Rectangle too small for such an INNER offset")
    #         else:
    #             point_a_y = self.point_1.y - offset
    #             point_b_y = self.point_2.y + offset
    #             if point_a_y < 0:
    #                 raise RuntimeError("Rectangle too big for such an OUTER offset")
    #     elif self.point_1.y > self.point_2.y:
    #         if direction == OffsetRectangle.INNER:
    #             point_a_y = self.point_1.y - offset
    #             point_b_y = self.point_2.y + offset
    #             if point_a_y < self.point_2.y:
    #                 raise RuntimeError("Rectangle too small for such an INNER offset")
    #         else:
    #             point_a_y = self.point_1.y + offset
    #             point_b_y = self.point_2.y - offset
    #             if point_b_y < 0:
    #                 raise RuntimeError("Rectangle too big for such an OUTER offset")
    #     elif self.point_1.y == self.point_2.y and direction == OffsetRectangle.INNER:
    #         raise RuntimeError("The Y are the same, impossible for an INNER")

    #     return Rectangle(Point(point_a_x, point_a_y), Point(point_b_x, point_b_y))
    
    def to_image_rectangle(self) -> list[tuple]:
        return [self.point_1.to_image_point(), self.point_2.to_image_point()]
    
    def is_valid(self, config: Config) -> bool:
        return True if self.point_1.is_valid and \
                        self.point_2.is_valid and \
                        not self.point_1.equals_to(self.point_2) \
                    else False