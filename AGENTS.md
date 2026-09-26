# ELEVEN BR — instruções para agentes

Este arquivo orienta o trabalho em todo o repositório. Leia-o antes de alterar
arquivos e consulte a implementação atual e o `README.md`. Implemente somente o
escopo solicitado; as fases e regras futuras abaixo não autorizam sua antecipação.

## Identidade e princípio do produto

**ELEVEN BR — Seu time. Seu jogo.** Plataforma brasileira para gestão do futebol amador.

> O aplicativo deve resolver a burocracia do futebol amador, e não criar uma nova burocracia.

Priorize mobile, poucos passos nas operações frequentes e formulários curtos.
Evite confirmações desnecessárias. Ações destrutivas, financeiras, mudança de
propriedade e perda de dados podem exigir confirmação adicional. Simplicidade
de uso não permite simplificar incorretamente regras de negócio.

## Escopo progressivo

O estado atual inclui a fundação, o Prompt 02 (conta, verificação, sessão e perfil)
o Prompt 03 (criação, perfil, edição e seleção de times), o Prompt 04 (elenco)
o Prompt 05 (eventos, peladas e presença), o Prompt 06 (formação de times da pelada)
o Prompt 07 (partidas e resultados da pelada) e o Prompt 08 (gols, assistências e cartões).
As áreas do aplicativo exigem
autenticação; Jogos apresenta eventos do time selecionado e Notificações continua placeholder. Verificação local é
simulada com opção explícita; provedor de produção e cobrança não foram implementados.

Times reutilizam a estrutura existente; a migration `0003_team_modalities` converte
a modalidade anterior em um array PostgreSQL não vazio, preservando o valor.
Uma ou mais modalidades estão disponíveis em **Free e Pro**, sem exclusividade Pro.
Novos times são Free, com um vínculo ativo para o Player criador e Presidência derivada
da FK existente. Códigos aleatórios de oito caracteres são únicos e imutáveis;
colisões são tratadas com savepoint e constraint. O vocabulário de modalidades e
UFs está em `app/domain/team_identity.py`, consumido pelo app via API. `modalities`
é uma lista JSON nos contratos e um array `varchar(40)[]` no banco, nunca CSV.
O seletor de UF pesquisa os 26 estados e o DF por nome/sigla e envia somente a
sigla oficial. O backend também valida e normaliza a UF.
O aviso de semelhança divulga somente identidade pública limitada e não impede
nomes iguais. Escudo opcional usa o upload de imagens e o campo `Team.crest_url` existente.

`apps/mobile/src/teams` mantém o contexto de time. Persista somente o UUID,
separado por User; restaure dados pela lista de vínculos ativos da API. Ao perder
acesso, descarte a preferência inválida e selecione um time autorizado ou nenhum.
Não confundir seleção local com autorização; não persistir dados privados de times.
Os testes de navegador em `apps/api/tests/browser_team_flow.py` são opt-in e usam
API temporária/banco `_test`; nunca inserir exemplos automaticamente no banco de desenvolvimento.

- **MVP 1 — Base utilizável:** conta, perfil, times, elenco, convidados, peladas,
  presença, sorteio básico, mensalidades, Pix, notificações e jogos contra adversários.
- **MVP 2 — Pro/avançado:** sorteio inteligente, financeiro completo, estatísticas
  avançadas, permissões administrativas avançadas, importações, exportações,
  formação tática e outros recursos Pro.
- **MVP 3:** campeonatos.

Não implementar vários módulos grandes simultaneamente. Não inventar regras de
produto. Quando uma decisão realmente necessária estiver indefinida, apresente
a questão objetivamente antes de criar uma dependência arquitetural difícil de reverter.
Campeonato não pertence necessariamente a um time; seu organizador será um
conceito independente em fase futura. Não criar essa modelagem antecipadamente.

## Arquitetura de negócio obrigatória

**User != Player != TeamMembership. Nunca fundir esses conceitos.**

- `User`: conta e autenticação. Cadastro não utiliza CPF; login deverá suportar
  telefone e/ou e-mail.
