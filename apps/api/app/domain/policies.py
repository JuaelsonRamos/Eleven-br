"""Business vocabulary and centralized team entitlements; no framework dependencies."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Plan(StrEnum):
    FREE = "free"
    PRO = "pro"


class Role(StrEnum):
    MEMBER = "member"
    ADMIN = "admin"


class Permission(StrEnum):
    MANAGE_TEAM = "manage_team"
    MANAGE_MEMBERS = "manage_members"


@dataclass(frozen=True)
class Entitlements:
    active_players: int
    administrators: int
    granular_permissions: bool


ENTITLEMENTS = MappingProxyType(
    {
        Plan.FREE: Entitlements(24, 0, False),
        Plan.PRO: Entitlements(100, 5, True),
    }
)


class DomainError(Exception):
    pass


class Forbidden(DomainError):
    pass


class Conflict(DomainError):
    pass


class NotFound(DomainError):
    pass


def allows(
    plan: Plan, *, is_president: bool, role: Role, grants: set[str], permission: Permission
) -> bool:
    if is_president:
        return True
    return (
        ENTITLEMENTS[plan].granular_permissions
        and role == Role.ADMIN
        and permission.value in grants
    )
