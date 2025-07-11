# Code Puppy Textual UI Architecture Design

## Overview

This document outlines the Textual UI architecture design for Code Puppy, based on analysis of existing patterns and Textual's capabilities.

## Main Layout Architecture

### Top-Level Application Structure
```
┌─────────────────────────────────────────────────────────────┐
│ Header Bar (Status, Model, Settings)                       │ 
├─────────────────┬───────────────────────────────────────────┤
│ Sidebar         │ Main Chat Area                           │
│ - History       │ ┌─────────────────────────────────────┐   │
│ - Models        │ │ Conversation Messages               │   │
│ - Files         │ │ (Scrollable)                        │   │
│ - Config        │ │                                     │   │
│                 │ │ User: Hello                         │   │
│                 │ │ Agent: Response...                  │   │
│                 │ │                                     │   │
│                 │ └─────────────────────────────────────┘   │
│                 │ ┌─────────────────────────────────────┐   │
│                 │ │ Input Area                          │   │
│                 │ │ Multi-line with syntax highlighting │   │
│                 │ └─────────────────────────────────────┘   │
├─────────────────┴───────────────────────────────────────────┤
│ Footer Bar (Current Dir, Shortcuts, Connection Status)     │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. CodePuppyApp (Main Application)
- **Base**: `textual.app.App`
- **Responsibilities**: 
  - Overall application state management
  - Integration with existing agent system
  - Key binding coordination
  - Mode switching (TUI vs legacy CLI)

### 2. Header Bar Components
- **StatusBar**: Current model, connection status, puppy name
- **MenuBar**: Settings, help, model switcher
- **ProgressIndicator**: Show agent thinking/processing state

### 3. Main Chat Area Components

#### ChatView (Primary Chat Interface)
- **Base**: `textual.containers.VerticalScroll`
- **Features**:
  - Message history display with Rich formatting
  - Syntax highlighting for code blocks
  - Markdown rendering for agent responses
  - Auto-scroll to latest messages
  - Message grouping by session/task

#### MessageWidget (Individual Message)
- **Base**: `textual.widget.Widget`
- **Types**:
  - `UserMessage`: User input styling
  - `AgentMessage`: Agent response with Rich markdown
  - `SystemMessage`: Meta-command results, status updates
  - `ErrorMessage`: Error display with styling

#### InputArea (Enhanced Text Input)
- **Base**: `textual.widgets.TextArea`
- **Features**:
  - Multi-line input support
  - Syntax highlighting for code
  - Auto-completion integration
  - History navigation (up/down arrows)
  - Meta-command prefix detection

### 4. Sidebar Components

#### HistoryPanel
- **Base**: `textual.containers.VerticalScroll`
- **Features**:
  - Session history browsing
  - Quick jump to previous conversations
  - Search through history
  - Export/save conversations

#### ModelPanel
- **Base**: `textual.widgets.ListView`
- **Features**:
  - Available models display
  - Current model highlighting
  - Model switching interface
  - Model status indicators (available/unavailable)

#### FileExplorer
- **Base**: `textual.widgets.DirectoryTree`
- **Features**:
  - Current directory navigation
  - File preview capability
  - Integration with `@` file completion
  - Code structure visualization integration

#### ConfigPanel
- **Base**: `textual.widgets.ListView`
- **Features**:
  - Configuration key-value display
  - In-place editing for settings
  - YOLO mode toggle
  - MCP server status

### 5. Footer Bar Components
- **DirectoryDisplay**: Current working directory
- **ShortcutHelp**: Context-sensitive keyboard shortcuts
- **ConnectionStatus**: Agent connection and MCP server status

## Integration with Existing Systems

### Agent System Integration
```python
class CodePuppyApp(App):
    def __init__(self):
        super().__init__()
        self.agent = get_code_generation_agent()
        self.session_memory = session_memory()
        
    async def process_user_input(self, message: str):
        # Handle meta-commands
        if message.startswith('~'):
            return await self.handle_meta_command(message)
        
        # Process with agent
        response = await self.agent.run(message, message_history=self.message_history)
        return response
