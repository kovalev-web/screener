def handler(req, context):
    return new Response('{"status":"ok","v":3}', status=200, headers={"Content-Type": "application/json"})