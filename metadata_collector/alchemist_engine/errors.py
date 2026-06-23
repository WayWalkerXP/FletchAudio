"""Custom exceptions raised by the audiobook converter."""

class ConfigError(Exception):
    """Raised when the INI configuration is missing or invalid."""

class LockError(Exception):
    """Raised when another converter instance already owns the lock file."""

class ProbeError(Exception):
    """Raised when ffprobe cannot read or describe a media file."""

class ExternalToolError(Exception):
    """Raised when an external media tool cannot be launched."""

class DiskSpaceError(Exception):
    """Raised when a file transaction detects disk-space exhaustion."""

class ForcedTermination(Exception):
    """Raised when the user requests immediate termination after a graceful quit."""
