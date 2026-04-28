async def handler(req):
    return Response('{"status":"ok","v":5}', status=200, headers={"Content-Type": "application/json"})