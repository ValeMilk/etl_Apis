"""Servidor MCP (somente leitura) para o PostgreSQL do BI_COMETA.

Expõe o banco e o `docs/DATA_DICTIONARY.md` para clientes MCP (Claude Code, Claude Desktop):

- tool `listar_tabelas`   -> as tabelas, com fonte/estratégia de carga e nº aproximado de linhas
- tool `descrever_tabela` -> colunas reais (information_schema) + descrição do dicionário
- tool `consultar_sql`    -> SELECT validado, em transação read-only, com timeout e limite de linhas
- resource `dicionario://bi_cometa` -> o dicionário de dados completo

Conexão: `MCP_DB_URL` (se existir) ou `DB_URL` do `.env` do projeto. O ideal é apontar
`MCP_DB_URL` para um role só com SELECT; mesmo sem isso, toda sessão roda read-only.

Transporte: stdio (padrão, o cliente MCP inicia o processo) ou HTTP com `MCP_TRANSPORT=http`
(para rodar na VPS atrás do proxy). No modo HTTP toda requisição exige
`Authorization: Bearer <token>`, com os tokens em `MCP_AUTH_TOKENS=nome:token,nome2:token2`.
Com `MCP_PUBLIC_URL` definido, o servidor também faz OAuth (login pelo Rebaixa) para os conectores do
Claude que só aceitam URL; ver oauth_provider.py.
"""
import hmac
import json
import logging
import os
import re
import sys
from contextvars import ContextVar
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

import psycopg
import uvicorn
from dotenv import load_dotenv
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from oauth_provider import LOGIN_PATH, build_oauth

BASE_DIR = Path(__file__).resolve().parent.parent
DICTIONARY_PATH = BASE_DIR / "docs" / "DATA_DICTIONARY.md"

STATEMENT_TIMEOUT_MS = 15_000
CONNECT_TIMEOUT_S = 5
DEFAULT_LIMIT = 200
MAX_LIMIT = 1_000
MIN_TOKEN_LEN = 24
LOG_SQL_CHARS = 500

# stdout é o canal do protocolo MCP (stdio) -- log só em stderr.
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bi_cometa_mcp")

load_dotenv(BASE_DIR / ".env")

# Quem está chamando quando só há tokens fixos (preenchido pelo middleware; "stdio" no processo local).
_current_user: ContextVar[str] = ContextVar("mcp_user", default="stdio")


def _auth_tokens() -> Dict[str, str]:
    """Lê `MCP_AUTH_TOKENS=nome:token,nome2:token2` e devolve {token: nome}."""
    tokens: Dict[str, str] = {}
    for item in filter(None, (p.strip() for p in os.getenv("MCP_AUTH_TOKENS", "").split(","))):
        name, sep, token = item.partition(":")
        # A mensagem não cita o item: se o formato estiver errado ele pode ser o próprio token.
        if not sep or not name or len(token) < MIN_TOKEN_LEN:
            raise RuntimeError(
                f"MCP_AUTH_TOKENS inválido: use nome:token, com token de pelo menos {MIN_TOKEN_LEN} caracteres."
            )
        tokens[token] = name
    return tokens


HTTP_MODE = os.getenv("MCP_TRANSPORT", "stdio") == "http"
# OAuth (login pelo Rebaixa) só no modo HTTP e só se MCP_PUBLIC_URL estiver definido.
_oauth = build_oauth(_auth_tokens()) if HTTP_MODE else None

mcp = FastMCP(
    "bi-cometa-postgres",
    # Só usados no modo HTTP. Sem estado + resposta JSON: cada chamada é um POST independente, sem
    # SSE de longa duração (o Cloudflare corta conexões abertas por ~100s).
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8001")),
    stateless_http=True,
    json_response=True,
    auth_server_provider=_oauth[0] if _oauth else None,
    auth=_oauth[1] if _oauth else None,
    instructions=(
        "Banco PostgreSQL `bi_cometa` (ETL de Cometa/ValeMilk, Cometa/ValeFish, InfoMarket e ATIVMOB). "
        "Comece por `listar_tabelas` e `descrever_tabela`. Pontos que costumam enganar: "
        "(1) não há foreign keys -- os joins são lógicos (`vendas.cod_interno` = `estoque.codigo_produto`); "
        "(2) `estoque` e `estoque_valefish` são snapshot atual, não histórico; "
        "(3) `ean` em vendas/estoque é sempre NULL; "
        "(4) `vendas_valefish`/`estoque_valefish` espelham as tabelas do ValeMilk; "
        "(5) `infomarket` é recarregada do zero 3x/dia e é CRUA (uma linha por loja, com preço padrão): "
        "para encartes e preços de concorrentes use a view `infomarket_tratado`, nunca a tabela crua; "
        "antes de responder qualquer pergunta de encarte (histórico, preço, presença de marca numa rede), "
        "leia o racional e o SQL modelo em `descrever_tabela('infomarket_tratado')`: rede sem acento, "
        "categoria e gramatura pela `description`, encarte = `leaflet_id` distinto, `dynamic` antes de comparar preço. "
        "Só SELECT é aceito; filtre por período e use LIMIT/agregações em tabelas grandes."
    ),
)


