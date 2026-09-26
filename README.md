# ELEVEN BR

**Seu time. Seu jogo.** Fundação técnica para gestão de futebol amador.

O projeto entrega a fundação, cadastro, verificação de contato, login, sessão,
perfil inicial, gestão básica de times, elenco e eventos com confirmação de presença.
As áreas pessoais e do time ficam na área autenticada. Inclui formação de equipes e partidas
com placar por pelada. Não inclui estatísticas individuais, financeiro ou cobrança.

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
    src/auth/            # Cliente da API, sessão e armazenamento por plataforma
    src/screens/         # Conta, áreas pessoais e navegação do time
    assets/              # Local reservado para assets oficiais
packages/shared/         # Identidade visual e vocabulário TypeScript
scripts/                 # PostgreSQL local isolado no Windows
```

Backend: Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic e PostgreSQL 18.
Mobile: TypeScript, React Native, Expo SDK 55 e React Navigation.
Dependências reproduzíveis em `apps/api/uv.lock` e `package-lock.json`.

`User` é a conta; `Player` é a identidade esportiva (no máximo uma por conta);
`TeamMembership` é o vínculo único entre jogador e time. Uma conta pode existir sem
perfil esportivo; Player pode existir sem conta. Funções administrativas não são atributos de `User`.

`Team.president_membership_id` é obrigatório. A FK composta para `(team_id, id)` do
vínculo garante exatamente um Presidente pertencente ao próprio time. A checagem
é adiada até o commit para permitir a criação atômica do time e do primeiro vínculo.
Presidente é derivado dessa referência, sem um segundo campo de função que possa divergir.
O elenco permite inativar membros, preservando o vínculo; Presidente não pode ser
inativado nesse fluxo. Transferência de Presidência permanece fora do escopo.

O plano está no time. `domain/policies.py` centraliza 24/100 jogadores ativos e
0/5 administradores adicionais para Free/Pro. Permissões de administradores são
explícitas e por vínculo; no Free, somente o Presidente tem poderes administrativos.
Os limites de inclusão são checados sob bloqueio da linha do time, inclusive em
requisições concorrentes. Reativação usa essas mesmas políticas e o mesmo bloqueio;
futuras operações de troca de plano e papel também deverão usá-los. Escritas SQL diretas não
aplicam os limites de plano da camada de aplicação.

Os routers são finos; regras ficam na aplicação/domínio. Consultas usam sessões
SQLAlchemy explícitas, sem camada genérica de repositórios. Não há carga automática
de dados fictícios. Preferências de notificação e assinaturas
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
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8011 --no-proxy-headers
```

- Swagger: http://127.0.0.1:8011/docs
- OpenAPI: http://127.0.0.1:8011/openapi.json
- Processo: http://127.0.0.1:8011/health
- Conexão PostgreSQL: http://127.0.0.1:8011/ready

`0001_foundation` cria `users`, `players`, `teams`, `team_memberships` e
`membership_permissions`, com UUIDs, timestamps, índices, unicidade, checks e FKs.
`updated_at` é atualizado em alterações feitas pelo SQLAlchemy.

`0002_authentication_sessions` adiciona desafios de verificação, sessões revogáveis,
hashes de refresh tokens e contadores de rate limit. Acrescenta nome provisório
de cadastro ao User e `photo_url` opcional ao Player, preservando os dados existentes.
A migration `0001` não foi alterada. Tokens antigos sem sessão persistida exigem novo login.

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
O aplicativo restaura a sessão antes de mostrar login ou abas. Cadastro pede nome,
telefone OU e-mail e senha com confirmação. A verificação cria o Player com o nome
já informado, sem TeamMembership e sem exigir time. Contas existentes sem Player
recebem apenas a complementação de nome. Times permitem criação, consulta, edição
e seleção; Jogos apresenta eventos do time selecionado e Notificações continua placeholder.

A API deve estar executando junto com o Expo. Web usa por padrão o hostname do
navegador na porta 8011; celular usa o host LAN anunciado pelo Expo. Para aparelho
físico, execute a API com `--host 0.0.0.0 --no-proxy-headers`, permita a conexão
na rede local e use a mesma rede Wi-Fi. Se necessário, crie `apps/mobile/.env`
a partir de seu `.env.example` e defina `EXPO_PUBLIC_API_URL=http://IP-DO-PC:8011`.
Reinicie o Expo após alterar essa variável. Nunca use `localhost` para apontar do
celular ao computador. Nenhum segredo deve usar o prefixo público `EXPO_PUBLIC_`.

Na Web, mantenha o mesmo hostname para app e API (por exemplo, ambos `localhost`)
para o cookie SameSite. `CORS_ORIGINS` deve conter a origem exata do app, inclusive
porta. Se usar `8083`, acrescente `http://localhost:8083` ao `.env` da API e reinicie-a.

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

## Autenticação, verificação e sessão

