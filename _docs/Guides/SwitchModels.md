# How to Switch Models

## What You'll Learn
By the end of this guide, you'll be able to switch between AI models on the fly, browse the full model catalog, and fine-tune model settings like temperature and reasoning effort.

## Prerequisites
- Code Puppy installed and running
- At least one API key configured (see [Configuration](../Getting-Started/Configuration))

## Quick Version

```
/model <model-name>
```

Or just type `/model` to open the interactive model picker.

## Detailed Steps

### 1. See Your Current Model

Type `/config` to see your current configuration, including the active model:

```
/config
```

The output will show something like:

```
model:               claude-4-5-sonnet
agent:               code_puppy
temperature:         (model default)
```

### 2. Switch Models with the Interactive Picker

The easiest way to switch models is with the interactive picker. Just type:

```
/model
```

This opens a visual selector showing all available models. The currently active model is marked with a ✓. Use the **arrow keys** to navigate and **Enter** to select.

> [!TIP]
> You can also use `/m` as a shorthand for `/model`.

### 3. Switch Models Directly by Name

If you already know the model name, switch directly:

```
/model claude-4-5-opus
```

You'll see a confirmation:

```
✓ Active model set and loaded: claude-4-5-opus
```

> [!TIP]
> You can also type `/m claude-4-5-opus` for the same result.

### 4. Switch Models Inline (While Typing a Prompt)

You can switch models as part of a prompt. Prefix your message with `/model <name>`:

```
/model gpt-5.1 Explain the architecture of this project
```

This switches to the specified model and immediately sends your prompt to it — all in one step.

### 5. Browse and Add New Models from the Catalog

If you want to add models from other providers, use the model catalog browser:

```
/add_model
```

This opens a split-panel interface where you can:
- Browse models by provider (OpenAI, Anthropic, Google, Mistral, and many more)
- See model details like context length and capabilities
- Add a model to your configuration with one keypress

Use **arrow keys** to navigate, **Enter** to select a provider or add a model, and **Esc** to go back.

> [!NOTE]
> When you add a model, you'll be prompted for an API key if one isn't already configured for that provider.

## Configuring Model Settings

Each model supports different settings that you can customize.

### Open the Model Settings Menu

```
/model_settings
```

Or use the shorthand:

```
/ms
```

This opens an interactive two-panel TUI:
- **Left panel**: Lists all available models (paginated). Models with custom settings show a ⚙ icon.
- **Right panel**: Shows details and configurable settings for the highlighted model.

### Navigate the Settings Menu

| Key | Action |
|-----|--------|
| ↑/↓ | Navigate models or settings |
| PgUp/PgDn | Change page (when many models are listed) |
| Enter | Select a model / edit a setting |
| ←/→ | Adjust a value while editing |
| d | Reset a setting to its default |
| Esc | Go back / exit |

### Available Settings

Different models support different settings:

| Setting | Description | Models |
|---------|-------------|--------|
| **Temperature** | Controls randomness (0.0–1.0). Lower = more deterministic. | Most models |
| **Top-P** | Controls token diversity (0.0–1.0). | Most models |
| **Seed** | Fixed seed for reproducible outputs. | Select models |
| **Reasoning Effort** | How much effort the model spends reasoning (minimal → high). | GPT-5 models |
| **Verbosity** | Response length (low → max). | GPT-5 models |
| **Extended Thinking** | Enables the model's thinking/reasoning mode. | Claude models |
| **Thinking Budget** | Max tokens for extended thinking. | Claude models |
| **Effort** | Overall effort level (low → max). | Claude Opus models |

### View Settings Without the TUI

To quickly check a model's settings from the command line:

```
/model_settings --show
```

To check settings for a specific model:

```
/model_settings --show claude-4-5-sonnet
```

## Pinning Models to Agents

You can pin a specific model to an agent so that agent always uses it, regardless of the global model selection.

```
/pin_model <agent-name> <model-name>
```

**Example:**

```
/pin_model code_puppy claude-4-5-opus
```

Result:

```
✓ Model 'claude-4-5-opus' pinned to agent 'code_puppy'
```

To unpin (reset to the global default):

```
/unpin_model <agent-name>
```

> [!WARNING]
> When an agent has a pinned model, switching the global model with `/model` will **not** affect that agent. You'll see a warning message reminding you of the pinned model.

## Example

**Scenario:** You want to use a fast model for simple tasks and a powerful model for complex reasoning.

```
# Start with a fast model for quick edits
/model claude-4-5-haiku
Fix the typo on line 12 of README.md

# Switch to a powerful model for complex work
/model claude-4-5-opus
Refactor the authentication module to use JWT tokens

# Check what model you're on
/config
```

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "Model not found" error | Typo in model name | Run `/model` with no arguments to see the interactive picker |
| Model switch doesn't take effect | Agent has a pinned model | Run `/unpin_model <agent>` to unpin, then switch again |
| Missing API key error after switching | The new model needs a different API key | Set the required environment variable (see [Configuration](../Getting-Started/Configuration)) |
| Settings menu shows no configurable settings | That model doesn't expose tunable parameters | Try a different model — not all models support custom settings |

## Related Guides
- [How to Add Models from the Catalog](AddModels)
- [How to Set Up Round Robin Models](RoundRobinModels)
- [How to Switch and Use Agents](UseAgents)
- [Reference: Configuration Options](../Reference/ConfigReference)
