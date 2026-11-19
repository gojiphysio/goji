"""Webhook bodies in Meta's Cloud API shapes."""


def inbound(wa_id="6591234567", msg_id="wamid.in1", text="What are your hours?", ts=1763431200,
            name="Mei Ling", kind="text"):
    msg = {"from": wa_id, "id": msg_id, "timestamp": str(ts), "type": kind}
    if kind == "text":
        msg["text"] = {"body": text}
    else:
        msg[kind] = {"id": "media1"}
    return {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "6583770401", "phone_number_id": "pnid"},
            "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
            "messages": [msg]}}]}]}


def echo(wa_id="6591234567", msg_id="wamid.echo1", text="Hi! Chris here", ts=1763431210):
    return {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "smb_message_echoes", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "6583770401", "phone_number_id": "pnid"},
            "message_echoes": [{"from": "6583770401", "to": wa_id, "id": msg_id,
                                "timestamp": str(ts), "type": "text",
                                "text": {"body": text}}]}}]}]}


def status(msg_id="wamid.out1", st="delivered", wa_id="6591234567", ts=1763431230):
    return {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "6583770401", "phone_number_id": "pnid"},
            "statuses": [{"id": msg_id, "status": st, "timestamp": str(ts),
                          "recipient_id": wa_id}]}}]}]}
