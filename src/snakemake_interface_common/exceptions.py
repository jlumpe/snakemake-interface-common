__author__ = "Johannes Köster"
__copyright__ = "Copyright 2023, Johannes Köster"
__email__ = "johannes.koester@uni-due.de"
__license__ = "MIT"

import sys
import textwrap
from typing import Optional, Any
from dataclasses import dataclass
import traceback

from snakemake_interface_common.rules import RuleInterface


class ApiError(Exception):
    pass


class WorkflowError(Exception):
    lineno: Optional[int]
    snakefile: Optional[str]
    rule: Optional[RuleInterface]

    def format_arg(self, arg: object) -> str:
        if isinstance(arg, str):
            return arg
        elif isinstance(arg, WorkflowError):
            spec = self._get_spec(arg)

            if spec:
                spec = f" ({spec})"

            return "{}{}:\n{}".format(
                arg.__class__.__name__, spec, textwrap.indent(str(arg), "    ")
            )
        elif sys.version_info >= (3, 11) and isinstance(
            arg,
            ExceptionGroup,  # noqa: F821
        ):
            return "\n".join(self.format_arg(exc) for exc in arg.exceptions)
        else:
            return f"{arg.__class__.__name__}: {arg}"

    def __init__(
        self,
        *args: Any,
        lineno: Optional[int] = None,
        snakefile: Optional[str] = None,
        rule: Optional[RuleInterface] = None,
    ):
        if rule is not None:
            self.lineno = rule.lineno
            self.snakefile = rule.snakefile
        else:
            self.lineno = lineno
            self.snakefile = snakefile
        self.rule = rule

        # if there is an initial message, append the spec
        if args and isinstance(args[0], str):
            spec = self._get_spec(self)
            if spec:
                args = tuple([f"{args[0]} ({spec})"] + list(args[1:]))

        super().__init__("\n".join(self.format_arg(arg) for arg in args))

    @classmethod
    def _get_spec(cls, exc: "WorkflowError") -> str:
        spec = ""
        if exc.rule is not None:
            spec += f"rule {exc.rule.name}"
        if exc.snakefile is not None:
            if spec:
                spec += ", "
            spec += f"line {exc.lineno}, {exc.snakefile}"
        return spec


@dataclass(repr=False)
class InvalidPluginException(ApiError):
    """Raised when an error occurs during plugin loading or registration."""

    plugin_name: str
    message: str
    # Just for clearer error message (make this optional for backwards compatibility, and because
    # some contexts don't have easy access to the registry instance)
    plugin_type: str | None = None

    def __post_init__(self) -> None:
        ApiError.__init__(self, str(self))

    def __str__(self) -> str:
        # Support assigning plugin_type after construction
        typestr = "plugin" if self.plugin_type is None else f"{self.plugin_type} plugin"
        return f"Error loading Snakemake {typestr} {self.plugin_name!r}: {self.message}"

    @classmethod
    def wrap(
        cls,
        plugin_name: str,
        exc: Exception,
        message: str | None = None,
        plugin_type: str | None = None,
    ) -> "InvalidPluginException":
        """Initialize from another exception.

        This is mostly intended to wrap unexpected exceptions during plugin import. It includes
        the location of the error (file and line number) because the traceback and cause/context
        information is cleared in exception instances stored in the registry.
        """
        if message is None:
            message = ""
        else:
            message += " "
        # Add location of wrapped exception if available
        tb = traceback.extract_tb(exc.__traceback__)
        if tb:
            frame = tb[-1]
            message += f"(in {frame.filename}:{frame.lineno})"
        # Wrapped exception type and message
        message += f": {type(exc).__name__}: {exc}"
        plugin_exc = cls(plugin_name, message, plugin_type=plugin_type)
        # This gets cleared when caught in the registry's collect_plugins() method, but it could be
        # useful information during testing or in other contexts.
        plugin_exc.__cause__ = exc
        return plugin_exc


class InvalidPluginWarning(Warning):
    """Emitted when an error occurs during plugin loading or registration."""
