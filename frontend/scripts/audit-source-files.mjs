import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

// Audit source reachability, not export usage or individual CSS selectors.
// Test fixtures, test setup and ambient declarations are legitimate entry points.
const root = fileURLToPath(new URL("../src/", import.meta.url));
const walk = directory => readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
  const name = path.join(directory, entry.name);
  return entry.isDirectory() ? walk(name) : [name];
});
const files = walk(root).filter(name => /\.(?:tsx?|css|json|svg)$/.test(name));
const fileSet = new Set(files);
const edges = new Map();
for (const file of files) {
  const source = readFileSync(file, "utf8");
  const imports = /\.tsx?$/.test(file)
    ? ts.preProcessFile(source, true, true).importedFiles.map(item => item.fileName)
    : [...source.matchAll(/@import\s+["']([^"']+)["']|url\(\s*["']?([^"')]+)["']?\s*\)/g)].map(match => match[1] ?? match[2]);
  const dependencies = imports.filter(name => name.startsWith(".")).map(name => {
    const base = path.resolve(path.dirname(file), name.split("?")[0]);
    return [base, ...[".ts", ".tsx", ".css", ".json", "/index.ts", "/index.tsx"].map(ext => path.normalize(base + ext))]
      .find(candidate => fileSet.has(candidate));
  }).filter(Boolean);
  edges.set(file, dependencies);
}
const seen = new Set();
function visit(file) {
  if (seen.has(file)) return;
  seen.add(file);
  for (const dependency of edges.get(file) ?? []) visit(dependency);
}
visit(path.join(root, "main.tsx"));
const appCount = seen.size;
for (const file of files.filter(name => /\.(?:test\.tsx?|d\.ts)$/.test(name))) visit(file);
visit(path.join(root, "test", "setup.ts"));
const unused = files.filter(file => !seen.has(file));
console.log(`Application graph: ${appCount} files. Application + tests: ${seen.size} files.`);
for (const file of unused) console.error(`Unreferenced: ${path.relative(root, file)}`);
console.log(unused.length ? `${unused.length} unreferenced source files.` : "No unreferenced source files.");
process.exitCode = unused.length ? 1 : 0;
