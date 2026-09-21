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

O estado atual é uma fundação: modelagem, políticas, estrutura de autenticação,
API de leitura protegida e cinco telas placeholder. Ainda não há fluxo público
completo de cadastro/login, cadastro completo de time ou cobrança.

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
futuros fluxos de reativação, troca de papel ou plano devem aplicar as mesmas
políticas e transações. Limites de plano não são garantidos por escritas SQL diretas.
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

As cinco abas aprovadas são **Início, Jogos, Times, Notificações e Perfil**.
Não adicionar abas inferiores sem decisão explícita do produto. Administração
fica dentro do contexto do time, conforme as permissões do usuário.

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
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger: `http://127.0.0.1:8000/docs`; processo: `/health`; conexão com banco:
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
