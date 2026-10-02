import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from solicitacoes.permissions import EhAutor
from usuarios.models import Papel, Usuario

pytestmark = pytest.mark.django_db

SENHA = "Senha@123"


def criar_usuario(login="maria", papel=Papel.SOLICITANTE, ativo=True, senha=SENHA):
    return Usuario.objects.create_user(
        login, senha, nome=login.capitalize(), papel=papel, ativo=ativo
    )


def logar(cliente, login="maria", senha=SENHA):
    return cliente.post("/api/auth/login/", {"login": login, "senha": senha}, format="json")


def autenticado(token):
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return cliente


@pytest.fixture
def maria():
    return criar_usuario()


@pytest.fixture
def cliente():
    return APIClient()


class TestLogin:
    def test_login_valido_devolve_tokens_e_usuario(self, cliente, maria):
        resposta = logar(cliente)

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert set(corpo) == {"acesso", "renovacao", "usuario"}
        assert corpo["usuario"] == {
            "id": maria.pk,
            "nome": "Maria",
            "login": "maria",
            "papel": "SOLICITANTE",
        }

    def test_resposta_nao_expoe_senha_nem_hash(self, cliente, maria):
        resposta = logar(cliente)

        maria.refresh_from_db()
        assert SENHA not in resposta.content.decode()
        assert maria.password not in resposta.content.decode()

    def test_login_registra_o_ultimo_acesso(self, cliente, maria):
        assert maria.last_login is None

        logar(cliente)

        maria.refresh_from_db()
        assert maria.last_login is not None

    def test_senha_fica_gravada_com_hash(self, maria):
        assert maria.password != SENHA
        assert maria.password.startswith(("md5$", "pbkdf2_sha256$"))
        assert maria.check_password(SENHA)

    @pytest.mark.parametrize(
        "credenciais",
        [
            {"login": "maria", "senha": "errada"},
            {"login": "ninguem", "senha": SENHA},
            {"login": "MARIA", "senha": SENHA},
        ],
        ids=["senha errada", "usuario inexistente", "maiusculas diferentes"],
    )
    def test_credenciais_invalidas_recebem_a_mesma_resposta_generica(
        self, cliente, maria, credenciais
    ):
        resposta = cliente.post("/api/auth/login/", credenciais, format="json")

        assert resposta.status_code == 400
        assert resposta.json() == {
            "erro": "CREDENCIAIS_INVALIDAS",
            "mensagem": "Usuário ou senha inválidos.",
        }

    def test_usuario_inativo_nao_entra_e_nao_se_distingue_de_senha_errada(self, cliente):
        criar_usuario("inativo", ativo=False)

        resposta = logar(cliente, "inativo")

        assert resposta.status_code == 400
        assert resposta.json()["erro"] == "CREDENCIAIS_INVALIDAS"

    def test_campos_obrigatorios(self, cliente):
        resposta = cliente.post("/api/auth/login/", {}, format="json")

        assert resposta.status_code == 400
        assert resposta.json() == {
            "erro": "VALIDACAO",
            "mensagem": "Dados inválidos",
            "detalhes": {"login": "Informe o usuário.", "senha": "Informe a senha."},
        }

    def test_campos_em_branco(self, cliente):
        resposta = cliente.post("/api/auth/login/", {"login": "  ", "senha": ""}, format="json")

        assert resposta.json()["detalhes"] == {
            "login": "Informe o usuário.",
            "senha": "Informe a senha.",
        }

    def test_corpo_que_nao_e_json(self, cliente):
        resposta = cliente.generic(
            "POST", "/api/auth/login/", data="{quebrado", content_type="application/json"
        )

        assert resposta.status_code == 400
        assert resposta.json()["erro"] == "REQUISICAO_INVALIDA"

    def test_metodo_get_nao_e_aceito(self, cliente):
        assert cliente.get("/api/auth/login/").status_code == 405

    def test_login_recusado_vai_para_o_log_sem_a_senha(self, cliente, maria, caplog):
        with caplog.at_level(logging.INFO, logger="portal.auth"):
            logar(cliente, "maria", "senha-que-nao-pode-vazar")

        texto = " ".join(registro.getMessage() for registro in caplog.records)
        assert "Login recusado" in texto
        assert "senha-que-nao-pode-vazar" not in texto

    def test_limite_de_cinco_tentativas_por_minuto(self, cliente, maria):
        for _ in range(5):
            assert logar(cliente, "maria", "errada").status_code == 400

        sexta = logar(cliente, "maria", "errada")

        assert sexta.status_code == 429
        assert sexta.json() == {
            "erro": "MUITAS_TENTATIVAS",
            "mensagem": "Muitas tentativas de login. Aguarde 1 minuto e tente novamente.",
        }
        assert int(sexta["Retry-After"]) > 0
        # Mesmo com a senha certa, o bloqueio vale até a janela passar.
        assert logar(cliente).status_code == 429

    def test_usuarios_do_seed_entram_com_as_senhas_de_demonstracao(self, cliente):
        call_command("carregar_seed", verbosity=0)

        maria = logar(cliente, "maria.solicitante", "Demo@123")
        ana = logar(APIClient(), "ana.atendente", "Demo@123")

        assert maria.status_code == 200
        assert maria.json()["usuario"]["papel"] == "SOLICITANTE"
        assert ana.status_code == 200
        assert ana.json()["usuario"]["papel"] == "ATENDENTE"