if _oauth:
    mcp.custom_route(LOGIN_PATH, methods=["GET", "POST"])(_oauth[0].handle_login)


def _caller() -> str:
    """Quem chamou: o dono do token OAuth/fixo, ou o nome do token fixo no modo sem OAuth."""
    token = get_access_token()
    return (token.subject or token.client_id) if token else _current_user.get()


def _db_url() -> str:
    """URL do banco no formato do psycopg (remove o sufixo de driver do SQLAlchemy)."""
    url = os.getenv("MCP_DB_URL") or os.getenv("DB_URL")
    if not url:
        raise RuntimeError("Defina MCP_DB_URL ou DB_URL (ex.: no .env do BI_COMETA).")
    return re.sub(r"^postgres(?:ql)?\+\w+://", "postgresql://", url)


def _connect() -> psycopg.Connection:
    """Abre uma conexão cuja sessão é read-only e tem timeout de statement."""
    conn = psycopg.connect(
        _db_url(),
        connect_timeout=CONNECT_TIMEOUT_S,
        options=f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}",
    )
    conn.read_only = True
    return conn


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _jsonable(rows: List[tuple]) -> List[list]:
    """Converte valores não serializáveis (datas, Decimal...) via round-trip JSON."""
    return json.loads(json.dumps([list(r) for r in rows], default=_json_default))


def _read_dictionary() -> str:
    return DICTIONARY_PATH.read_text(encoding="utf-8")


def _dictionary_sections() -> Dict[str, str]:
    """Mapeia nome de tabela -> seção `## ...` do dicionário (heading pode citar várias tabelas)."""
    sections: Dict[str, str] = {}
    for block in re.split(r"^(?=## )", _read_dictionary(), flags=re.MULTILINE):
        heading = block.split("\n", 1)[0]
        if not heading.startswith("## "):
            continue
        for name in re.findall(r"`([a-z_]+)`", heading):
            sections[name] = block.strip().rstrip("-").strip()
    return sections


def _dictionary_overview() -> Dict[str, Dict[str, str]]:
    """Linhas da tabela 'Visão geral': fonte, estratégia de carga e job de cada tabela."""
    overview: Dict[str, Dict[str, str]] = {}
    # Só a primeira seção `## Visão geral...`: as tabelas de colunas abaixo têm o mesmo formato de linha.
    section = re.search(r"^## Visão geral.*?(?=^## |^---)", _read_dictionary(), re.MULTILINE | re.DOTALL)
    for line in (section.group(0) if section else "").splitlines():
        match = re.match(r"^\|\s*`([a-z_]+)`\s*\|(.+)\|\s*$", line)
        if not match:
            continue
        cells = [c.strip() for c in match.group(2).split("|")]
        if len(cells) == 3:
            overview[match.group(1)] = {"fonte": cells[0], "carga": cells[1], "job": cells[2]}
    return overview


def _real_tables(conn: psycopg.Connection) -> Dict[str, str]:
    """Tabelas e views do schema public: {nome: "tabela" | "view"}."""
    rows = conn.execute(
        "SELECT table_name, table_type FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type IN ('BASE TABLE', 'VIEW') ORDER BY table_name"
    ).fetchall()
    return {name: "view" if kind == "VIEW" else "tabela" for name, kind in rows}


@mcp.resource("dicionario://bi_cometa", mime_type="text/markdown")
def dicionario() -> str:
    """Dicionário de dados completo do banco bi_cometa (docs/DATA_DICTIONARY.md)."""
    return _read_dictionary()


@mcp.tool()
def listar_tabelas() -> Dict[str, Any]:
    """Lista as tabelas e views do banco com fonte, estratégia de carga, job e nº aproximado de linhas."""
    overview = _dictionary_overview()
    with _connect() as conn:
        stats = {
            r[0]: r[1]
            for r in conn.execute("SELECT relname, n_live_tup FROM pg_stat_user_tables").fetchall()
        }
        tables = _real_tables(conn)
    return {
        "tabelas": [
            {"tabela": t, "tipo": kind, **overview.get(t, {}), "linhas_aprox": stats.get(t)}
            for t, kind in tables.items()
        ],
        "observacao": (
            "linhas_aprox vem das estatísticas do Postgres (n_live_tup), não é COUNT exato; "
            "views não têm estatística (null)."
        ),
    }


