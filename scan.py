async def handler(request):
    return Response('{"status":"ok","v":8}', status=200, headers={"Content-Type": "application/json"})