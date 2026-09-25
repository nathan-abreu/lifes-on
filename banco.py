"""Cliente compartilhado do Supabase com validação TLS pelos certificados do SO."""

import ssl

import httpx
from supabase import ClientOptions, create_client


def criar_cliente(url, chave):
    # Mantém verificação de certificado e hostname. No Windows, inclui as raízes
    # confiáveis do sistema, ausentes do pacote certifi neste ambiente.
    cliente_http = httpx.Client(verify=ssl.create_default_context(), timeout=20)
    return create_client(url, chave, options=ClientOptions(httpx_client=cliente_http))
