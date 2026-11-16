from .point import Point

class Line:

    point_1: Point = None
    point_2: Point = None

    def __init__(self, point_1: Point, point_2: Point):
        self.point_1 = point_1
        self.point_2 = point_2

    def fromTuple(positions: tuple):
        return Line(Point(positions[0], positions[1]), Point(positions[2], positions[3]))
    
    def to_image_line(self) -> list[tuple]:
        return [self.point_1.to_image_point(), self.point_2.to_image_point()]
    
    def is_valid(self, display_size: Point = None) -> bool:
        return True if self.point_1.is_valid(display_size) and \
                        self.point_2.is_valid(display_size) and \
                        not self.point_1.equals_to(self.point_2) \
                    else False