- `Player`: identidade esportiva da pessoa.
- `TeamMembership`: vínculo do jogador com determinado time.

O Prompt 04 permite `Player.user_id` nulo, mantendo unicidade quando há User.
Cadastro manual cria Player e vínculo atomicamente, sem criar conta e sem vincular
por coincidência de contato. `TeamMembership` guarda `roster_name`, `nickname`,
`contact_phone` e `contact_email`. Edições do cadastro manual são locais ao vínculo;
não alteram a identidade global do Player compartilhado com outro time. Para
Player com conta, nome e contatos globais permanecem sob controle do titular;
no elenco, a administração pode editar apenas o apelido local. Contatos manuais
são visíveis somente a quem pode gerenciar o elenco; contatos de User não são expostos.

Elenco usa `Permission.MANAGE_MEMBERS` e as policies existentes. Membros ativos
podem visualizar; somente os autorizados gerenciam. Cadastro, edição e mudanças
de status bloqueiam a linha do time antes de autorizar/contar/escrever. Reativação
reutiliza Player/Membership e respeita limites ativos e de papéis já existentes.
O Presidente conta uma vez e não pode ser inativado pelo fluxo comum.
Duplicidades são verificadas apenas dentro do time, incluindo inativos; inclusão
ou edição com coincidência exige confirmação explícita, inclusive para contatos.
Não criar endpoints de consulta global de Player nem vínculo automático por contato.
`0004_roster_management` preserva registros existentes; o downgrade é bloqueado
se houver dados do elenco que a estrutura anterior não consegue representar.

Eventos usam `Permission.MANAGE_EVENTS` e as policies existentes. `0005_events_attendance`
adiciona séries semanais, ocorrências, presença única por evento/vínculo e convidados
exclusivos do evento. FKs compostas mantêm presença e ocorrência no mesmo time.
Respostas são derivadas do User autenticado, somente para seu vínculo ativo; nunca
aceitar ID de jogador enviado pelo cliente para responder por outra pessoa.
Recorrência pode ter término ou ser indefinida. O modelo semanal gera até oito
semanas adiante ao consultar Jogos, sob bloqueio do time e chave única série/data.
Não gerar histórico faltante nem sobrescrever ocorrências editadas/canceladas.
Edição e cancelamento individuais valem só para a ocorrência. Encerrar recorrência
impede novas datas e cancela ocorrências de hoje em diante, preservando histórico,
respostas e convidados. Datas/horários são locais da partida; a janela usa a data
local do servidor. Cancelamento encerra respostas; nenhuma ocorrência é apagada.
Convidados não criam Player, User ou Membership. Não antecipar placar,
estatísticas, busca de adversários ou financeiro.

Formações usam `Permission.MANAGE_EVENTS`, também no Free. `0006_event_formations`
cria formação única por ocorrência, equipes temporárias e participantes relacionais,
com FKs compostas para isolar time/evento/formação. Não criar Team permanente no sorteio.
Pool inclui somente vínculos ativos com VOU e convidados não removidos. Exclusão e goleiro
são locais à formação; não alteram presença nem Player. `event_guests.removed_at` preserva
o convidado histórico; consultas de presenças e candidatos filtram removidos.
Sorteio aleatório embaralha goleiros e demais separadamente e distribui em rodízio,
com diferença máxima de um no total e nos goleiros. Limites: 2–32 equipes, até 256
participantes; nunca mais equipes que selecionados. Nenhum bloqueio por falta de goleiros.
Fingerprint do pool completo (inclusive excluídos) detecta mudança de elegibilidade sem
alterar silenciosamente o resultado. Refazer exige confirmação e versão atual; mover
exige participante e destino da mesma formação. Escritas usam o lock de Team existente.
Membro ativo pode consultar; apenas gestores autorizados alteram pelada aberta.
Não adicionar ranking, habilidade, cores/coletes ou estatísticas nesta etapa.

