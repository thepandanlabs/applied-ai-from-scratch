/**
 * Lesson 01: Dev Environment (TypeScript)
 * Verifies that the Node environment and Anthropic SDK are correctly installed.
 * Run with: npx ts-node main.ts
 */

import Anthropic from "@anthropic-ai/sdk";

async function main(): Promise<void> {
  // Step 1: Verify Node version
  const [nodeMajor] = process.versions.node.split(".").map(Number);
  console.log(`Node version: ${process.versions.node}`);
  if (nodeMajor < 20) {
    console.warn("WARNING: Node 20+ is recommended for this course.");
  } else {
    console.log(`OK: Node ${nodeMajor} meets the 20+ requirement.`);
  }

  // Step 2: Verify SDK import
  console.log("OK: @anthropic-ai/sdk imported successfully.");

  // Step 3: Verify API key
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    console.warn("WARNING: ANTHROPIC_API_KEY not set.");
    console.warn("  export ANTHROPIC_API_KEY=sk-ant-...");
    console.log("Skipping API call verification.");
    return;
  }
  console.log("OK: ANTHROPIC_API_KEY found in environment.");

  // Step 4: Make a minimal API call
  console.log("\nMaking a minimal API call to verify key and connectivity...");

  const client = new Anthropic({ apiKey });

  const message = await client.messages.create({
    model: "claude-3-5-haiku-20241022",
    max_tokens: 32,
    messages: [{ role: "user", content: "Reply with exactly: ENVIRONMENT OK" }],
  });

  const responseText =
    message.content[0].type === "text" ? message.content[0].text : "";
  console.log(`Model response: ${responseText}`);
  console.log(`Input tokens: ${message.usage.input_tokens}`);
  console.log(`Output tokens: ${message.usage.output_tokens}`);

  if (responseText.toUpperCase().includes("ENVIRONMENT")) {
    console.log("\nAll TypeScript checks passed. Your environment is ready.");
  } else {
    console.log(
      "\nAPI call succeeded but response was unexpected. Environment is likely fine."
    );
  }
}

main().catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
