async def handler(req, context):
    return Response('{"status":"ok","v":4}', status=200, headers={"Content-Type": "application/json"})