from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from solicitacoes.models import Categoria, HistoricoStatus, Solicitacao, Status
from usuarios.models import Papel, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    return Usuario.objects.create_user("maria", "senha-forte-1", nome="Maria")


@pytest.fixture
def categoria():
    return Categoria.objects.create(nome="TI")


@pytest.fixture
def solicitacao(usuario, categoria):
    return Solicitacao.objects.create(
        titulo="Notebook não liga",
        descricao="O notebook não liga depois da atualização.",
        categoria=categoria,
        solicitante=usuario,
    )


def test_valores_padrao_vem_do_banco(solicitacao):
    solicitacao.refresh_from_db()

    assert solicitacao.status == Status.ABERTO
    # O relógio do banco pode divergir milissegundos do relógio da aplicação.
    assert abs(timezone.now() - solicitacao.criado_em) < timedelta(seconds=5)
    assert abs(solicitacao.atualizado_em - solicitacao.criado_em) < timedelta(seconds=5)


def test_codigo_deriva_do_id(solicitacao):
    assert solicitacao.codigo == f"SOL-{solicitacao.pk:05d}"


def test_usuario_novo_e_solicitante_ativo(usuario):
    assert usuario.papel == Papel.SOLICITANTE
    assert usuario.is_active
    assert not usuario.is_staff


def test_senha_fica_em_hash(usuario):
    assert usuario.password != "senha-forte-1"
    assert usuario.check_password("senha-forte-1")


@pytest.mark.parametrize(
    "campos",
    [
        {"status": "INVALIDO"},
        {"titulo": "ab"},
        {"titulo": "   a   "},
        {"descricao": "curta"},
    ],
)
def test_check_rejeita_solicitacao_invalida(usuario, categoria, campos):
    dados = {
        "titulo": "Título válido",
        "descricao": "Descrição com mais de dez caracteres.",
        "categoria": categoria,
        "solicitante": usuario,
        **campos,
    }
    with pytest.raises(IntegrityError), transaction.atomic():
        Solicitacao.objects.create(**dados)


def test_papel_invalido_e_rejeitado():
    with pytest.raises(IntegrityError), transaction.atomic():
        Usuario.objects.create_user("x", "senha-forte-1", nome="X", papel="CHEFE")


def test_login_e_nome_de_categoria_sao_unicos(usuario, categoria):
    with pytest.raises(IntegrityError), transaction.atomic():
        Usuario.objects.create_user("maria", "outra-senha-1", nome="Outra")
    with pytest.raises(IntegrityError), transaction.atomic():
        Categoria.objects.create(nome="TI")


def test_historico_aceita_criacao_sem_status_anterior(solicitacao, usuario):
    HistoricoStatus.objects.create(
        solicitacao=solicitacao,
        status_anterior=None,
        status_novo=Status.ABERTO,
        alterado_por=usuario,
    )

    assert solicitacao.historico.count() == 1


def test_historico_rejeita_mesmo_status(solicitacao, usuario):
    with pytest.raises(IntegrityError), transaction.atomic():
        HistoricoStatus.objects.create(
            solicitacao=solicitacao,
            status_anterior=Status.ABERTO,
            status_novo=Status.ABERTO,
            alterado_por=usuario,
        )


def test_excluir_solicitacao_remove_o_historico(solicitacao, usuario):
    HistoricoStatus.objects.create(
        solicitacao=solicitacao, status_novo=Status.ABERTO, alterado_por=usuario
    )

    solicitacao.delete()

    assert HistoricoStatus.objects.count() == 0


def test_categoria_em_uso_nao_pode_ser_excluida(solicitacao, categoria):
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        categoria.delete()


def test_seed_cria_os_dados_e_e_idempotente():
    call_command("carregar_seed")
    call_command("carregar_seed")

    assert Categoria.objects.count() == 5
    assert Usuario.objects.count() == 4
    assert Solicitacao.objects.count() == 12
    assert HistoricoStatus.objects.count() == 24
    assert set(Solicitacao.objects.values_list("status", flat=True)) == set(Status.values)
    ana = Usuario.objects.get(login="ana.atendente")
    assert ana.papel == Papel.ATENDENTE
    assert ana.check_password("Demo@123")
    assert Usuario.objects.get(login="admin").is_staff
