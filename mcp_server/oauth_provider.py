"""OAuth 2.1 (authorization code + PKCE, registro dinâmico) do MCP, com login pelo Rebaixa.

Fluxo: o conector do Claude (claude.ai / Desktop) descobre os endpoints, se registra em /register e manda
o usuário para /authorize -> /mcp-login (e-mail e senha do Rebaixa) -> volta ao Claude com um código, que
vira access token (1h) + refresh token (30 dias, com rotação).

Só entra quem (1) está em MCP_OAUTH_ALLOWED_EMAILS, (2) autentica no Rebaixa e (3) tem um perfil de
MCP_OAUTH_ALLOWED_ROLES. Códigos e tokens são guardados só como hash SHA-256, em SQLite (volume do container).
Os tokens fixos de MCP_AUTH_TOKENS continuam valendo (Claude Code, mcp-remote).
"""
import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

logger = logging.getLogger("bi_cometa_mcp.oauth")

LOGIN_PATH = "/mcp-login"
SCOPE = "bi:read"
ACCESS_TTL_S = 3600
REFRESH_TTL_S = 30 * 24 * 3600
CODE_TTL_S = 300
PENDING_TTL_S = 600
MAX_CLIENTS = 1_000
LOGIN_TIMEOUT_S = 8
# Callbacks do Claude (a Anthropic avisa que o domínio pode migrar de claude.ai para claude.com).
DEFAULT_REDIRECT_URIS = "https://claude.ai/api/mcp/auth_callback,https://claude.com/api/mcp/auth_callback"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (client_id TEXT PRIMARY KEY, data TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pending (id TEXT PRIMARY KEY, data TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS codes (hash TEXT PRIMARY KEY, data TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS tokens (
    hash TEXT PRIMARY KEY, kind TEXT NOT NULL, family TEXT NOT NULL,
    client_id TEXT NOT NULL, subject TEXT NOT NULL, expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tokens_family ON tokens (family);
"""


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _csv(name: str, default: str = "") -> Set[str]:
    return {item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()}


class Store:
    """SQLite mínimo e síncrono: as operações são pontuais e rápidas, então um lock basta."""

    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        try:
            os.chmod(path, 0o600)
        except OSError:  # Windows
            pass

    def run(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            return self._db.execute(sql, params).rowcount

    def one(self, sql: str, params: tuple = ()) -> Optional[tuple]:
        with self._lock:
            return self._db.execute(sql, params).fetchone()

    def purge(self) -> None:
        now = int(time.time())
        for table in ("pending", "codes", "tokens"):
            self.run(f"DELETE FROM {table} WHERE expires_at < ?", (now,))


class AttemptLimiter:
    """Falhas de login por e-mail, por IP e no total (janela deslizante, em memória)."""

    MAX_BY_EMAIL = 5
    MAX_BY_IP = 10
    MAX_GLOBAL = 40
    WINDOW_S = 900
    MAX_KEYS = 10_000

    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = {}

    def _recent(self, key: str) -> Deque[float]:
        hits = self._hits.setdefault(key, deque())
        cutoff = time.time() - self.WINDOW_S
        while hits and hits[0] < cutoff:
            hits.popleft()
        return hits

    def blocked(self, ip: str, email: str) -> bool:
        return (
            len(self._recent(f"e:{email}")) >= self.MAX_BY_EMAIL
            or len(self._recent(f"i:{ip}")) >= self.MAX_BY_IP
            or len(self._recent("g")) >= self.MAX_GLOBAL
        )

    def fail(self, ip: str, email: str) -> None:
        if len(self._hits) > self.MAX_KEYS:
            self._hits.clear()
        now = time.time()
        for key in (f"e:{email}", f"i:{ip}", "g"):
            self._recent(key).append(now)

    def clear(self, email: str) -> None:
        self._hits.pop(f"e:{email}", None)


@dataclass
class OAuthConfig:
    public_url: str
    login_url: str
    allowed_emails: Set[str]
    allowed_roles: Set[str]
    redirect_uris: Set[str]
    db_path: str
    static_tokens: Dict[str, str]  # token -> nome


def _page(body: str, status: int = 200) -> HTMLResponse:
    html_doc = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BI_COMETA - Conectar ao Claude</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f3f6fa;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center}}
main{{background:#fff;max-width:380px;width:calc(100% - 32px);padding:28px;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08)}}
h1{{color:#0056A6;font-size:1.25rem;margin:0 0 8px}} p{{color:#334;font-size:.92rem;line-height:1.4}}
label{{display:block;font-size:.85rem;margin:14px 0 4px;color:#334}}
input{{width:100%;box-sizing:border-box;padding:10px;border:1px solid #b9c4d0;border-radius:8px;font-size:1rem}}
button{{width:100%;margin-top:20px;padding:11px;background:#0056A6;color:#fff;border:0;border-radius:8px;font-size:1rem;cursor:pointer}}
.erro{{background:#fdecea;color:#8a1f17;padding:10px;border-radius:8px;font-size:.88rem;margin-top:12px}}
.nota{{font-size:.78rem;color:#667;margin-top:16px}}
</style></head><body><main>{body}</main></body></html>"""
    return HTMLResponse(
        html_doc,
        status_code=status,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
        },
    )


def _form(req_id: str, client_name: str, erro: str = "") -> str:
    aviso = f'<div class="erro">{html.escape(erro)}</div>' if erro else ""
    return f"""<h1>Conectar o Claude ao BI_COMETA</h1>
<p><b>{html.escape(client_name)}</b> pede acesso <b>somente leitura</b> ao banco de dados do BI
(vendas, estoque, encartes). Entre com a sua conta do Rebaixa para autorizar.</p>
{aviso}
<form method="post" action="{LOGIN_PATH}" autocomplete="on">
<input type="hidden" name="req" value="{html.escape(req_id)}">
<label for="email">E-mail</label><input id="email" name="email" type="email" required autofocus autocomplete="username">
<label for="senha">Senha</label><input id="senha" name="senha" type="password" required autocomplete="current-password">
<button type="submit">Entrar e autorizar</button>
</form>
<p class="nota">Se você não iniciou esta conexão, feche esta página.</p>"""


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")


class BiOAuthProvider:
    """Implementa OAuthAuthorizationServerProvider (duck-typing) sobre SQLite + login do Rebaixa."""

    def __init__(self, config: OAuthConfig) -> None:
        self.cfg = config
        self.store = Store(config.db_path)
        self.limiter = AttemptLimiter()

    # --- registro de clientes (DCR) -------------------------------------------------------------
    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        row = self.store.one("SELECT data FROM clients WHERE client_id = ?", (client_id,))
        return OAuthClientInformationFull.model_validate_json(row[0]) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in (client_info.redirect_uris or [])]
        if not uris or any(u not in self.cfg.redirect_uris for u in uris):
            logger.warning("registro recusado: redirect_uri fora da lista %s", uris)
            raise RegistrationError("invalid_redirect_uri", "redirect_uri não permitido neste servidor")
        if self.store.one("SELECT count(*) FROM clients")[0] >= MAX_CLIENTS:
            raise RegistrationError("invalid_client_metadata", "limite de clientes registrados atingido")
        self.store.run(
            "INSERT INTO clients (client_id, data, created_at) VALUES (?, ?, ?)",
            (client_info.client_id, client_info.model_dump_json(), int(time.time())),
        )

    # --- autorização ----------------------------------------------------------------------------
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        self.store.purge()
        req_id = secrets.token_urlsafe(24)
        data = {
            "client_id": client.client_id,
            "client_name": (client.client_name or "Claude")[:60],
            "redirect_uri": str(params.redirect_uri),
            "explicit": params.redirect_uri_provided_explicitly,
            "state": params.state,
            "code_challenge": params.code_challenge,
            "resource": params.resource,
        }
        self.store.run(
            "INSERT INTO pending (id, data, expires_at) VALUES (?, ?, ?)",
            (req_id, json.dumps(data), int(time.time()) + PENDING_TTL_S),
        )
        return f"{self.cfg.public_url}{LOGIN_PATH}?req={req_id}"

    def _pending(self, req_id: str) -> Optional[Dict[str, Any]]:
        row = self.store.one("SELECT data, expires_at FROM pending WHERE id = ?", (req_id,))
        if not row or row[1] < int(time.time()):
            return None
        return json.loads(row[0])

    async def handle_login(self, request: Request) -> Response:
        """GET: mostra o formulário. POST: confere e-mail/senha no Rebaixa e devolve o código ao Claude."""
        if request.method == "GET":
            req_id = request.query_params.get("req", "")
            pending = self._pending(req_id)
            if not pending:
                return _page("<h1>Link expirado</h1><p>Volte ao Claude e inicie a conexão de novo.</p>", 400)
            return _page(_form(req_id, pending["client_name"]))

        form = await request.form()
        req_id = str(form.get("req", ""))
        email = str(form.get("email", "")).strip().lower()
        senha = str(form.get("senha", ""))
        pending = self._pending(req_id)
        if not pending:
            return _page("<h1>Link expirado</h1><p>Volte ao Claude e inicie a conexão de novo.</p>", 400)

        ip = _client_ip(request)
        if self.limiter.blocked(ip, email):
            logger.warning("login bloqueado por excesso de tentativas email=%s ip=%s", email, ip)
            return _page(_form(req_id, pending["client_name"], "Muitas tentativas. Aguarde 15 minutos."), 429)

        generic = "E-mail ou senha inválidos, ou sem permissão para este conector."
        if email not in self.cfg.allowed_emails:
            self.limiter.fail(ip, email)
            logger.warning("login recusado (e-mail fora da lista) email=%s ip=%s", email, ip)
            return _page(_form(req_id, pending["client_name"], generic), 401)

        try:
            user = await self._rebaixa_login(email, senha)
        except httpx.HTTPError as exc:
            logger.error("login: Rebaixa indisponível (%s)", type(exc).__name__)
            return _page(_form(req_id, pending["client_name"], "Não foi possível validar agora. Tente de novo."), 503)
        if user is None:
            self.limiter.fail(ip, email)
            logger.warning("login recusado (credenciais/perfil) email=%s ip=%s", email, ip)
            return _page(_form(req_id, pending["client_name"], generic), 401)

        self.limiter.clear(email)
        code = secrets.token_urlsafe(32)
        self.store.run(
            "INSERT INTO codes (hash, data, expires_at) VALUES (?, ?, ?)",
            (
                _hash(code),
                json.dumps({**{k: pending[k] for k in ("client_id", "code_challenge", "redirect_uri", "explicit", "resource")}, "subject": email}),
                int(time.time()) + CODE_TTL_S,
            ),
        )
        self.store.run("DELETE FROM pending WHERE id = ?", (req_id,))
        logger.info("login ok usuario=%s ip=%s cliente=%s", email, ip, pending["client_name"])
        return RedirectResponse(
            construct_redirect_uri(pending["redirect_uri"], code=code, state=pending["state"]),
            status_code=302,
            headers={"Cache-Control": "no-store"},
        )

    async def _rebaixa_login(self, email: str, senha: str) -> Optional[Dict[str, Any]]:
        """Usuário do Rebaixa se e-mail/senha batem e o perfil é permitido; None caso contrário."""
        async with httpx.AsyncClient(timeout=LOGIN_TIMEOUT_S) as client:
            response = await client.post(self.cfg.login_url, json={"email": email, "senha": senha})
        if response.status_code in (400, 401, 403):
            return None
        response.raise_for_status()
        user = response.json().get("user") or {}
        roles = {str(r).lower() for r in [user.get("role"), *(user.get("roles") or [])] if r}
        if str(user.get("email", "")).lower() != email or not roles & self.cfg.allowed_roles:
            return None
        return user

    # --- códigos e tokens -----------------------------------------------------------------------
    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[AuthorizationCode]:
        row = self.store.one("SELECT data, expires_at FROM codes WHERE hash = ?", (_hash(authorization_code),))
        if not row or row[1] < int(time.time()):
            return None
        data = json.loads(row[0])
        if data["client_id"] != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=[SCOPE],
            expires_at=row[1],
            client_id=data["client_id"],
            code_challenge=data["code_challenge"],
            redirect_uri=AnyUrl(data["redirect_uri"]),
            redirect_uri_provided_explicitly=data["explicit"],
            resource=data["resource"],
            subject=data["subject"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # Uso único: se outra requisição já consumiu o código, rowcount = 0.
        if self.store.run("DELETE FROM codes WHERE hash = ?", (_hash(authorization_code.code),)) == 0:
            raise TokenError("invalid_grant", "authorization code já utilizado")
        return self._issue(client.client_id, authorization_code.subject or "")

    def _allowed(self, subject: str) -> bool:
        return subject.lower() in self.cfg.allowed_emails

    def _issue(self, client_id: str, subject: str) -> OAuthToken:
        family = secrets.token_hex(8)
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(time.time())
        for token, kind, ttl in ((access, "access", ACCESS_TTL_S), (refresh, "refresh", REFRESH_TTL_S)):
            self.store.run(
                "INSERT INTO tokens (hash, kind, family, client_id, subject, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (_hash(token), kind, family, client_id, subject, now + ttl),
            )
        return OAuthToken(access_token=access, expires_in=ACCESS_TTL_S, scope=SCOPE, refresh_token=refresh)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> Optional[RefreshToken]:
        row = self.store.one(
            "SELECT client_id, subject, expires_at FROM tokens WHERE hash = ? AND kind = 'refresh'",
            (_hash(refresh_token),),
        )
        if not row or row[2] < int(time.time()) or row[0] != client.client_id or not self._allowed(row[1]):
            return None
        return RefreshToken(token=refresh_token, client_id=row[0], scopes=[SCOPE], expires_at=row[2], subject=row[1])

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: List[str]
    ) -> OAuthToken:
        row = self.store.one("SELECT family FROM tokens WHERE hash = ?", (_hash(refresh_token.token),))
        # Rotação: o refresh antigo (e o access do mesmo par) deixam de valer; reapresentá-lo dá invalid_grant.
        if not row or self.store.run("DELETE FROM tokens WHERE family = ?", (row[0],)) == 0:
            raise TokenError("invalid_grant", "refresh token inválido")
        return self._issue(client.client_id, refresh_token.subject or "")

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        # Tokens fixos (Claude Code, mcp-remote), comparados em tempo constante.
        for static, name in self.cfg.static_tokens.items():
            if hmac.compare_digest(token.encode(), static.encode()):
                return AccessToken(token=token, client_id="static", scopes=[SCOPE], subject=name)
        row = self.store.one(
            "SELECT client_id, subject, expires_at FROM tokens WHERE hash = ? AND kind = 'access'",
            (_hash(token),),
        )
        if not row or row[2] < int(time.time()) or not self._allowed(row[1]):
            return None
        return AccessToken(token=token, client_id=row[0], scopes=[SCOPE], expires_at=row[2], subject=row[1])

    async def revoke_token(self, token: Any) -> None:
        row = self.store.one("SELECT family FROM tokens WHERE hash = ?", (_hash(token.token),))
        if row:
            self.store.run("DELETE FROM tokens WHERE family = ?", (row[0],))


def build_oauth(static_tokens: Dict[str, str]) -> Optional[Tuple[BiOAuthProvider, AuthSettings]]:
    """Provedor + settings do FastMCP se MCP_PUBLIC_URL estiver definido; None = só tokens fixos."""
    public_url = os.getenv("MCP_PUBLIC_URL", "").strip().rstrip("/")
    if not public_url:
        return None
    emails = _csv("MCP_OAUTH_ALLOWED_EMAILS")
    if not emails:
        raise RuntimeError("MCP_OAUTH_ALLOWED_EMAILS vazio: o OAuth não sobe sem uma lista de e-mails autorizados.")
    config = OAuthConfig(
        public_url=public_url,
        login_url=os.getenv("MCP_OAUTH_LOGIN_URL", "http://rebaixa-backend:4000/api/auth/login"),
        allowed_emails=emails,
        allowed_roles=_csv("MCP_OAUTH_ALLOWED_ROLES", "admin"),
        redirect_uris={str(AnyUrl(u)) for u in os.getenv("MCP_OAUTH_REDIRECT_URIS", DEFAULT_REDIRECT_URIS).split(",") if u.strip()},
        db_path=os.getenv("MCP_OAUTH_DB", "/data/oauth.db"),
        static_tokens=static_tokens,
    )
    settings = AuthSettings(
        issuer_url=public_url,
        resource_server_url=f"{public_url}/mcp",
        validate_token_resource=False,  # um único recurso: não há outro servidor para confundir
        client_registration_options=ClientRegistrationOptions(enabled=True),
        revocation_options=RevocationOptions(enabled=True),
    )
    logger.info("OAuth ativo: issuer=%s, %d e-mail(s) autorizado(s), perfis=%s", public_url, len(emails), sorted(config.allowed_roles))
    return BiOAuthProvider(config), settings
