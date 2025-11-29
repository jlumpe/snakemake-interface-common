"""Test the PluginRegistry class."""

from pathlib import Path

import pytest

from snakemake_interface_common.plugin_registry import PluginRegistryBase
from snakemake_interface_common.plugin_registry.plugin import SettingsBase
from snakemake_interface_common.exceptions import (
    InvalidPluginException,
    InvalidPluginWarning,
)
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
    with pytest.raises(
        InvalidPluginException,
        match="The package snakemake-example-plugin-foo is not installed",
    ):
        registry.get_plugin("foo")


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


def check_valid_example_plugins(registry: ExamplePluginRegistry):
    """Check the two valid plugins are present in the example registry.

    This is just to check that an error in loading/registering one plugin doesn't prevent the others
    from being registered. Only checks basic attributes.
    """
    valid1 = registry.get_plugin("valid-1")
    assert isinstance(valid1, ExamplePlugin)
    assert valid1.string_attr == "valid 1"
    valid2 = registry.get_plugin("valid-2")
    assert isinstance(valid2, ExamplePlugin)
    assert valid2.string_attr == "valid 2"


def expect_plugin_error(
    registry_cls: type[PluginRegistryBase], plugin_name: str
) -> InvalidPluginException:
    """Expect the given plugin to cause an error during registration.

    First argument is a registry class which has not been initialized yet.

    Checks that an error is stored in the registry for the plugin, that the error is re-raised
    during plugin lookup, and that a warning is emitted during registration that matches the error.

    Returns the error instance.
    """

    # Initialize registry and record warnings
    with pytest.warns(InvalidPluginWarning) as warnings:
        registry = registry_cls()

    # Check that the error is re-emitted during plugin lookup
    with pytest.raises(InvalidPluginException) as exc_info:
        registry.get_plugin(plugin_name)

    plugin_err = exc_info.value
    assert plugin_err.plugin_name == plugin_name
    assert plugin_err.plugin_type == registry.get_plugin_type()

    # Check one of the warnings matches the error
    for warning in warnings:
        if str(warning.message) == str(plugin_err):
            break
    else:
        pytest.fail(f"No matching warning emitted for plugin error")

    return plugin_err


def test_missing_attr(monkeypatch: pytest.MonkeyPatch):
    """Test plugin with missing required attribute."""

    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "valid"))
    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "missing-attr"))

    err = expect_plugin_error(ExamplePluginRegistry, "missing-attr")
    assert "plugin does not define example_string" in err.message

    check_valid_example_plugins(ExamplePluginRegistry())


def test_invalid_object(monkeypatch: pytest.MonkeyPatch):
    """Test plugin with invalid object attribute."""

    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "valid"))
    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "invalid-object"))

    err = expect_plugin_error(ExamplePluginRegistry, "invalid-object")
    assert "example_string must be of type str" in err.message

    check_valid_example_plugins(ExamplePluginRegistry())


def test_invalid_class(monkeypatch: pytest.MonkeyPatch):
    """Test plugin with invalid class attribute."""

    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "valid"))
    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "invalid-class"))

    err = expect_plugin_error(ExamplePluginRegistry, "invalid-class")
    assert "ExampleSettings must be a subclass of" in err.message
    assert "SettingsBase" in err.message

    check_valid_example_plugins(ExamplePluginRegistry())


def test_import_error(monkeypatch: pytest.MonkeyPatch):
    """Test plugin with import error."""

    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "valid"))
    monkeypatch.syspath_prepend(str(PLUGIN_DIR / "import-error"))

    err = expect_plugin_error(ExamplePluginRegistry, "import-error")
    assert "RuntimeError" in err.message
    assert "Test error" in err.message

    check_valid_example_plugins(ExamplePluginRegistry())
