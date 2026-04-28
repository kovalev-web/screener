async def handler(request):
    return Response('{"ok":true}', status=200, headers={"Content-Type": "application/json"})