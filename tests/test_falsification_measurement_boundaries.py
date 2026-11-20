"""Regression checks: accidental substrings are not measurement cues.

Plain test functions are intentional: the repository's custom test runner imports
modules using a lightweight pytest shim, so decorators must not be required.
"""

from causalgate.scientific.falsification_policy import _prediction_is_measurable


def test_incidental_substrings_are_not_measurable():
    for prediction in (
        "Community practices affect Y.",
        "An opportunity influences the outcome.",
        "The data suggests a connection between X and Y.",
    ):
        assert not _prediction_is_measurable(prediction), prediction


def test_explicit_measurement_signals_still_accepted():
    for prediction in (
        "Y will increase after X.",
        "Y is 12% higher when X is present.",
        "Y is measured within 7 days.",
        "The count changes by 3 units.",
    ):
        assert _prediction_is_measurable(prediction), prediction
