# How to Set Up Round Robin Models

## What You'll Learn
By the end of this guide, you'll be able to configure a round-robin model that automatically cycles through multiple AI models, distributing your requests across them to help with rate limits or balance usage across providers.

## Prerequisites
- Code Puppy installed and running
- At least two models already configured and working (see [How to Add Models](AddModels))
- API keys set up for each model you want to include (see [Configuration](../Getting-Started/Configuration))

## Quick Version

Add a round-robin entry to your `extra_models.json` file:

```json
{
  "my-round-robin": {
    "type": "round_robin",
    "models": ["gpt-5.1", "claude-4-5-sonnet"],
    "rotate_every": 1
  }
}
```

Then select it with `/model my-round-robin`.

## Detailed Steps

### 1. Choose Which Models to Include

First, decide which models you want to cycle through. You can use any models that are already configured in Code Puppy — whether they're built-in or ones you've added yourself.

To see your available models, type:

```
/model
```

Note the exact names of the models you want to include in your round-robin group.

> [!TIP]
> Round robin works best with models that have similar capabilities. For example, combine two fast models for general coding, or two reasoning models for complex tasks.

### 2. Create the Round Robin Configuration

Open your `extra_models.json` file. This file is located in your Code Puppy data directory:

| OS | Path |
|----|------|
| Linux | `~/.local/share/code_puppy/extra_models.json` |
| macOS | `~/.local/share/code_puppy/extra_models.json` |
| Fallback | `~/.code_puppy/extra_models.json` |

If the file doesn't exist yet, create it. Add a new model entry with `"type": "round_robin"`:

```json
{
  "my-round-robin": {
    "type": "round_robin",
    "models": ["gpt-5.1", "claude-4-5-sonnet"],
    "rotate_every": 1
  }
}
```

> [!WARNING]
> Every model name in the `"models"` list must exactly match the name of an existing model in Code Puppy. If any name is wrong, the round-robin model will fail to load.

### 3. Understand the `rotate_every` Setting

The `rotate_every` value controls how many requests are sent to one model before switching to the next:

| `rotate_every` | Behavior |
|----------------|----------|
| `1` (default) | Alternates models on every request |
| `2` | Sends 2 requests to each model before rotating |
| `5` | Sends 5 requests to each model before rotating |

For example, with `"rotate_every": 2` and two models:
1. Request 1 → Model A
2. Request 2 → Model A
3. Request 3 → Model B
4. Request 4 → Model B
5. Request 5 → Model A (cycle repeats)

> [!TIP]
> Use `rotate_every: 1` to spread load evenly. Use a higher value if you want continuity with the same model over a short conversation burst.

### 4. Switch to Your Round Robin Model

Once saved, use the `/model` command to switch:

```
/model my-round-robin
```

Code Puppy will now automatically distribute your requests across the configured models.

### 5. Verify It's Working

After switching, you can confirm the active model by checking the status display in Code Puppy. The model name will show as your round-robin name (e.g., `my-round-robin`).

As you send messages, requests will be distributed across your configured models according to the `rotate_every` setting.

## Example

### Balancing Between Two Providers

If you have API keys for both OpenAI and Anthropic and want to spread your requests across both:

```json
{
  "balanced-duo": {
    "type": "round_robin",
    "models": ["gpt-5.1", "claude-4-5-sonnet"],
    "rotate_every": 1
  }
}
```

### Three-Model Rotation with Batching

For heavier workloads where you want to use three models and send a few requests to each before rotating:

```json
{
  "triple-rotation": {
    "type": "round_robin",
    "models": ["gpt-5.1", "claude-4-5-sonnet", "Gemini-3"],
    "rotate_every": 3
  }
}
```

### Adding to Existing Extra Models

If you already have custom models in `extra_models.json`, simply add the round-robin entry alongside them:

```json
{
  "my-custom-model": {
    "type": "custom_openai",
    "name": "some-model",
    "custom_endpoint": {
      "url": "https://api.example.com/v1/",
      "api_key": "$MY_API_KEY"
    }
  },
  "my-round-robin": {
    "type": "round_robin",
    "models": ["my-custom-model", "gpt-5.1"],
    "rotate_every": 1
  }
}
```

> [!NOTE]
> You can include custom models you've defined in the same `extra_models.json` file as part of your round-robin group.

## Options & Variations

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `type` | string | Yes | — | Must be `"round_robin"` |
| `models` | list | Yes | — | List of model names to cycle through |
| `rotate_every` | integer | No | `1` | Number of requests per model before rotating |

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "requires a 'models' list" error | Missing or invalid `models` field | Ensure `"models"` is a JSON array of strings |
| "At least one model must be provided" | Empty models list | Add at least one model name to the list |
| Model fails to load | A model name in the list doesn't exist | Check spelling and ensure the referenced models are properly configured |
| Rate limit errors persist | All models share the same API key/provider | Use models from different providers for effective rate limit distribution |
| JSON parse error | Syntax error in `extra_models.json` | Validate your JSON (check for missing commas, brackets, or quotes) |

## Key Things to Know

- **Distribution, not failover** — Round robin rotates models in order. If one model fails, the error is returned immediately; it does not automatically try the next model.
- **Stateless rotation** — The rotation counter resets when you restart Code Puppy.
- **Any model type works** — You can mix built-in models, custom OpenAI-compatible models, and OAuth-connected models in the same round-robin group.

## Related Guides
- [How to Switch Models](SwitchModels) — Change your active model on the fly
- [How to Add Models from the Catalog](AddModels) — Add new models to Code Puppy
- [Configuration](../Getting-Started/Configuration) — Set up API keys and preferences
