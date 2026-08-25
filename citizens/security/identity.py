# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Current-user identity from AppAPI request headers."""

from typing import Annotated

from fastapi import Depends, HTTPException
from nc_py_api import NextcloudApp
from nc_py_api.ex_app import nc_app


def get_current_user_id(nc: Annotated[NextcloudApp, Depends(nc_app)]) -> str:
    user = nc.user
    if not user:
        raise HTTPException(status_code=401, detail="No authenticated Nextcloud user")
    return user


CurrentUser = Annotated[str, Depends(get_current_user_id)]
