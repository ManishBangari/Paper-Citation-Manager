import pytest
from app.calculations import add

@pytest.mark.parametrize("num1, num2, expected", [
    (3, 2, 5),
    (0, 0, 0),
    (-1, 1, 0),
    (100, 200, 300),
])
def test_add(num1, num2, expected):
    print("testing add function")
    sum = add(num1, num2)
    assert sum == expected, "add function is broken"

    

