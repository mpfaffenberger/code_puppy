# llama.cpp: `failed to process mtmd chunk`

This message comes from the model server's multimodal processing path. On an
OpenAI-compatible streaming endpoint, the server can accept the HTTP request and
then send an error event before producing the first response chunk. The OpenAI
SDK raises a bare `openai.APIError`; the class name does not mean the request was
sent to OpenAI's hosted service.

Code Puppy emits a targeted diagnostic and retains the full exception traceback
in `~/.code_puppy/logs/errors.log`. The diagnostic does not change retry policy,
strip images, reset conversation history, or modify the server configuration.

## Investigate the server, not just the client traceback

1. Check the llama-server log around the failed request. The `mtmd` message is a
   summary; preceding decoder messages are more useful.
2. Verify that the loaded model supports images and uses its matching multimodal
   projector (`--mmproj`).
3. Check resource/context limits and server build compatibility.
4. If speculative decoding is enabled, test the same image with speculative
   decoding disabled. In particular, a failure naming `ctx_dft` is in the draft
   decoder, not necessarily the image projector or main decoder.
5. Once the server-side problem is corrected, resume the session and retry the
   prompt. Starting a new conversation alone does not fix a broken decoder.

Do not silently delete screenshots to make a computer-use session continue: the
model would lose the visual observations needed to choose safe UI actions.

## Observed failure pattern

A local Qwen3.8-27B llama.cpp server using Vulkan tensor splitting and DFlash2
speculative decoding failed after valid PNG screenshots were supplied. Its log
contained:

```text
find_slot: non-consecutive token position ... for sequence 0 with 512 new tokens
decode: failed to find a memory slot for batch of size 64
process: llama_decode(ctx_dft) failed rc=1 (n_tokens=64, offset=256)
post-decode callback failed
failed to decode mtmd chunk
failed to process mtmd chunk
```

The client traceback ended in:

```text
pydantic_ai/models/openai.py: _process_streamed_response
    first_chunk = await peekable_response.peek()
openai/_streaming.py: __stream__
    raise APIError(...)
openai.APIError: failed to process mtmd chunk
```

This establishes a server-side draft-decoder failure for that incident. The
signature alone is not enough to diagnose every server's underlying cause.
Disabling speculative decoding is a troubleshooting workaround, not a repair to
llama.cpp's implementation. Updating/fixing that implementation is outside the
scope of Code Puppy's diagnostic handling.
