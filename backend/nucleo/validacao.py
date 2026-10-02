"""Peças de validação reaproveitáveis pelos serializers de todas as rotas.

A validação de formato e de tamanho fica no serializer (DRF); as regras de estado
ficam nos services; o banco reforça com NOT NULL, FK e CHECK.
"""

from rest_framework import serializers


class CampoTexto(serializers.CharField):
    """Texto obrigatório, sem espaços nas pontas e com limites de tamanho.

    As mensagens seguem o padrão do projeto, por exemplo:
    "Informe o título." e "O título deve ter entre 3 e 150 caracteres."
    `artigo` é "o" ou "a", conforme o gênero do rótulo ("o título", "a descrição").
    """

    def __init__(self, *, rotulo, minimo, maximo, artigo="o", **kwargs):
        informe = f"Informe {artigo} {rotulo}."
        tamanho = f"{artigo.upper()} {rotulo} deve ter entre {minimo} e {maximo} caracteres."
        kwargs.setdefault("trim_whitespace", True)
        kwargs["error_messages"] = {
            "required": informe,
            "blank": informe,
            "null": informe,
            "min_length": tamanho,
            "max_length": tamanho,
            "invalid": informe,
        }
        super().__init__(min_length=minimo, max_length=maximo, **kwargs)
