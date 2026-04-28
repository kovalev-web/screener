async def handler(request):
    return Response('{"status":"ok","v":7}', status=200, headers={"Content-Type": "application/json"})