Partidas (`0007_event_matches`) pertencem à ocorrência e às equipes da formação por
FKs compostas. Usam `MANAGE_EVENTS`, lock de Team e versão otimista em toda alteração.
Primeira partida bloqueia refazer formação e mover participantes, inclusive se cancelada.
Consulta de participantes não modifica a formação. Placar 0–999; início obrigatório
antes de finalizar. Finalização, cancelamento e correção final exigem confirmação.
Cancelada é terminal e preservada; correção registra último autor/data e updated_at.
Evento cancelado permite somente leitura de partidas. Downgrade com partidas é bloqueado.

`0008_match_events` adiciona gols e cartões ligados ao participante salvo na formação,
com assistência opcional no próprio gol. FKs compostas isolam partida/formação/equipe;
backend restringe participantes às duas equipes da partida. Assistência exige outro
participante da mesma equipe. Convidados usam FormationParticipant/EventGuest, sem
criar conta/Player/vínculo. Participação histórica independe da presença/elenco atuais.
MANAGE_EVENTS autoriza escritas em partidas iniciadas/finalizadas de ocorrência aberta;
canceladas são somente leitura. Placar oficial nunca é derivado ou alterado pelos gols
identificados; comparação é informativa. Todas as escritas usam lock de Team e a versão
da partida, incrementada também pelos registros; envio repetido com versão antiga é 409.
Remoção confirmada é lógica (`removed_at`); criação e última alteração guardam autor/data.
Não implementar rankings, estatísticas consolidadas ou agregação na formação nesta etapa.
Downgrade com registros, inclusive removidos, é bloqueado.

Foto própria e escudo usam `Player.photo_url`/`Team.crest_url`, sem migration extra.
Upload multipart aceita JPEG/PNG/WebP reais, até 5 MB e 20 megapixels, com orientação
corrigida, metadados removidos e lado máximo 512 px. Só o titular altera sua foto;
escudo exige `manage_team` pelas policies existentes. Nunca aceitar ID arbitrário
para alterar foto global. Imagens ficam em `.local/media` (`MEDIA_ROOT` configurável),
com nomes UUID e referências relativas `/v1/media/...`; nunca Base64 no banco.
`ImageStorage` separa armazenamento da aplicação. Persistir arquivo novo antes do
commit e apagar o antigo depois; em rollback remover o novo. Arquivos órfãos não
são servidos. URLs de mídia são públicas para quem possui a URL aleatória, somente
enquanto referenciadas, sem listagem de diretórios. Produção precisa de volume
durável/backup ou adapter object storage e rotina de limpeza para órfãos após falhas.
`ImageSelector`, `Avatar` e `TeamBadge` são reutilizáveis; preservar navegação atual.
Na criação do time, falha no escudo permite repetir o envio sem criar outro time.

Um usuário pode participar de vários times, ser jogador em um, administrador em
outro e Presidente em outro, inclusive Presidente de vários times. Papéis,
permissões, dados e configurações devem respeitar o contexto de cada time.
Nunca armazenar papéis administrativos de time globalmente em `User` ou conceder
acesso porque a pessoa administra outro time.

Cada time possui **exatamente um Presidente**, com autoridade administrativa
principal. Na implementação atual, `Team.president_membership_id` referencia um
vínculo do próprio time por FK composta, obrigatória e diferida até o commit.
Presidente é derivado dessa referência, não de um papel global nem de um segundo
campo concorrente. Preserve essa integridade e a criação transacional de time/vínculo.

## Planos e permissões

O plano e a futura assinatura pertencem ao **Team**, nunca ao User ou Presidente.

| Política | Free | Pro |
| --- | --- | --- |
| Jogadores ativos por time | Até 24 | Até 100 |
| Administração | Somente Presidente | Presidente + até 5 responsáveis administrativos |
| Recursos | Básicos | Avançados, com permissões granulares |

Somente jogadores ativos contam para os limites; inativos não contam.
Permissões administrativas são granulares e por vínculo. Elenco, jogos, peladas,
financeiro, avaliações, agenda e estatísticas são exemplos de áreas futuras,
não permissões a implementar sem solicitação.

