def handler(req, context):
    return new Response('{"status":"ok","step":"5"}', status=200, headers={"Content-Type": "application/json"})