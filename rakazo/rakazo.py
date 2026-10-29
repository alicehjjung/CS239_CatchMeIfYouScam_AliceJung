"""Small teaching wrapper around this Rakazo version's authenticated HTTP API.

This is not an official Rakazo SDK or an A2A server. Rakazo must already run.
"""
from dataclasses import asdict, dataclass, field
import httpx


@dataclass(frozen=True)
class ModelConnection:
    provider: str
    model_id: str
    base_url: str
    api_key: str = field(default='', repr=False)


@dataclass(frozen=True)
class MCPConnection:
    name: str
    slug: str
    endpoint: str


@dataclass(frozen=True)
class BotProfile:
    name: str
    instructions: str
    model: ModelConnection
    mcp: tuple[MCPConnection, ...] = ()


class Rakazo:
    def __init__(self, url: str, *, origin: str | None = None):
        # Use the web origin when its API is reached on a different port.
        self.http = httpx.Client(base_url=url.rstrip('/'), timeout=30,
                                 headers={'Origin': origin or url.rstrip('/')})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.http.close()

    def login(self, email: str, password: str):
        response = self.http.post('/api/auth/sign-in/email',
                                  json={'email': email, 'password': password})
        if not response.is_success:
            raise RuntimeError(f'Login failed (HTTP {response.status_code}). Check account and origin.')

    def rpc(self, route: str, data: dict | None = None):
        response = self.http.post('/rpc/' + route, json={'json': data or {}})
        if not response.is_success:
            # Do not print response bodies: provider errors can echo credentials.
            raise RuntimeError(f'{route} failed (HTTP {response.status_code}). Check the Rakazo server logs.')
        body = response.json()
        if 'json' not in body:
            raise RuntimeError(f'{route} returned an unexpected response')
        return body['json']

    def create_team(self, *profiles: BotProfile) -> dict[str, str]:
        """Create new bots. Refuse duplicate names; do not silently overwrite a workspace."""
        names = [p.name for p in profiles]
        if len(set(names)) != len(names):
            raise ValueError('Bot names must be distinct')
        existing = {b['name'] for b in self.rpc('bots/list')}
        if existing.intersection(names):
            raise ValueError('These bot names already exist. Use a fresh workspace or edit them in Rakazo.')
        servers = {s['slug']: s for s in self.rpc('mcp/servers/list')}
        endpoints = {}
        for p in profiles:
            for mcp in p.mcp:
                if mcp.slug in endpoints and endpoints[mcp.slug] != mcp.endpoint:
                    raise ValueError('Conflicting MCP endpoints for the same slug')
                endpoints[mcp.slug] = mcp.endpoint
                if mcp.slug in servers and servers[mcp.slug]['endpoint'] != mcp.endpoint:
                    raise ValueError('Existing MCP slug points to a different endpoint')
        bots = {}
        for p in profiles:
            self.rpc('models/connect', {'provider': p.model.provider, 'modelId': p.model.model_id,
                     'baseUrl': p.model.base_url, 'apiKey': p.model.api_key})
            bot = self.rpc('bots/create', {'name': p.name, 'title': '',
                           'description': p.instructions, 'instructions': p.instructions,
                           'notifyOnFinish': False})
            self.rpc('bots/update', {'botId': bot['id'], 'modelProvider': p.model.provider,
                                    'modelId': p.model.model_id})
            for mcp in p.mcp:
                if mcp.slug not in servers:
                    servers[mcp.slug] = self.rpc('mcp/servers/create', {
                        **asdict(mcp), 'transport': 'streamable_http'})
                self.rpc('mcp/assignments/approve', {'botId': bot['id'],
                         'serverId': servers[mcp.slug]['id']})
            bots[p.name] = bot['id']
        return bots

    def send(self, bot_id: str, message: str):
        """Start an asynchronous run; this returns a run handle, not its final answer."""
        return self.rpc('threads/send', {'botId': bot_id, 'text': message})

    def conversation(self, bot_id: str):
        return self.rpc('threads/get', {'botId': bot_id})
