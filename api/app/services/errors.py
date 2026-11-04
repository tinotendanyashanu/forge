class DomainError(Exception):
    """Base for errors that map to a specific HTTP response."""

    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    status_code = 409


class InvalidAnswer(DomainError):
    status_code = 422


class Unprocessable(DomainError):
    status_code = 422


class Forbidden(DomainError):
    status_code = 403
