import pytest

from pentestagent.tools.executor import _FLAG_PATTERN


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Open port 80\nflag{hello_world}\nEnd", ["flag{hello_world}"]),
        ("CTF{test_123}", ["CTF{test_123}"]),
        ("no flag here", []),
        ("FLAG{A} and flag{B}", ["FLAG{A}", "flag{B}"]),
        ("flag{} empty braces", []),
    ],
)
def test_flag_pattern(text, expected):
    assert _FLAG_PATTERN.findall(text) == expected
