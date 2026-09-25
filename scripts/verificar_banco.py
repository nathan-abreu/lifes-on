"""Diagnóstico somente de leitura: python -m scripts.verificar_banco.

Não lê registros, não grava dados e não imprime chaves. Confere as colunas
esperadas pelo Flask usando SELECT com limit=0 no Supabase configurado.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from httpx import HTTPError
from postgrest.exceptions import APIError
from banco import criar_cliente


def verificar():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    url = os.getenv("SUPABASE_URL")
    chave = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not chave:
        print("Configure SUPABASE_URL e a chave do banco no .env.")
        return 1
    cliente = criar_cliente(url, chave)
    consultas = {
        "alertas": "id_alerta,mensagem,tipo,data_hora,status,id_usuario,chave_evento",
        "atividades": "id_atividade,id_usuario,tipo_exercicio,duracao,frequencia,data_registro",
        "metas": "id_meta,id_usuario,descricao,prazo,progresso",
        "agenda": "id_agenda,id_usuario,horario,lembrete,titulo",
        "conquistas": "id_conquista,nome,descricao,pontos",
        "usuario_conquista": "id_usuario,id_conquista,data_obtencao",
    }
    falhou = False
    for tabela, campos in consultas.items():
        try:
            cliente.table(tabela).select(campos).limit(0).execute()
            print(f"{tabela}: colunas acessíveis (nenhum registro consultado).")
        except APIError as erro:
            falhou = True
            if erro.code in ("42703", "PGRST204", "42P01", "PGRST205"):
                print(f"{tabela}: estrutura incompleta ({erro.code}); confira schema.sql e a migração antes de aplicar SQL.")
            else:
                print(f"{tabela}: acesso recusado ou falha de banco ({erro.code}); confira chave e permissões.")
        except HTTPError:
            falhou = True
            print(f"{tabela}: falha de conexão; confira URL, DNS e disponibilidade do projeto.")
    print("Este diagnóstico não valida INSERT, UPDATE, DELETE, policies ou persistência.")
    return int(falhou)


if __name__ == "__main__":
    sys.exit(verificar())
