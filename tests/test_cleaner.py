import pandas as pd

from src.data.cleaner import find_duplicate_mask, is_usable_text, normalize_text


def test_normalize_text_collapses_whitespace_and_newlines():
    assert normalize_text("hello\n\nworld   there") == "hello world there"
    assert normalize_text("  padded  ") == "padded"


def test_is_usable_text():
    assert is_usable_text("a real message")
    assert not is_usable_text("")
    assert not is_usable_text("   ")
    assert not is_usable_text(None)
    assert not is_usable_text(float("nan"))
    assert not is_usable_text("a", min_length=2)


def test_find_duplicate_mask_flags_repeats_only():
    df = pd.DataFrame(
        {
            "author_id": ["A", "A", "B", "A"],
            "created_at": ["t1", "t1", "t1", "t1"],
            "text": ["hello", "hello", "hello", "different"],
        }
    )
    mask = find_duplicate_mask(df)
    assert list(mask) == [False, True, False, False]
