__author__ = "Johannes Köster"
__copyright__ = "Copyright 2022, Johannes Köster, Vanessa Sochat"
__email__ = "johannes.koester@uni-due.de"
__license__ = "MIT"

from abc import ABC, abstractmethod
import re
import types
import pkgutil
import importlib
from typing import Dict, List, Mapping, TYPE_CHECKING, TypeVar, Generic

from snakemake_interface_common.exceptions import InvalidPluginException
from snakemake_interface_common.plugin_registry.plugin import PluginBase
from snakemake_interface_common.plugin_registry.attribute_types import AttributeType

if TYPE_CHECKING:
    from argparse import ArgumentParser

TPlugin = TypeVar("TPlugin", bound=PluginBase, covariant=True)


class PluginRegistryBase(ABC, Generic[TPlugin]):
    """Base class to discover and record all available plugins of a given type.

    This class is a singleton, all calls to the constructor will return the same instance.
    ``__init__()`` should not take any arguments.

    Derived class names are expected to end with ``PluginRegistry``, where the prefix is the type of
    plugin (e.g. ``ExecutorPluginRegistry``). This is returned by :meth:`get_plugin_type()`.

    Package discovery works by searching through all importable top-level modules in ``sys.path``
    and selecting those where the full name matches ``"{self.module_prefix}_{plugin_name}"``, where
    :attr:`module_prefix` should be ``"snakemake_{plugin_type}_plugin_"``. The plugin will be
    registered under the name ``plugin_name``, but with underscores replaced with dashes. Note that
    this will not detect packages installed in editable mode ``(pip install -e .)``.

    Example: a package named ``snakemake_executor_plugin_my_executor`` will be discovered by the
    ``executor`` registry (with ``module_prefix = "snakemake_executor_plugin_"``) and registered
    under the name ``"my-executor"``. The corresponding Pip/distribution package should be named
    ``snakemake-executor-plugin-my-executor``, although this is not enforced.
    """

    _instance = None
    plugins: Dict[str, TPlugin]

    def __new__(cls):
        if cls._instance is None:
            instance = super().__new__(cls)
            instance.collect_plugins()
            cls._instance = instance
        # The following can cause issues with the type checker, ignore the line to make it assume
        # standard behavior of returning an instance of cls (which should be the case).
        return cls._instance  # type: ignore

    ######## Abstract methods ########

    @property
    @abstractmethod
    def module_prefix(self) -> str:
        """Prefix used to identify plugins by importable module name."""

    @abstractmethod
    def load_plugin(self, name: str, module: types.ModuleType) -> TPlugin:
        """Instantiate the plugin object given its name and imported module."""

    @abstractmethod
    def expected_attributes(self) -> Mapping[str, AttributeType]:
        """Get expected attributes of imported plugin module."""

    ######## Other methods ########

    def get_registered_plugins(self) -> List[str]:
        """Return a list of registered plugin names."""
        return [name for name in self.plugins.keys()]

    def is_installed(self, plugin_name: str) -> bool:
        """Return True if the plugin is registered."""
        return plugin_name in self.plugins

    def get_plugin(self, plugin_name: str) -> TPlugin:
        """Get a registered plugin by name.

        Raises
        ------
        InvalidPluginException
            If the plugin is not registered.
        """
        try:
            return self.plugins[plugin_name]
        except KeyError:
            pkgname = self.get_plugin_package_name(plugin_name)
            raise InvalidPluginException(
                plugin_name,
                f"The package {pkgname} is not installed.",
            )

    def get_plugin_package_name(self, plugin_name: str) -> str:
        """Get the package name of a plugin by name.

        This is the pip-installable package name, not the name used to import the plugin module.
        """
        return f"{self.module_prefix.replace('_', '-')}{plugin_name}"

    def register_cli_args(self, argparser: "ArgumentParser") -> None:
        """Add arguments derived from all registered plugins to given argparser."""
        plugin_type = self.get_plugin_type()
        for _, plugin in self.plugins.items():
            plugin.register_cli_args(argparser, plugin_type)

    def get_plugin_type(self) -> str:
        """Get a string describing the type of plugin tracked by the registry.

        This is derived from the class name.
        """
        m = re.match(r"(?P<type>.+)PluginRegistry", self.__class__.__name__)
        if m is not None:
            return m.group("type").lower()
        raise ValueError(
            "Unable to infer plugin type name from registry class "
            f"name: {self.__class__.__name__}. The name is expected to follow the "
            "pattern <type>PluginRegistry, e.g. ExecutorPluginRegistry."
        )

    def collect_plugins(self) -> None:
        """Collect plugins, import their modules, and call :meth:`register_plugin` for each."""
        self.plugins = dict()

        for moduleinfo in pkgutil.iter_modules():
            if not moduleinfo.ispkg or not moduleinfo.name.startswith(
                self.module_prefix
            ):
                continue

            name = moduleinfo.name.removeprefix(self.module_prefix).replace("_", "-")
            module = importlib.import_module(moduleinfo.name)
            self.register_plugin(name, module)

    def register_plugin(self, name: str, module: types.ModuleType) -> None:
        """Validate and register a plugin.

        Does nothing if the plugin is already registered.

        Parameters
        ----------
        name
            The name to register the plugin under. If derived from the module name, it should have
            :attr:`module_prefix` removed.
        module
            The plugin's imported module.

        Raises
        ------
        InvalidPluginException
            If validation fails.
        """
        name = name.removeprefix(self.module_prefix).replace("_", "-")
        if name in self.plugins:
            return

        self.validate_plugin(name, module)
        self.plugins[name] = self.load_plugin(name, module)

    def is_valid_plugin_package_name(self, name: str) -> bool:
        return True

    def validate_plugin(self, name: str, module: types.ModuleType) -> None:
        """Validate a plugin module for attributes and naming.

        Parameters
        ----------
        name
            The name the plugin is to be registered under.
        module
            The plugin's imported module.

        Raises
        ------
        InvalidPluginException
            If any module attributes have an incorrect type or a required attribute is missing.
        """

        expected_attributes = self.expected_attributes()
        for attr, attr_type in expected_attributes.items():
            # check if attr is missing and fail if it is not optional
            if not hasattr(module, attr):
                if attr_type.is_optional:
                    continue
                raise InvalidPluginException(name, f"plugin does not define {attr}.")

            attr_value = getattr(module, attr)
            if attr_type.is_class:
                # check for class type
                if not isinstance(attr_value, type) or not issubclass(
                    attr_value, attr_type.cls
                ):
                    raise InvalidPluginException(
                        name,
                        f"{attr} must be a subclass of "
                        f"{attr_type.cls.__module__}.{attr_type.cls.__name__}.",
                    )
            else:
                # check for instance type
                if not isinstance(attr_value, attr_type.cls):
                    raise InvalidPluginException(
                        name, f"{attr} must be of type {attr_type.cls.__name__}."
                    )
