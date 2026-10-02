from rest_framework.throttling import SimpleRateThrottle


class LimiteDeLogin(SimpleRateThrottle):
    """No máximo 5 tentativas de login por minuto por endereço IP (RN19).

    A taxa está em REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["login"]. O contador usa o
    cache padrão; atrás de um proxy reverso, configure NUM_PROXIES para o DRF ler o IP real.
    """

    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
