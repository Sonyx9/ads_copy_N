from flask import Flask, request, jsonify
from openai import OpenAI
import os
import json
import time

app = Flask(__name__)

# API klíč a Assistant ID z environmentu (na Railway je nastavíš ve Variables)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")

client = OpenAI(api_key=OPENAI_API_KEY)


def default_response():
    """Fallback, když se něco pokazí – MCC skript nespadne."""
    return {
        "replace_headline_index": None,
        "replace_headline_text": "",
        "additional_headline_text": "",
        "replace_description_index": None,
        "replace_description_text": "",
        "additional_description_text": ""
    }


@app.route("/generate_rsa_edits", methods=["POST"])
def generate_rsa_edits():
    if not ASSISTANT_ID:
        return jsonify({"error": "ASSISTANT_ID not set"}), 500
    if not OPENAI_API_KEY:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 500

    data = request.get_json(force=True)

    account_name = data.get("account_name", "")
    campaign_name = data.get("campaign_name", "")
    ad_group_name = data.get("ad_group_name", "")
    final_url = data.get("final_url", "")
    headlines = data.get("headlines", []) or []
    descriptions = data.get("descriptions", []) or []

    # Krátká zpráva pro Asistenta – veškeré chování, pravidla, JSON schema máš v jeho Instructions
    user_message = f"""
Účet: {account_name}
Kampaň: {campaign_name}
Reklamní sestava: {ad_group_name}
Landing page: {final_url}

NADPISY (seřazené podle pořadí v RSA):
{chr(10).join(['- ' + h for h in headlines])}

POPISY:
{chr(10).join(['- ' + d for d in descriptions])}

Použij prosím svoje instrukce:
- vyber 1 nejslabší nadpis a navrhni lepší náhradu
- přidej 1 nový nadpis
- vyber 1 nejslabší popis a navrhni lepší náhradu
- přidej 1 nový popis
- dodrž limity (headline 30 znaků, description 90 znaků)
- vrať POUZE JSON podle definované struktury.
"""

    try:
        # 1) vytvoříme thread
        thread = client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        # 2) spustíme run Asistenta
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
        )

        # 3) polling na dokončení
        while run.status not in ("completed", "failed", "cancelled", "expired"):
            time.sleep(0.5)
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id,
            )

        if run.status != "completed":
            # něco se nepovedlo – vrátíme prázdné změny
            return jsonify(default_response())

        # 4) stáhneme poslední zprávu Asistenta
        messages = client.beta.threads.messages.list(
            thread_id=thread.id,
            order="desc",
            limit=1
        )

        if not messages.data:
            return jsonify(default_response())

        # obsah zprávy (očekáváme čistý JSON jako text)
        text_content = ""
        for part in messages.data[0].content:
            if part.type == "text":
                text_content += part.text.value

        try:
            result = json.loads(text_content)
        except Exception:
            # pokud neprojde JSON, radši nic neměníme
            result = default_response()

        # pro jistotu zajistíme, že všechny potřebné klíče existují
        base = default_response()
        base.update({k: result.get(k, base[k]) for k in base.keys()})

        return jsonify(base)

    except Exception as e:
        # fallback na jakoukoliv chybu
        print("Error in /generate_rsa_edits:", e)
        return jsonify(default_response())


@app.route("/", methods=["GET"])
def health():
    return "OK – AI RSA editor (Assistant) běží", 200


if __name__ == "__main__":
    # lokální běh – Railway si stejně nastaví vlastní port
    app.run(host="0.0.0.0", port=8000)