```

### Meta-Command Integration
- Preserve existing `~` command system
- Route meta-commands to appropriate UI components
- Maintain backward compatibility with current commands

### Completion System Migration
```python
class TextualCompleter:
    def __init__(self):
        self.file_completer = FilePathCompleter()
        self.model_completer = ModelNameCompleter()
        self.config_completer = SetCompleter()
    
    async def get_completions(self, text: str, cursor_pos: int):
        # Context-aware completion based on current input
        if '@' in text:
            return await self.file_completer.complete(text, cursor_pos)
        elif text.startswith('~m'):
            return await self.model_completer.complete(text, cursor_pos)
        # ... etc
```

## State Management

### Application State
```python
@dataclass
class AppState:
    current_model: str
    message_history: List[Dict]
    current_directory: Path
    session_memory: SessionMemory
    yolo_mode: bool
    active_panel: str  # 'chat', 'history', 'files', 'config'
```

### Message State
```python
@dataclass
class Message:
    id: str
    type: MessageType  # USER, AGENT, SYSTEM, ERROR
    content: str
    timestamp: datetime
    metadata: Dict[str, Any]  # syntax highlighting, formatting hints
```

## Key Bindings and Navigation

### Global Shortcuts
- **Ctrl+C**: Graceful exit/cancel
- **Ctrl+Q**: Quit application
- **F1**: Help/shortcuts
- **F2**: Model switcher
- **F3**: File explorer
- **F4**: Configuration panel

### Chat Area Shortcuts
- **Tab**: Trigger completion
- **Alt+Enter**: Submit multi-line input
- **Ctrl+L**: Clear chat history
- **Up/Down**: Navigate input history
- **Ctrl+R**: Regenerate last response

### Navigation Shortcuts
- **Ctrl+1-4**: Switch between sidebar panels
- **Ctrl+Tab**: Cycle focus between main areas
- **Esc**: Return focus to input area

## Responsive Design

### Layout Adaptation
- **Wide screens** (>120 cols): Full sidebar + chat
- **Medium screens** (80-120 cols): Collapsible sidebar
- **Narrow screens** (<80 cols): Tab-based navigation

### Component Scaling
- Chat messages: Automatic text wrapping
- Code blocks: Horizontal scrolling if needed
- Tables: Responsive column sizing

## Styling and Theming

### CSS Classes
```css
.chat-area {
    background: $background;
    scrollbar-background: $primary;
}

.user-message {
    background: $primary;
    color: $on-primary;
    margin: 1;
}

.agent-message {
    background: $surface;
    border-left: thick $accent;
    margin: 1;
}

.input-area {
    background: $surface;
    border: round $primary;
}
```

### Dark/Light Mode Support
- Respect terminal/system theme preferences
- Configurable theme switching
- High contrast mode support

## Error Handling and Feedback

### Progressive Enhancement
- Graceful degradation if Textual features unavailable
- Fallback to legacy CLI mode
- Clear error messages with recovery suggestions

### User Feedback
- Loading spinners for agent processing
- Progress bars for long operations
- Toast notifications for quick actions
- Modal dialogs for confirmations

## Implementation Phases

### Phase 1: Basic Structure
1. Main app container with header/footer
2. Basic chat area with message display
3. Simple input area with submission

### Phase 2: Core Features
1. Message history and scrolling
2. Meta-command integration
3. Model switching UI
4. Basic sidebar components

### Phase 3: Advanced Features
1. File explorer integration
2. Completion system migration
3. Configuration panel
4. Full keyboard navigation

### Phase 4: Polish
1. Responsive design
2. Theming and styling
3. Performance optimization
4. Comprehensive error handling

This architecture maintains compatibility with existing Code Puppy features while providing a modern, extensible TUI foundation.