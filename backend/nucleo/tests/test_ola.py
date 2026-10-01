from rest_framework.test import APIClient


def test_ola_devolve_mensagem():
    resposta = APIClient().get("/api/ola/")

    assert resposta.status_code == 200
    assert "mensagem" in resposta.json()
