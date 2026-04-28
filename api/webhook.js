export default async function handler(req) {
  return new Response('{"ok":true}', {
    status: 200,
    headers: {'Content-Type': 'application/json'}
  })
}