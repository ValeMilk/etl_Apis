# GitHub Actions CI/CD Setup

## Visão Geral

O workflow `.github/workflows/ci-cd.yml` automatiza:
1. **Testes & Lint** — a cada push/PR
2. **Build Docker** — constrói imagens API e ETL
3. **Push para Registry** — envia para GitHub Container Registry
4. **Deploy na VPS** — deploy automático ao fazer push na `main`

---

## Configuração Necessária

### 1. Criar SSH Key para Deploy

Na sua máquina local:

```bash
ssh-keygen -t ed25519 -f github_deploy_key -N ""
```

Isso cria dois arquivos:
- `github_deploy_key` (privada)
- `github_deploy_key.pub` (pública)

### 2. Adicionar Chave Pública na VPS

Na VPS (`root@72.61.62.17`):

```bash
# Como root
mkdir -p ~/.ssh
cat >> ~/.ssh/authorized_keys << 'EOF'
[cole aqui o conteúdo de github_deploy_key.pub]
EOF
chmod 600 ~/.ssh/authorized_keys
```

### 3. Adicionar Secrets no GitHub

No seu repositório GitHub:
- **Settings → Secrets and variables → Actions → New repository secret**

Adicione 3 secrets:

| Nome | Valor |
|------|-------|
| `VPS_HOST` | `72.61.62.17` |
| `VPS_USER` | `root` |
| `VPS_SSH_KEY` | [conteúdo completo de `github_deploy_key` privada] |

**Importante**: A chave privada deve estar em texto puro (com as quebras de linha `\n` convertidas para quebras reais).

### 4. Permitir GitHub Actions

Se você não tem, habilite GitHub Actions:
- **Settings → Actions → General → Enable for this repository**

---

## Como Funciona

### Trigger

- **Push em `main`**: Roda testes → build → deploy
- **Push em `develop`**: Roda testes → build (sem deploy)
- **Pull Requests**: Roda testes apenas

### Fluxo de Execução

```
Push na main
    ↓
Testes & Lint (ubuntu-latest, Python 3.10)
    ↓ (se passou)
Build Docker (API + ETL) → Push para GitHub Registry
    ↓ (se passou e é main)
SSH Deploy na VPS (git pull + docker pull + restart)
```

---

## Verificar Status

No GitHub:
- Vá para **Actions** tab
- Clique no workflow mais recente
- Veja o status de cada job

---

## Troubleshooting

### Deploy falha com "Permission denied"
- Verifique se a chave SSH pública está em `~/.ssh/authorized_keys` na VPS
- Teste localmente: `ssh -i github_deploy_key root@72.61.62.17`

### Imagens Docker não atualizam
- Verifique se `GITHUB_TOKEN` tem permissão `write:packages`
- Isso é automático para repositórios, mas em caso de erro:
  - **Settings → Actions → General → Workflow permissions → Read and write permissions**

### Testes falhando
- Verifique logs em **Actions → Workflow → Test job**
- Adicione mais testes em `tests/` conforme necessário

---

## Próximos Passos

1. **Commit e push do workflow**:
   ```bash
   git add .github/
   git commit -m "ci: add GitHub Actions CI/CD pipeline"
   git push
   ```

2. **Monitore o primeiro deploy** em **GitHub → Actions**

3. **Configure secrets** conforme acima

4. **Faça um push teste** e veja o workflow rodar

---

## Customizações Possíveis

- **Adicionar notificações** (Slack, Discord)
- **Testes em múltiplas versões** de Python (3.9, 3.10, 3.11)
- **Deploy em ambiente de staging** antes de produção
- **Versioning automático** com semantic release