class TestRotasProtegidas:
    @pytest.mark.parametrize(
        ("metodo", "rota"),
        [("get", "/api/auth/me/"), ("post", "/api/auth/logout/")],
    )
    def test_sem_token_devolve_401(self, cliente, metodo, rota):
        resposta = getattr(cliente, metodo)(rota)

        assert resposta.status_code == 401
        assert resposta.json() == {
            "erro": "NAO_AUTENTICADO",
            "mensagem": "Faça login para continuar.",
        }
        assert resposta["WWW-Authenticate"].startswith("Bearer")

    @pytest.mark.parametrize("rota", ["/api/saude/", "/api/ola/"])
    def test_rotas_publicas_nao_exigem_login(self, cliente, rota):
        assert cliente.get(rota).status_code == 200

    def test_rota_inexistente_continua_404_e_nao_401(self, cliente):
        assert cliente.get("/api/nao-existe/").status_code == 404

    def test_me_com_token_devolve_os_dados_do_usuario(self, maria):
        token = str(AccessToken.for_user(maria))

        resposta = autenticado(token).get("/api/auth/me/")

        assert resposta.status_code == 200
        assert resposta.json() == {
            "id": maria.pk,
            "nome": "Maria",
            "login": "maria",
            "papel": "SOLICITANTE",
        }

    def test_token_de_acesso_do_login_funciona_no_me(self, cliente, maria):
        acesso = logar(cliente).json()["acesso"]

        assert autenticado(acesso).get("/api/auth/me/").status_code == 200

    @pytest.mark.parametrize(
        "cabecalho",
        ["Bearer lixo.que.nao.e.jwt", "Bearer", "Token abc", "Bearer a b c"],
    )
    def test_token_malformado_devolve_401(self, cliente, cabecalho):
        cliente.credentials(HTTP_AUTHORIZATION=cabecalho)

        resposta = cliente.get("/api/auth/me/")

        assert resposta.status_code == 401
        assert resposta.json()["erro"] == "NAO_AUTENTICADO"

    def test_token_de_renovacao_nao_serve_como_acesso(self, maria):
        renovacao = str(RefreshToken.for_user(maria))

        resposta = autenticado(renovacao).get("/api/auth/me/")

        assert resposta.status_code == 401
        assert resposta.json()["erro"] == "NAO_AUTENTICADO"

    def test_token_expirado_devolve_sessao_expirada(self, maria):
        token = AccessToken.for_user(maria)
        token.set_exp(lifetime=-timedelta(seconds=5))

        resposta = autenticado(str(token)).get("/api/auth/me/")

        assert resposta.status_code == 401
        assert resposta.json() == {
            "erro": "SESSAO_EXPIRADA",
            "mensagem": "Sua sessão expirou. Faça login novamente.",
        }

    def test_token_assinado_com_outra_chave_e_recusado(self, maria):
        import jwt

        forjado = jwt.encode(
            {"token_type": "access", "user_id": maria.pk, "jti": "x", "exp": 9999999999},
            "chave-errada-com-mais-de-32-caracteres-para-hmac",
            algorithm="HS256",
        )

        resposta = autenticado(forjado).get("/api/auth/me/")

        assert resposta.status_code == 401
        assert resposta.json()["erro"] == "NAO_AUTENTICADO"

    def test_usuario_desativado_perde_o_acesso_na_hora(self, maria):
        token = str(AccessToken.for_user(maria))
        maria.ativo = False
        maria.save()

        resposta = autenticado(token).get("/api/auth/me/")

        assert resposta.status_code == 401

    def test_usuario_excluido_nao_autentica(self, maria):
        token = str(AccessToken.for_user(maria))
        maria.delete()

        assert autenticado(token).get("/api/auth/me/").status_code == 401

    def test_validade_dos_tokens_segue_a_configuracao(self, maria):
        refresh = RefreshToken.for_user(maria)

        assert refresh.access_token["exp"] - refresh.access_token["iat"] == 15 * 60
        assert refresh["exp"] - refresh["iat"] == 8 * 3600


