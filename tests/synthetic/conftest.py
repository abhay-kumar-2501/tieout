import pytest

from synthetic.generate import Dataset, generate


@pytest.fixture(scope="session")
def small() -> Dataset:
    """A proportionate 15% dataset: fast enough for every test run."""
    return generate(7, scale=0.15)


@pytest.fixture(scope="session")
def full() -> Dataset:
    """The held-out demo seed at full size (slow tests only)."""
    return generate(4)
