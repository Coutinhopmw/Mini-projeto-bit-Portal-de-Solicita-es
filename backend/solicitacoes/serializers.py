"""Serializers: validação de formato e tamanho dos dados que chegam e saem da API."""

from rest_framework import serializers

from nucleo.validacao import CampoTexto
from usuarios.models import Usuario

from . import repositories, services
from .models import Categoria, HistoricoStatus, Solicitacao


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nome"]
        read_only_fields = fields


class UsuarioResumoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "nome"]
        read_only_fields = fields


class HistoricoSerializer(serializers.ModelSerializer):
    alterado_por = UsuarioResumoSerializer(read_only=True)

    class Meta:
        model = HistoricoStatus
        fields = ["status_anterior", "status_novo", "alterado_por", "alterado_em"]
        read_only_fields = fields


class SolicitacaoListaSerializer(serializers.ModelSerializer):
    """Colunas da listagem: código, título, categoria, solicitante, data de abertura e status."""

    codigo = serializers.CharField(read_only=True)
    categoria = CategoriaSerializer(read_only=True)
    solicitante = UsuarioResumoSerializer(read_only=True)

    class Meta:
        model = Solicitacao
        fields = ["id", "codigo", "titulo", "categoria", "solicitante", "status", "criado_em"]
        read_only_fields = fields


class SolicitacaoDetalheSerializer(SolicitacaoListaSerializer):
    """Detalhes: acrescenta descrição, histórico e o que o usuário logado pode fazer."""

    historico = HistoricoSerializer(many=True, read_only=True)
    pode_editar = serializers.SerializerMethodField()
    pode_excluir = serializers.SerializerMethodField()

    class Meta(SolicitacaoListaSerializer.Meta):
        fields = [
            *SolicitacaoListaSerializer.Meta.fields,
            "descricao",
            "atualizado_em",
            "pode_editar",
            "pode_excluir",
            "historico",
        ]
        read_only_fields = fields

    def _pode_alterar(self, solicitacao):
        return services.pode_alterar(self.context["request"].user, solicitacao)

    def get_pode_editar(self, solicitacao):
        return self._pode_alterar(solicitacao)

    def get_pode_excluir(self, solicitacao):
        return self._pode_alterar(solicitacao)


class SolicitacaoEntradaSerializer(serializers.Serializer):
    """Corpo de POST e PUT. Id, código, solicitante, status e datas enviados são ignorados."""

    titulo = CampoTexto(rotulo="título", minimo=3, maximo=150)
    descricao = CampoTexto(rotulo="descrição", minimo=10, maximo=2000, artigo="a")
    categoria = serializers.PrimaryKeyRelatedField(
        queryset=repositories.categorias_ativas(),
        error_messages={
            "required": "Selecione uma categoria.",
            "null": "Selecione uma categoria.",
            "does_not_exist": "Categoria inválida ou inativa.",
            "incorrect_type": "Categoria inválida ou inativa.",
        },
    )
