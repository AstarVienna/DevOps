"""What is the meaning of life?"""
import numpy


def meaning_of_life():
    """Get the meaning of life."""
    roads_to_go_down = 6 * 9
    return int(numpy.base_repr(roads_to_go_down, 13))
