from functools import lru_cache

from supabase import Client, ClientOptions, create_client

from app.config import settings


def create_user_client(access_token: str) -> Client:
    """Client acting as the signed-in user — RLS applies to every query.

    Built per request because each request carries a different user JWT.
    """
    options = ClientOptions(
        headers={"Authorization": f"Bearer {access_token}"},
        auto_refresh_token=False,
        persist_session=False,
    )
    client = create_client(settings.supabase_url, settings.supabase_anon_key, options)
    client.postgrest.auth(access_token)
    return client


@lru_cache(maxsize=1)
def get_admin_client() -> Client:
    """Service-role client for privileged backend writes — bypasses RLS.

    Cached singleton: it carries no per-user state, so one instance serves all requests.
    Never expose this client's key to logs, responses, or the frontend.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
