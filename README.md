# ELEVEN BR

**Seu time. Seu jogo.** Fundação técnica para gestão de futebol amador.

Esta etapa entrega a estrutura executável, a modelagem fundamental e cinco telas
iniciais. Não inclui cadastro completo de time, elenco, jogos, financeiro ou cobrança.

## Arquitetura

```text
apps/
  api/
    app/domain/          # Vocabulário, permissões e limites Free/Pro
    app/application/     # Operações transacionais e autorização por vínculo
    app/infrastructure/  # SQLAlchemy, PostgreSQL, configuração e segurança
    app/presentation/    # REST, dependências e contratos Pydantic
    migrations/          # Alembic
    tests/               # Segurança e integração com PostgreSQL real
  mobile/
    src/components/      # Componentes acessíveis e reutilizáveis
    src/screens/         # Início, Jogos, Times, Notificações, Perfil
    assets/              # Local reservado para assets oficiais
packages/shared/         # Identidade visual e vocabulário TypeScript
scripts/                 # PostgreSQL local isolado no Windows
```

Backend: Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic e PostgreSQL 18.
Mobile: TypeScript, React Native, Expo SDK 55 e React Navigation.
Dependências reproduzíveis em `apps/api/uv.lock` e `package-lock.json`.

`User` é a conta; `Player` é a identidade esportiva (no máximo uma por conta);
`TeamMembership` é o vínculo único entre jogador e time. Uma conta pode existir sem
perfil esportivo. Funções administrativas não são atributos de `User`.

`Team.president_membership_id` é obrigatório. A FK composta para `(team_id, id)` do
vínculo garante exatamente um Presidente pertencente ao próprio time. A checagem
é adiada até o commit para permitir a criação atômica do time e do primeiro vínculo.
Presidente é derivado dessa referência, sem um segundo campo de função que possa divergir.
Não há fluxo de transferência ou inativação de membros nesta etapa.

O plano está no time. `domain/policies.py` centraliza 24/100 jogadores ativos e
0/5 administradores adicionais para Free/Pro. Permissões de administradores são
explícitas e por vínculo; no Free, somente o Presidente tem poderes administrativos.
Os limites de inclusão são checados sob bloqueio da linha do time, inclusive em
requisições concorrentes. Novas operações de reativação, troca de plano e papel
deverão usar essas mesmas políticas e o mesmo bloqueio. Escritas SQL diretas não
aplicam os limites de plano da camada de aplicação.

Os routers são finos; regras ficam na aplicação/domínio. Consultas usam sessões
SQLAlchemy explícitas, sem camada genérica de repositórios. Não há dados fictícios
carregados no banco nem no aplicativo. Preferências de notificação e assinaturas
com cobrança foram adiadas por não serem necessárias à fundação.

## Instalação e configuração no Windows