Normalização central em `app/domain/contacts.py`: e-mail em minúsculas, celular
brasileiro com DDD convertido para `+55...` e números internacionais com `+` em
E.164. E-mail e telefone permanecem únicos. Senhas têm 8–128 caracteres, sem
exigências de símbolos/maiúsculas, e são armazenadas com Argon2id. CPF não é utilizado.

| Método | Endpoint | Função |
| --- | --- | --- |
| POST | `/v1/auth/register` | Nome, contato, senha e confirmação; inicia verificação |
| POST | `/v1/auth/login` | Telefone/e-mail e senha; retoma verificação ou abre sessão |
| POST | `/v1/auth/verify` | Confirma código e cria Player/sessão |
| POST | `/v1/auth/resend` | Reenvia respeitando cooldown e orçamento de tentativas |
| POST | `/v1/auth/change-contact` | Corrige contato ainda não verificado e emite novo código |
| POST | `/v1/auth/refresh` | Rotaciona refresh e emite novo access token |
| POST | `/v1/auth/logout` | Revoga a sessão atual e limpa cookie Web |
| GET | `/v1/me` | Conta/perfil atuais, sem credenciais |
| PUT | `/v1/me/profile` | Completa/atualiza nome do Player autenticado |

No Swagger, use o cliente `native` para receber refresh no JSON e o botão
**Authorize** com o access token para consultar `/v1/me`. Para executar POSTs pelo
próprio Swagger, inclua sua origem (ex.: `http://localhost:8011`) em `CORS_ORIGINS`;
a validação de origem também se aplica às ferramentas no navegador.

Código numérico de seis dígitos, validade de 10 minutos, uso único, cinco erros
permitidos e cooldown de 60 segundos. O banco guarda HMAC do código e do token de
continuação, com finalidade e contato vinculados. O token de continuação expira
em 24 horas; login correto permite retomada sem criar outra conta. Novo envio
invalida o código anterior; novo login invalida o token de continuação anterior.
Senhas, códigos e tokens não são gravados em logs nem refletidos em erros de validação.

Access JWT dura 15 minutos e exige emissor, audiência, algoritmo fixo e ID de
sessão. O refresh é opaco, aleatório e armazenado no banco somente como hash.
Cada renovação consome o refresh e emite outro; reutilizar um refresh consumido
revoga toda aquela sessão. A sessão tem prazo absoluto de 30 dias, não prorrogado
por renovação. Logout invalida também access tokens em uso, pois cada requisição
protegida confere a sessão no banco. Cada login cria sessão independente para
permitir múltiplos dispositivos, sem painel de gerenciamento nesta etapa.

No Android/iOS, somente o refresh é persistido no **Expo SecureStore**; access
fica em memória. Na Web, refresh fica em **cookie HttpOnly, SameSite=Strict**, com
`Secure` em produção e caminho `/v1/auth`; access fica em memória. Nenhum token
vai para localStorage/sessionStorage. Requisições Web de autenticação exigem
`X-Eleven-Client: web` e Origin autorizado; clientes nativos usam `native` e refresh
no corpo JSON, sem consumir cookies. A API não permite transportar cookie Web
como refresh nativo. Headers personalizados e validação de origem protegem os
fluxos de cookie contra CSRF. CORS aceita apenas origens explícitas.

Renovações concorrentes do cliente são unificadas; na Web, Web Locks serializa
renovações entre abas quando disponível. Um replay real ou perda da resposta de
rotação pode exigir novo login; não há janela de tolerância que aceite refresh
já consumido. Logout depende da confirmação da API: se a conexão falhar, a tela
informa a falha e permite tentar de novo, sem alegar que houve revogação.

Rotas `/v1/me`, `/v1/teams`, `/v1/teams/{id}` e `/v1/teams/{id}/administration`
exigem token válido, sessão válida, conta ativa e contato verificado. Administração
também exige vínculo ativo e permissão do time. Usuários externos recebem 404
para times aos quais não pertencem. As regras Free/Pro não foram alteradas.

### Código de desenvolvimento e teste manual

Adicione explicitamente ao `.env` da raiz e reinicie a API:

```dotenv
APP_ENV=development
DEV_VERIFICATION_CODES=true
```

A opção é **false por padrão** e já foi ativada no `.env` local desta implementação.
O adaptador `DevelopmentSender` não envia SMS/e-mail: devolve `development_code`
apenas nas respostas de cadastro/reenvio/troca de contato autorizadas. O Expo em
modo de desenvolvimento mostra o código na tela de verificação, identificado como
ambiente local. Ele não é persistido em texto puro. Se perder o código, aguarde
o cooldown e solicite outro. Não compartilhe esse ambiente de simulação publicamente.

`APP_ENV=production` rejeita a configuração `DEV_VERIFICATION_CODES=true` na
inicialização. Sem adaptador configurado, o envio falha com 503; não existe fallback
silencioso de produção para desenvolvimento. `VerificationSender` é o contrato
para um futuro provedor, ainda não implementado.

Para testar, inicie PostgreSQL, aplique `alembic upgrade head`, inicie API e execute
`npm.cmd run mobile:web` na raiz. Então:

