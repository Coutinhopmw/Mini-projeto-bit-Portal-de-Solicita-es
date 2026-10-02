import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def limpar_cache():
    """O limite de tentativas de login usa o cache; cada teste começa com ele vazio."""
    cache.clear()
    yield
    cache.clear()
