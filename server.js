const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const Anthropic = require('@anthropic-ai/sdk');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = new Server(server);
const client = new Anthropic();

app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

// In-memory store
const behaviors = { above: [], below: [] };
let categories = { above: [], below: [] };

app.get('/state', (req, res) => {
  res.json({ behaviors, categories });
});

app.post('/categorize', async (req, res) => {
  try {
    const aboveList = behaviors.above.map((b, i) => `${i + 1}. ${b}`).join('\n');
    const belowList = behaviors.below.map((b, i) => `${i + 1}. ${b}`).join('\n');

    const prompt = `Analiza los siguientes comportamientos y agrúpalos en categorías temáticas comunes. Responde ÚNICAMENTE con JSON válido.

COMPORTAMIENTOS SOBRE LA LÍNEA:
${aboveList || '(ninguno)'}

COMPORTAMIENTOS BAJO LA LÍNEA:
${belowList || '(ninguno)'}

Responde con este formato JSON exacto:
{
  "above": [
    { "category": "Nombre de categoría", "items": ["comportamiento 1", "comportamiento 2"] }
  ],
  "below": [
    { "category": "Nombre de categoría", "items": ["comportamiento 1", "comportamiento 2"] }
  ]
}

Reglas:
- Agrupa comportamientos similares o relacionados bajo una misma categoría
- Los nombres de categoría deben ser descriptivos y en español
- Cada comportamiento debe aparecer en exactamente una categoría
- Si no hay comportamientos en un tipo, devuelve array vacío`;

    const message = await client.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 2048,
      messages: [{ role: 'user', content: prompt }],
    });

    const text = message.content[0].text.trim();
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('No JSON found');

    categories = JSON.parse(jsonMatch[0]);
    io.emit('categories_updated', categories);
    res.json({ success: true, categories });
  } catch (err) {
    console.error('Categorize error:', err);
    res.status(500).json({ error: err.message });
  }
});

io.on('connection', (socket) => {
  socket.emit('state', { behaviors, categories });

  socket.on('submit_behavior', ({ type, text }) => {
    if (!['above', 'below'].includes(type)) return;
    const clean = (text || '').trim().slice(0, 500);
    if (!clean) return;

    behaviors[type].push(clean);
    io.emit('new_behavior', { type, text: clean });
  });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`Servidor corriendo en http://localhost:${PORT}`);
  console.log(`Vista participante: http://localhost:${PORT}`);
  console.log(`Vista display:      http://localhost:${PORT}/display.html`);
});
