import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const [, , inputPath, outputDirectory, dependencyRoot] = process.argv;

if (!inputPath || !outputDirectory || !dependencyRoot) {
  throw new Error(
    "Usage: node render_pdf.mjs <input.pdf> <output-directory> <dependency-root>",
  );
}

const requireFromRuntime = createRequire(
  path.join(path.resolve(dependencyRoot), "package.json"),
);
const pdfjs = requireFromRuntime("pdfjs-dist/legacy/build/pdf.js");
const { createCanvas } = requireFromRuntime("@napi-rs/canvas");
const pdfBytes = new Uint8Array(fs.readFileSync(inputPath));
const document = await pdfjs.getDocument({
  data: pdfBytes,
  disableWorker: true,
  useSystemFonts: true,
}).promise;

fs.mkdirSync(outputDirectory, { recursive: true });

for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
  const page = await document.getPage(pageNumber);
  const baseViewport = page.getViewport({ scale: 1 });
  const scale = 1920 / baseViewport.width;
  const viewport = page.getViewport({ scale });
  const canvas = createCanvas(
    Math.ceil(viewport.width),
    Math.ceil(viewport.height),
  );
  const context = canvas.getContext("2d");
  context.fillStyle = "white";
  context.fillRect(0, 0, canvas.width, canvas.height);
  await page.render({ canvasContext: context, viewport }).promise;

  const fileName = `slide-${String(pageNumber).padStart(3, "0")}.png`;
  fs.writeFileSync(path.join(outputDirectory, fileName), canvas.toBuffer("image/png"));
  page.cleanup();
}

const pageCount = document.numPages;
await document.destroy();
process.stdout.write(String(pageCount));

