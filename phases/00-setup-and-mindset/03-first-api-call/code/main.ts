/**
 * Lesson 03: First API Call (TypeScript)
 * Demonstrates non-streaming, streaming, token counting, and stop reason detection.
 * Run with: npx ts-node main.ts
 */

import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

const PROMPT = "Explain what a context window is in one sentence.";

/**
 * Inspect all fields of a Message response object.
 */
function inspectResponse(response: Anthropic.Message): void {
  console.log("=== Response Object Fields ===");
  console.log(`  id:            ${response.id}`);
  console.log(`  type:          ${response.type}`);
  console.log(`  role:          ${response.role}`);
  console.log(`  model:         ${response.model}`);
  console.log(`  stop_reason:   ${response.stop_reason}`);
  console.log(`  stop_sequence: ${response.stop_sequence}`);
  console.log(`  input_tokens:  ${response.usage.input_tokens}`);
  console.log(`  output_tokens: ${response.usage.output_tokens}`);
  console.log(`  content blocks:${response.content.length}`);

  for (const [i, block] of response.content.entries()) {
    const textLen = block.type === "text" ? block.text.length : "N/A";
    console.log(`    [${i}] type=${block.type}, text_length=${textLen}`);
  }

  const firstBlock = response.content[0];
  if (firstBlock.type === "text") {
    console.log(`\n  Text:\n  ${firstBlock.text.slice(0, 200)}`);
  }
}

/**
 * Extract text from response, throwing if truncated.
 */
function safeExtractText(response: Anthropic.Message): string {
  if (response.stop_reason === "max_tokens") {
    throw new Error(
      `Response truncated at ${response.usage.output_tokens} tokens. ` +
        "Increase max_tokens or split the task."
    );
  }
  const firstBlock = response.content[0];
  if (!firstBlock || firstBlock.type !== "text") {
    throw new Error(`Unexpected content type: ${firstBlock?.type}`);
  }
  return firstBlock.text;
}

/**
 * Stream a response to stdout, return accumulated text and usage.
 */
async function streamToStdout(
  prompt: string
): Promise<{ text: string; usage: Anthropic.Usage }> {
  console.log("\n=== Streaming (TypeScript) ===");
  const chunks: string[] = [];
  let finalUsage: Anthropic.Usage | null = null;

  const stream = await client.messages.stream({
    model: "claude-3-5-haiku-20241022",
    max_tokens: 256,
    messages: [{ role: "user", content: prompt }],
  });

  // Accumulate chunks as they arrive
  for await (const event of stream) {
    if (
      event.type === "content_block_delta" &&
      event.delta.type === "text_delta"
    ) {
      process.stdout.write(event.delta.text);
      chunks.push(event.delta.text);
    }
    if (event.type === "message_delta") {
      finalUsage = event.usage as unknown as Anthropic.Usage;
    }
  }

  process.stdout.write("\n");

  const finalMessage = await stream.finalMessage();
  return {
    text: chunks.join(""),
    usage: finalMessage.usage,
  };
}

/**
 * Demonstrate max_tokens truncation detection.
 */
async function demonstrateTruncation(): Promise<void> {
  console.log("\n=== max_tokens Truncation Demo ===");
  const response = await client.messages.create({
    model: "claude-3-5-haiku-20241022",
    max_tokens: 10,
    messages: [
      {
        role: "user",
        content: "Write a 100-word explanation of how APIs work.",
      },
    ],
  });

  console.log(`stop_reason: ${response.stop_reason}`);
  console.log(`output_tokens generated: ${response.usage.output_tokens}`);
  const firstBlock = response.content[0];
  if (firstBlock.type === "text") {
    console.log(`truncated text: '${firstBlock.text}'`);
  }
}

async function main(): Promise<void> {
  if (!process.env.ANTHROPIC_API_KEY) {
    console.error("ERROR: ANTHROPIC_API_KEY not set.");
    process.exit(1);
  }

  // 1. Non-streaming call
  console.log("=== Non-Streaming Call ===");
  const response = await client.messages.create({
    model: "claude-3-5-haiku-20241022",
    max_tokens: 256,
    messages: [{ role: "user", content: PROMPT }],
  });
  inspectResponse(response);

  // 2. Safe text extraction
  console.log("\n=== Safe Text Extraction ===");
  const text = safeExtractText(response);
  console.log(`Extracted: ${text.slice(0, 100)}...`);

  // 3. Streaming
  const { text: streamedText, usage: streamUsage } = await streamToStdout(PROMPT);
  console.log(`\nStream stats:`);
  console.log(`  input_tokens:  ${streamUsage.input_tokens}`);
  console.log(`  output_tokens: ${streamUsage.output_tokens}`);
  console.log(`  accumulated characters: ${streamedText.length}`);

  // 4. Truncation demo
  await demonstrateTruncation();

  // 5. Compare token counts
  console.log("\n=== Token Count Comparison ===");
  console.log(
    `Non-streaming: ${response.usage.input_tokens} in / ${response.usage.output_tokens} out`
  );
  console.log(
    `Streaming:     ${streamUsage.input_tokens} in / ${streamUsage.output_tokens} out`
  );
  console.log("(Should be identical for the same prompt)");
}

main().catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
