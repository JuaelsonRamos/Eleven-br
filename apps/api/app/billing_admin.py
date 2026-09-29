"""Trusted operator CLI, no public route. Never grants privileges to a team president."""

import argparse
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.billing import administrative_grant
from app.application.billing_reconciliation import reconcile
from app.infrastructure.config import get_settings
from app.infrastructure.database import get_engine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audited administrative Pro grant or billing reconciliation by internal UUID"
    )
    parser.add_argument("team_id", type=UUID)
    parser.add_argument("action", choices=["grant", "revoke", "reconcile"])
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--expires-at", type=datetime.fromisoformat)
    args = parser.parse_args()
    if args.expires_at and args.expires_at.tzinfo is None:
        parser.error("--expires-at must include a timezone")
    if args.expires_at and args.action == "reconcile":
        parser.error("--expires-at is not valid with reconcile")
    with Session(get_engine()) as session:
        if args.action == "reconcile":
            report = reconcile(
                session,
                args.team_id,
                operator=args.operator,
                reason=args.reason,
                settings=get_settings(),
            )
            print("\n".join(report))
            return
        administrative_grant(
            session,
            args.team_id,
            enabled=args.action == "grant",
            operator=args.operator,
            reason=args.reason,
            expires_at=args.expires_at,
            settings=get_settings(),
        )
    print("Administrative access updated and audited.")


if __name__ == "__main__":
    main()