Nunca excluir dados, jogadores ou histórico automaticamente por limite ou downgrade.
Se um time Pro com mais de 24 ativos voltar ao Free, preserve os jogadores e o
histórico e bloqueie novas adições/ativações enquanto exceder o limite; ao atingir
o limite também não permita ultrapassá-lo. Voltar ao Pro restaura os recursos
correspondentes. No Free, somente o Presidente administra, mesmo que existam
vínculos administrativos preservados do Pro.

Centralize regras em `apps/api/app/domain/policies.py` (`ENTITLEMENTS` e `allows`).
Não espalhar verificações como `if plan == "PRO"` quando a política central resolve
a decisão. As operações em `apps/api/app/application/teams.py` bloqueiam a linha
do time antes de contar/incluir membros. Preserve a proteção contra concorrência;
reativação usa as mesmas políticas e transações; futuras trocas de papel ou plano
também devem usá-las. Limites de plano não são garantidos por escritas SQL diretas.
O fluxo de downgrade ainda não está implementado; esta seção define sua evolução.

## Stack e estrutura reais

Preserve o monorepo, npm workspaces no frontend e uv no backend. Não trocar
framework, ORM, banco, gerenciador ou estrutura principal sem solicitação explícita.

| Caminho | Responsabilidade |
| --- | --- |
| `apps/mobile` | React Native, Expo SDK 55, TypeScript, React Navigation e React Native Web |
| `apps/mobile/src/components/ui.tsx` | Componentes básicos reutilizáveis |
| `apps/mobile/src/theme.ts` | Tema do aplicativo |
| `apps/mobile/assets` | Assets oficiais futuros |
| `apps/api/app/domain` | Vocabulário, permissões e políticas de negócio |
| `apps/api/app/application` | Operações, transações e autorização por contexto |
| `apps/api/app/infrastructure` | SQLAlchemy, PostgreSQL, configuração e segurança |
| `apps/api/app/presentation` | REST/FastAPI, dependências e contratos Pydantic |
| `apps/api/migrations` | Migrations Alembic |
| `apps/api/tests` | Testes de segurança e integração com PostgreSQL |
| `packages/shared/src/index.ts` | Identidade visual e vocabulário TypeScript compartilhado |
| `scripts` | Inicialização/parada do PostgreSQL local no Windows |

Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2 e PostgreSQL são a base
do backend. Preserve `package-lock.json` e `apps/api/uv.lock` para instalações reproduzíveis.

## Backend, banco e segurança

Mantenha a separação entre domínio, aplicação, infraestrutura e apresentação.
Routers não devem concentrar regras de negócio. Evite arquivos gigantes,
dependências circulares, duplicação e abstrações sem necessidade. Valide entradas,
use transações quando necessário e preserve constraints e integridade referencial.

Mudanças persistentes de schema exigem migrations Alembic incrementais, revisadas
e testadas. Não editar migrations já aplicadas quando for necessária nova migration;
a fundação existente é `0001_foundation.py`. Preserve dados sempre que possível e
não dependa de recriar bancos em produção. Não execute downgrade destrutivo em
bancos com dados a preservar. PostgreSQL é o banco principal; não substituir por
SQLite para funcionalidades de produção. Eventual teste com SQLite deve ser
explicitamente isolado e justificado, sem substituir validações específicas de PostgreSQL.

O isolamento entre times é crítico. Nunca confiar apenas nos IDs do frontend.
Para acesso protegido, valide autenticação, conta ativa, vínculo ativo, time,
papel, permissão e capability do plano quando aplicável. Alterar um ID na
requisição não pode liberar dados privados ou administrativos de outro time.
Preserve a autorização em `require_membership` e nas dependências da API; operações
internas de escrita não dispensam a autorização no futuro caso de uso público.

Nunca armazenar senha em texto puro, commitar secrets, colocar credenciais reais
no código, expor tokens em logs ou retornar dados sensíveis desnecessários.
Preserve hashing seguro e validação de tokens existentes. Configurações sensíveis
usam variáveis de ambiente; não transforme auxiliares internos de emissão de token
em login público sem implementar o fluxo de autenticação solicitado.

## Mobile, UX, marca e acessibilidade

