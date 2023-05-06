"""Test the meaning of life."""
from sample.meaning import meaning_of_life


def test_meaning():
    assert meaning_of_life() == 42
