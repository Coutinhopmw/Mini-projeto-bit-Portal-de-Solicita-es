"""Services: regras de negócio da sessão do usuário (login, renovação e logout).

Levantam subclasses de `nucleo.excecoes.ErroDeNegocio` quando uma regra é violada.
Não conhecem HTTP.
"""

import logging

from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.exceptions import ExpiredTokenError, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from nucleo.excecoes import CredenciaisInvalidas, SessaoExpirada

from . import repositories

logger = logging.getLogger("portal.auth")

TOKEN_DE_RENOVACAO_INVALIDO = "Token de renovação inválido."


def autenticar(login, senha):
    """Valida usuário e senha e devolve (usuário, tokens).

    A senha é conferida pelo hash do Django (PBKDF2). Usuário inexistente, senha errada e
    usuário inativo recebem a mesma resposta, para não revelar quais usuários existem.
    """
    usuario = authenticate(login=login, password=senha)
    if usuario is None:
        logger.warning("Login recusado: login=%r", login[:50])
        raise CredenciaisInvalidas()

    repositories.registrar_ultimo_acesso(usuario)
    logger.info("Login realizado: usuario=%s", usuario.login)
    return usuario, _emitir_tokens(usuario)


def renovar_acesso(renovacao):
    """Troca um token de renovação válido por um novo token de acesso."""
    refresh = _abrir_token_de_renovacao(renovacao)
    usuario = repositories.buscar_por_id(refresh["user_id"])
    if usuario is None or not usuario.ativo:
        raise AuthenticationFailed()
    return str(refresh.access_token)


def encerrar_sessao(usuario, renovacao):
    """Bloqueia o token de renovação do próprio usuário, impedindo novas renovações.

    O token de acesso já emitido continua valendo até expirar (15 minutos por padrão).
    """
    try:
        refresh = RefreshToken(renovacao)
    except TokenError as erro:
        raise ValidationError({"renovacao": TOKEN_DE_RENOVACAO_INVALIDO}) from erro
    if str(refresh["user_id"]) != str(usuario.pk):
        raise ValidationError({"renovacao": TOKEN_DE_RENOVACAO_INVALIDO})

    refresh.blacklist()
    logger.info("Logout realizado: usuario=%s", usuario.login)


def _emitir_tokens(usuario):
    refresh = RefreshToken.for_user(usuario)
    return {"acesso": str(refresh.access_token), "renovacao": str(refresh)}


def _abrir_token_de_renovacao(renovacao):
    try:
        return RefreshToken(renovacao)
    except ExpiredTokenError as erro:
        raise SessaoExpirada() from erro
    except TokenError as erro:
        raise AuthenticationFailed() from erro
