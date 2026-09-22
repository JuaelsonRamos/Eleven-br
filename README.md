# ELEVEN BR

**Seu time. Seu jogo.** Fundação técnica para gestão de futebol amador.

O projeto entrega a fundação, cadastro, verificação de contato, login, sessão,
perfil inicial e gestão básica de times. As cinco abas ficam na área autenticada.
Não inclui elenco, jogos, financeiro ou cobrança.

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
    src/screens/         # Entrada, cadastro, verificação, login e cinco abas
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
e seleção; Jogos e Notificações continuam placeholders.

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

Foto é opcional: a interface usa avatar e permite continuar sem upload. O campo
`Player.photo_url` está preparado, mas não há endpoint para gravar URLs arbitrárias
ou arquivos; armazenamento de fotos será definido em tarefa posterior.

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

Em **Times**, crie um time com nome, cidade, UF e uma ou mais modalidades (Campo,
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

O campo `crest_url` foi preservado. Upload de escudo continua pendente de uma
solução de armazenamento; Free pode ter escudo e a criação funciona sem imagem.
Não há transferência de Presidência, exclusão, elenco, convites ou cobrança.

### Teste manual de times

Com PostgreSQL ativo, inicie a API em `apps/api`:

```powershell
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --no-proxy-headers --port 8011
```

Na raiz, execute `npm.cmd run mobile:web` e abra `http://localhost:8081`.
Swagger: `http://127.0.0.1:8011/docs`.

1. Entre com sua conta e abra **Times → Criar time**.
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

## Próxima etapa

Definir provedor de verificação para publicação, armazenamento de fotos e futura
recuperação de conta. Entregar assets oficiais e validar em Android/iOS reais.
Elenco, convites, jogos, financeiro e assinaturas continuam fora deste escopo.

O `npm audit` identificou 9 alertas moderados na cadeia de ferramentas do Expo
(`xcode` → `uuid`), sem alertas altos/críticos. A correção automática sugerida
regride o Expo para SDK 46, portanto não foi aplicada. Acompanhar a correção
upstream antes de preparar a distribuição nativa.
