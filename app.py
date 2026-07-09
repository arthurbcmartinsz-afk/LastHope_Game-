

import os                      # ler variáveis de ambiente (ex.: GROQ_API_KEY)
import json                    # ler o arquivo eduardo_pistas.json
import datetime as dt          # calcular quanto tempo já passou de missão

from flask import Flask, render_template, request, jsonify  # framework web

from storage import (          # funções que leem/gravam o progresso em disco
    init_db,
    salvar_mensagem,
    carregar_historico,
    resetar_historico,
    obter_inicio_sessao,
    obter_proativos_enviados,
    marcar_proativo_enviado,
    AGENTES_VALIDOS,
)
from agents.engine import get_system_prompt, get_agent_response  # motor de IA

app = Flask(__name__)          # cria a aplicação Flask

# ID fixo do único jogador deste protótipo (veja explicação no topo do arquivo).
ID_JOGADOR = "jogador"

init_db()  # garante que a pasta data/ existe assim que o servidor sobe


def montar_mensagens(agent_id):
    """Monta a lista de mensagens no formato que a IA espera:
    1) o system prompt (a personalidade fixa daquele personagem, vinda do .txt)
    2) todo o histórico de conversa já salvo com ele."""
    historico = carregar_historico(ID_JOGADOR, agent_id)          # busca o que já foi conversado
    mensagens_api = [{"role": m["role"], "content": m["content"]} for m in historico]  # só role+content, do jeito que a IA espera
    return [{"role": "system", "content": get_system_prompt(agent_id)}] + mensagens_api  # persona + histórico


@app.route("/")
def index():
    # Só serve a página; o cronômetro da missão começa mesmo é quando o
    # jogador clica em "INICIAR MISSÃO" (rota /api/missao/iniciar).
    return render_template("index.html")


@app.route("/api/chat/<agent_id>", methods=["POST"])
def chat_agente(agent_id):
    # ── 0. Personagem válido? ──────────────────────────────────────
    if agent_id not in AGENTES_VALIDOS:
        return jsonify({"error": "Personagem inválido"}), 404       # 404: personagem não existe

    # ── 1. Leitura defensiva do JSON enviado pelo front-end ────────
    data = request.get_json(force=True, silent=True)  # força tentar ler; nunca lança exceção crua
    if data is None:
        return jsonify({
            "error": "Corpo da requisição inválido. Envie JSON com "
                    "Content-Type: application/json, ex: {\"message\": \"...\"}"
        }), 400

    user_message = (data.get("message") or "").strip()  # pega o texto e tira espaços nas pontas
    if not user_message:
        return jsonify({"error": "Mensagem vazia"}), 400  # não manda nada vazio pra IA

    salvar_mensagem(ID_JOGADOR, agent_id, "user", user_message)  # grava a fala do jogador
    mensagens = montar_mensagens(agent_id)                       # persona + histórico atualizado

    # ── 2. Chamada à IA isolada em try/except ─────────────────────
    # Qualquer erro aqui (chave da Groq ausente/inválida, persona .txt
    # faltando, timeout, rate limit etc.) sempre devolve JSON, nunca uma
    # página de erro HTML (que quebraria o front-end).
    try:
        resposta = get_agent_response(agent_id, mensagens)             # pergunta pra IA
        salvar_mensagem(ID_JOGADOR, agent_id, "assistant", resposta)   # grava a resposta
        return jsonify({"reply": resposta})                            # devolve pro front-end
    except FileNotFoundError as e:
        print("Persona ausente:", repr(e))
        return jsonify({
            "error": f"A persona de '{agent_id}' ainda não foi configurada "
                    f"(falta o arquivo agents/personas/{agent_id}.txt)."
        }), 500
    except Exception as e:
        print("Erro Groq:", repr(e))
        return jsonify({"error": f"{agent_id.capitalize()} não respondeu. Tente novamente."}), 500