Com time selecionado, as abas são **Início, Jogos, Elenco e Mais**. Mais dá acesso
às áreas pessoais: Meus Times/Trocar time, Notificações e Perfil. Sem time, mostre
Meus Times, Notificações e Perfil, com acesso à criação. Abrir um time leva ao seu
Início. O painel identifica escudo, nome, cidade/UF e plano, com atalhos Jogos e Elenco.
Use somente o `TeamContext` existente e sua persistência por User; não criar outra
seleção. Telas operacionais recebem o time validado e usam seu ID em todas as operações.
`TeamHeading` identifica o time inclusive nos formulários. Remonte os painéis por ID
e bloqueie conteúdo durante revalidação/erro para não misturar dados ou rascunhos.
As rotas pessoais permanecem acessíveis pelo menu sem ocupar abas do contexto do time.
Administração fica dentro do time, conforme permissões. Não antecipar módulos futuros.

Interface predominantemente clara: branco como base, verde como identidade,
dourado moderado para destaques e azul de apoio. Áreas especiais podem usar
fundos verdes/escuros. Paleta oficial:

| Token de marca | Cor |
| --- | --- |
| Verde principal | `#075E45` |
| Dourado | `#F2B705` |
| Azul | `#123B66` |
| Branco | `#FFFFFF` |
| Grafite | `#182026` |
| Verde claro | `#E8F3EF` |

Use os tokens de `packages/shared/src/index.ts` e `apps/mobile/src/theme.ts`;
não espalhe hexadecimais quando já houver token correspondente. Evite aparência
empresarial, excesso de cores, gradientes, cards, texto, decoração sem função e
telas burocráticas. O conceito aprovado de logo é o monograma E11; os assets
oficiais serão fornecidos. Não redesenhar ou substituir a marca por conta própria;
até lá, use placeholders discretos.

Reutilize componentes quando houver reutilização real, sem duplicação desnecessária
nem abstrações prematuras. Telas com dados devem considerar loading, vazio, erro,
sucesso e sem permissão quando aplicável. Não esconder erros; mensagens devem
ser curtas e claras. Preserve contraste, labels acessíveis, legibilidade, safe
areas, áreas de toque apropriadas e suporte a diferentes tamanhos de tela.

## Forma de trabalhar e Git

Antes de modificar, inspecione os arquivos relacionados, compreenda a implementação
e preserve decisões anteriores. Faça a menor alteração coerente que resolva a tarefa.
Não reescreva módulos, renomeie estruturas, refatore arquitetura estável por gosto,
adicione dependências sem necessidade ou remova código válido fora do escopo.

Antes de adicionar dependência, verifique soluções existentes, necessidade real,
manutenção e compatibilidade. Não aplique mudanças destrutivas automaticamente;
`npm audit fix --force` exige análise e autorização.

Não incluir no Git `.env`, secrets, tokens, bancos locais, caches, `node_modules`,
builds ou temporários. Preserve `.env.example` sem segredos. Não fazer force push,
apagar histórico ou executar comandos destrutivos de Git sem autorização explícita.

Fluxo preferencial: planejar → implementar → testar → executar → revisar visual
e funcionalmente → commit → próxima funcionalidade. Respeite o escopo da tarefa
e não inclua alterações alheias no commit.

## Comandos existentes

Os comandos abaixo usam PowerShell/Windows. `npm.cmd` e `npx.cmd` evitam bloqueios
dos wrappers `.ps1`. Cada bloco informa seu diretório; não encadeie mudanças de
diretório de blocos diferentes sem voltar à raiz.

**Na raiz do repositório — instalação e PostgreSQL local:**

```powershell
uv python install 3.13
npm.cmd ci
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start-local-postgres.ps1
```

