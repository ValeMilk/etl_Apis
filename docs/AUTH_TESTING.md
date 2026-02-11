# BI_COMETA - Guia Rápido de Autenticação

## 🚀 Como Testar a Autenticação

### 1. Configurar Ambiente

Edite o arquivo `.env` e defina um token de autenticação:

```bash
API_AUTH_TOKEN=meu-token-secreto-12345
CORS_ORIGINS=http://localhost:3000
```

> 💡 **Em produção**, use um token forte gerado via:
> ```bash
> openssl rand -hex 32
> ```

### 2. Iniciar Aplicação

```bash
cd src
uvicorn main:app --reload
```

Logs esperados:
```
INFO | Main | BI_COMETA Starting...
INFO | Main | Configuration loaded and validated
INFO | Main | CORSMiddleware configured with origins: ['http://localhost:3000']
INFO | Main | GZipMiddleware configured (minimum_size=1000)
```

### 3. Testar via Swagger UI

1. Acesse: http://localhost:8000/docs
2. Clique no botão **🔓 Authorize** (canto superior direito)
3. Digite: `meu-token-secreto-12345`
4. Clique **Authorize**
5. Teste os endpoints:
   - `GET /api/v1/vendas` → Status 200 ✅
   - `GET /api/v1/estoque` → Status 200 ✅

### 4. Testar via cURL

#### ✅ Com Token Válido (Sucesso)
```bash
curl -H "Authorization: Bearer meu-token-secreto-12345" \
     http://localhost:8000/api/v1/vendas
```

**Response**: Status 200 + JSON data

---

#### ❌ Sem Token (Não Autorizado)
```bash
curl http://localhost:8000/api/v1/vendas
```

**Response**: 
```json
{
  "detail": "Not authenticated"
}
```

---

#### ❌ Com Token Inválido (Não Autorizado)
```bash
curl -H "Authorization: Bearer token-errado" \
     http://localhost:8000/api/v1/vendas
```

**Response**:
```json
{
  "detail": "Invalid authentication credentials"
}
```

---

#### ✅ Health Check Público (Sem Auth)
```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "app": "BI_COMETA",
  "version": "1.0.0"
}
```

### 5. Testar via Python Requests

```python
import requests

BASE_URL = "http://localhost:8000"
TOKEN = "meu-token-secreto-12345"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

# Vendas (autenticado)
response = requests.get(f"{BASE_URL}/api/v1/vendas", headers=headers)
print(f"Status: {response.status_code}")
print(f"Data: {response.json()[:2]}")  # Primeiras 2 linhas

# Estoque (autenticado)
response = requests.get(f"{BASE_URL}/api/v1/estoque", headers=headers)
print(f"Status: {response.status_code}")

# Health (público)
response = requests.get(f"{BASE_URL}/health")
print(f"Health: {response.json()}")
```

### 6. Testar via Power BI

#### Web Data Source Configuration

1. **Get Data** → **Web**
2. **URL**: `http://localhost:8000/api/v1/vendas`
3. **Authentication**: **Header**
   - **Header Name**: `Authorization`
   - **Header Value**: `Bearer meu-token-secreto-12345`
4. **OK** → Power Query carrega dados

---

## 🔐 Variações de Teste

### Cenário 1: Token no .env diferente do enviado
**`.env`**: `API_AUTH_TOKEN=token-correto`  
**Request**: `Authorization: Bearer token-errado`  
**Resultado**: ❌ 401 Unauthorized

### Cenário 2: Token sem prefixo "Bearer"
**Request**: `Authorization: meu-token-secreto-12345`  
**Resultado**: ❌ 401 Not authenticated (FastAPI espera "Bearer ")

### Cenário 3: Header com typo
**Request**: `Authorisation: Bearer token` (typo em Authorization)  
**Resultado**: ❌ 401 Not authenticated

### Cenário 4: Token vazio
**Request**: `Authorization: Bearer `  
**Resultado**: ❌ 401 Invalid authentication credentials

---

## 📊 Logs de Autenticação

### Logs de Sucesso
```
INFO | uvicorn.access | GET /api/v1/vendas 200
```

### Logs de Falha
```
WARNING | Dependencies | Invalid authentication token attempt
INFO | uvicorn.access | GET /api/v1/vendas 401
```

---

## 🐳 Testando no Docker

### 1. Build e Start
```bash
cd docker
docker-compose up --build
```

### 2. Testar Endpoint
```bash
curl -H "Authorization: Bearer your-secure-bearer-token-here" \
     http://localhost:8000/api/v1/vendas
```

> ⚠️ **Importante**: Use o token definido no `.env` (não no `.env.example`)

---

## 🛠️ Troubleshooting

### Erro: "detail": "Not authenticated"
**Causa**: Header `Authorization` ausente ou malformado  
**Solução**: Verificar formato `Authorization: Bearer <token>`

### Erro: "detail": "Invalid authentication credentials"
**Causa**: Token enviado ≠ `API_AUTH_TOKEN` no `.env`  
**Solução**: Conferir valor exato do token

### Erro: "Connection refused"
**Causa**: Aplicação não está rodando  
**Solução**: `uvicorn main:app --reload` ou `docker-compose up`

### CORS Error no Browser
**Causa**: Origem não está em `CORS_ORIGINS`  
**Solução**: Adicionar domínio: `CORS_ORIGINS=http://localhost:3000,http://example.com`

---

## ✅ Checklist de Validação

- [ ] `.env` contém `API_AUTH_TOKEN=<valor-forte>`
- [ ] Swagger UI aceita token e retorna 200
- [ ] Request sem token retorna 401
- [ ] Request com token errado retorna 401
- [ ] `/health` funciona sem autenticação
- [ ] Power BI consegue consumir dados com header auth
- [ ] Logs mostram "Invalid authentication token attempt" para falhas
- [ ] Docker compose expõe apenas porta 8000 (não 5432)

---

**Autenticação Validada**: ✅ HTTPBearer funcionando  
**Rotas Protegidas**: `/api/v1/vendas`, `/api/v1/estoque`  
**Rotas Públicas**: `/health`, `/docs`, `/openapi.json`
