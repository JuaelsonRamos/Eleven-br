from app.domain.policies import DomainError

ACCESS_MINUTES = 15
SESSION_DAYS = 30
CODE_MINUTES = 10
RESEND_SECONDS = 60
MAX_CODE_ATTEMPTS = 5


class Unauthorized(DomainError):
    pass


class InvalidVerification(DomainError):
    pass


class RateLimited(DomainError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Muitas tentativas. Aguarde e tente novamente.")
        self.retry_after = max(1, retry_after)


class DeliveryUnavailable(DomainError):
    pass
