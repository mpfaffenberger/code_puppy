# How to Add Models from the Catalog

## What You'll Learn
By the end of this guide, you'll be able to browse 1500+ AI models from the models.dev catalog, add them to your Code Puppy configuration, and set up the required API credentials — all from an interactive terminal interface.

## Prerequisites
- Code Puppy installed and running
- An API key for the provider whose model you want to add (e.g., OpenAI, Anthropic, Groq, etc.)
- See [Configuration](../Getting-Started/Configuration) for help setting up API keys

## Quick Version

```
/add_model
```

This opens an interactive browser. Use arrow keys to navigate, Enter to select, and Ctrl+C to cancel.

## Detailed Steps

### 1. Open the Model Browser

Type the following command in Code Puppy:

```
/add_model
```

A split-panel interface appears with two sections:
- **Left panel** — A list of providers (OpenAI, Anthropic, Google, Groq, Mistral, etc.)
- **Right panel** — Details about the selected provider or model

### 2. Browse Providers

Use the arrow keys to navigate through the provider list:

| Key | Action |
|-----|--------|
| ↑ / ↓ | Move between providers |
| ← / → | Previous / next page |
| Enter | Select a provider and view its models |
| Ctrl+C | Cancel and exit |

The right panel shows information about the highlighted provider, including:
- Number of available models
- Required environment variables (API keys)
- Documentation links

> [!NOTE]
> Some providers appear dimmed with a ⚠️ icon. These are **unsupported providers** that require special authentication (such as AWS SigV4 or GCP service accounts) and cannot be added through the catalog.

### 3. Browse Models

After selecting a provider, you'll see its available models. Each model displays capability icons:

| Icon | Meaning |
|------|----------|
| 👁 | Vision (can process images) |
| 🔧 | Tool calling (can edit files, run commands) |
| 🧠 | Reasoning (extended thinking capabilities) |

Use the same navigation keys, plus:

| Key | Action |
|-----|--------|
| Enter | Add the selected model |
| Esc or Backspace | Go back to the provider list |

The right panel shows detailed model information:
- **Capabilities** — Vision, tool calling, reasoning, temperature, structured output, attachments
- **Pricing** — Input/output cost per token
- **Limits** — Context window size and max output tokens
- **Modalities** — Supported input/output types

> [!WARNING]
> Models without **tool calling** support (no 🔧 icon) will be very limited for coding tasks. They won't be able to edit files, run shell commands, or use any tools. Code Puppy will warn you before adding such a model.

### 4. Enter API Credentials

After selecting a model, Code Puppy checks whether the required API key is already set. If not, you'll be prompted to enter it:

```
🔑 ProviderName requires the following credentials:

  💡 Get your API key from https://...
  Enter PROVIDER_API_KEY (or press Enter to skip):
```

Type your API key and press Enter. The key is saved to your configuration and immediately available.

> [!TIP]
> If you don't have the API key yet, press Enter to skip. You can set it later with:
> ```
> /set PROVIDER_API_KEY=your-key-here
> ```

### 5. Confirm the Addition

Once credentials are handled, the model is added to your configuration:

```
Added provider-model-name to extra_models.json
Successfully added model configuration
```

You can now switch to the new model with:

```
/model provider-model-name
```

## Adding a Custom Model

If the model you want isn't listed in the catalog (e.g., a newly released, fine-tuned, or preview model), you can add it manually through any provider:

1. Open the model browser with `/add_model`
2. Select the appropriate provider
3. Scroll to the bottom of the model list and select **✨ Custom model...**
4. Enter the model ID exactly as the provider expects it (e.g., `gpt-4-turbo-preview`)
5. Enter the context window size in tokens (default: 128,000)
6. Provide API credentials if needed

> [!TIP]
> You can use shorthand for context sizes: `128k` for 128,000 or `1m` for 1,000,000 tokens.

## Example

**Scenario:** You want to add Groq's Llama model to Code Puppy.

1. Run `/add_model`
2. Navigate to **Groq** in the provider list and press Enter
3. Browse the available models and select the one you want
4. When prompted, enter your Groq API key (from https://console.groq.com/keys)
5. The model is added! Switch to it with `/model groq-llama-...`

## Where Are Models Stored?

Added models are saved in a file called `extra_models.json` in your Code Puppy data directory. This file persists across sessions, so you only need to add a model once.

If you add a model that already exists in the configuration, Code Puppy will let you know it's already there — no duplicates are created.

## Supported Providers

The catalog includes models from many providers, including:

| Provider | API Key Variable | Where to Get It |
|----------|-----------------|------------------|
| OpenAI | `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| Anthropic | `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| Google | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| Groq | `GROQ_API_KEY` | https://console.groq.com/keys |
| Mistral | `MISTRAL_API_KEY` | https://console.mistral.ai/ |
| DeepSeek | `DEEPSEEK_API_KEY` | https://platform.deepseek.com/ |
| Together AI | `TOGETHER_API_KEY` | https://api.together.xyz/settings/api-keys |
| Fireworks | `FIREWORKS_API_KEY` | https://fireworks.ai/api-keys |
| OpenRouter | `OPENROUTER_API_KEY` | https://openrouter.ai/keys |
| Cohere | `COHERE_API_KEY` | https://dashboard.cohere.com/api-keys |
| Perplexity | `PERPLEXITY_API_KEY` | https://www.perplexity.ai/settings/api |
| Cerebras | `CEREBRAS_API_KEY` | https://cloud.cerebras.ai/ |
| xAI | `XAI_API_KEY` | https://console.x.ai/ |

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "No providers found" | Models database couldn't be loaded | Check your internet connection — the catalog fetches from models.dev on first use |
| Provider shows ⚠️ | Provider requires special authentication | Use a different provider, or configure the model manually |
| Model doesn't work after adding | API key missing or incorrect | Run `/set PROVIDER_API_KEY=your-key` to set or update the key |
| "Already in extra_models.json" | Model was previously added | No action needed — switch to it with `/model model-name` |
| Model can't edit files or run commands | Model lacks tool calling support | Choose a model with the 🔧 icon, or accept limited functionality |

## Related Guides
- [How to Switch Models](SwitchModels) — Switch between your configured models
- [How to Set Up Round Robin Models](RoundRobinModels) — Rotate between multiple models automatically
- [Configuration](../Getting-Started/Configuration) — Set up API keys and other settings
