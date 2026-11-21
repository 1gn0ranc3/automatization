import pytest


@pytest.mark.filterwarnings("error::pytest.PytestRemovedIn10Warning")
def test_base_url_fixture_avoids_deprecated_plugin_method(base_url, pytestconfig):
    expected = pytestconfig.getoption("--base-url") or pytestconfig.getini("base_url") or None
    assert base_url == expected
