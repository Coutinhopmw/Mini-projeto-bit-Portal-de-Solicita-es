from rest_framework.exceptions import APIException, AuthenticationFailed


class ErroDeNegocio(APIException):
    """Base dos erros previstos pelas regras de negócio.

    Os services levantam subclasses desta classe; o handler central (nucleo.erros)
    as converte no formato padrão de erro. Cada subclasse define o status HTTP e o
    código estável que o frontend usa para decidir o que mostrar.
    """

    status_code = 400
    erro = "ERRO_DE_NEGOCIO"
    default_detail = "Não foi possível concluir a operação."

    def __init__(self, mensagem=None, detalhes=None):
        super().__init__(mensagem)
        self.detalhes = detalhes


class NaoEncontrado(ErroDeNegocio):
    status_code = 404
    erro = "NAO_ENCONTRADO"
    default_detail = "Recurso não encontrado."


class BancoIndisponivel(ErroDeNegocio):
    status_code = 503
    erro = "BANCO_INDISPONIVEL"
    default_detail = "Não foi possível conectar ao banco de dados."


class SessaoExpirada(AuthenticationFailed):
    """Token válido no formato, mas vencido. Leva o usuário de volta ao login com aviso."""

    default_detail = "Sua sessão expirou. Faça login novamente."


class CredenciaisInvalidas(ErroDeNegocio):
    """Mensagem genérica: não revela se o usuário existe nem qual campo errou (RN19)."""

    status_code = 400
    erro = "CREDENCIAIS_INVALIDAS"
    default_detail = "Usuário ou senha inválidos."
