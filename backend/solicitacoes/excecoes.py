from nucleo.excecoes import ErroDeNegocio, NaoEncontrado


class SolicitacaoNaoEncontrada(NaoEncontrado):
    """Também vale para a solicitação de outra pessoa: não confirmamos que ela existe (D04)."""

    default_detail = "Solicitação não encontrada."


class SolicitacaoNaoEditavel(ErroDeNegocio):
    status_code = 409
    erro = "SOLICITACAO_NAO_EDITAVEL"
    default_detail = "Só é possível editar ou excluir solicitações com status Aberto."


class TransicaoInvalida(ErroDeNegocio):
    """Mudança de status fora do ciclo Aberto, Em Atendimento, Concluído (D03)."""

    status_code = 409
    erro = "TRANSICAO_INVALIDA"
    default_detail = "Transição de status inválida."
