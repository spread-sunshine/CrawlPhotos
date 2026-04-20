const http = require('http');
const fs = require('fs');
const path = require('path');
const urlModule = require('url');

const BACKEND = '127.0.0.1:8000';
const ROOT = path.join(__dirname, 'web', 'dist');

function serveStatic(reqPath, res) {
  let filePath = path.join(ROOT, reqPath === '/' ? 'index.html' : reqPath);
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('Not Found');
      return;
    }
    const ext = path.extname(filePath);
    const types = {
      '.html': 'text/html',
      '.js': 'application/javascript',
      '.css': 'text/css',
      '.svg': 'image/svg+xml',
      '.png': 'image/png',
      '.jpg': 'image/jpeg',
      '.ico': 'image/x-icon',
    };
    res.writeHead(200, {
      'Content-Type': types[ext] || 'text/plain',
      'Access-Control-Allow-Origin': '*'
    });
    res.end(data);
  });
}

function proxyToBackend(req, res) {
  const fwdHeaders = {};
  for (const [k, v] of Object.entries(req.headers)) {
    if (k.toLowerCase() !== 'host') {
      fwdHeaders[k] = v;
    }
  }
  fwdHeaders['Host'] = '127.0.0.1:8000';

  const options = {
    hostname: '127.0.0.1',
    port: 8000,
    path: req.url,
    method: req.method,
    headers: fwdHeaders,
  };

  console.log(`[PROXY] ${req.method} ${req.url} -> :8000`);

  const proxyReq = http.request(options, (backendRes) => {
    console.log(`[PROXY] <- ${backendRes.statusCode}`);
    res.writeHead(backendRes.statusCode, backendRes.headers);
    backendRes.pipe(res);
  });
  proxyReq.setTimeout(10000);
  proxyReq.on('timeout', () => {
    console.error('[PROXY] timeout');
    proxyReq.destroy();
    res.writeHead(504);
    res.end('Gateway Timeout');
  });
  proxyReq.on('error', (e) => {
    console.error('[PROXY] error:', e.code || e.message);
    res.writeHead(502);
    res.end('Bad Gateway: ' + (e.code || e.message));
  });

  // Collect and forward request body
  let chunks = [];
  req.on('data', (c) => chunks.push(c));
  req.on('end', () => {
    if (chunks.length > 0) {
      proxyReq.end(Buffer.concat(chunks));
    } else {
      proxyReq.end();
    }
  });
}

const server = http.createServer((req, res) => {
  const parsed = urlModule.parse(req.url || '/');
  const pathname = parsed.pathname;

  console.log(`[${req.method}] ${pathname}`);

  if (pathname.startsWith('/api/') ||
      pathname.startsWith('/health') ||
      pathname.startsWith('/metrics')) {
    proxyToBackend(req, res);
  } else {
    serveStatic(pathname, res);
  }
});

server.listen(3000, '0.0.0.0', () => {
  console.log('=== Frontend + API Proxy Server ===');
  console.log('Static files from: web/dist/');
  console.log('API proxy -> http://' + BACKEND);
  console.log('Open: http://localhost:3000/');
});