@app.route("/api/missao/iniciar", methods=["POST"])
def iniciar_missao():
    """Chamada quando o jogador clica em "INICIAR MISSÃO". Marca o instante
    zero do cronômetro — a partir daqui as mensagens espontâneas do Eduardo
    passam a contar tempo."""
    inicio = obter_inicio_sessao(ID_JOGADOR)   # cria (ou reaproveita) o horário de início
    return jsonify({"status": "ok", "inicio": inicio})


@app.route("/api/missao/reiniciar", methods=["POST"])
def reiniciar_missao():
    """Chamada em "REINICIAR MISSÃO": apaga todo o histórico (todos os
    personagens, cronômetro e pistas já enviadas) pra recomeçar do zero."""
    resetar_historico(ID_JOGADOR, agent_id=None)  # None = apaga tudo, não só 1 personagem
    return jsonify({"status": "ok"})


@app.route("/api/chat/<agent_id>/historico", methods=["GET"])
def historico_agente(agent_id):
    """Usado quando o jogador reabre um chat, pra recarregar as mensagens anteriores."""
    if agent_id not in AGENTES_VALIDOS:
        return jsonify({"error": "Personagem inválido"}), 404
    return jsonify({"mensagens": carregar_historico(ID_JOGADOR, agent_id)})


@app.route("/api/chat/<agent_id>/reset", methods=["POST"])
def reset_agente(agent_id):
    """Zera o histórico de apenas UM personagem (não usado na interface hoje,
    mas fica disponível pra depuração/futuras funções)."""
    if agent_id not in AGENTES_VALIDOS:
        return jsonify({"error": "Personagem inválido"}), 404
    resetar_historico(ID_JOGADOR, agent_id)
    return jsonify({"status": "ok"})


@app.route("/api/chat/eduardo/proativo", methods=["GET"])
def eduardo_proativo():
    """Confere se já passou tempo suficiente (desde o início da missão) pra
    alguma mensagem espontânea do Eduardo (definidas em eduardo_pistas.json)
    "disparar" sozinha. O front-end chama essa rota de tempos em tempos
    (polling); cada mensagem só é enviada uma única vez."""
    inicio = dt.datetime.fromisoformat(obter_inicio_sessao(ID_JOGADOR))  # horário em que a missão começou
    decorrido_segundos = (dt.datetime.utcnow() - inicio).total_seconds()  # quanto tempo já passou

    pistas = _carregar_pistas_eduardo()                       # lê o roteiro de pistas do JSON
    ja_enviadas = obter_proativos_enviados(ID_JOGADOR, "eduardo")  # índices que já foram mandados

    novas_mensagens = []
    for indice, pista in enumerate(pistas):
        if indice in ja_enviadas:
            continue                                          # essa pista já foi enviada antes
        if decorrido_segundos >= pista.get("segundos", 0):    # já deu o tempo dessa pista?
            textos = pista.get("mensagens", [])                # lista de falas dessa pista
            for texto in textos:
                salvar_mensagem(ID_JOGADOR, "eduardo", "assistant", texto)
            novas_mensagens.extend(textos)
            marcar_proativo_enviado(ID_JOGADOR, "eduardo", indice)  # não repetir essa pista de novo

    return jsonify({"mensagens": novas_mensagens})


def _carregar_pistas_eduardo():
    """Lê agents/eduardo_pistas.json (tempo + texto de cada pista
    espontânea do Eduardo). Editar esse arquivo não exige mexer em código."""
    caminho = os.path.join(os.path.dirname(__file__), "agents", "eduardo_pistas.json")
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print("Aviso: não foi possível ler eduardo_pistas.json:", repr(e))
        return []


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Rota não encontrada"}), 404


@app.errorhandler(500)
def internal_error(e):
    # Rede de segurança final: qualquer erro não tratado ainda devolve JSON
    # (nunca a página de erro HTML padrão do Flask).
    return jsonify({"error": "Erro interno do servidor"}), 500


if __name__ == "__main__":
    app.run(debug=True)
