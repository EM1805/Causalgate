"""Shared holdout for lexical measurement cues on both A/B branches.

Unlike the original regression examples, these cases were added after the
alternative implementations were written. This is exploratory, not blinded.
"""
from causalgate.scientific.falsification_policy import _prediction_is_measurable


def test_holdout_unrelated_containing_words_stay_negative():
    negatives = (
        "Beforehand we discussed the general approach.",
        "A windowless model is described here.",
        "The community discussed the theory.",
        "The afterglow is beautiful.",
        "Unitary transformations are considered.",
        "Observationless speculation remains possible.",
    )
    for text in negatives:
        assert not _prediction_is_measurable(text), text


def test_holdout_explicit_directional_and_numeric_cues_stay_positive():
    positives = (
        "Rate falls at the next lag.",
        "Output decreases within five days.",
        "Outcome increased before treatment.",
        "The outcome has a measured value.",
        "The error is 17% higher.",
        "The response rises as load increases.",
    )
    for text in positives:
        assert _prediction_is_measurable(text), text
