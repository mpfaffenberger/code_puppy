# 🎨 Code Puppy TUI - Sexy Theme

A modern, beautiful dark theme for the Code Puppy Terminal User Interface.

## Color Palette

### Core Colors
- **Background**: `#0a0e1a` - Deep navy, almost black
- **Surface**: `#0f172a` - Dark slate for containers
- **Primary**: `#1e3a8a` - Rich blue for headers and accents
- **Accent**: `#3b82f6` - Bright blue for borders and highlights

### Message Types

#### User Messages
- **Background**: `#1e3a5f` - Deep blue
- **Text**: `#e0f2fe` - Light cyan
- **Border**: `tall #3b82f6` - Tall blue border
- **Style**: Bold text

#### Agent Response
- **Background**: `#0f172a` - Dark slate
- **Text**: `#e0e7ff` - Light indigo
- **Border**: `double #818cf8` - Double purple-blue border
- **Features**: Markdown rendering with syntax highlighting

#### System Messages
- **Background**: `#1a1a2e` - Dark purple-blue
- **Text**: `#94a3b8` - Muted gray-blue
- **Border**: `dashed #334155` - Dashed gray border
- **Style**: Italic

#### Error Messages
- **Background**: `#4c0519` - Deep red
- **Text**: `#fecdd3` - Light pink
- **Border**: `heavy #f43f5e` - Heavy red border

#### Success Messages
- **Background**: `#065f46` - Deep green
- **Text**: `#d1fae5` - Light mint
- **Border**: `heavy #34d399` - Heavy green border

#### Warning Messages
- **Background**: `#78350f` - Deep orange-brown
- **Text**: `#fef3c7` - Light yellow
- **Border**: `wide #fbbf24` - Wide yellow border

#### Tool Output
- **Background**: `#2e1065` - Deep purple
- **Text**: `#ddd6fe` - Light lavender
- **Border**: `round #7c3aed` - Round purple border

#### Command Output
- **Background**: `#431407` - Deep orange
- **Text**: `#fed7aa` - Light peach
- **Border**: `solid #f97316` - Solid orange border

## Components

### Status Bar
- **Background**: `#1e3a8a` - Rich blue
- **Text**: `#dbeafe` - Light blue
- **Border Bottom**: `wide #3b82f6` - Wide blue border
- **Features**: Emoji indicators for status (🤔 Thinking, ⚡ Processing, ✅ Ready, etc.)

### Input Area
- **Background**: `#0f172a` - Dark slate
- **Border Top**: `wide #1e3a8a` - Wide blue border
- **Input Field**:
  - Background: `#1e293b` → `#1e3a5f` on focus
  - Border: `heavy #3b82f6` → `heavy #60a5fa` on focus
  - Text: `#e0f2fe`
- **Submit Button**:
  - Background: `#1e3a8a` → `#2563eb` on hover
  - Border: `round #3b82f6` → `double #60a5fa` on focus
  - Text: `#93c5fd` → `#dbeafe` on hover

### Sidebar
- **Background**: `#1e293b` - Dark slate
- **Border Right**: `wide #3b82f6` - Wide blue border
- **History List**:
  - Background: `#1e293b`
  - Scrollbar: `#60a5fa` on `#334155`
  - Text: `#e0f2fe`

### Chat View
- **Background**: `#0a0e1a` - Deep navy
- **Scrollbar**:
  - Background: `#1e293b`
  - Color: `#60a5fa`
  - Hover: `#93c5fd`
  - Active: `#3b82f6`
- **Padding**: 1 row, 2 columns for comfortable spacing

## Border Styles

The theme uses various Textual border styles for visual variety:
- `tall` - User messages (vertical emphasis)
- `round` - Agent messages, tool output (friendly, rounded)
- `dashed` - System messages (subtle, informational)
- `heavy` - Errors, success messages (strong emphasis)
- `double` - Agent responses (important content)
- `wide` - Warnings, borders (attention-grabbing)
- `solid` - Command output (standard emphasis)

## Customization

To customize the theme, edit the `DEFAULT_CSS` strings in:
- `/code_puppy/tui/app.py` - Main app layout
- `/code_puppy/tui/components/chat_view.py` - Message styling
- `/code_puppy/tui/components/input_area.py` - Input area styling
- `/code_puppy/tui/components/status_bar.py` - Status bar styling
- `/code_puppy/tui/components/sidebar.py` - Sidebar styling

## Design Philosophy

This theme follows a **dark, modern, cyberpunk-inspired** aesthetic:
- **High contrast** for readability
- **Vibrant accent colors** for visual interest
- **Varied borders** for component distinction
- **Responsive design** adapts to terminal size
- **Semantic colors** - each message type has a distinct, meaningful color
- **Professional polish** with hover states and focus indicators

## Tips for Best Experience

1. **Use a terminal with true color support** (24-bit color)
2. **Recommended fonts**: Fira Code, JetBrains Mono, Cascadia Code
3. **Terminal size**: Minimum 80x24, recommended 120x30+
4. **Enable font ligatures** for a better coding experience

---

**Enjoy your sexy new TUI!** 🐶✨
