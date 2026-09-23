import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const [, , specPath, outputPath, dependencyRoot] = process.argv;

if (!specPath || !outputPath || !dependencyRoot) {
  throw new Error(
    "Usage: node renderer.mjs <spec.json> <output.pptx> <dependency-root>",
  );
}

const requireFromRuntime = createRequire(
  path.join(path.resolve(dependencyRoot), "package.json"),
);
const pptxgen = requireFromRuntime("pptxgenjs");
const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));

const pptx = new pptxgen();
pptx.layout = spec.layout ?? "LAYOUT_WIDE";
pptx.author = spec.author ?? "Code Puppy Presentation Maker";
pptx.company = spec.company ?? "";
pptx.subject = spec.subject ?? spec.title ?? "";
pptx.title = spec.title ?? "";
pptx.lang = spec.language ?? "en-US";
pptx.theme = {
  headFontFace: spec.theme?.headingFont ?? spec.theme?.font ?? "Aptos Display",
  bodyFontFace: spec.theme?.bodyFont ?? spec.theme?.font ?? "Aptos",
  lang: spec.language ?? "en-US",
};

const defaultBackground = spec.theme?.background ?? "FFFFFF";
const defaultTextColor = spec.theme?.text ?? "202124";
const defaultTitleColor = spec.theme?.primary ?? defaultTextColor;

function cleanOptions(element, omitted) {
  return Object.fromEntries(
    Object.entries(element).filter(
      ([key, value]) => !omitted.has(key) && value !== null && value !== undefined,
    ),
  );
}

function addElement(slide, element) {
  switch (element.type) {
    case "text": {
      const options = cleanOptions(element, new Set(["type", "text"]));
      options.fontFace ??= spec.theme?.bodyFont ?? spec.theme?.font ?? "Aptos";
      options.color ??= defaultTextColor;
      slide.addText(element.text, options);
      break;
    }
    case "image": {
      slide.addImage(cleanOptions(element, new Set(["type"])));
      break;
    }
    case "table": {
      slide.addTable(element.rows, element.options ?? {});
      break;
    }
    case "chart": {
      const chartType = pptx.ChartType[element.chartType] ?? element.chartType;
      slide.addChart(chartType, element.data, element.options ?? {});
      break;
    }
    case "shape": {
      const shapeType = pptx.ShapeType[element.shape] ?? element.shape;
      slide.addShape(shapeType, element.options ?? {});
      break;
    }
    case "line": {
      slide.addShape(pptx.ShapeType.line, element.options ?? {});
      break;
    }
    default:
      throw new Error(`Unsupported element type: ${element.type}`);
  }
}

for (const slideSpec of spec.slides) {
  const slide = pptx.addSlide();
  const background = slideSpec.background ?? defaultBackground;
  slide.background =
    typeof background === "string" ? { color: background } : background;

  if (slideSpec.title) {
    slide.addText(slideSpec.title, {
      x: 0.7,
      y: 0.35,
      w: 11.9,
      h: 0.65,
      margin: 0,
      fontFace: spec.theme?.headingFont ?? spec.theme?.font ?? "Aptos Display",
      fontSize: 30,
      bold: true,
      color: defaultTitleColor,
      breakLine: false,
      fit: "shrink",
      ...(slideSpec.titleOptions ?? {}),
    });
  }

  for (const element of slideSpec.elements ?? []) {
    addElement(slide, element);
  }

  if (slideSpec.notes?.length) {
    slide.addNotes(slideSpec.notes);
  }
}

fs.mkdirSync(path.dirname(path.resolve(outputPath)), { recursive: true });
await pptx.writeFile({ fileName: path.resolve(outputPath) });

