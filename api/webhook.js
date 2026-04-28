module.exports = async function handler(req, context) {
  return new Response('{"ok":true}', {
    status: 200,
    headers: {"Content-Type": "application/json"}
  })
}