class TestRenovacao:
    def test_renovacao_valida_devolve_novo_acesso(self, cliente, maria):
        renovacao = logar(cliente).json()["renovacao"]

        resposta = APIClient().post("/api/auth/refresh/", {"renovacao": renovacao}, format="json")

        assert resposta.status_code == 200
        assert set(resposta.json()) == {"acesso"}
        assert autenticado(resposta.json()["acesso"]).get("/api/auth/me/").status_code == 200

    def test_renovacao_nao_rotaciona_o_token_de_renovacao(self, cliente, maria):
        renovacao = logar(cliente).json()["renovacao"]

        for _ in range(2):
            resposta = cliente.post("/api/auth/refresh/", {"renovacao": renovacao}, format="json")
            assert resposta.status_code == 200

    def test_renovacao_sem_corpo(self, cliente):
        resposta = cliente.post("/api/auth/refresh/", {}, format="json")

        assert resposta.status_code == 400
        assert resposta.json()["detalhes"] == {"renovacao": "Informe o token de renovação."}

    def test_renovacao_invalida(self, cliente):
        resposta = cliente.post("/api/auth/refresh/", {"renovacao": "lixo"}, format="json")

        assert resposta.status_code == 401
        assert resposta.json()["erro"] == "NAO_AUTENTICADO"

    def test_token_de_acesso_nao_serve_como_renovacao(self, cliente, maria):
        acesso = str(AccessToken.for_user(maria))

        resposta = cliente.post("/api/auth/refresh/", {"renovacao": acesso}, format="json")

        assert resposta.status_code == 401

    def test_renovacao_expirada(self, cliente, maria):
        refresh = RefreshToken.for_user(maria)
        refresh.set_exp(lifetime=-timedelta(seconds=5))

        resposta = cliente.post("/api/auth/refresh/", {"renovacao": str(refresh)}, format="json")

        assert resposta.status_code == 401
        assert resposta.json()["erro"] == "SESSAO_EXPIRADA"

    def test_renovacao_de_usuario_inativo_e_recusada(self, cliente, maria):
        renovacao = str(RefreshToken.for_user(maria))
        maria.ativo = False
        maria.save()

        resposta = cliente.post("/api/auth/refresh/", {"renovacao": renovacao}, format="json")

        assert resposta.status_code == 401


