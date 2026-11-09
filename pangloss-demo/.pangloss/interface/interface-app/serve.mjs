// The production server: the one the Solid plugin builds (dist/server/node.js), with its answers gzipped when the
// browser accepts it. Rendered pages are mostly repeated markup (a calendar month runs to megabytes) and shrink by
// 90% or more. And `/api` is passed on to the Pangloss API, as the development server does: the browser only talks
// to this server. `pangloss interface serve` runs this file (env: PORT, HOST, PANGLOSS_API_URL, PANGLOSS_API_PROXY).
import { createServer, request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import zlib from "node:zlib";
import { createListener } from "./dist/server/node.js";

// Where the API is (the pages rendered here ask it too: src/api.ts)
const apiUrl = process.env.PANGLOSS_API_URL || "http://127.0.0.1:8000";
// "off" where something in front of this server passes `/api` on itself, so that nothing for it should come here
const passesApiOn = process.env.PANGLOSS_API_PROXY !== "off";

// (and other paths the API answers, from `pangloss interface serve --api-path`, such as an installed app's)
const apiPaths = ["/api", ...(process.env.PANGLOSS_API_PATHS ?? "").split(",").filter(Boolean)];

const isForApi = (url) => apiPaths.some((path) => url === path || url.startsWith(`${path}/`) || url.startsWith(`${path}?`));

function refuse(res, detail) {
  if (res.headersSent) return res.destroy();
  res.writeHead(502, { "content-type": "application/json" });
  res.end(JSON.stringify({ detail }));
}

/**
 * Pass a request for `/api` on to the API and its answer back, both as they come (a stream of events stays one). The
 * headers are the browser's, with its `Host`, so that the API sees the request as the browser made it; the answer is
 * not compressed here (the API does that itself). If the API is not there, the answer says so: a login that says
 * only "Not Found" takes a while to understand.
 */
function passOn(req, res) {
  if (!passesApiOn) {
    return refuse(
      res,
      "The interface's server was started with --no-api-proxy, so it does not pass /api on to the Pangloss API: " +
        "what is in front of it has to, and did not",
    );
  }
  let target;
  try {
    target = new URL(req.url, apiUrl);
  } catch {
    return refuse(res, `'${apiUrl}' is not the address of an API: see 'pangloss interface serve --api-url'`);
  }
  const from = [req.headers["x-forwarded-for"], req.socket.remoteAddress].filter(Boolean).join(", ");
  const upstream = (target.protocol === "https:" ? httpsRequest : httpRequest)(
    target,
    { method: req.method, headers: { ...req.headers, "x-forwarded-for": from } },
    (answer) => {
      res.writeHead(answer.statusCode ?? 502, answer.headers);
      answer.pipe(res);
    },
  );
  upstream.on("error", (error) =>
    refuse(
      res,
      `The Pangloss API cannot be reached at ${apiUrl} (${error.code ?? error.message}). Start it ('pangloss run'), ` +
        "or say where it is: 'pangloss interface serve --api-url URL'",
    ),
  );
  // (the browser went away, as it does from a stream of events: the API is not left sending to no one)
  res.on("close", () => upstream.destroy());
  req.pipe(upstream);
}

const COMPRESSIBLE = /^(text\/|application\/(json|javascript|xml|manifest\+json)|image\/svg\+xml)/;
// (smaller answers are sent as they are: compressing them saves nothing worth the time)
const MINIMUM_SIZE = 1000;

/** Make `res` gzip what is written to it, if the request accepts gzip and the answer is text */
function compressed(req, res) {
  if (!/\bgzip\b/.test(req.headers["accept-encoding"] ?? "")) return;
  const write = res.write.bind(res);
  const end = res.end.bind(res);
  let gzip = null;
  let decided = false;

  // (decided on the first write, when the headers are set: the type says whether it is worth it)
  const decide = (firstChunk, ending) => {
    if (decided) return;
    decided = true;
    const type = String(res.getHeader("content-type") ?? "");
    const length = Number(res.getHeader("content-length") ?? NaN);
    const small = (ending && (firstChunk?.length ?? 0) < MINIMUM_SIZE) || length < MINIMUM_SIZE;
    if (!COMPRESSIBLE.test(type) || res.getHeader("content-encoding") || res.statusCode < 200 || res.statusCode === 204 ||
      res.statusCode === 304 || small || res.headersSent) {
      return;
    }
    res.removeHeader("content-length");
    res.setHeader("content-encoding", "gzip");
    res.setHeader("vary", [res.getHeader("vary"), "Accept-Encoding"].filter(Boolean).join(", "));
    // (each chunk is flushed as it comes, so that a page rendered as a stream still arrives as one)
    gzip = zlib.createGzip({ flush: zlib.constants.Z_SYNC_FLUSH });
    gzip.on("data", (chunk) => write(chunk));
    gzip.on("end", () => end());
    gzip.on("drain", () => res.emit("drain"));
    res.on("close", () => gzip.destroy());
  };

  res.write = (chunk, encoding, callback) => {
    decide(chunk, false);
    return gzip ? gzip.write(chunk, encoding, callback) : write(chunk, encoding, callback);
  };
  res.end = (chunk, encoding, callback) => {
    if (typeof chunk === "function") [chunk, callback] = [undefined, chunk];
    if (typeof encoding === "function") [encoding, callback] = [undefined, encoding];
    decide(chunk, true);
    if (!gzip) return end(chunk, encoding, callback);
    if (callback) res.once("finish", callback);
    if (chunk !== undefined && chunk !== null) gzip.end(chunk, encoding);
    else gzip.end();
    return res;
  };
}

const listener = createListener();
const server = createServer((req, res) => {
  if (isForApi(req.url ?? "")) return passOn(req, res);
  compressed(req, res);
  return listener(req, res);
});
const port = Number(process.env.PORT || 3000);
const host = process.env.HOST;
server.listen(port, host, () =>
  console.log(
    `Listening on http://${host || "localhost"}:${port}` +
      (passesApiOn ? ` (/api is passed on to ${apiUrl})` : " (/api is not passed on)"),
  ),
);
