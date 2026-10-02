"""Configuração dos testes: hash de senha rápido para a suíte não gastar tempo no PBKDF2."""

from .base import *  # noqa: F403

# O MD5 só cria os hashes dos testes; o PBKDF2 continua na lista para validar os
# hashes do seed (database/seed.sql).
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
