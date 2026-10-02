"""Autenticação das requisições por token JWT de acesso (cabeçalho Authorization: Bearer)."""

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import ExpiredTokenError, TokenError
from rest_framework_simplejwt.settings import api_settings

from nucleo.excecoes import SessaoExpirada


class AutenticacaoJWT(JWTAuthentication):
    """Igual à do simplejwt, mas distingue token vencido de token inválido.

    O simplejwt junta os dois num único erro com texto traduzido. Aqui a decisão usa o
    tipo da exceção: vencido vira SESSAO_EXPIRADA (o frontend tenta renovar ou volta ao
    login com aviso) e qualquer outro problema vira NAO_AUTENTICADO. Ambos devolvem 401.
    """

    def get_validated_token(self, raw_token):
        for classe in api_settings.AUTH_TOKEN_CLASSES:
            try:
                return classe(raw_token)
            except ExpiredTokenError as erro:
                raise SessaoExpirada() from erro
            except TokenError:
                continue
        raise AuthenticationFailed()
