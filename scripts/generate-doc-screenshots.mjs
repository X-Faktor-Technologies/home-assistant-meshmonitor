#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { access, mkdtemp, readFile, realpath, rename, rm, stat } from "node:fs/promises";
import { extname, join, normalize, resolve, sep } from "node:path";

const root = resolve(import.meta.dirname, "..");
const output = join(root, "docs", "images");
const frontendRoot = join(root, "custom_components", "meshmonitor", "frontend");
const harnessRoot = join(root, "scripts", "docs-screenshots");
const host = "127.0.0.1";
const browsers = [process.env.CHROMIUM, "chromium", "chromium-browser", "google-chrome", "brave"].filter(Boolean);

const mime = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
};

const exactRoutes = new Map([
  ["/scripts/docs-screenshots/harness.html", join(harnessRoot, "harness.html")],
  ["/scripts/docs-screenshots/harness.js", join(harnessRoot, "harness.js")],
  ["/scripts/docs-screenshots/fixture.js", join(harnessRoot, "fixture.js")],
]);

const containedRealpath = async (path, directory) => {
  const canonicalRoot = await realpath(directory);
  const canonical = await realpath(path);
  if (canonical !== canonicalRoot && !canonical.startsWith(`${canonicalRoot}${sep}`)) {
    throw new Error("Route leaves its approved asset directory");
  }
  return canonical;
};

const resolveRequest = async (pathname) => {
  const exact = exactRoutes.get(pathname);
  if (exact) return containedRealpath(exact, harnessRoot);
  if (!pathname.startsWith("/meshmonitor_panel/")) throw new Error("Route not allowed");
  const relative = normalize(pathname.slice("/meshmonitor_panel/".length));
  const requested = resolve(frontendRoot, relative);
  const canonical = await containedRealpath(requested, frontendRoot);
  if (!new Set([".css", ".js", ".png"]).has(extname(canonical))) {
    throw new Error("Asset type not allowed");
  }
  return canonical;
};

const browser = await (async () => {
  for (const candidate of browsers) {
    const paths = (process.env.PATH || "").split(":").map((directory) => join(directory, candidate));
    if (candidate.includes("/")) paths.unshift(candidate);
    for (const path of paths) {
      try { await access(path); return path; } catch { /* Try the next candidate. */ }
    }
  }
  throw new Error("No supported Chromium browser found; set CHROMIUM to its executable path.");
})();

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, `http://${host}`);
    const requested = await resolveRequest(url.pathname);
    const info = await stat(requested);
    if (!info.isFile()) throw new Error("Not a file");
    response.writeHead(200, {
      "content-security-policy": [
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "connect-src 'none'",
        "font-src 'none'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
      ].join("; "),
      "content-type": mime[extname(requested)] || "application/octet-stream",
      "x-content-type-options": "nosniff",
    });
    response.end(await readFile(requested));
  } catch {
    response.writeHead(404).end("Not found");
  }
});

await new Promise((resolveReady) => server.listen(0, host, resolveReady));
const { port } = server.address();

const browserArgs = (tab, width) => [
    "--headless=new",
    "--disable-gpu",
    "--disable-background-networking",
    "--hide-scrollbars",
    "--no-first-run",
    "--no-default-browser-check",
    "--run-all-compositor-stages-before-draw",
    "--virtual-time-budget=20000",
    "--lang=en-US",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    `--window-size=${width},900`,
    `http://${host}:${port}/scripts/docs-screenshots/harness.html?tab=${tab}`,
  ];
const browserEnvironment = { ...process.env, LANG: "en_US.UTF-8", TZ: "UTC" };

const capture = (tab, filename, directory, width = 1440) => new Promise((resolveCapture, rejectCapture) => {
  const destination = join(directory, filename);
  const child = spawn(
    browser,
    ["--dump-dom", `--screenshot=${destination}`, ...browserArgs(tab, width)],
    { env: browserEnvironment, stdio: ["ignore", "pipe", "inherit"] },
  );
  let html = "";
  let finished = false;
  const fail = (error) => {
    if (finished) return;
    finished = true;
    clearTimeout(timeout);
    rejectCapture(error);
  };
  const timeout = setTimeout(() => {
    child.kill("SIGKILL");
    fail(new Error(`Synthetic ${tab} capture timed out`));
  }, 30000);
  child.stdout.on("data", (chunk) => { html += chunk; });
  child.on("error", fail);
  child.on("exit", (code) => {
    if (finished) return;
    finished = true;
    clearTimeout(timeout);
    if (code !== 0) rejectCapture(new Error(`${browser} capture exited with status ${code}`));
    else if (!html.includes('data-screenshot-ready="true"')) {
      rejectCapture(new Error(`Synthetic ${tab} view did not reach its ready state`));
    } else if (html.includes("data-screenshot-error=")) {
      rejectCapture(new Error(`Synthetic ${tab} view reported an error`));
    } else resolveCapture();
  });
});

const captures = [
  ["overview", "panel-overview-v0.17.png", 1440],
  ["messages", "panel-conversations-v0.17.png", 1440],
  ["nodes", "panel-nodes-v0.17.png", 1440],
  ["map", "panel-map-v0.17.png", 1600],
];
const staging = await mkdtemp(join(output, ".screenshot-stage-"));

try {
  for (const path of ["/.env", "/.git/config", "/scripts/docs-screenshots/../README.md"]) {
    const response = await fetch(`http://${host}:${port}${path}`);
    if (response.status !== 404) throw new Error(`Private route was served: ${path}`);
  }
  for (const [tab, filename, width] of captures) {
    await capture(tab, filename, staging, width);
  }
  for (const [, filename] of captures) {
    await rename(join(staging, filename), join(output, filename));
  }
} finally {
  await new Promise((resolveClose) => server.close(resolveClose));
  await rm(staging, { recursive: true, force: true });
}
