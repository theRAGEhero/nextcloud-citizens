"""Admin API. Access control is enforced by the AppAPI proxy route level
(`^api/v1/admin/.*` is registered as ADMIN): non-admin requests never reach
this router in production. Tests exercise these endpoints directly and that
assumption is documented in docs/architecture.md.
"""

import base64
import binascii
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from nc_py_api import NextcloudApp
from nc_py_api.ex_app import nc_app
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from citizens.db.session import get_db
from citizens.security.identity import CurrentUser
from citizens.services import branding, provider_config
from citizens.services.analysis import ROUND_SYSTEM, TABLE_SYSTEM
from citizens.services.audit import record_audit_event

router = APIRouter(prefix="/admin")

DB = Annotated[Session, Depends(get_db)]


def get_config_store(nc: Annotated[NextcloudApp, Depends(nc_app)]) -> provider_config.ConfigStore:
    return provider_config.AppConfigStore(nc)


Store = Annotated[provider_config.ConfigStore, Depends(get_config_store)]


@router.get("/ping")
def ping(user: CurrentUser):
    return {"ok": True, "user": user}


@router.get("/providers")
def get_providers(store: Store, user: CurrentUser):
    summary = provider_config.providers_summary(store)
    # shown read-only in Settings so admins see what their extra
    # instructions are appended to
    summary["analysis"]["default_prompts"] = {
        "table": TABLE_SYSTEM,
        "round": ROUND_SYSTEM,
    }
    summary["logo_set"] = branding.logo_path() is not None
    return summary


class ProvidersUpdate(BaseModel):
    stt_provider: Literal["mistral", "deepgram"] | None = None
    stt_live_enabled: bool | None = None
    stt_batch_enabled: bool | None = None
    mistral_api_key: str | None = Field(default=None, max_length=500)
    mistral_live_model: str | None = Field(default=None, max_length=100)
    mistral_batch_model: str | None = Field(default=None, max_length=100)
    deepgram_api_key: str | None = Field(default=None, max_length=500)
    deepgram_live_model: str | None = Field(default=None, max_length=100)
    deepgram_batch_model: str | None = Field(default=None, max_length=100)
    analysis_base_url: str | None = Field(default=None, max_length=500)
    analysis_model: str | None = Field(default=None, max_length=200)
    analysis_api_key: str | None = Field(default=None, max_length=500)
    analysis_enabled: bool | None = None
    analysis_extra_instructions: str | None = Field(default=None, max_length=4000)


@router.put("/providers")
def update_providers(data: ProvidersUpdate, store: Store, user: CurrentUser, session: DB):
    values: dict[str, str] = {}
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if isinstance(value, bool):
            values[field] = "1" if value else "0"
        else:
            values[field] = value.strip() if field in provider_config.KEY_FIELDS else value
    changed = provider_config.set_settings(store, values)
    provider_config.invalidate_snapshot()
    record_audit_event(
        session, "providers_updated", actor=user, data={"fields": changed}
    )
    return provider_config.providers_summary(store)


class TestIn(BaseModel):
    target: Literal["mistral", "deepgram", "analysis"]
    # lets the admin test what's typed in the form before saving it
    api_key: str | None = Field(default=None, max_length=500)
    base_url: str | None = Field(default=None, max_length=500)


@router.post("/providers/test")
def test_provider(data: TestIn, store: Store, user: CurrentUser):
    return provider_config.test_connection(
        store,
        data.target,
        override_key=(data.api_key or "").strip() or None,
        override_base_url=(data.base_url or "").strip() or None,
    )


class LogoIn(BaseModel):
    # base64 rather than multipart: small payload, simpler through the proxy
    data: str = Field(max_length=1_400_000)


@router.put("/logo", status_code=204)
def upload_logo(data: LogoIn, user: CurrentUser, session: DB):
    try:
        raw = base64.b64decode(data.data, validate=True)
        branding.save_logo(raw)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit_event(session, "logo_updated", actor=user, data={"bytes": len(raw)})


@router.get("/logo")
def get_logo(user: CurrentUser):
    path = branding.logo_path()
    if path is None:
        raise HTTPException(status_code=404, detail="No logo uploaded")
    media = "image/png" if path.suffix == ".png" else "image/jpeg"
    return Response(path.read_bytes(), media_type=media)


@router.delete("/logo", status_code=204)
def delete_logo(user: CurrentUser, session: DB):
    if branding.delete_logo():
        record_audit_event(session, "logo_deleted", actor=user, data={})
