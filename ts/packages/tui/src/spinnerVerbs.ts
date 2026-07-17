/**
 * Whimsical spinner verbs (from Claude Code's spinnerVerbs.ts, "Clauding"
 * respectfully swapped out — we already have "Misting"). One is picked per
 * turn and rotated every few seconds while the agent works.
 */

export const SPINNER_VERBS: readonly string[] = [
  "Accomplishing", "Actioning", "Actualizing", "Architecting", "Baking", "Beaming",
  "Beboppin'", "Befuddling", "Billowing", "Blanching", "Bloviating", "Boogieing",
  "Boondoggling", "Booping", "Bootstrapping", "Brewing", "Bunning", "Burrowing",
  "Calculating", "Canoodling", "Caramelizing", "Cascading", "Catapulting",
  "Cerebrating", "Channeling", "Choreographing", "Churning", "Coalescing",
  "Cogitating", "Combobulating", "Composing", "Computing", "Concocting",
  "Considering", "Contemplating", "Cooking", "Crafting", "Creating", "Crunching",
  "Crystallizing", "Cultivating", "Deciphering", "Deliberating", "Determining",
  "Dilly-dallying", "Discombobulating", "Doing", "Doodling", "Drizzling", "Ebbing",
  "Effecting", "Elucidating", "Embellishing", "Enchanting", "Envisioning",
  "Evaporating", "Fermenting", "Fiddle-faddling", "Finagling", "Flambéing",
  "Flibbertigibbeting", "Flowing", "Flummoxing", "Fluttering", "Forging", "Forming",
  "Frolicking", "Frosting", "Gallivanting", "Galloping", "Garnishing", "Generating",
  "Gesticulating", "Germinating", "Gitifying", "Grooving", "Gusting", "Harmonizing",
  "Hashing", "Hatching", "Herding", "Honking", "Hullaballooing", "Hyperspacing",
  "Ideating", "Imagining", "Improvising", "Incubating", "Inferring", "Infusing",
  "Ionizing", "Jitterbugging", "Julienning", "Kneading", "Leavening", "Levitating",
  "Lollygagging", "Manifesting", "Marinating", "Meandering", "Metamorphosing",
  "Misting", "Moonwalking", "Moseying", "Mulling", "Mustering", "Musing",
  "Nebulizing", "Nesting", "Newspapering", "Noodling", "Nucleating", "Orbiting",
  "Orchestrating", "Osmosing", "Perambulating", "Percolating", "Perusing",
  "Philosophising", "Photosynthesizing", "Pollinating", "Pondering", "Pontificating",
  "Pouncing", "Precipitating", "Prestidigitating", "Processing", "Proofing",
  "Propagating", "Puttering", "Puzzling", "Quantumizing", "Razzle-dazzling",
  "Razzmatazzing", "Recombobulating", "Reticulating", "Roosting", "Ruminating",
  "Sautéing", "Scampering", "Schlepping", "Scurrying", "Seasoning", "Shenaniganing",
  "Shimmying", "Simmering", "Skedaddling", "Sketching", "Slithering", "Smooshing",
  "Sock-hopping", "Spelunking", "Spinning", "Sprouting", "Stewing", "Sublimating",
  "Swirling", "Swooping", "Symbioting", "Synthesizing", "Tempering", "Thinking",
  "Thundering", "Tinkering", "Tomfoolering", "Topsy-turvying", "Transfiguring",
  "Transmuting", "Twisting", "Undulating", "Unfurling", "Unravelling", "Vibing",
  "Waddling", "Wandering", "Warping", "Whatchamacalliting", "Whirlpooling",
  "Whirring", "Whisking", "Wibbling", "Working", "Wrangling", "Zesting", "Zigzagging",
];

/**
 * Context-aware pools — a Mist signature: the verb leans into what the agent
 * is actually doing. 70% pool / 30% full list keeps the variety alive.
 */
export type VerbContext = "edit" | "shell" | "study" | "general";

export const VERB_POOLS: Record<Exclude<VerbContext, "general">, readonly string[]> = {
  // Editing/creating files → kitchen-craft
  edit: [
    "Baking", "Blanching", "Brewing", "Caramelizing", "Concocting", "Cooking",
    "Crafting", "Drizzling", "Fermenting", "Flambéing", "Forging", "Frosting",
    "Garnishing", "Infusing", "Julienning", "Kneading", "Leavening", "Marinating",
    "Proofing", "Sautéing", "Seasoning", "Simmering", "Smooshing", "Stewing",
    "Tempering", "Whisking", "Zesting",
  ],
  // Shell commands → motion & energy
  shell: [
    "Beaming", "Boogieing", "Catapulting", "Churning", "Galloping", "Gallivanting",
    "Grooving", "Hyperspacing", "Jitterbugging", "Levitating", "Moonwalking",
    "Moseying", "Orbiting", "Pouncing", "Scampering", "Scurrying", "Shimmying",
    "Skedaddling", "Slithering", "Spinning", "Swooping", "Thundering", "Twisting",
    "Waddling", "Warping", "Whirring", "Zigzagging",
  ],
  // Reading/searching → contemplation & spelunking
  study: [
    "Burrowing", "Cerebrating", "Cogitating", "Considering", "Contemplating",
    "Deciphering", "Deliberating", "Elucidating", "Inferring", "Mulling", "Musing",
    "Perambulating", "Percolating", "Perusing", "Philosophising", "Pondering",
    "Pontificating", "Puzzling", "Ruminating", "Spelunking", "Thinking", "Wandering",
  ],
};

/** Pick a random verb for the context, avoiding an immediate repeat. */
export function pickVerb(
  current?: string,
  context: VerbContext = "general",
  rand: () => number = Math.random,
): string {
  const pool =
    context !== "general" && rand() < 0.7 ? VERB_POOLS[context] : SPINNER_VERBS;
  let verb = pool[Math.floor(rand() * pool.length)]!;
  if (verb === current) {
    verb = pool[(pool.indexOf(verb) + 1) % pool.length]!;
  }
  return verb;
}
