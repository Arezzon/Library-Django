"""Explicit numerical ratings are independent of likes/favorites."""

MIN_RATING = 1
MAX_RATING = 5


def validate_rating(value):
    if type(value) is not int or not MIN_RATING <= value <= MAX_RATING:
        raise ValueError("Rating must be an integer from 1 to 5.")
    return value


def rating_weight(value):
    """1/2: -12/-6; 3: neutral; 4/5: +6/+12. Explicit opinion wins per book."""
    return 6 * (validate_rating(value) - 3)
