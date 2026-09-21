from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.infrastructure.config import get_settings
from app.infrastructure.database import get_session
from app.infrastructure.models import User
from app.infrastructure.security import decode_access_token

SessionDep = Annotated[Session, Depends(get_session)]
bearer = HTTPBearer(auto_error=False)


def current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    unauthorized = HTTPException(
        status_code=401, detail="Autenticação necessária", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials, get_settings())
    except jwt.InvalidTokenError:
        raise unauthorized from None
    user = session.get(User, user_id)
    if user is None or user.status != "active":
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]
