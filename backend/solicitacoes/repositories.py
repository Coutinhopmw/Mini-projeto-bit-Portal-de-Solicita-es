"""Repositories: único ponto de acesso ao banco (consultas e gravações do ORM).

Não contém regra de negócio: quem decide o que cada usuário pode ver é o service, que
passa `solicitante_id` quando a consulta precisa ser restrita às solicitações dele.
"""

from django.db.models import Prefetch

from .models import Categoria, HistoricoStatus, Solicitacao


def _solicitacoes():
    return Solicitacao.objects.select_related("categoria", "solicitante")


def listar(solicitante_id=None):
    """Da mais recente para a mais antiga (RN15)."""
    consulta = _solicitacoes().order_by("-criado_em", "-id")
    if solicitante_id is not None:
        consulta = consulta.filter(solicitante_id=solicitante_id)
    return consulta


def buscar(pk, solicitante_id=None):
    """Uma solicitação com o histórico em ordem cronológica, ou None."""
    historico = HistoricoStatus.objects.select_related("alterado_por").order_by("alterado_em", "id")
    consulta = _solicitacoes().prefetch_related(Prefetch("historico", queryset=historico))
    if solicitante_id is not None:
        consulta = consulta.filter(solicitante_id=solicitante_id)
    return consulta.filter(pk=pk).first()


def buscar_para_atualizar(pk):
    """Trava a linha até o fim da transação, para o status não mudar entre ler e gravar."""
    return Solicitacao.objects.select_for_update().filter(pk=pk).first()


def criar(**dados):
    return Solicitacao.objects.create(**dados)


def atualizar(solicitacao, **dados):
    for campo, valor in dados.items():
        setattr(solicitacao, campo, valor)
    # atualizado_em precisa estar na lista para o auto_now ser aplicado.
    solicitacao.save(update_fields=[*dados, "atualizado_em"])


def excluir(solicitacao):
    """O histórico sai junto, por CASCADE no ORM (D05)."""
    solicitacao.delete()


def registrar_historico(solicitacao, status_anterior, status_novo, alterado_por):
    return HistoricoStatus.objects.create(
        solicitacao=solicitacao,
        status_anterior=status_anterior,
        status_novo=status_novo,
        alterado_por=alterado_por,
    )


def categorias_ativas():
    return Categoria.objects.filter(ativa=True).order_by("nome")
