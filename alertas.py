"""Persistência dos eventos da Semana 6 na tabela alertas existente."""
from hashlib import sha256

DESTINOS = {"agenda", "metas", "atividade_nova"}


def sincronizar_alertas(cliente, usuario, gerados, existentes, agora):
    conhecidos = {a.get("chave_evento") for a in existentes}
    novos = []
    for alerta in gerados:
        # Tamanho fixo, identidade independente do texto exibido e do dia da visita.
        chave = sha256(alerta["chave_evento"].encode("utf-8")).hexdigest()
        alerta["chave_evento"] = chave
        if chave not in conhecidos:
            novos.append({"id_usuario": usuario, "chave_evento": chave,
                          "mensagem": alerta["mensagem"], "tipo": alerta["destino"],
                          "data_hora": agora.isoformat(), "status": "nao_lido"})
            conhecidos.add(chave)
    if novos:
        cliente.table("alertas").upsert(novos, on_conflict="id_usuario,chave_evento",
                                       ignore_duplicates=True).execute()


def preparar_alertas(registros):
    return [{**a, "lido": a.get("status") == "lido",
             "destino": a["tipo"] if a.get("tipo") in DESTINOS else "alertas"}
            for a in registros]