Requisitos: Node >= 22.13, npm, [uv](https://docs.astral.sh/uv/) e PostgreSQL 18.
Use `npm.cmd`/`npx.cmd` no PowerShell se a política local bloquear os wrappers `.ps1`.

Na raiz:

```powershell
uv python install 3.13
npm.cmd ci
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start-local-postgres.ps1
```

O script usa os binários em `C:\Program Files\PostgreSQL\18\bin`; ajuste com
`-PostgresBin 'C:\caminho\bin'` se necessário. Cria um cluster exclusivo em
`.local/postgres-data`, escutando somente em `127.0.0.1:55432`, os bancos `eleven`
e `eleven_test` e um `.env` com segredos aleatórios. Não altera serviços ou bancos
PostgreSQL existentes, nem sobrescreve `.env`. Execute novamente para reiniciar
o cluster após reiniciar o computador. `.local` e `.env` são ignorados pelo Git.

Para parar esse cluster:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/stop-local-postgres.ps1
```

### Alternativa: PostgreSQL em Docker

Não use simultaneamente com o cluster local na mesma porta. Copie `.env.example`
para `.env`, substitua `JWT_SECRET` por um segredo aleatório e configure a senha
do banco no `DATABASE_URL` e `TEST_DATABASE_URL`.

```powershell
$env:POSTGRES_PASSWORD = 'sua-senha-local'
docker compose up -d db
docker compose exec db createdb -U eleven eleven_test
```

A API lê o `.env` da raiz independentemente do diretório de execução. Para usar
outro PostgreSQL, crie os dois bancos e ajuste as URLs. Não use o banco de
desenvolvimento como banco de testes.

## Executar API e migrations

```powershell
cd apps/api
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Swagger: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json
- Processo: http://127.0.0.1:8000/health
- Conexão PostgreSQL: http://127.0.0.1:8000/ready

`0001_foundation` cria `users`, `players`, `teams`, `team_memberships` e
`membership_permissions`, com UUIDs, timestamps, índices, unicidade, checks e FKs.
`updated_at` é atualizado em alterações feitas pelo SQLAlchemy.

```powershell
uv run alembic current
uv run alembic check
# Depois de alterações futuras de modelagem, revisar o arquivo gerado:
uv run alembic revision --autogenerate -m descricao
```

O ciclo de downgrade/upgrade é testado em schemas temporários. Não execute
`downgrade base` em banco com dados que deseja manter.

## Executar aplicativo

Em outro terminal, na raiz:

```powershell
npm.cmd run mobile
# Ou para abrir a versão web:
npm.cmd run mobile:web
```

Use um cliente Expo Go compatível com SDK 55 ou um development build.
O comando `mobile` anuncia o servidor na rede local para o celular (mesma rede
Wi-Fi). `mobile:web` abre o navegador em `http://localhost:8081` e mantém o
servidor no terminal; `web` é um alias para esse comando. Se a porta estiver
ocupada, confira a porta indicada pelo Expo ou encerre a instância anterior com
Ctrl+C. Não é necessário iniciar um servidor separado para cada plataforma.
Android pode usar emulador/dispositivo; o simulador iOS exige macOS/Xcode.
O mobile nesta etapa apresenta placeholders funcionais e navegação local;
não simula login nem consulta dados privados sem autenticação.

Tema claro, áreas seguras, conteúdo rolável, largura limitada em telas grandes,
rótulos de acessibilidade e botões de pelo menos 48 pontos. Componentes:
AppHeader, Card, Button, EmptyState, LoadingState, ErrorState, Badge, Avatar e TeamBadge.
O logotipo oficial pode ser adicionado em `apps/mobile/assets`; nenhum monograma foi redesenhado.

### Diagnóstico do servidor Web no Windows

Execute os scripts acima a partir da raiz do monorepo. Eles selecionam
explicitamente o workspace `@eleven/mobile`; não execute `npx expo start` na
raiz, que não é um aplicativo Expo. A entrada correta é `apps/mobile/index.ts`,
que chama `registerRootComponent`. O HTML de desenvolvimento referencia
`/apps/mobile/index.ts.bundle?platform=web...` — esse prefixo é esperado no monorepo.

Não são necessários `metro.config.js` ou `babel.config.js` personalizados nesta
fundação: os padrões do Expo SDK 55 resolvem npm workspaces, o pacote compartilhado
e React Native Web. O `app.json` seleciona Metro para Web e o `tsconfig.json` do
mobile estende `expo/tsconfig.base`. Não adicione aliases ou `watchFolders` manuais
para tentar corrigir uma instalação incompleta.

Se o servidor aceitar conexões mas não responder, confira primeiro se há outra
instância antiga do Expo. Encerre os servidores deste projeto com Ctrl+C **antes**
de reinstalar dependências. Uma falha `ENOTEMPTY`/`EPERM` no `npm ci` pode deixar
`node_modules` parcialmente removido no Windows. Depois de encerrar as instâncias,
rode na raiz e aguarde a conclusão bem-sucedida:

```powershell
npm.cmd ci
npm.cmd run mobile:web
```

Se `npx` propuser baixar outra versão do Expo, interrompa: o SDK deve vir do
lockfile local. Limpar o cache do Metro não restaura arquivos de pacotes ausentes.
Para repassar opções ao Expo por um script npm, use `--`, por exemplo
`npm.cmd run mobile:web -- --port 8083`.

Na correção do ambiente, a conexão com o Metro antigo expirava sem receber HTML;
faltavam `node_modules/expo/package.json` e o executável local, e o log do npm
registrava `ENOTEMPTY`. Após encerrar a instância e restaurar o lockfile, foi
verificado o servidor **de desenvolvimento** em `localhost:8081`: HTML 200,
bundle JavaScript 200, mensagem `Web Bundled`, cinco abas e navegação funcionando
sem erros JavaScript. Essa verificação é distinta da exportação estática.

## Autenticação e ambientes

Estrutura preparada: contatos e-mail/telefone E.164, normalização/validação,
campos de verificação de contato, hash Argon2id e tokens com expiração de 15 minutos,
emissor, audiência e algoritmo fixos. CPF e login social não fazem parte do modelo.

Não existem endpoints públicos de cadastro/login ou emissão de tokens nesta etapa.
`create_access_token` é uma função interna para o futuro fluxo de login verificado.
Rotas `/v1/me`, `/v1/teams`, `/v1/teams/{id}` e `/v1/teams/{id}/administration`
exigem token válido e conta ativa. Administração também exige vínculo ativo e
permissão do time. Usuários externos recebem 404 para times aos quais não pertencem.

- `development`: `.env` local, Swagger disponível.
- `test`: testes usam `TEST_DATABASE_URL`, segredo exclusivo de teste e um schema
  aleatório por teste, removido ao final. O nome do banco deve terminar em `_test`.
- `production`: configurar `APP_ENV=production`, URLs e segredo via variáveis de
  ambiente, banco com usuário de privilégio mínimo e TLS conforme o provedor;
  HTTPS na publicação. CORS exige origens HTTPS; Swagger/OpenAPI públicos são desativados.
  Nunca usar o usuário de bootstrap local em produção.

As escolhas seguem as bases documentadas do [Expo SDK 55](https://expo.dev/changelog/sdk-55),
do [FastAPI para hashing e JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
e do [PostgreSQL no Windows](https://www.postgresql.org/download/windows/).

## Verificações

Na raiz:

```powershell
npm.cmd run typecheck
npm.cmd run lint
cd apps/mobile
npx.cmd expo install --check
npx.cmd expo-doctor
npx.cmd expo export --platform all
```

Na API, com PostgreSQL local iniciado:

```powershell
cd apps/api
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Testes cobrem separação de identidades, múltiplos times/presidências, unicidade de
vínculo, FK de Presidente no commit, isolamento e permissões granulares, limites
Free/Pro, concorrência na última vaga, validação de contatos, hashing, tokens
inválidos, autorização HTTP e ciclo de migration com verificação de divergência.

Validação realizada nesta entrega: 23 testes passaram em PostgreSQL 18; Ruff,
formatação, mypy, ESLint e TypeScript passaram; Expo Doctor passou em 20/20
verificações; bundles Android/iOS/web foram exportados. A navegação pelas cinco
abas e o botão da tela inicial foram conferidos em Chromium, em larguras de
320, 390 e 1440 pixels, sem erros JavaScript. API, readiness e Swagger responderam.
A execução nativa em aparelho/simulador Android/iOS ainda não foi validada.
Resta um aviso de depreciação interno de Starlette/AnyIO nos testes, sem falhas.

## Próxima etapa

Definir o fluxo de acesso e verificação de e-mail/telefone, incluindo provedor de
mensagens, recuperação de conta, limitação de tentativas e revogação de sessões,
antes de expor login ao público. Entregar assets oficiais e validar visualmente
em Android/iOS reais. Cadastro de time e demais módulos continuam fora deste escopo.

O `npm audit` identificou 9 alertas moderados na cadeia de ferramentas do Expo
(`xcode` → `uuid`), sem alertas altos/críticos. A correção automática sugerida
regride o Expo para SDK 46, portanto não foi aplicada. Acompanhar a correção
upstream antes de preparar a distribuição nativa.
