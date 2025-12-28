from pyxavi.config import Config
from .point import Point


class Matrix:

    points: list[Point] = None
    _size: Point = None

    DEFAULT_WIDTH: int = 8
    DEFAULT_HEIGHT: int = 8

    def __init__(self, size: Point = None, points: list[Point] | list[list[int]] = None):
        if size is None:
            size = Point(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self._size = size

        if points is not None:
            if isinstance(points[0], Point):
                self.points = points
            elif isinstance(points[0], list):
                self.points = Matrix.from_lists(points)
            else:
                raise ValueError("The 'points' parameter can only be a list of Point objects or a list of lists of integers, but was [" + type(points) + "]")

    
    def to_list_of_image_points(self) -> list[tuple]:
        points = []
        for point in self.points:
            points.append(point.to_image_point())
        return points

    def get_points(self) -> list[Point]:
        return self.points
    
    def is_valid(self, display_size: Point = None) -> bool:

        are_points_valid = []
        # column_index = 0
        # row_index = 0
        max_column_index = 0
        max_row_index = 0
        for point in self.points:
            are_points_valid.append(point.is_valid(display_size))
            max_column_index = max(point.x, max_column_index)
            max_row_index = max(point.x, max_row_index)
        
        return all(are_points_valid)

    @staticmethod
    def from_lists(points: list[list[int]]):
        column_index = 0
        row_index = 0
        columns_per_row = []
        rows_per_column = []
        result: list[Point] = []
        for row in points:
            
            for column in row:
                result.append(Point(column_index, row_index))
                rows_per_column[column] = column_index
                column_index += column_index
            
            columns_per_row[row_index] = column_index
            row_index += row_index
        
        # Simple validation, all columns & rows should be the same length
        consistent_row_length = set(columns_per_row)
        if len(consistent_row_length) != 1:
            raise ValueError("The received list of lists of integers does not have consistent row lengths")
        consistent_column_length = set(rows_per_column)
        if len(consistent_column_length) != 1:
            raise ValueError("The received list of lists of integers does not have consistent column lengths")

        return Matrix(size=Point(consistent_row_length, consistent_column_length), points=result)