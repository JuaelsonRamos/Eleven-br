import type { IconName } from '../components/design';

/**
 * "Aprenda a usar" guide. Describe only features available in the app today.
 * Text between ** is shown in bold (usually an on-screen label). Screenshots, GIFs,
 * videos and links go in `media`; new topics and sections need no screen changes.
 */
export type HelpMedia =
  | { kind: 'image' | 'gif'; source: number | { uri: string }; description: string }
  | { kind: 'video' | 'link'; url: string; label: string };

export type HelpTopic = {
  id: string;
  title: string;
  summary: string;
  steps: readonly string[];
  notes?: readonly string[];
  media?: readonly HelpMedia[];
  related?: readonly string[];
};

export type HelpSection = { id: string; title: string; icon: IconName; topics: readonly HelpTopic[] };

export const helpSections = [
  {
    id: 'start', title: 'Começando', icon: 'rocket-outline',
    topics: [
      {
        id: 'create-account', title: 'Como criar sua conta',
        summary: 'Cadastro com nome, contato e senha, confirmado por código.',
        steps: [
          'Na tela inicial, toque em **Criar minha conta**.',
          'Informe seu nome e escolha como receber o código: e-mail ou celular (**Usar celular**).',
          'Crie uma senha com pelo menos 8 caracteres, repita em **Confirmar senha** e toque em **Criar minha conta**.',
          'Digite o código de 6 dígitos recebido e toque em **Confirmar**.',
        ],
        notes: [
          'Já tem conta? Toque em **Já tenho conta** e entre com telefone ou e-mail e senha.',
          'Esqueceu a senha? Em **Já tenho conta → Esqueci minha senha**, receba um código no e-mail verificado da conta.',
          'O código vale por 10 minutos. Se não chegar, toque em **Reenviar código**.',
        ],
        related: ['create-team', 'join-team'],
      },
      {
        id: 'create-team', title: 'Como criar um time',
        summary: 'Crie seu time e torne-se o Presidente.',
        steps: [
          'Abra **Meus Times** (com um time aberto, em **Mais → Meus Times / Trocar time**) e toque em **Criar time**.',
          'Preencha nome, cidade, UF e categoria e marque uma ou mais modalidades: Campo, Society / Fut7 ou Futsal. O escudo é opcional.',
          'Toque em **Criar time**. Você passa a ser o Presidente e o time começa no plano Free.',
        ],
        notes: [
          'Se existir um time parecido na mesma cidade, o app avisa. Confira e, se for outro time, toque em **Criar mesmo assim**.',
          'Para mudar os dados depois, abra **Perfil do time → Editar time**.',
        ],
        related: ['invite-players', 'administrators'],
      },
      {
        id: 'join-team', title: 'Como entrar em um time',
        summary: 'Peça entrada e aguarde a aprovação do responsável.',
        steps: [
          'Em **Meus Times**, toque em **Entrar em um time**.',
          'Escolha **Usar código/link** para digitar o código recebido ou **Encontrar um time** para buscar pelo nome ou ID.',
          'Toque em **Buscar time**, confira nome, cidade e modalidades e toque em **Solicitar entrada**.',
          'Acompanhe em **Meus pedidos**. Depois da aprovação, o time aparece em **Meus Times**.',
        ],
        notes: ['Enquanto o pedido estiver pendente, você pode cancelá-lo em **Meus pedidos**.'],
        related: ['invite-code'],
      },
      {
        id: 'invite-code', title: 'Como utilizar um código ou convite',
        summary: 'O código identifica o time, mas não libera o acesso sozinho.',
        steps: [
          'Cada time tem um código de 8 caracteres, que também é o ID do time. Ele aparece no Início e no Perfil do time.',
          'Recebeu um link de convite? Abra o link, entre na sua conta e o código já estará preenchido em **Entrar em um time**.',
          'Recebeu só o código? Digite em **Entrar em um time → Usar código/link** e toque em **Buscar time**.',
          'Toque em **Solicitar entrada**. O acesso ao time depende da aprovação do responsável.',
        ],
        related: ['join-team', 'invite-players'],
      },
    ],
  },
  {
    id: 'roster', title: 'Elenco', icon: 'people-outline',
    topics: [
      {
        id: 'add-players', title: 'Como cadastrar jogadores',
        summary: 'Inclua jogadores no elenco, mesmo sem conta no app.',
        steps: [
          'No time, abra **Elenco** e toque em **Adicionar jogador**.',
          'Informe o nome. Apelido, telefone e e-mail são opcionais.',
          'Toque em **Salvar jogador**. Se houver alguém parecido no elenco, o app mostra antes de salvar.',
        ],
        notes: [
          'Disponível para o Presidente e para administradores com a área Elenco e solicitações.',
          'Esse cadastro não cria conta. Quando o jogador pedir entrada, a aprovação pode ligar a conta dele a este cadastro.',
          'Limite de jogadores ativos: 24 no Free e 100 no ELEVEN PRO. Inativos não contam.',
        ],
        related: ['invite-players', 'positions'],
      },
      {
        id: 'invite-players', title: 'Como convidar jogadores',
        summary: 'Compartilhe o código do time e aprove os pedidos.',
        steps: [
          'Em **Elenco**, toque em **Convidar jogadores**.',
          'Use **Copiar código** ou **Compartilhar convite** e envie para o jogador.',
          'Quando ele pedir entrada, abra **Solicitações de entrada** e analise o pedido.',
          'Toque em **Aprovar** ou **Recusar** e confirme.',
        ],
        notes: ['Na aprovação, você pode ligar a conta a um jogador já cadastrado sem conta, preservando o histórico dele.'],
        related: ['invite-code', 'add-players'],
      },
      {
        id: 'positions', title: 'Como definir posições',
        summary: 'Registre onde cada jogador atua neste time.',
        steps: [
          'Em **Elenco**, abra o jogador e toque em **Editar posições**.',
          'Marque as posições em que ele joga e escolha a posição principal.',
          'Toque em **Salvar posições**.',
        ],
        notes: ['As posições valem somente neste time e aparecem como sugestão na escalação. Disponível também no Free.'],
        related: ['place-players'],
      },
      {
        id: 'remove-player', title: 'Como remover ou inativar jogador',
        summary: 'Tire alguém do elenco ativo sem perder o histórico.',
        steps: [
          'Em **Elenco**, abra o jogador.',
          '**Inativar jogador** mantém o vínculo, mas tira o jogador do elenco ativo. Para voltar, use **Reativar jogador**.',
          '**Remover do time** encerra a participação e pede confirmação. Para voltar, o jogador precisa de uma nova solicitação aprovada.',
        ],
        notes: [
          'Nos dois casos, partidas, estatísticas e financeiro do jogador são preservados.',
          'O Presidente não pode ser inativado nem removido. Transfira a Presidência antes.',
        ],
        related: ['presidency'],
      },
      {
        id: 'administrators', title: 'Como selecionar administradores',
        summary: 'O Presidente escolhe quem ajuda a administrar cada área.',
        steps: [
          'No **Elenco**, o Presidente abre o jogador e toca em **Tornar administrador**.',
          'Escolha as áreas que ele poderá gerenciar: Perfil do time, Elenco e solicitações, Jogos, peladas e escalações ou Financeiro.',
          'Toque em **Salvar administração**.',
          'Para mudar as áreas, use **Editar administração**. Para retirar, toque em **Remover administração**.',
        ],
        notes: [
          'Recurso do ELEVEN PRO: até 5 administradores além do Presidente. No Free, somente o Presidente administra o time.',
          'Somente jogadores ativos e com conta no ELEVEN BR podem ser administradores. Administradores não nomeiam outros administradores.',
          'Contratar ou cancelar o ELEVEN PRO continua exclusivo do Presidente.',
        ],
        related: ['presidency', 'pro-overview'],
      },
      {
        id: 'presidency', title: 'Como transferir a Presidência',
        summary: 'Passe o comando do time para outro jogador.',
        steps: [
          'No **Elenco**, o Presidente abre o jogador que vai assumir e toca em **Transferir Presidência**.',
          'Confira a mensagem e toque em **Confirmar transferência**.',
          'O novo Presidente assume na hora todos os poderes da Presidência.',
        ],
        notes: [
          'Somente jogadores ativos e com conta no ELEVEN BR podem assumir. O time sempre tem exatamente um Presidente.',
          'Você continua no time como jogador, sem os poderes de Presidente. Seus dados, estatísticas e histórico são preservados.',
          'Se o novo Presidente era administrador, as áreas dele deixam de ser necessárias: a Presidência já inclui todas.',
        ],
        related: ['administrators'],
      },
    ],
  },
  {
    id: 'events', title: 'Peladas e eventos', icon: 'calendar-outline',
    topics: [
      {
        id: 'pelada-overview', title: 'Como organizar uma pelada',
        summary: 'Da agenda ao resultado: presença, times e partidas.',
        steps: [
          'Crie a pelada em **Jogos → Criar evento**.',
          'Os jogadores respondem **VOU** ou **NÃO VOU**. Gestores podem incluir convidados.',
          'Na hora do jogo, toque em **Montar times** para sortear as equipes.',
          'Registre as partidas, gols e cartões na seção **Partidas** da pelada.',
        ],
        related: ['create-pelada', 'attendance', 'participants', 'draw-teams', 'record-result'],
      },
      {
        id: 'create-pelada', title: 'Como criar uma pelada',
        summary: 'Agende uma data única ou uma pelada semanal.',
        steps: [
          'Abra **Jogos** e toque em **Criar evento**.',
          'Escolha **Pelada** e informe título, modalidade, data, horário e local.',
          'Para repetir toda semana, ative **Repetir semanalmente**. Sem data de término, a pelada se repete até ser encerrada.',
          'Toque em **Salvar evento**.',
        ],
        notes: [
          'Disponível para o Presidente e para administradores com a área Jogos, peladas e escalações.',
          'Cada data tem sua própria lista de presença. Editar ou cancelar vale só para aquela data; **Encerrar recorrência** cancela as próximas e preserva o histórico.',
          'O time recebe um aviso em **Notificações**.',
        ],
        related: ['attendance', 'create-game'],
      },
      {
        id: 'attendance', title: 'Como confirmar presença',
        summary: 'Avise se você vai ao jogo.',
        steps: [
          'Em **Jogos**, encontre o evento. Toque em **Ver detalhes** para abrir a lista completa.',
          'Toque em **VOU** ou **NÃO VOU**. Sem resposta, você aparece como pendente.',
          'Você pode mudar a resposta enquanto o evento estiver aberto.',
        ],
        notes: ['Gestores podem tocar em **Lembrar pendentes** para avisar no app quem ainda não respondeu.'],
      },
      {
        id: 'participants', title: 'Como organizar participantes',
        summary: 'Confirmados, convidados e quem entra no sorteio.',
        steps: [
          'A lista de confirmados considera os jogadores ativos do elenco que responderam **VOU**.',
          'Para incluir alguém de fora, abra o evento, preencha **Nome/apelido do convidado** e toque em **Adicionar convidado**. Convidados não precisam de conta.',
          'Em **Montar times**, desmarque quem fica fora deste sorteio e marque os goleiros.',
        ],
        notes: ['Tirar alguém do sorteio não muda a presença dele. Use **Atualizar participantes** para ver mudanças feitas por outras pessoas.'],
        related: ['draw-teams'],
      },
      {
        id: 'draw-teams', title: 'Como sortear times automaticamente',
        summary: 'Equipes equilibradas em poucos toques.',
        steps: [
          'Na pelada, toque em **Montar times**.',
          'Confira os participantes, marque os goleiros e escolha o número de times (de 2 a 32).',
          'Toque em **Sortear**. Goleiros e demais jogadores são distribuídos para equilibrar as equipes.',
          'Ajuste com **Mover** ou use **Refazer sorteio**, que pede confirmação.',
        ],
        notes: [
          'Depois da primeira partida, os times não podem mais ser alterados.',
          'Os membros consultam o resultado em **Ver times da pelada**.',
        ],
        related: ['record-result'],
      },
    ],
  },
  {
    id: 'lineups', title: 'Escalação', icon: 'football-outline',
    topics: [
      {
        id: 'create-lineup', title: 'Como criar uma escalação',
        summary: 'Monte e salve o time em campo.',
        steps: [
          'No Início do time, toque em **Escalação** e depois em **Nova escalação**.',
          'Dê um nome em **Nome da escalação** e, se quiser, vincule a um evento.',
          'Escolha a modalidade e a formação, posicione os jogadores e toque em **Salvar escalação**.',
        ],
        notes: [
          'Recurso do ELEVEN PRO. Os membros consultam; editar exige a área Jogos, peladas e escalações.',
          'A escalação não altera o sorteio da pelada.',
        ],
        related: ['choose-formation', 'place-players'],
      },
      {
        id: 'choose-formation', title: 'Como escolher formação',
        summary: 'Formações prontas para Campo, Society e Futsal.',
        steps: [
          'Na escalação, escolha a modalidade: Campo (11), Society (7) ou Futsal (5), conforme as modalidades do time.',
          'Toque na formação desejada, como 4-4-2, 4-3-3 e 3-5-2 no Campo, 2-3-1 no Society ou 1-2-1 no Futsal.',
          'Ao trocar a formação, quem estava em posição compatível é mantido; o app avisa quem ficou sem lugar.',
        ],
        related: ['place-players'],
      },
      {
        id: 'place-players', title: 'Como posicionar jogadores',
        summary: 'Escolha quem ocupa cada posição do campo.',
        steps: [
          'Toque em uma posição do campo para escolher um jogador ativo.',
          'Quem tem aquela posição cadastrada aparece primeiro, mas você pode improvisar.',
          'Para liberar a posição, use **Deixar posição vazia**. O mesmo jogador não ocupa duas posições.',
          'Toque em **Salvar escalação** para guardar.',
        ],
        related: ['positions'],
      },
    ],
  },
  {
    id: 'games', title: 'Jogos', icon: 'trophy-outline',
    topics: [
      {
        id: 'create-game', title: 'Como cadastrar jogo',
        summary: 'Agende um jogo avulso, com adversário opcional.',
        steps: [
          'Em **Jogos**, toque em **Criar evento** e escolha **Jogo avulso**.',
          'Preencha título, modalidade, data, horário, local e, se quiser, o **Adversário (opcional)**.',
          'Toque em **Salvar evento**. O elenco confirma presença como em qualquer evento.',
        ],
        notes: ['O adversário é informado só pelo nome: ele não precisa ter um time no ELEVEN BR.'],
        related: ['attendance'],
      },
      {
        id: 'record-result', title: 'Como registrar resultado',
        summary: 'O placar oficial fica nas partidas da pelada.',
        steps: [
          'Primeiro, monte os times da pelada em **Montar times**.',
          'Na seção **Partidas**, toque em **Nova partida**, escolha as duas equipes e toque em **Criar partida**.',
          'Toque em **Iniciar partida** e ajuste o placar com os botões de + e −.',
          'Ao final, toque em **Finalizar partida** e confirme. Se precisar, use **Corrigir resultado**.',
        ],
        notes: [
          'Jogos avulsos contra adversários ainda não têm registro de placar.',
          'Partidas canceladas ficam no histórico, mas não contam nas estatísticas.',
        ],
        related: ['match-stats'],
      },
      {
        id: 'match-stats', title: 'Como registrar gols, cartões e estatísticas',
        summary: 'Registros por partida alimentam as estatísticas do time.',
        steps: [
          'Com a partida iniciada ou finalizada, toque em **Eventos da partida**.',
          'Use **Registrar gol** (assistência opcional) ou **Registrar cartão** e escolha o participante.',
          'As estatísticas contam só as partidas finalizadas. Veja em **Início → Estatísticas**.',
        ],
        notes: [
          'Os registros não mudam o placar oficial; o app apenas compara os dois.',
          'Gestores podem ajustar totais históricos em **Elenco → jogador → Editar estatísticas**.',
        ],
      },
    ],
  },
  {
    id: 'finance', title: 'Financeiro', icon: 'wallet-outline',
    topics: [
      {
        id: 'finance-overview', title: 'Como funciona o Financeiro',
        summary: 'Mensalidades dos jogadores e caixa do time, com registros manuais.',
        steps: [
          'Abra **Início → Financeiro**.',
          '**Mensalidades**: cobranças mensais geradas para os jogadores ativos.',
          '**Caixa**: receitas e despesas do time, com o saldo atual.',
          'Cada jogador vê somente as próprias cobranças em **Minhas mensalidades**.',
        ],
        notes: [
          'Quem gerencia: o Presidente e, no ELEVEN PRO, administradores com a área Financeiro.',
          'Os pagamentos são registrados manualmente (Pix, dinheiro, cartão ou outro). O app não recebe dinheiro dos jogadores.',
        ],
        related: ['dues-settings', 'register-payment', 'cash-entries', 'cash-follow'],
      },
      {
        id: 'dues-settings', title: 'Como configurar mensalidade',
        summary: 'Defina valor e vencimento e gere as cobranças do mês.',
        steps: [
          'Em **Financeiro**, toque em **Configurar mensalidade**.',
          'Informe o valor, o dia de vencimento e ative a mensalidade. Toque em **Salvar configuração**.',
          'Escolha a competência (mês/ano) e toque em **Gerar mensalidades**. Confira a prévia e toque em **Confirmar geração**.',
        ],
        notes: [
          'Todos os jogadores ativos recebem a cobrança, inclusive o Presidente e quem ainda não tem conta.',
          'Se o mês não tiver o dia de vencimento, a cobrança vence no último dia do mês. Mudanças valem só para cobranças futuras.',
          'Gerar de novo a mesma competência não duplica cobranças.',
        ],
        related: ['register-payment'],
      },
      {
        id: 'register-payment', title: 'Como registrar pagamentos',
        summary: 'Registre recebimentos, inclusive parciais.',
        steps: [
          'Em **Financeiro → Mensalidades**, abra a cobrança do jogador.',
          'Toque em **Registrar pagamento**, informe o valor recebido, a data e a forma de pagamento e confirme.',
          'Pagamentos parciais são aceitos: a cobrança fica paga quando o total recebido chega ao valor devido.',
        ],
        notes: [
          'Errou? Use **Estornar lançamento** com um motivo. O registro é preservado e o saldo é reaberto.',
          'Também é possível **Isentar mensalidade** ou **Cancelar cobrança**. Se já houver recebimento, estorne antes.',
        ],
        related: ['cash-follow'],
      },
      {
        id: 'cash-entries', title: 'Como registrar entradas e saídas',
        summary: 'Receitas e despesas do time no caixa.',
        steps: [
          'Em **Financeiro → Caixa**, toque em **Novo lançamento**.',
          'Escolha **Receita** ou **Despesa** e informe valor, categoria, descrição e data.',
          'Toque em **Conferir lançamento** e confirme.',
        ],
        notes: [
          'Lançamentos não são apagados: para corrigir, use **Estornar lançamento** com um motivo.',
          'Datas futuras não são aceitas: o caixa registra o que já aconteceu.',
        ],
        related: ['cash-follow'],
      },
      {
        id: 'cash-follow', title: 'Como acompanhar o caixa',
        summary: 'Saldo, histórico e situação das mensalidades.',
        steps: [
          'Em **Caixa**, veja o **Saldo atual**, as receitas e as despesas.',
          'Escolha período, tipo e categoria e toque em **Filtrar movimentações** para consultar o histórico.',
          'Em **Mensalidades**, escolha a competência e filtre por situação: pendentes, atrasadas, pagas, isentas ou canceladas.',
        ],
        notes: ['O saldo atual considera todos os lançamentos válidos; os filtros mudam só a lista.'],
      },
    ],
  },
  {
    id: 'pro', title: 'ELEVEN PRO', icon: 'star-outline',
    topics: [
      {
        id: 'pro-overview', title: 'O que é o ELEVEN PRO',
        summary: 'O plano completo do seu time.',
        steps: [
          'É o plano pago do time: R$ 30 por mês, por time.',
          'Libera até 100 jogadores ativos, até 5 administradores com permissões por área e escalações visuais.',
          'O Free continua gratuito, com até 24 jogadores ativos e administração somente pelo Presidente.',
        ],
        notes: ['Mudar de plano nunca apaga jogadores, histórico ou dados do time.'],
        related: ['pro-subscribe', 'administrators'],
      },
      {
        id: 'pro-subscribe', title: 'Como contratar',
        summary: 'Somente o Presidente contrata para o time.',
        steps: [
          'O Presidente abre **Mais → ELEVEN PRO** e toca em **ASSINAR ELEVEN PRO**.',
          'Escolha **PIX** ou **Cartão de crédito** e informe nome, e-mail e CPF ou CNPJ de quem paga.',
          'Confirme. O Pro é liberado depois que o pagamento é confirmado; toque em **Atualizar assinatura** para conferir.',
        ],
        notes: ['Administradores não contratam nem cancelam o ELEVEN PRO.'],
        related: ['pro-payment', 'pro-cancel'],
      },
      {
        id: 'pro-payment', title: 'Como funciona Pix e cartão',
        summary: 'Duas formas de pagar a assinatura mensal.',
        steps: [
          'Pix: a cada mês, uma cobrança de R$ 30 é gerada com QR Code e código copia e cola. O pagamento é manual, sem débito automático.',
          'Cartão: você informa o cartão na página segura do Asaas, que faz as cobranças recorrentes. O ELEVEN BR não recebe os dados do cartão.',
          'Se um pagamento atrasar, o Pro já pago continua por até 3 dias.',
        ],
        related: ['pro-subscribe'],
      },
      {
        id: 'pro-cancel', title: 'Como cancelar',
        summary: 'Interrompa as próximas cobranças.',
        steps: [
          'O Presidente abre **Mais → ELEVEN PRO** e toca em **Cancelar assinatura**.',
          'Toque em **Confirmar cancelamento**.',
          'As novas cobranças são interrompidas e o time mantém o Pro até o fim do período já pago.',
        ],
        notes: ['Nenhum dado ou histórico é apagado ao voltar para o Free.'],
      },
    ],
  },
] as const satisfies readonly HelpSection[];

type Topics = (typeof helpSections)[number]['topics'][number];
export type HelpTopicId = Topics['id'];
// Compile-time guard: every related topic must exist.
type RelatedId = Topics extends infer T ? (T extends { related: readonly (infer R)[] } ? R : never) : never;
export const relatedTopicsExist: RelatedId extends HelpTopicId ? true : never = true;

export function findTopic(id: string): { section: HelpSection; topic: HelpTopic } | null {
  for (const section of helpSections as readonly HelpSection[]) {
    const topic = section.topics.find(item => item.id === id);
    if (topic) return { section, topic };
  }
  return null;
}
