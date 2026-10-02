"""Services: regras de negócio (permissões, estados, transições).

Levantam subclasses de `nucleo.excecoes.ErroDeNegocio` quando uma regra é violada.
Não conhecem HTTP.
"""

import logging

from django.db import transaction

from usuarios.models import Papel

from . import repositories
from .excecoes import SolicitacaoNaoEditavel, SolicitacaoNaoEncontrada
from .models import Status

logger = logging.getLogger("portal.solicitacoes")


def _escopo(usuario):
    """Quem vê tudo (Atendente) não tem filtro; o Solicitante vê só as próprias (D04)."""
    return None if usuario.papel == Papel.ATENDENTE else usuario.pk


def listar(usuario):
    return repositories.listar(_escopo(usuario))


def obter(usuario, pk):
    """Solicitação visível ao usuário. Se não existe ou é de outra pessoa, é 404 (D04)."""
    solicitacao = repositories.buscar(pk, _escopo(usuario))
    if solicitacao is None:
        raise SolicitacaoNaoEncontrada()
    return solicitacao


def pode_alterar(usuario, solicitacao):
    """Editar e excluir: só o autor, e só com status Aberto (D05)."""
    return solicitacao.solicitante_id == usuario.pk and solicitacao.status == Status.ABERTO


@transaction.atomic
def criar(usuario, titulo, descricao, categoria):
    """Solicitante, data e status Aberto são definidos aqui, nunca pelo corpo da requisição.

    A criação também grava o primeiro registro do histórico, na mesma transação (D11).
    """
    solicitacao = repositories.criar(
        titulo=titulo, descricao=descricao, categoria=categoria, solicitante=usuario
    )
    repositories.registrar_historico(solicitacao, None, Status.ABERTO, usuario)
    logger.info("Solicitação criada: %s por %s", solicitacao.codigo, usuario.login)
    return repositories.buscar(solicitacao.pk)


@transaction.atomic
def editar(usuario, pk, titulo, descricao, categoria):
    solicitacao = _travar_aberta(pk)
    repositories.atualizar(solicitacao, titulo=titulo, descricao=descricao, categoria=categoria)
    logger.info("Solicitação editada: %s por %s", solicitacao.codigo, usuario.login)
    return repositories.buscar(pk)


@transaction.atomic
def excluir(usuario, pk):
    solicitacao = _travar_aberta(pk)
    codigo = solicitacao.codigo
    repositories.excluir(solicitacao)
    logger.info("Solicitação excluída: %s por %s", codigo, usuario.login)


def listar_categorias():
    return repositories.categorias_ativas()


def _travar_aberta(pk):
    """Relê a solicitação travada e confirma o status Aberto, evitando corrida com o atendente."""
    solicitacao = repositories.buscar_para_atualizar(pk)
    if solicitacao is None:
        raise SolicitacaoNaoEncontrada()
    if solicitacao.status != Status.ABERTO:
        raise SolicitacaoNaoEditavel()
    return solicitacao
