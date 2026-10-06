#!/usr/bin/env node
// DEAD LEGACY — retired 2026-10-02. Production moved to https://scout-packs-production.up.railway.app (Railway). Kept for reference only.
// Minimal localtunnel client that reaches the tunnel server through an
// HTTP CONNECT egress proxy (the stock `lt` client opens raw TCP, which the
// sandbox blocks). Protocol mirror of localtunnel@2.0.2 TunnelCluster:
// one local proxied connection per tunnel leg, replaced when it dies.
const net = require('net');
const { execSync } = require('child_process');
const { URL } = require('url');

const SUBDOMAIN = process.argv[2] || 'scoutpacks-tunnel-1';
const LOCAL_PORT = parseInt(process.argv[3] || '8000', 10);
const MAX_CONN = 2;

const proxyUrl = new URL(process.env.https_proxy || process.env.HTTPS_PROXY || '');
function dec(s) { try { return decodeURIComponent(s); } catch { return s; } }
const proxyAuth = proxyUrl.username
  ? Buffer.from(dec(proxyUrl.username) + ':' + dec(proxyUrl.password)).toString('base64')
  : null;
const PROXY_HOST = proxyUrl.hostname;
const PROXY_PORT = parseInt(proxyUrl.port || '3128', 10);

function allocate() {
  const out = execSync(`curl -s -m 20 "https://localtunnel.me/${SUBDOMAIN}"`, { encoding: 'utf8' });
  return JSON.parse(out);
}

function openLeg(tunnelHost, tunnelPort) {
  const sock = new net.Socket();
  sock.setKeepAlive(true);
  let established = false;
  let buf = Buffer.alloc(0);

  sock.on('data', (chunk) => {
    if (!established) {
      buf = Buffer.concat([buf, chunk]);
      const idx = buf.indexOf('\r\n\r\n');
      if (idx === -1) return;
      const head = buf.slice(0, idx).toString('latin1');
      const rest = buf.slice(idx + 4);
      buf = null;
      if (!/^HTTP\/1\.[01] 200/.test(head)) {
        console.error('[leg] CONNECT failed:', head.split('\r\n')[0]);
        sock.destroy();
        setTimeout(() => openLeg(tunnelHost, tunnelPort), 5000);
        return;
      }
      established = true;
      legs.add(sock);
      console.log('[leg] established ->', `${tunnelHost}:${tunnelPort}`, `(legs: ${legs.size})`);
      if (rest.length) serveRequest(sock, rest);
      else waitForRequest(sock);
      return;
    }
  });

  sock.on('error', (e) => console.error('[leg] socket error:', e.message));
  const dead = () => {
    if (legs.delete(sock)) console.log('[leg] lost, replacing (legs: %d)', legs.size);
    // replace lost legs (debounced by watchdog too)
    setTimeout(() => openLeg(tunnelHost, tunnelPort), 2000);
  };
  sock.on('close', () => {
    // if we never got established, retry (original behavior); if established, replace
    dead();
  });

  sock.connect(PROXY_PORT, PROXY_HOST, () => {
    let req = `CONNECT ${tunnelHost}:${tunnelPort} HTTP/1.1\r\nHost: ${tunnelHost}:${tunnelPort}\r\n`;
    if (proxyAuth) req += `Proxy-Authorization: Basic ${proxyAuth}\r\n`;
    sock.write(req + '\r\n');
  });
}

function waitForRequest(sock) {
  const onData = (chunk) => {
    sock.removeListener('data', onData);
    serveRequest(sock, chunk);
  };
  sock.on('data', onData);
}

function serveRequest(sock, firstChunk) {
  const m = firstChunk.toString('latin1').match(/^(\w+) (\S+)/);
  console.log('[req]', m ? `${m[1]} ${m[2]}` : '(unparsed)');
  const local = net.connect(LOCAL_PORT, '127.0.0.1');
  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    try { local.destroy(); } catch {}
    // destroying sock triggers openLeg's close handler, which replaces the leg
    try { sock.destroy(); } catch {}
  };
  local.on('connect', () => {
    local.write(firstChunk);
    sock.pipe(local);
    local.pipe(sock);
  });
  local.on('error', (e) => { console.error('[local] error:', e.message); cleanup(); });
  local.on('close', cleanup);
  sock.on('close', cleanup);
  sock.on('error', () => {});
}

let currentHost, currentPort;
const legs = new Set(); // live, established tunnel sockets (top-up via watchdog below)
try {
  const info = allocate();
  console.log('[alloc]', info.url, '-> remote port', info.port);
  // NOTE: the tunnel server is localtunnel.me itself (remote_host in the lt
  // client = the API host); the *.loca.lt hostname is only the public URL.
  currentHost = 'localtunnel.me';
  currentPort = info.port;
  console.log('[info] public URL:', info.url);
  for (let i = 0; i < (info.max_conn_count || MAX_CONN); i++) openLeg(currentHost, currentPort);
  // watchdog: keep MAX_CONN legs alive (survives local server restarts, etc.)
  setInterval(() => {
    const want = info.max_conn_count || MAX_CONN;
    for (let i = legs.size; i < want; i++) {
      console.log('[watchdog] topping up leg (have %d, want %d)', legs.size, want);
      openLeg(currentHost, currentPort);
    }
  }, 15000);
} catch (e) {
  console.error('[alloc] failed:', e.message);
  process.exit(1);
}
