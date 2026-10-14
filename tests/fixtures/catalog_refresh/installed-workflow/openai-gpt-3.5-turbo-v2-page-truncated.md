# GPT-3.5 Turbo

> For the complete documentation index, see [llms.txt](/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

> Legacy GPT model for cheaper chat and non-chat tasks

Model ID: `gpt-3.5-turbo`

GPT-3.5 Turbo models can understand and generate natural language or code and have been optimized for chat using the Chat Completions API but work well for non-chat tasks as well. As of July 2024, use gpt-4o-mini in place of GPT-3.5 Turbo, as it is cheaper, more capable, multimodal, and just as fast. GPT-3.5 Turbo is still available for use in the API.

## Model details

- Default snapshot: `gpt-3.5-turbo-0125`
- Input modalities: text
- Output modalities: text
- 16,385 context window
- 4,096 max output tokens
- Sep 01, 2021 knowledge cutoff

## Pricing

Pricing is based on the number of tokens used, or other metrics based on the model type. For tool-specific models, like search and computer use, there’s a fee per tool call. See details in the [pricing page](/api/docs/pricing).

### Text tokens

| Metric | Price | Unit |
| --- | ---: | --- |
| Input | $0.75 | 1M tokens |
| Output | $1