"""Cliente compartilhado do Supabase com validação TLS pelos certificados do SO."""

import ssl
import os
import base64
import json
import re

import httpx
from supabase import ClientOptions, create_client


def chave_do_servidor():
    """Modo estrito evita publicar Flask com a chave anon por engano.

    A inspeção local do JWT identifica a configuração, não verifica assinatura nem
    concede autorização. O Supabase é quem autentica a credencial de fato.
    """
    chave = (os.getenv('SUPABASE_SECRET_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
             or os.getenv('SUPABASE_KEY'))
    if os.getenv('LIFES_REQUIRE_SERVER_KEY') == '1':
        # Chaves atuais são opacas; formato não comprova validade/autorização.
        if chave and re.fullmatch(r'sb_secret_[A-Za-z0-9_-]+', chave):
            return chave
        try:
            parte = chave.split('.')[1]
            papel = json.loads(base64.urlsafe_b64decode(parte + '=' * (-len(parte) % 4)))['role']
        except (AttributeError, IndexError, ValueError, KeyError, TypeError):
            papel = None
        if papel != 'service_role':
            raise RuntimeError('Configure SUPABASE_SECRET_KEY (sb_secret_...) ou SUPABASE_SERVICE_ROLE_KEY (JWT service_role) exclusiva do servidor. Nunca exponha essa chave ao navegador.')
    return chave


def criar_cliente(url, chave):
    # Mantém verificação de certificado e hostname. No Windows, inclui as raízes
    # confiáveis do sistema, ausentes do pacote certifi neste ambiente.
    cliente_http = httpx.Client(verify=ssl.create_default_context(), timeout=20)
    return create_client(url, chave, options=ClientOptions(httpx_client=cliente_http))