1. Clique em **Criar minha conta**, informe nome, e-mail OU celular e senha duas vezes.
2. Copie o **Código de desenvolvimento** mostrado e clique em **Confirmar**.
3. Confira a Home e as cinco abas; feche/reabra ou recarregue o app e confira a sessão.
4. Em **Perfil**, confira nome/contato e clique em **Sair da conta**.
5. Na tela de login, entre novamente com o mesmo contato e senha.

Foto é opcional. Em Perfil, selecione, confira a prévia e salve; é possível
substituir ou remover. Sem foto, o avatar padrão permanece. O campo `Player.photo_url`
existente guarda somente a referência da imagem processada, nunca URLs arbitrárias
enviadas no JSON. Consulte a seção de imagens abaixo.

### Proteção contra abuso e ambientes

Rate limit compartilhado e atômico no PostgreSQL, sem Redis: cadastro até 10
tentativas/IP/hora; demais endpoints de autenticação até 60/IP/15 minutos; login
até 10/contato normalizado/15 minutos; reenvio e troca de contato compartilham
até 5 tentativas/usuário/hora, inclusive após novo login. Erros de código são
persistidos e operações críticas usam locks. Respostas 429 incluem `Retry-After`.
Os identificadores dos contadores são HMACs, não contatos/IPs em texto puro.

Essa proteção básica não substitui proteção de borda contra ataques distribuídos.
Antes da publicação, definir proxy confiável, HTTPS, provedor real e rotina de
retenção/limpeza de contadores expirados e sessões/tokens após seu prazo absoluto.
Não remova hashes de refresh consumidos de sessões ainda válidas: são necessários
para detectar replay. Os comandos locais usam `--no-proxy-headers` para não confiar
em um `X-Forwarded-For` arbitrário. Em produção, configure proxies confiáveis explicitamente.

- `development`: `.env` local, Swagger disponível.
- `test`: testes usam `TEST_DATABASE_URL`, segredo exclusivo de teste e um schema
  aleatório por teste, removido ao final. O nome do banco deve terminar em `_test`.
- `production`: configurar `APP_ENV=production`, URLs e segredo via variáveis de
  ambiente, banco com usuário de privilégio mínimo e TLS conforme o provedor;
  HTTPS na publicação. CORS exige origens HTTPS; Swagger/OpenAPI públicos são desativados.
  Nunca usar o usuário de bootstrap local em produção. Configure `EXPO_PUBLIC_API_URL`
  com HTTPS e mantenha frontend/API no mesmo site para o cookie SameSite.

