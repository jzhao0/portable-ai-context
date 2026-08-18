class PortableAIContextError(Exception):
    """Base exception."""


class UnsupportedSourceError(PortableAIContextError):
    """No adapter can parse the supplied source."""


class ParseError(PortableAIContextError):
    """A supported source could not be parsed."""


class CompilerError(PortableAIContextError):
    """Migration compilation failed."""
