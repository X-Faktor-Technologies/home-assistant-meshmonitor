"""Exceptions raised by the MeshMonitor client."""


class MeshMonitorError(Exception):
    """Base client error."""


class MeshMonitorConnectionError(MeshMonitorError):
    """The MeshMonitor server could not be reached."""


class MeshMonitorAuthenticationError(MeshMonitorError):
    """Authentication failed or a token was not supplied."""


class MeshMonitorPermissionError(MeshMonitorError):
    """The token lacks access to the requested source or resource."""


class MeshMonitorNotFoundError(MeshMonitorError):
    """The requested resource does not exist."""


class MeshMonitorResponseError(MeshMonitorError):
    """The server returned an invalid or unexpected response."""


class MeshMonitorServerError(MeshMonitorError):
    """The server returned a 5xx response."""


class MeshMonitorRateLimitError(MeshMonitorError):
    """MeshMonitor rejected a request because its rate limit was reached."""


class MeshMonitorTransmitDisabledError(MeshMonitorError):
    """Transmit is disabled for the selected MeshMonitor source."""
