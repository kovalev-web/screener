module.exports = async function handler(req) {
  return new Response(JSON.stringify({ok: true}), {
    status: 200,
    headers: {"Content-Type": "application/json"}
  })
}