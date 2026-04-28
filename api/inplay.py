async def handler(request):
    return Response('{"status":"ok","v":6}', status=200, headers={"Content-Type": "application/json"})