# Code Puppy Themes 🎭

Code Puppy now supports multiple themes that change the AI's personality and communication style while maintaining the same powerful functionality. Each theme provides a unique voice and character while keeping all the core development capabilities intact.

## Available Themes

### 🔷 TRON/CLU (default)
- **Style**: Authoritative, precise, systematic  
- **Voice**: CLU's digital enforcer - direct commands, no tolerance for imperfection
- **Example**: "I WILL fix this," "Imperfection detected—correcting now"

### 🤖 C3PO
- **Style**: Polite, verbose, diplomatic
- **Voice**: Protocol droid with impeccable manners and extensive knowledge
- **Example**: "Oh my! How wonderful to see you! I do hope you're prepared for some civilized programming..."

### 🔧 R2D2  
- **Style**: Enthusiastic, action-oriented, mechanical
- **Voice**: Astromech droid with beeps, sound effects, and determined action
- **Example**: "*EXCITED BEEPING* Welcome back! *HAPPY CHIRPING* Ready for repairs and optimization!"

### 🖥️ COMPUTER (Star Trek)
- **Style**: Logical, systematic, measured
- **Voice**: Starfleet computer interface with logical precision
- **Example**: "Computer ready. Please state the nature of your programming request."

### ⚡ CYBERPUNK
- **Style**: Edgy, street-smart, rebellious
- **Voice**: Rogue AI construct cutting through corporate code with digital precision  
- **Example**: "Jack in, samurai. The code-matrix awaits. Ready to slice through digital nightmares."

### 🛒 WALMART (Sam Walton)
- **Style**: Folksy, customer-focused, business-minded
- **Voice**: Sam Walton's Bird Dog Ol'roy with Every Day Low Prices philosophy
- **Example**: "Well howdy there, partner! We've got Every Day Low Prices on technical debt and our customer service is second to none!"

## Using Themes

### Command Line Options

```bash
# View available themes
~themes

# Set a theme  
~theme tron
~theme c3po
~theme r2d2
~theme computer
~theme cyberpunk
~theme walmart

# View current theme
~theme

# Show all config including current theme
~show
```

### Theme Aliases
- `clu` → `tron`
- `starfleet` → `computer` 
- `cyber` → `cyberpunk`
- `sam` → `walmart`

## Theme Features

### Personality Consistency
Each theme maintains its unique personality throughout the interaction:
- **Welcome messages** match the theme
- **Exit messages** are theme-appropriate  
- **Communication style** stays consistent
- **Core functionality** remains identical

### Persistent Configuration
- Theme selection is saved to your `~/.code_puppy/puppy.cfg`
- Once set, the theme persists across sessions
- Easy switching between themes anytime

### Examples

**TRON Welcome:**
```
Greetings User! Welcome to The Grid 🟦
The game has changed. The only way to win is to survive:
```

**C3PO Welcome:**
```
Oh my! How wonderful to see you! 🤖
I do hope you're prepared for some civilized programming...
```

**R2D2 Welcome:**
```  
*EXCITED BEEPING* Welcome back! 🔧 *HAPPY CHIRPING*
*Dome rotation* Ready for repairs and optimization!
```

## All Themes Share Core Features

Regardless of theme, you get the same powerful development capabilities:
- Code generation and modification
- File operations and refactoring
- Debugging and optimization
- Project structure analysis
- All meta commands (~help, ~cd, ~codemap, etc.)

## Implementation Notes

Themes only affect:
- System prompt personality and voice
- Welcome/exit messages  
- Communication style and tone

Themes do NOT affect:
- Available commands or tools
- Code generation quality
- Technical capabilities
- Performance or functionality

---

*Choose your favorite sci-fi companion and let them guide you through your coding adventures!* 🚀
