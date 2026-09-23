function run(argv) {
  if (argv.length !== 2) {
    throw new Error("Expected input PPTX and output path");
  }

  const inputPath = argv[0];
  const outputPath = argv[1];
  const powerPoint = Application("/Applications/Microsoft PowerPoint.app");
  powerPoint.includeStandardAdditions = true;
  powerPoint.activate();
  powerPoint.open(Path(inputPath));

  let presentation = null;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const openPresentations = powerPoint.presentations();
    for (const candidate of openPresentations) {
      try {
        if (candidate.fullName() === inputPath) {
          presentation = candidate;
          break;
        }
      } catch (_error) {
        // The collection can briefly contain an unresolved object while the
        // application finishes opening the file.
      }
    }
    if (presentation !== null) {
      break;
    }
    delay(0.25);
  }

  if (presentation === null) {
    throw new Error("PowerPoint did not finish opening the presentation");
  }

  try {
    // 0x00cc000e is PowerPoint's EPPSaveAsFileType value for PDF. The JXA
    // bridge silently ignores the human-readable enum name on current Office.
    presentation.save({ in: Path(outputPath), as: 0x00cc000e });
  } finally {
    presentation.close({ saving: "no" });
  }

  return outputPath;
}
