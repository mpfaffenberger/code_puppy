# pet -- a desktop dog for your terminal

Adopt a tiny ASCII pup that lounges in the **bottom-right of your prompt**,
animates (blinks + wags), and barks fun quips while you think. It reflects the
model you've set and gets out of the way the moment the agent starts working.

> **Zero LLM tokens.** Quips are a static list; everything is local string
> rendering. Your bill is identical whether the pup naps or does zoomies.

## Usage

```
/pet on            Open the adoption picker, then summon your dog
/pet off           Send the dog back to the yard
/pet pick          Re-open the picker to swap breeds
/pet <breed>       Adopt a breed directly (e.g. /pet shiba)
/pet rename <name> Rename your pup (max 20 chars)
/pet quip          Reroll the quip
/pet list | grid   Show the rarity-colored list of all 19 breeds
/pet               Status
```

## 19 breeds, 5 rarities

corgi, shiba, pug, husky, poodle, dachshund, beagle, labrador, chihuahua,
dalmatian, bulldog, greatdane, pomeranian, terrier, boxer, collie, samoyed,
doberman, mutt -- each tinted by rarity (common -> legendary, gray -> gold).

## How it works (no core edits)

Like the `prompt_newline` plugin, this hooks core cleanly:

* **`startup`** -- subclasses the `PromptSession` used by the main input prompt
  so an adopted pet rides along as an animated `bottom_toolbar` (right-aligned,
  so it sits bottom-right). prompt_toolkit renders/refreshes it itself, which is
  why it never fights the REPL or smears escape codes.
* **`custom_command` / `custom_command_help`** -- the `/pet` command and its
  help entry.

State (enabled / species / name) persists in `puppy.cfg` via the generic
config API. Themed to Code Puppy's prompt palette (bright cyan / blue / green).
