"""A user cancellation is a resumable pause, not a bad page or model error."""


class OperationCancelled(RuntimeError):
    pass