As escolhas seguem as bases documentadas do [Expo SDK 55](https://expo.dev/changelog/sdk-55),
do [FastAPI para hashing e JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
e do [PostgreSQL no Windows](https://www.postgresql.org/download/windows/).
Armazenamento e sessão seguem a separação de plataformas do
[Expo SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/) e as orientações
da [OWASP sobre sessões](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

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

Validação do Prompt 02: 45 testes passaram em PostgreSQL 18, incluindo cadastro por
telefone/e-mail, duplicidade, códigos, login, cookies/CSRF, refresh, revogação,
concorrência, rate limit e preservação de dados na migration incremental. Ruff,
formatação, mypy, ESLint e TypeScript passaram; Expo Doctor passou em 20/20
verificações; bundles Android/iOS/web foram exportados. A navegação pelas cinco
abas e o fluxo de cadastro → verificação → Home → reabertura → Perfil → logout →
login foram conferidos em Chromium, sem erros JavaScript. A restauração foi
testada também com falha de conexão e retry; tokens não apareceram em armazenamento JS.
A execução nativa em aparelho/simulador Android/iOS ainda não foi validada.
Resta um aviso de depreciação interno de Starlette/AnyIO nos testes, sem falhas.

## Times — Prompt 03

Em **Meus Times**, crie um time com nome, cidade, UF e uma ou mais modalidades (Campo,
Society / Fut7 e Futsal), inclusive no Free. O criador usa seu Player existente e recebe exatamente
um vínculo ativo, referenciado como Presidente. Time e vínculo são criados na
mesma transação. Todo novo time começa Free; nenhum campo do formulário altera
plano, Presidência, UUID ou código. As policies Free/Pro existentes são preservadas.

A migration incremental `0003_team_modalities` converte `modality` em `modalities`,
um array nativo PostgreSQL `varchar(40)[]`, mantendo a modalidade anterior como
único item inicial. `0001` e `0002` foram preservadas. O banco exige array não vazio,
unidimensional e sem itens nulos. A API valida cada modalidade pelo vocabulário
centralizado, remove repetições e usa ordem estável. Novas modalidades podem ser
acrescentadas ao vocabulário sem mudar a estrutura de persistência.
O downgrade para `0002` recusa execução se houver times com múltiplas modalidades,
evitando descartar escolhas silenciosamente. Não execute downgrade em dados reais.

No formulário, os chips permitem seleção múltipla; é obrigatório selecionar ao
menos uma modalidade para salvar. Perfil, lista e Home mostram os nomes separados
por `•`. Essa regra vale igualmente para **Free e Pro**.

UF usa seletor pesquisável com 26 estados e Distrito Federal. A lista apresenta
nome e sigla, como `Espírito Santo (ES)`, e aceita busca por nome/sigla, ignorando
acentos e caixa. Digitar na busca não altera a UF: é necessário selecionar uma opção.
Somente a sigla oficial é enviada/persistida; a API valida a lista oficial e
normaliza entradas como ` es ` para `ES`.

O código usa oito caracteres aleatórios de `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`,
sem 0/O/1/I. A unicidade é garantida pelo PostgreSQL; uma colisão gera outra
tentativa dentro de savepoint, sem deixar time/vínculo parcial. Renomear não muda o código.

| Método | Endpoint | Função |
| --- | --- | --- |
| GET | `/v1/teams` | Times com vínculo ativo, papel e permissão de edição |
| GET | `/v1/teams/options` | Modalidades e UFs centralizadas no domínio |
| POST | `/v1/teams/similar` | Aviso por nome, cidade, UF e alguma modalidade em comum |
| POST | `/v1/teams` | Cria time Free e vínculo do Presidente |
| GET | `/v1/teams/{id}` | Perfil do time autorizado |
| PUT | `/v1/teams/{id}` | Atualiza nome, cidade, UF e modalidades com permissão |
| GET | `/v1/teams/{id}/administration` | Contexto administrativo autorizado existente |

Todos exigem autenticação. A consulta de semelhança é uma exceção deliberada à
consulta por vínculo: retorna até cinco identidades públicas (nome, código,
cidade/UF e modalidades), nunca UUID, membros ou informações administrativas.
Compara nomes ignorando caixa e acentos, por inclusão de texto ou similaridade
de pelo menos 80%, na mesma cidade/UF e com ao menos uma modalidade em comum.
É uma heurística de aviso, não
uma garantia de encontrar toda duplicidade. **Criar mesmo assim** permite nomes
iguais. Semelhança não concede acesso ao perfil privado nem cria associação.

**Abrir** um time seleciona seu contexto. A Home mostra somente os dados desse
time; não há indicadores fictícios de jogos ou financeiro. A preferência salva
é apenas um UUID por User, em localStorage na Web e SecureStore no Android/iOS.
Dados e permissões vêm da API. A restauração e o retorno às telas de Times/Início
revalidam a lista; retornar ao app nativo também revalida. Se o vínculo não existir
mais, a seleção passa ao primeiro time autorizado (ordem nome/UUID), ou fica vazia.
Falhas de rede mostram erro/retry sem apresentar dados antigos como autorizados.
Trocar de conta recria o contexto e não reaproveita dados da conta anterior.

O campo `crest_url` foi preservado e recebe o escudo opcional enviado pelo formulário.
Free pode ter escudo e a criação funciona sem imagem.
Não há transferência de Presidência, exclusão, convites ou cobrança.

### Teste manual de times

Com PostgreSQL ativo, inicie a API em `apps/api`:

```powershell
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --no-proxy-headers --port 8011
```

Na raiz, execute `npm.cmd run mobile:web` e abra `http://localhost:8081`.
Swagger: `http://127.0.0.1:8011/docs`.

1. Entre com sua conta e abra **Mais → Meus Times / Trocar time → Criar time**.
2. Informe Tabajara e sua cidade; abra UF, pesquise `Esp` ou `ES` e selecione
   Espírito Santo (ES). Marque Society / Fut7 e Futsal; salve.
3. Confira Presidente, Free e código; edite o nome e confirme que o código permanece.
4. Volte a Meus times, crie outro time e alterne usando **Abrir**.
5. Confira a Home; feche/reabra e confira o último contexto.
6. Edite adicionando Campo ou removendo uma modalidade; confira o resultado após reabrir.
7. Para conferir o aviso, repita nome/cidade/UF e alguma modalidade, usando **Criar mesmo assim**.

Teste automatizado de navegador, com Expo já ativo em 8081, a partir de `apps/api`:

```powershell
uv run --with playwright playwright install chromium
uv run --with playwright pytest tests/browser_team_flow.py -q -s
```

Esse teste usa a fixture PostgreSQL `_test` com schema temporário, cria uma API
temporária em porta livre e encaminha somente as requisições do navegador de teste
para ela. Não grava dados na API/banco de desenvolvimento. Remove o schema e para
o servidor temporário ao terminar. Playwright não foi adicionado às dependências
do produto; capturas locais ficam em `.local` e não são versionadas.

Validação do Prompt 03 e ajuste: 70 testes backend e o fluxo Chromium passaram. Foram
conferidos criação, edição, aviso de semelhança, alternância, reabertura, vínculo
revogado, troca de conta e ID local manipulado, além de listas com uma/duas/três
modalidades, edição, rejeição de lista vazia e pesquisa/validação de UF.
A migration foi aplicada preservando o Tabajara FC com `['society']`, todos os
outros campos e os dados das demais tabelas. Nenhum dado de teste foi inserido
no banco de desenvolvimento. Alembic upgrade/check, Ruff/check de formatação,
mypy, ESLint e TypeScript passaram; Expo Doctor passou em 20/20 e a exportação
Android/iOS/Web foi concluída. API/Swagger em 8011 e Web em 8081 responderam;
o navegador carregou o bundle de desenvolvimento sem erros JavaScript.
Execução nativa em aparelho permanece pendente. Há apenas o aviso já existente
de depreciação Starlette/AnyIO no pytest.

## Elenco — Prompt 04

Acesse **Elenco** na barra inferior ou na Home do time selecionado.
A lista tem filtros Ativos/Inativos/Todos (padrão Ativos), contagem e situação da
conta. Presidente aparece pelo vínculo já existente, sem duplicação. Cadastro
manual exige apenas nome; apelido, telefone e e-mail são opcionais. Foto usa avatar
ou a imagem que o próprio jogador enviou no Perfil. Há edição, confirmação de
inativação e reativação sem apagar registros nem criar novo vínculo.

`0004_roster_management` torna `Player.user_id` opcional e adiciona nome local,
apelido e contatos a `TeamMembership`. Nome original permanece na identidade do
Player; alterações manuais são específicas daquele time. Quando há conta vinculada,
nome/contatos globais não são editáveis pelo Presidente; apenas apelido local.
Contatos manuais são restritos à gestão do elenco. Telefone/e-mail são normalizados
pela regra existente e nunca criam User nem vinculam contas automaticamente.

Free permite 24 ativos e Pro 100, incluindo o Presidente uma única vez. Cadastro
e reativação bloqueiam a mesma linha do time antes da contagem/escrita, impedindo
ultrapassar o limite por concorrência. Inativos não contam; a reativação também
respeita os limites de papéis administrativos já existentes. Não há atribuição
de administradores ou compra de plano nesta etapa.

Todos os endpoints abaixo começam com `/v1/teams/{team_id}/players`:

| Método | Sufixo | Ação |
| --- | --- | --- |
| GET | `?status=active\|inactive\|all` | Lista, contagens, limite e permissão |
| POST | vazio | Cadastro manual |
| POST | `/similar?exclude={membership_id}` | Aviso de duplicidade; exclusão opcional na edição |
| GET / PUT | `/{membership_id}` | Perfil / edição dos campos enviados |
| POST | `/{membership_id}/deactivate` | Inativação, exceto Presidente |
| POST | `/{membership_id}/reactivate` | Reativação com verificação de vagas |

Leitura exige vínculo ativo; escrita exige `manage_members` pelas policies atuais.
Cada membership é validado dentro do time autorizado. Não existe consulta global
de Player. O aviso compara nomes e contatos apenas no mesmo elenco, inclusive
inativos; coincidências exigem `confirm_duplicate: true` para continuar. Contatos
iguais continuam cadastros separados e não autorizam vinculação de conta.

Para testar, aplique `uv run alembic upgrade head` em `apps/api`, mantenha API em
8011 e execute `npm.cmd run mobile:web` na raiz. Entre, abra Tabajara FC → Elenco,
confira o Presidente, adicione um jogador só com nome e outro com opcionais.
Edite, inative, filtre Inativos, reative e recarregue para conferir a persistência.

Testes automatizados usam exclusivamente schemas descartáveis no banco `_test`.
Além de `uv run pytest -q`, com Expo ativo em 8081:

```powershell
uv run --with playwright pytest tests/browser_roster_flow.py tests/browser_team_flow.py -q -s
```

O upgrade preserva Tabajara FC, contas, sessões, modalidades, códigos e vínculos.
Upgrade/downgrade/upgrade é testado no banco isolado; downgrade com dados novos de
elenco é recusado para não descartar Players sem conta ou informações do vínculo.
Pendentes: convites/vinculação por aprovação, sem fluxos antecipados.
Execução nativa em aparelhos ainda exige validação manual.

Validação do Prompt 04: 88 testes backend, ciclos de migration e dois fluxos
Chromium aprovados (times e elenco). Ruff, formatação, mypy, ESLint e TypeScript
passaram; Expo Doctor 20/20 e exportações Web/Android/iOS concluídas. A comparação
antes/depois da `0004` confirmou a preservação de todas as linhas existentes.

## Eventos e presença — Prompt 05

Abra **Jogos** com um time selecionado. O Presidente e administradores Pro com
`manage_events` podem criar/editar/cancelar eventos e adicionar/remover convidados.
Membros ativos visualizam e respondem **VOU / NÃO VOU** somente por si; ausência
de resposta é **PENDENTE**. Contagens/listas usam o elenco ativo, sem contatos privados.
Convidados aparecem separadamente e não criam conta, jogador nem vínculo permanente.

Pelada pode repetir semanalmente com término opcional: deixe o término vazio para
continuar até cancelar. A criação e as consultas geram uma janela de até oito semanas,
com unicidade por série/data, sem tarefas agendadas ou geração infinita antecipada.
Após períodos sem acesso, geram-se somente próximas datas, sem preencher o passado.
Editar/cancelar um evento afeta apenas aquela ocorrência. **Encerrar recorrência**
impede novas ocorrências e cancela as datas de hoje em diante, preservando histórico,
respostas e convidados. Datas/horários são locais da partida; a janela usa a data local
do servidor. Respostas podem ser alteradas enquanto a ocorrência não estiver cancelada.
Jogo avulso aceita adversário textual opcional, sem vínculo com outro time.

`0005_events_attendance` adiciona `event_series`, `events`, `event_attendance` e
`event_guests`, além da permissão `manage_events`. Preserva tabelas e linhas anteriores;
downgrade é recusado se houver dados novos que seriam perdidos.

Endpoints abaixo começam com `/v1/teams/{team_id}/events`:

| Método | Sufixo | Ação |
| --- | --- | --- |
| GET / POST | vazio | Lista / cria evento (e recorrência opcional) |
| GET / PUT | `/{event_id}` | Detalha / edita uma ocorrência |
| PUT | `/{event_id}/attendance` | Confirma/altera a própria presença |
| POST | `/{event_id}/cancel` | Cancela uma ocorrência |
| POST | `/{event_id}/cancel-series` | Encerra a recorrência |
| POST | `/{event_id}/guests` | Adiciona convidado |
| POST | `/{event_id}/guests/{guest_id}/remove` | Remove convidado daquela ocorrência |

Aplique `uv run alembic upgrade head` em `apps/api`, mantenha API na porta **8011**
e execute `npm.cmd run mobile:web` na raiz. Teste pelo fluxo **Jogos → Criar evento**.
Com Expo ativo em 8081, o teste isolado de navegador roda em `apps/api`:
`uv run --with playwright pytest tests/browser_events_flow.py -q -s`.
Não inclui sorteio, placar, estatísticas, campeonatos, busca de adversários ou financeiro.

Validação do Prompt 05: 114 testes backend e três fluxos Chromium aprovados (times,
elenco e eventos). Ruff, formatação, mypy, ESLint e TypeScript passaram; Expo Doctor
20/20 e exportações Web/Android/iOS concluídas. A aplicação da `0005` comparou todas
as linhas anteriores e preservou o Tabajara FC. Validação em aparelhos físicos permanece pendente.

## Navegação e contexto do time

**Meus Times → Abrir time → Início do time**. O Início mostra escudo, nome,
cidade/UF, plano e atalhos para Jogos, Elenco e Perfil do time, além de **Trocar time**.
Com time selecionado, a barra inferior contém **Início | Jogos | Elenco | Mais**.
**Mais** reúne Meus Times/Trocar time, Notificações e Perfil pessoal. Sem time,
as abas pessoais dão acesso à criação; convites/entrada em novos times seguem fora do escopo.

Jogos, detalhes/formulário de evento e todas as telas de Elenco mantêm cabeçalho
compacto do time. Nenhum formulário pede nova seleção: o `team_id` vem exclusivamente
do `TeamContext` já existente. Ao trocar time, os painéis são remontados, descartando
rascunhos e resultados do contexto anterior. A persistência e revalidação por User
continuam iguais, e a API continua validando vínculo, permissão e isolamento.
Nenhuma migration ou alteração de regra de negócio foi necessária.

Para validar: abra Tabajara FC, confira Início/Jogos/Elenco, use Trocar time,
confira os dados do segundo time e recarregue. Os testes de navegador usam somente
banco isolado e cobrem troca, persistência, formulários e seleção manipulada.
Não há módulos futuros exibidos como funcionalidades disponíveis.

## Foto de perfil e escudo

Em **Perfil → Alterar foto**, selecione a imagem, confira a prévia e clique em
**Salvar foto**. Substituição e remoção também exigem salvar. Foto aparece no Perfil,
cabeçalho pessoal e perfil do jogador no elenco, usando o componente `Avatar`.
Em **Meus Times → Criar time** ou **Início → Perfil do time → Editar time**, selecione um escudo opcional e salve o time.
`TeamBadge` preserva a proporção e é reutilizado no perfil, lista e Home do time.
Se o time for salvo mas o upload falhar, o formulário permite repetir o envio ou
continuar sem alterar o escudo; não cria um segundo time. O escudo é reutilizado na navegação do time.

São aceitos **JPEG/JPG, PNG e WebP estáticos**, até **5 MB** e **20 megapixels**.
O backend decodifica o conteúdo real, sem confiar na extensão/MIME do cliente,
corrige orientação EXIF, remove metadados e limita o lado maior a **512 pixels**,
sem ampliar imagens menores. Saída JPEG qualidade 85; PNG quando há transparência.
Multipart tem limite de corpo inclusive para envio sem `Content-Length`.

Os campos existentes `Player.photo_url` e `Team.crest_url` guardam referências
relativas `/v1/media/{identificador}.jpg|png`. **Não foi necessária migration 0006**;
`0001`–`0005` permanecem intactas. Arquivos não ficam em Base64 no PostgreSQL.
`ImageStorage` é a interface de armazenamento; `LocalImageStorage` usa
**`.local/media` na raiz**, ignorada pelo Git. `MEDIA_ROOT` aceita caminho absoluto
ou relativo à raiz e pode apontar para um volume persistente. O adaptador pode ser
substituído por object storage sem mudar as regras de autorização/substituição.

Arquivos recebem UUID, sem reaproveitar nome do upload. Só imagens processadas e
ainda referenciadas são servidas, por URL aleatória pública; não há listagem ou
exposição dos diretórios internos. Substituição grava o novo arquivo antes do commit
e remove o anterior depois; falha de banco remove o novo. Falha na exclusão gera log
e deixa um órfão inacessível pela API, sem quebrar a imagem atual. Produção precisa
de armazenamento durável/backup e rotina de limpeza de órfãos após falhas/interrupções,
ou adaptador object storage; o adaptador cloud não foi implementado nesta etapa.

| Método | Endpoint | Ação |
| --- | --- | --- |
| POST | `/v1/me/photo` | Envia/substitui a própria foto; multipart com campo `file` |
| POST | `/v1/me/photo/remove` | Remove a própria foto |
| POST | `/v1/teams/{team_id}/crest` | Envia/substitui escudo; multipart com campo `file` |
| POST | `/v1/teams/{team_id}/crest/remove` | Remove escudo |
| GET | `/v1/media/{key}` | Retorna apenas imagem processada ainda referenciada |

Escritas exigem sessão válida. Foto identifica Player pelo User autenticado, sem
ID de destino no payload. Escudo exige vínculo ativo e `manage_team`; no Free,
somente Presidente. As policies e limites anteriores não mudaram.

Seleção usa [Expo ImagePicker SDK 55](https://docs.expo.dev/versions/v55.0.0/sdk/imagepicker/);
processamento usa [Pillow](https://pillow.readthedocs.io/en/stable/reference/Image.html).
O app nativo usa a biblioteca de fotos, sem solicitar câmera ou microfone.
Após instalar dependências atualizadas, inicie os comandos usuais na porta 8011/8081.
Teste isolado de navegador (API/banco `_test` e arquivos temporários próprios):
`uv run --with playwright pytest tests/browser_images_flow.py -q -s`, em `apps/api`.

## Formação de times da pelada — Prompt 06

Abra **Jogos → Pelada → Montar times** no time selecionado. O gestor confere os
confirmados VOU e convidados, retira participantes somente deste sorteio, marca
os goleiros e escolhe o número de equipes. A previsão mostra as quantidades antes
de sortear. O recurso é **Free e Pro**, com as permissões de gestão de eventos atuais.
Membros comuns têm acesso somente à consulta do resultado, por **Ver times da pelada**.

O sorteio aleatório embaralha goleiros primeiro e os demais separadamente, distribuindo
em rodízio. Totais e goleiros diferem por no máximo um entre as equipes. Falta de goleiro
gera aviso, sem bloquear. Limites técnicos: **2–32 equipes e até 256 participantes**,
sem permitir mais equipes que participantes. Os limites do elenco continuam 24/100.

Resultado e ajustes persistem. **Mover → Time N** ajusta um participante, sem arrastar;
ajustes manuais podem deixar quantidades diferentes. **Refazer sorteio** permite
revisar a configuração e exige confirmação antes de substituir a formação atual.
Versão e bloqueio transacional impedem sobrescrever alterações concorrentes sem revisão.

A lista atual é comparada com a assinatura dos IDs elegíveis na época do sorteio,
incluindo quem foi excluído daquela formação. Mudanças de presença, atividade do elenco
ou convidados exibem **“A lista de participantes mudou desde o último sorteio.”** ao
consultar/atualizar. Use **Atualizar participantes** para conferir alterações de outras
pessoas enquanto a tela está aberta; não há atualização em tempo real nesta etapa.
O resultado anterior permanece até o gestor decidir refazer.

`0006_event_formations` adiciona `event_formations`, `formation_squads` e
`formation_participants`. Participantes referenciam Membership **ou** EventGuest,
com nome e goleiro daquela formação; exclusões permanecem sem equipe atribuída.
Equipes temporárias não são `Team`. Não se armazena a formação inteira em JSON.
Convidados removidos recebem `removed_at`, saem da lista ativa e continuam referenciáveis
no resultado salvo. Downgrade é bloqueado se perder formação ou restaurar convidados removidos.
Migrations 0001–0005 não foram alteradas.

Endpoints sob `/v1/teams/{team_id}/events/{event_id}/formation`:

- `GET`: participantes atuais, resultado e aviso de mudança.
- `POST /draw`: sorteio inicial/substituição confirmada.
- `PUT /participants/{participant_id}`: move para equipe da mesma formação.

Aplique `uv run alembic upgrade head` em `apps/api`. API permanece em **8011** e
Web em **8081** (`npm.cmd run mobile:web` na raiz). Testes usam PostgreSQL isolado;
com Expo ativo: `uv run --with playwright pytest tests/browser_formations_flow.py -q`.
Não há sorteio por habilidade/posição, placar, estatísticas ou financeiro.

## Partidas e resultados da pelada — Prompt 07

Abra **Jogos → Pelada → Montar times**, salve a formação e volte à pelada.
A seção **Partidas** permite escolher duas equipes salvas, criar e iniciar uma partida,
controlar o placar com +/− e finalizar com confirmação. Revanche é permitida.
Membros ativos consultam; Presidente e gestores com `manage_events` administram,
conforme as policies Free/Pro existentes. O placar altera somente o total de gols.

Cada linha de `event_matches` pertence a time, ocorrência e formação. FKs compostas
impedem equipes de outra formação/evento/time; check impede jogar contra si mesmo.
Placares inteiros vão de 0 a 999 e começam em 0 × 0. Histórico segue criação/ID.
Estados: `SCHEDULED → IN_PROGRESS → FINISHED`; qualquer estado não cancelado pode
ir para `CANCELLED`, sempre com confirmação. Cancelamento é terminal, preserva
placar e histórico e não representa resultado válido. Não existe exclusão física.
Finalização exige início e confirmação. Resultado final pode ser corrigido com
confirmação, sem reabrir a partida; `corrected_at`, `corrected_by_user_id`, versão e
`updated_at` identificam a última correção. A interface mostra quando foi corrigido.
Ocorrência cancelada mantém consulta e bloqueia todas as escritas de partidas.

A primeira partida, mesmo posteriormente cancelada, bloqueia refazer o sorteio e
mover participantes. **Atualizar participantes** continua sendo uma consulta e não
muda as equipes salvas. Presenças, convidados e elenco mantêm seus próprios fluxos;
nenhuma mudança de elegibilidade modifica silenciosamente a formação ou resultados.
O bloqueio evita destruir referências: o sorteio anterior substituía as equipes.

Todas as escritas usam o lock de Team existente. Alterações exigem `expected_version`;
criação exige `expected_formation_version`. Versão desatualizada retorna 409 e a
interface pede recarregamento antes de novas ações, sem sobrescrever outro dispositivo.

Endpoints sob `/v1/teams/{team_id}/events/{event_id}/matches`:

| Método | Sufixo | Ação |
| --- | --- | --- |
| GET / POST | vazio | Histórico / criação |
| GET | `/{match_id}` | Consulta individual |
| POST | `/{match_id}/start` | Inicia |
| PUT | `/{match_id}/score` | Placar ou correção confirmada |
| POST | `/{match_id}/finish` | Finaliza com confirmação |
| POST | `/{match_id}/cancel` | Cancela com confirmação |

Migration incremental **0007_event_matches**; 0001–0006 permanecem intactas.
Downgrade é recusado se houver partidas. A aplicação local comparou todas as linhas
das 16 tabelas anteriores e preservou integralmente os dados, incluindo TABAJARA FC.
Testes usam exclusivamente PostgreSQL `_test` e schemas descartáveis.

Para validar manualmente: em `apps/api`, `uv run alembic upgrade head` e
`uv run uvicorn app.main:app --reload --no-proxy-headers --port 8011`.
Na raiz, `npm.cmd run mobile:web`. Abra a pelada, crie duas partidas, finalize uma,
corrija seu resultado e cancele a outra; recarregue e confira o histórico.
Com Expo em 8081, execute em `apps/api`:
`uv run --with playwright pytest tests/browser_matches_flow.py -q`.
O fluxo cobre também empate, seleção de equipes distintas e larguras 320/390/1280.
Android/iOS têm bundles exportáveis; execução em aparelhos reais requer validação manual.

Validação do Prompt 07: 157 testes backend e seis fluxos Chromium aprovados.
Ruff, formatação, mypy, ESLint, TypeScript, Alembic check e git diff --check passaram.
Expo Doctor 20/20; bundles Web/Android/iOS gerados. Servidor Web: HTML e bundle 200,
Web Bundled e navegação conferidos. API/ready/Swagger em 8011 responderam.
Permanece o aviso já existente de depreciação Starlette/AnyIO nos testes.

## Próxima etapa

Definir provedor de verificação para publicação, armazenamento durável de imagens e futura
recuperação de conta. Entregar assets oficiais e validar em Android/iOS reais.
Convites para contas, financeiro e assinaturas continuam fora deste escopo.

O `npm audit` identificou 9 alertas moderados na cadeia de ferramentas do Expo
(`xcode` → `uuid`), sem alertas altos/críticos. A correção automática sugerida
regride o Expo para SDK 46, portanto não foi aplicada. Acompanhar a correção
upstream antes de preparar a distribuição nativa.
