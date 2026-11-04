// Serves Monaco from this app's own origin (public/monaco/vs) instead of a CDN.
import { cpSync, existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const pkgDir = join(process.cwd(), "node_modules", "monaco-editor");
const version = JSON.parse(readFileSync(join(pkgDir, "package.json"), "utf8")).version;
const target = join(process.cwd(), "public", "monaco");
const stamp = join(target, ".version");
if (existsSync(stamp) && readFileSync(stamp, "utf8") === version) process.exit(0);
rmSync(target, { recursive: true, force: true });
cpSync(join(pkgDir, "min", "vs"), join(target, "vs"), { recursive: true });
writeFileSync(stamp, version);
console.log(`monaco-editor ${version} copied to public/monaco`);
