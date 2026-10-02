import logging
import time

logger = logging.getLogger("portal.requisicoes")


class RegistroDeRequisicoesMiddleware:
    """Registra uma linha de log por requisição: método, caminho, status e duração."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inicio = time.perf_counter()
        resposta = self.get_response(request)
        duracao_ms = (time.perf_counter() - inicio) * 1000
        nivel = logging.WARNING if resposta.status_code >= 500 else logging.INFO
        logger.log(
            nivel,
            "%s %s -> %s (%.0f ms)",
            request.method,
            request.get_full_path(),
            resposta.status_code,
            duracao_ms,
        )
        return resposta
