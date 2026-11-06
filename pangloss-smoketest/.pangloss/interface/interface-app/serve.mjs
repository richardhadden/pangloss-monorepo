// The production server: the one the Solid plugin builds (dist/server/node.js), with its answers gzipped when the
// browser accepts it. Rendered pages are mostly repeated markup (a calendar month runs to megabytes) and shrink by
// 90% or more. `pangloss interface serve` runs this file (env: PORT, HOST).
import { createServer } from "node:http";
import zlib from "node:zlib";
import { createListener } from "./dist/server/node.js";

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
  compressed(req, res);
  return listener(req, res);
});
const port = Number(process.env.PORT || 3000);
const host = process.env.HOST;
server.listen(port, host, () => console.log(`Listening on http://${host || "localhost"}:${port}`));