class TestLogout:
    def test_logout_invalida_a_renovacao(self, cliente, maria):
        tokens = logar(cliente).json()
        sessao = autenticado(tokens["acesso"])

        logout = sessao.post("/api/auth/logout/", {"renovacao": tokens["renovacao"]}, format="json")
        renovar = APIClient().post(
            "/api/auth/refresh/", {"renovacao": tokens["renovacao"]}, format="json"
        )

        assert logout.status_code == 204
        assert logout.content == b""
        assert renovar.status_code == 401
        assert renovar.json()["erro"] == "NAO_AUTENTICADO"

    def test_logout_sem_estar_logado(self, cliente, maria):
        renovacao = str(RefreshToken.for_user(maria))

        resposta = cliente.post("/api/auth/logout/", {"renovacao": renovacao}, format="json")

        assert resposta.status_code == 401

    def test_logout_exige_o_token_de_renovacao(self, maria):
        resposta = autenticado(str(AccessToken.for_user(maria))).post(
            "/api/auth/logout/", {}, format="json"
        )

        assert resposta.status_code == 400
        assert resposta.json()["erro"] == "VALIDACAO"

    def test_logout_com_token_invalido(self, maria):
        resposta = autenticado(str(AccessToken.for_user(maria))).post(
            "/api/auth/logout/", {"renovacao": "lixo"}, format="json"
        )

        assert resposta.status_code == 400
        assert resposta.json()["detalhes"] == {"renovacao": "Token de renovação inválido."}

    def test_nao_e_possivel_encerrar_a_sessao_de_outro_usuario(self, maria):
        joao = criar_usuario("joao")
        renovacao_do_joao = str(RefreshToken.for_user(joao))

        resposta = autenticado(str(AccessToken.for_user(maria))).post(
            "/api/auth/logout/", {"renovacao": renovacao_do_joao}, format="json"
        )

        assert resposta.status_code == 400
        # A sessão do João segue renovável.
        renovar = APIClient().post(
            "/api/auth/refresh/", {"renovacao": renovacao_do_joao}, format="json"
        )
        assert renovar.status_code == 200

    def test_logout_repetido_com_o_mesmo_token(self, maria):
        refresh = str(RefreshToken.for_user(maria))
        sessao = autenticado(str(AccessToken.for_user(maria)))
        sessao.post("/api/auth/logout/", {"renovacao": refresh}, format="json")

        segunda = sessao.post("/api/auth/logout/", {"renovacao": refresh}, format="json")

        assert segunda.status_code == 400

    def test_acesso_ja_emitido_vale_ate_expirar(self, cliente, maria):
        """Limitação conhecida do JWT (D13): o logout só bloqueia a renovação."""
        tokens = logar(cliente).json()
        sessao = autenticado(tokens["acesso"])
        sessao.post("/api/auth/logout/", {"renovacao": tokens["renovacao"]}, format="json")

        assert sessao.get("/api/auth/me/").status_code == 200


class TestAutorizacao:
    def test_atendente_acessa_rota_restrita(self):
        ana = criar_usuario("ana", papel=Papel.ATENDENTE)

        resposta = autenticado(str(AccessToken.for_user(ana))).get("/api/so-atendente/")

        assert resposta.status_code == 200

    def test_solicitante_recebe_403_em_rota_de_atendente(self, maria):
        resposta = autenticado(str(AccessToken.for_user(maria))).get("/api/so-atendente/")

        assert resposta.status_code == 403
        assert resposta.json() == {
            "erro": "SEM_PERMISSAO",
            "mensagem": "Você não tem permissão para realizar esta ação.",
        }

    def test_sem_token_a_rota_de_atendente_devolve_401_e_nao_403(self, cliente):
        assert cliente.get("/api/so-atendente/").status_code == 401

    def test_so_o_autor_passa_na_permissao_de_objeto(self, maria):
        joao = criar_usuario("joao")
        solicitacao = SimpleNamespace(solicitante_id=maria.pk)
        permissao = EhAutor()

        autor = permissao.has_object_permission(SimpleNamespace(user=maria), None, solicitacao)
        outro = permissao.has_object_permission(SimpleNamespace(user=joao), None, solicitacao)

        assert autor is True
        assert outro is False

    def test_atendente_que_nao_e_autor_nao_edita(self, maria):
        ana = criar_usuario("ana", papel=Papel.ATENDENTE)
        solicitacao = SimpleNamespace(solicitante_id=maria.pk)

        assert not EhAutor().has_object_permission(SimpleNamespace(user=ana), None, solicitacao)

    def test_atendente_pode_editar_a_propria_solicitacao(self):
        ana = criar_usuario("ana", papel=Papel.ATENDENTE)
        solicitacao = SimpleNamespace(solicitante_id=ana.pk)

        assert EhAutor().has_object_permission(SimpleNamespace(user=ana), None, solicitacao)


@pytest.fixture(autouse=True)
def rotas_de_teste(request, settings):
    """Só os testes de autorização usam a rota extra de teste."""
    if request.cls is TestAutorizacao:
        settings.ROOT_URLCONF = "usuarios.tests.urls_teste"
