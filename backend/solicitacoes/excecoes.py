from nucleo.excecoes import ErroDeNegocio, NaoEncontrado


class SolicitacaoNaoEncontrada(NaoEncontrado):
    """Também vale para a solicitação de outra pessoa: não confirmamos que ela existe (D04)."""

    default_detail = "Solicitação não encontrada."


class SolicitacaoNaoEditavel(ErroDeNegocio):
    status_code = 409
    erro = "SOLICITACAO_NAO_EDITAVEL"
    default_detail = "Só é possível editar ou excluir solicitações com status Aberto."
