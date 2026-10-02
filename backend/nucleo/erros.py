"""Handler central de erros: toda resposta de erro da API segue o mesmo formato.

    {"erro": "VALIDACAO", "mensagem": "Dados inválidos", "detalhes": {"titulo": "Obrigatório"}}

`detalhes` só aparece quando há o que detalhar (erros de validação por campo).
Nunca devolvemos stack trace: exceções inesperadas viram ERRO_INTERNO e o
detalhe técnico vai só para o log.
"""

import logging

from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as handler_padrao_drf
from rest_framework.views import set_rollback

from .excecoes import ErroDeNegocio, SessaoExpirada

logger = logging.getLogger("portal.erros")

MENSAGEM_ERRO_INTERNO = "Erro inesperado. Tente novamente em instantes."


def montar_corpo(erro, mensagem, detalhes=None):
    corpo = {"erro": erro, "mensagem": mensagem}
    if detalhes:
        corpo["detalhes"] = detalhes
    return corpo


def _achatar(detalhe):
    """Reduz a estrutura de erros do DRF a {campo: "mensagem"}."""
    if isinstance(detalhe, dict):
        chaves = {"non_field_errors": "geral"}
        return {chaves.get(campo, campo): _achatar(valor) for campo, valor in detalhe.items()}
    if isinstance(detalhe, list):
        if detalhe and all(isinstance(item, dict) for item in detalhe):
            return [_achatar(item) for item in detalhe]
        return str(detalhe[0]) if detalhe else ""
    return str(detalhe)


def _traduzir(exc, view=None):
    """Devolve (código, mensagem, detalhes) para uma exceção já tratada pelo DRF."""
    if isinstance(exc, ErroDeNegocio):
        return exc.erro, str(exc.detail), exc.detalhes
    if isinstance(exc, exceptions.ValidationError):
        detalhes = _achatar(exc.detail)
        if not isinstance(detalhes, dict):
            detalhes = {"geral": detalhes}
        return "VALIDACAO", "Dados inválidos", detalhes
    if isinstance(exc, exceptions.ParseError):
        return "REQUISICAO_INVALIDA", "O corpo da requisição não é um JSON válido.", None
    if isinstance(exc, SessaoExpirada):
        return "SESSAO_EXPIRADA", str(exc.detail), None
    if isinstance(exc, exceptions.NotAuthenticated | exceptions.AuthenticationFailed):
        return "NAO_AUTENTICADO", "Faça login para continuar.", None
    if isinstance(exc, exceptions.PermissionDenied):
        return "SEM_PERMISSAO", "Você não tem permissão para realizar esta ação.", None
    if isinstance(exc, exceptions.NotFound):
        return "NAO_ENCONTRADO", "Recurso não encontrado.", None
    if isinstance(exc, exceptions.MethodNotAllowed):
        return "METODO_NAO_PERMITIDO", "Método não permitido para esta rota.", None
    if isinstance(exc, exceptions.NotAcceptable | exceptions.UnsupportedMediaType):
        return "FORMATO_NAO_SUPORTADO", "Envie e aceite o conteúdo em JSON.", None
    if isinstance(exc, exceptions.Throttled):
        mensagem = getattr(view, "mensagem_limite", "Muitas tentativas. Aguarde e tente novamente.")
        return "MUITAS_TENTATIVAS", mensagem, None
    return "ERRO_NA_REQUISICAO", str(getattr(exc, "detail", exc)), None


def tratar_excecao(exc, contexto):
    """Configurado em REST_FRAMEWORK["EXCEPTION_HANDLER"]."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()

    resposta = handler_padrao_drf(exc, contexto)
    if resposta is None:
        # Exceção inesperada: registra o detalhe técnico e devolve uma resposta genérica.
        view = contexto.get("view")
        logger.error(
            "Erro inesperado em %s",
            view.__class__.__name__ if view else "view desconhecida",
            exc_info=exc,
        )
        set_rollback()
        return Response(montar_corpo("ERRO_INTERNO", MENSAGEM_ERRO_INTERNO), status=500)

    erro, mensagem, detalhes = _traduzir(exc, contexto.get("view"))
    resposta.data = montar_corpo(erro, mensagem, detalhes)
    return resposta
