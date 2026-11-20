"""Regression checks: unrelated substrings must not satisfy measurement gates."""

import pytest

from causalgate.scientific.falsification_policy import _prediction_is_measurable


@pytest.mark.parametrize("prediction", [
    "Community practices affect Y.",
    "An opportunity influences the outcome.",
    "The data suggests a connection between X and Y.",
])
def test_incidental_substrings_are_not_measurable(prediction):
    assert not _prediction_is_measurable(prediction)


@pytest.mark.parametrize("prediction", [
    "Y will increase after X.",
    "Y is 12% higher when X is present.",
    "Y is measured within 7 days.",
    "The count changes by 3 units.",
])
def test_explicit_measurement_signals_still_accepted(prediction):
    assert _prediction_is_measurable(prediction)
