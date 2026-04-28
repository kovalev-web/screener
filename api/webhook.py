async def handler(request):
    return Response('{"ok":true,"v":2}', status=200, headers={"Content-Type": "application/json"})