O script espera PostgreSQL em `C:\Program Files\PostgreSQL\18\bin` (ajustável via
`-PostgresBin`). Usa `.local/postgres-data`, porta `55432` e bancos `eleven` e
`eleven_test`; gera `.env` com segredos aleatórios se não existir, sem sobrescrevê-lo.
Não alterar bancos/serviços existentes. Para parar somente esse cluster:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/stop-local-postgres.ps1
```

**Em `apps/api` — instalar backend, aplicar migrations e iniciar API:**

```powershell
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --no-proxy-headers --port 8011
```

Swagger: `http://127.0.0.1:8011/docs`; processo: `/health`; conexão com banco:
`/ready`. A API lê `.env` na raiz. O README detalha ambientes e a alternativa Docker.

**Na raiz — Expo/celular, Web e verificações TypeScript:**

```powershell
npm.cmd run mobile
# Alternativa Web, com abertura do navegador:
npm.cmd run mobile:web
# Alias Web existente:
npm.cmd run web
npm.cmd run lint
npm.cmd run typecheck
```

`mobile` usa LAN; o celular precisa estar na mesma rede e usar cliente compatível
com SDK 55 ou development build. `mobile:web` usa localhost, normalmente porta
8081. Ambos selecionam o workspace `@eleven/mobile`. Para outra porta:
`npm.cmd run mobile:web -- --port 8083`.

**Em `apps/mobile` — compatibilidade e bundle Expo:**

```powershell
npx.cmd expo install --check
npx.cmd expo-doctor
npx.cmd expo export --platform all
```

**Em `apps/api` — testes, lint, formatação, typecheck e migrations:**

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run alembic current
uv run alembic check
# Somente ao implementar uma mudança de schema; revisar o resultado:
uv run alembic revision --autogenerate -m descricao
```

Testes de integração exigem PostgreSQL iniciado e `TEST_DATABASE_URL` para banco
separado cujo nome termine em `_test`. Usam schemas temporários; nunca aponte
testes para dados reais. Não há script npm de testes da API: use pytest nesse diretório.

## Cuidados com Expo no monorepo Windows

O entry point é `apps/mobile/index.ts`, com `registerRootComponent`. O `app.json`
seleciona Metro para Web; React Native Web e React DOM já estão instalados como
dependências do mobile. O `tsconfig.json` do mobile estende `expo/tsconfig.base`.
Não existem configurações Metro/Babel personalizadas nesta fundação: preserve os
padrões do Expo que já resolvem os workspaces; não adicionar aliases/watchFolders
sem diagnosticar uma necessidade real.

Não iniciar `npx expo start` na raiz, que não é o app. Encerre instâncias antigas
deste projeto com Ctrl+C antes de `npm ci`. Falhas `ENOTEMPTY`/`EPERM` podem deixar
dependências parcialmente removidas; verifique a conclusão da instalação.
Se `npx` oferecer baixar outro SDK por não encontrar o Expo local, interrompa e
restaure as dependências do lockfile. Limpar cache não restaura pacotes ausentes.
Não encerre processos de outros projetos nem deixe servidores de teste ocultos
ocupando portas após a validação.

## Testes, qualidade e conclusão

Toda alteração relevante de negócio exige testes adequados. Priorize autenticação,
autorização, isolamento de times, Presidente, permissões, planos, limites,
financeiro, operações destrutivas e demais regras críticas. Não criar testes
artificiais só para cobertura nem suítes excessivas para mudanças visuais simples.

Antes de concluir, execute testes relevantes, lint e typecheck das partes afetadas;
valide migrations quando houver e verifique Expo quando alterar mobile. Para
mudanças exclusivamente documentais, confira conteúdo, caminhos e comandos sem
reinstalar dependências ou iniciar serviços desnecessariamente. Nunca afirmar que
um comando passou sem executá-lo; informe verificações não executadas e o motivo.

Para alterações do ambiente Web, confirme o servidor de desenvolvimento, resposta
HTTP do HTML e bundle, mensagem `Web Bundled` e navegação no navegador. Exportação
estática sozinha não prova que `expo start --web` funciona. Não confundir geração
de bundles nativos com execução validada em aparelho Android/iOS.

Ao concluir uma tarefa, responda brevemente com: o que foi implementado, arquivos
principais alterados, migrations (se houver), testes/verificações executados,
resultado, comando para validação manual e pendências reais. Evite relatórios gigantes.
