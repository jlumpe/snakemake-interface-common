"""Test the PluginRegistry class."""

from pathlib import Path

import pytest

from snakemake_interface_common.plugin_registry import PluginRegistryBase
from snakemake_interface_common.plugin_registry.plugin import SettingsBase
from snakemake_interface_common.exceptions import InvalidPluginException
from .example_plugin import ExamplePlugin, ExamplePluginRegistry


# Directory containing importable example plugins
PLUGIN_DIR = Path(__file__).parent / "plugins"


@pytest.fixture(autouse=True)
def _reset_example_registry_singleton():
    """Reset the singleton instance of ExamplePluginRegistry before/after all tests."""
    ExamplePluginRegistry._instance = None
    yield
    ExamplePluginRegistry._instance = None


def test_basic():
    """Test basic attributes and behavior."""

    registry = ExamplePluginRegistry()
    assert registry.get_plugin_type() == "example"

    # Check singleton
    assert ExamplePluginRegistry() is registry

    # Check plugin not found
    assert not registry.is_installed("foo")
    with pytest.raises(InvalidPluginException):
        registry.get_plugin("foo")


def test_abc():
    """
    Test that the metaclass preserves ABCMeta behavior of raising an exception on instantiation if
    the class does not implement all abstract methods.
    """

    class AbstractRegistry(PluginRegistryBase):
        pass

    with pytest.raises(
        TypeError, match="Can't instantiate abstract class AbstractRegistry"
    ):
        AbstractRegistry()


def test_discovery(monkeypatch: pytest.MonkeyPatch):
    """Test plugin discovery and initialization."""

    # Add directory of valid plugins to import path so they can be discovered by module name
    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "valid"))

    registry = ExamplePluginRegistry()

    expected_plugins = {"valid-1", "valid-2"}
    plugins: dict[str, ExamplePlugin] = {}

    # Check valid plugins
    assert set(registry.get_registered_plugins()) == expected_plugins

    for name in expected_plugins:
        assert registry.is_installed(name)
        plugins[name] = registry.get_plugin(name)
        assert isinstance(plugins[name], ExamplePlugin)
        assert plugins[name].name == name
        assert plugins[name].file.is_relative_to(PLUGIN_DIR)

    # Valid plugin 1
    assert plugins["valid-1"].string_attr == "valid 1"
    assert plugins["valid-1"].settings_cls is not None
    assert issubclass(plugins["valid-1"].settings_cls, SettingsBase)

    # Valid plugin 2
    assert plugins["valid-2"].string_attr == "valid 2"
    assert plugins["valid-2"].settings_cls is None


def test_missing_attr(monkeypatch: pytest.MonkeyPatch):
    """Test plugin with missing required attribute."""

    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "missing-attr"))

    with pytest.raises(InvalidPluginException) as exc_info:
        ExamplePluginRegistry()

    errmsg = str(exc_info.value)
    assert "missing-attr" in errmsg
    assert "plugin does not define example_string" in errmsg


def test_invalid_object(monkeypatch: pytest.MonkeyPatch):
    """Test plugin with invalid object attribute."""

    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "invalid-object"))

    with pytest.raises(InvalidPluginException) as exc_info:
        ExamplePluginRegistry()

    errmsg = str(exc_info.value)
    assert "invalid-object" in errmsg
    assert "example_string must be of type str" in errmsg


def test_invalid_class(monkeypatch: pytest.MonkeyPatch):
    """Test plugin with invalid class attribute."""

    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "invalid-class"))

    with pytest.raises(InvalidPluginException) as exc_info:
        ExamplePluginRegistry()

    errmsg = str(exc_info.value)
    assert "invalid-class" in errmsg
    assert "ExampleSettings must be a subclass of" in errmsg
    assert "SettingsBase" in errmsg
