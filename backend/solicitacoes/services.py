"""Services: regras de negócio (permissões, estados, transições).

Levantam subclasses de `nucleo.excecoes.ErroDeNegocio` quando uma regra é violada.
Não conhecem HTTP.
"""

import logging

from django.db import transaction

from usuarios.models import Papel

from . import filtros, repositories
from .excecoes import SolicitacaoNaoEditavel, SolicitacaoNaoEncontrada, TransicaoInvalida
from .models import Status

logger = logging.getLogger("portal.solicitacoes")

# Ciclo de vida (D03): cada status só avança para o próximo. Concluído é estado final.
PROXIMO_STATUS = {
    Status.ABERTO: Status.EM_ATENDIMENTO,
    Status.EM_ATENDIMENTO: Status.CONCLUIDO,
}


def _escopo(usuario):
    """Quem vê tudo (Atendente) não tem filtro; o Solicitante vê só as próprias (D04)."""
    return None if usuario.papel == Papel.ATENDENTE else usuario.pk


def listar(usuario, parametros=None):
    """Solicitações que o usuário pode ver, com os filtros aplicados sobre elas (D04, D09).

    Os filtros partem da consulta já restrita ao usuário, então um Solicitante nunca alcança
    as solicitações de outra pessoa, não importa o que peça.
    """
    consulta = repositories.listar(_escopo(usuario))
    return filtros.filtrar(consulta, parametros if parametros is not None else {})


def resumo(usuario):
    """Indicadores do dashboard sobre as solicitações visíveis ao usuário (RN12)."""
    return repositories.contar_por_status(_escopo(usuario))


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


@transaction.atomic
def alterar_status(usuario, pk, novo_status):
    """Muda o status e grava o histórico na mesma transação (D11).

    A solicitação é relida com a linha travada, então dois cliques seguidos não geram duas
    transições: o segundo encontra o status já alterado e recebe 409. Transição inválida
    não altera nada, nem o histórico.
    """
    solicitacao = repositories.buscar_para_atualizar(pk)
    if solicitacao is None:
        raise SolicitacaoNaoEncontrada()

    atual = Status(solicitacao.status)
    novo = Status(novo_status)
    if PROXIMO_STATUS.get(atual) != novo:
        raise TransicaoInvalida(
            f"Não é possível alterar o status de {atual.label} para {novo.label}."
        )

    repositories.atualizar(solicitacao, status=novo)
    repositories.registrar_historico(solicitacao, atual, novo, usuario)
    logger.info(
        "Status alterado: %s de %s para %s por %s", solicitacao.codigo, atual, novo, usuario.login
    )
    return repositories.buscar(pk)


def proximo_status(solicitacao):
    """Próximo status válido, ou None quando a solicitação já está concluída."""
    return PROXIMO_STATUS.get(solicitacao.status)


def pode_alterar_status(usuario, solicitacao):
    return usuario.papel == Papel.ATENDENTE and proximo_status(solicitacao) is not None


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