@mcp.tool()
def descrever_tabela(tabela: str) -> Dict[str, Any]:
    """Colunas reais da tabela (tipo, nulo, tamanho) e a descrição dela no dicionário de dados.

    Args:
        tabela: nome da tabela, como retornado por `listar_tabelas` (ex.: "vendas").
    """
    with _connect() as conn:
        if tabela not in _real_tables(conn):
            raise ValueError(f"Tabela '{tabela}' não existe. Use listar_tabelas.")
        cols = conn.execute(
            "SELECT column_name, data_type, character_maximum_length, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
            (tabela,),
        ).fetchall()
    return {
        "tabela": tabela,
        "colunas": [
            {"nome": c[0], "tipo": c[1], "tamanho": c[2], "aceita_nulo": c[3] == "YES"} for c in cols
        ],
        "dicionario": _dictionary_sections().get(tabela, "Sem seção no DATA_DICTIONARY.md."),
    }


@mcp.tool()
def consultar_sql(sql: str, limite: int = DEFAULT_LIMIT) -> Dict[str, Any]:
    """Executa um SELECT (ou WITH ... SELECT) somente leitura e devolve as linhas.

    A sessão é read-only e tem timeout de 15s. Prefira agregar no banco (GROUP BY) e filtrar
    por período em vez de trazer linhas cruas.

    Args:
        sql: uma única instrução SELECT/WITH.
        limite: máximo de linhas retornadas (padrão 200, teto 1000).
    """
    statement = sql.strip().rstrip(";").strip()
    if not re.match(r"^(select|with)\b", statement, re.IGNORECASE):
        raise ValueError("Só são aceitas consultas que comecem com SELECT ou WITH.")
    if ";" in statement:
        raise ValueError("Envie uma única instrução, sem ';' no meio.")

    limite = max(1, min(limite, MAX_LIMIT))
    logger.info("consultar_sql usuario=%s sql=%s", _caller(), statement[:LOG_SQL_CHARS])
    # Pede uma linha a mais para saber se o resultado foi truncado.
    wrapped = f"SELECT * FROM (\n{statement}\n) AS _q LIMIT {limite + 1}"
    with _connect() as conn:
        cur = conn.execute(wrapped)
        columns = [d.name for d in cur.description]
        rows = cur.fetchall()

    truncado = len(rows) > limite
    rows = rows[:limite]
    return {
        "colunas": columns,
        "linhas": _jsonable(rows),
        "total_linhas": len(rows),
        "truncado": truncado,
        "sql_executado": statement,
    }


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request: Request) -> PlainTextResponse:
    """Liveness para o healthcheck do container (não toca no banco)."""
    return PlainTextResponse("ok")


class BearerAuthMiddleware:
    """ASGI (modo sem OAuth): exige `Authorization: Bearer <token>` (menos em /healthz) e guarda quem chamou."""

    def __init__(self, app: Any, tokens: Dict[str, str]) -> None:
        self.app = app
        self.tokens = tokens

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["path"] == "/healthz":
            await self.app(scope, receive, send)
            return

        header = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
        candidate = header[7:].strip().encode() if header[:7].lower() == "bearer " else b""
        user = next(
            (name for token, name in self.tokens.items() if hmac.compare_digest(candidate, token.encode())),
            None,
        )
        if user is None:
            logger.warning("acesso negado path=%s", scope["path"])
            response = JSONResponse(
                {"error": "Token ausente ou inválido"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        reset = _current_user.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user.reset(reset)


def run_http() -> None:
    """Sobe o MCP via HTTP (streamable, sem estado): OAuth + tokens fixos, ou só tokens fixos."""
    app = mcp.streamable_http_app()
    if _oauth:
        # A autenticação (OAuth e tokens fixos) fica por conta do FastMCP, via BiOAuthProvider.load_access_token.
        logger.info("MCP HTTP em %s:%s com OAuth", mcp.settings.host, mcp.settings.port)
    else:
        tokens = _auth_tokens()
        if not tokens:
            raise SystemExit("MCP_AUTH_TOKENS vazio: o modo HTTP não sobe sem autenticação.")
        app.add_middleware(BearerAuthMiddleware, tokens=tokens)
        logger.info("MCP HTTP em %s:%s com %d token(s)", mcp.settings.host, mcp.settings.port, len(tokens))
    uvicorn.run(app, host=mcp.settings.host, port=mcp.settings.port)


if __name__ == "__main__":
    if os.getenv("MCP_TRANSPORT", "stdio") == "http":
        run_http()
    else:
        mcp.run()
