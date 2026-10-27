import pytest

from src.classifier import needs_current_info


@pytest.mark.parametrize(
    "text",
    [
        "who is tamilnadu cm?",
        "tell me some good latest tamil films",
        "what's the weather in Chennai today?",
        "what is the price of bitcoin now",
        "who is the prime minister of India",
        "which tamil movies released this year?",
        "any news about the election",
        "what happened in 2026",
    ],
)
def test_current_questions_need_web_info(text):
    assert needs_current_info(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "what is the capital of France?",
        "write me a short love poem",
        "hi, how are you",
        "who was Albert Einstein?",
        "the table is 10 cm wide, how do I hang it?",
        "what's today's date?",
        "what time is it?",
        "",
    ],
)
def test_other_questions_skip_web_info(text):
    assert needs_current_info(text) is False


def test_short_follow_up_inherits_previous_routing():
    assert needs_current_info("and before him?", previous="who is tamilnadu cm?") is True
    assert needs_current_info("and before him?", previous="who was Albert Einstein?") is False
    assert needs_current_info("thanks", previous="who is tamilnadu cm?") is False
