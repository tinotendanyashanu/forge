class PaymentError(Exception):
    """Base class for payment domain errors."""


class IdempotencyConflict(PaymentError):
    """The idempotency key was already used for a different account or amount."""


class AccountNotFound(PaymentError):
    """The account does not exist."""
