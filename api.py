def handler(req, context):
    return new Response('{"status": "ok"}', status=200, headers={"Content-Type": "application/json"})