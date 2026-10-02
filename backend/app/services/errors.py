class ServiceError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class LostRun(Exception):
    """A superseded worker must stop without changing the current attempt."""
