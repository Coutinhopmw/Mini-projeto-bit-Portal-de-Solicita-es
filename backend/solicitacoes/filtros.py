"""Filtros da listagem de solicitações (D09), declarados com o django-filter.

Parâmetros de GET /api/solicitacoes/ (todos opcionais e combináveis, todos precisam ser
atendidos):

    de=AAAA-MM-DD       data de criação a partir do dia informado, inclusive
    ate=AAAA-MM-DD      data de criação até o dia informado, inclusive
    categoria=<id>      categoria da solicitação
    status=<STATUS>     ABERTO, EM_ATENDIMENTO ou CONCLUIDO
    q=<texto>           busca parcial no título, sem diferenciar maiúsculas de minúsculas

O período usa o fuso America/Sao_Paulo (o `TIME_ZONE` do projeto). Os dois extremos são
inclusos: `ate` vale até 23:59:59.999999 do dia, e a consulta compara com "menor que o dia
seguinte às 00:00", que também aproveita o índice de `criado_em`.
"""

import datetime

import django_filters
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Categoria, Solicitacao, Status

FORMATOS_DE_DATA = ["%Y-%m-%d"]
MENSAGEM_DATA_INVALIDA = "Data inválida. Use o formato AAAA-MM-DD."
MENSAGEM_PERIODO_INVERTIDO = "A data inicial não pode ser maior que a data final."
TAMANHO_MAXIMO_DA_BUSCA = 100


def _meia_noite(dia):
    """00:00 do dia, no fuso do projeto."""
    return timezone.make_aware(datetime.datetime.combine(dia, datetime.time.min))


class FiltroSolicitacao(django_filters.FilterSet):
    de = django_filters.DateFilter(
        method="filtrar_de",
        input_formats=FORMATOS_DE_DATA,
        error_messages={"invalid": MENSAGEM_DATA_INVALIDA},
    )
    ate = django_filters.DateFilter(
        method="filtrar_ate",
        input_formats=FORMATOS_DE_DATA,
        error_messages={"invalid": MENSAGEM_DATA_INVALIDA},
    )
    categoria = django_filters.ModelChoiceFilter(
        queryset=Categoria.objects.all(),
        error_messages={"invalid_choice": "Categoria inválida."},
    )
    status = django_filters.ChoiceFilter(
        choices=Status.choices,
        empty_label=None,
        error_messages={"invalid_choice": "Status inválido."},
    )
    q = django_filters.CharFilter(
        method="filtrar_q",
        max_length=TAMANHO_MAXIMO_DA_BUSCA,
        error_messages={
            "max_length": f"A busca deve ter no máximo {TAMANHO_MAXIMO_DA_BUSCA} caracteres."
        },
    )

    class Meta:
        model = Solicitacao
        fields = []

    def filtrar_de(self, consulta, nome, valor):
        return consulta.filter(criado_em__gte=_meia_noite(valor))

    def filtrar_ate(self, consulta, nome, valor):
        return consulta.filter(criado_em__lt=_meia_noite(valor + datetime.timedelta(days=1)))

    def filtrar_q(self, consulta, nome, valor):
        # O icontains escapa % e _, então a busca por "50%" procura o texto literal.
        return consulta.filter(titulo__icontains=valor)


def filtrar(consulta, parametros):
    """Aplica os filtros a uma consulta já restrita ao que o usuário pode ver.

    Parâmetros inválidos levantam ValidationError com a mensagem de cada campo, no mesmo
    formato dos demais erros de validação (400).
    """
    filtro = FiltroSolicitacao(data=parametros, queryset=consulta)
    formulario = filtro.form
    erros = {campo: lista[0] for campo, lista in formulario.errors.items()}

    inicio = formulario.cleaned_data.get("de")
    fim = formulario.cleaned_data.get("ate")
    if not erros and inicio and fim and inicio > fim:
        erros["de"] = MENSAGEM_PERIODO_INVERTIDO

    if erros:
        raise ValidationError(erros)
    return filtro.qs
