/**
 * L07: Build an MCP Server - TypeScript
 * appliedaifromscratch.com | Phase 03
 *
 * Same product catalog server as main.py, in TypeScript.
 * Uses @modelcontextprotocol/sdk and better-sqlite3.
 *
 * Setup:
 *   npm install
 *   npx tsc
 *   node dist/main.js
 *
 * Or run directly with tsx:
 *   npx tsx main.ts
 *
 * Claude Desktop config:
 *   {
 *     "mcpServers": {
 *       "product-catalog-ts": {
 *         "command": "node",
 *         "args": ["/absolute/path/to/dist/main.js"]
 *       }
 *     }
 *   }
 */

import { McpServer, ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import Database from "better-sqlite3";

// ---------------------------------------------------------------------------
// Database
// ---------------------------------------------------------------------------

interface Product {
  id: string;
  name: string;
  category: string;
  price_cents: number;
  description: string;
  in_stock: number;
}

function createDb(): Database.Database {
  const db = new Database(":memory:");

  db.exec(`
    CREATE TABLE IF NOT EXISTS products (
      id          TEXT    PRIMARY KEY,
      name        TEXT    NOT NULL,
      category    TEXT    NOT NULL,
      price_cents INTEGER NOT NULL,
      description TEXT,
      in_stock    INTEGER DEFAULT 1
    )
  `);

  const insert = db.prepare(
    "INSERT OR IGNORE INTO products VALUES (?, ?, ?, ?, ?, ?)"
  );

  const seed = db.transaction(() => {
    insert.run("P001", "Mechanical Keyboard",   "electronics", 12999, "TKL, Cherry MX Brown switches", 1);
    insert.run("P002", "USB-C Hub 7-port",       "electronics",  4999, "4K HDMI, 100W PD, SD card reader", 1);
    insert.run("P003", "Standing Desk Mat",      "office",        3499, "Anti-fatigue foam, 36x24 inches", 1);
    insert.run("P004", "Monitor Arm",            "office",        8999, "Gas spring, holds up to 32-inch dual monitors", 1);
    insert.run("P005", "Wireless Headphones",    "electronics", 19999, "Active noise cancellation, 30hr battery", 0);
    insert.run("P006", "Laptop Stand",           "office",        5999, "Aluminum, 6 adjustable height positions", 1);
    insert.run("P007", "Webcam 4K",              "electronics", 14999, "Auto-focus, excellent low-light performance", 1);
    insert.run("P008", "Cable Management Kit",   "office",        1299, "Velcro straps, adhesive clips, under-desk tray", 1);
    insert.run("P009", "Desk Lamp LED",          "office",        4499, "3 color temps, USB-A charging port", 1);
    insert.run("P010", "Wrist Rest Set",         "office",        2999, "Memory foam for keyboard and mouse", 1);
  });

  seed();
  return db;
}

const dbInstance = createDb();

// ---------------------------------------------------------------------------
// Server
// ---------------------------------------------------------------------------

const server = new McpServer({
  name: "product-catalog",
  version: "1.0.0",
});

// ---------------------------------------------------------------------------
// Tool: search_products
// ---------------------------------------------------------------------------

server.tool(
  "search_products",
  "Search products by name or description. Returns in-stock items only.",
  {
    query: z.string().min(1).describe("Search term to match against name or description"),
    limit: z
      .number()
      .int()
      .min(1)
      .max(50)
      .default(10)
      .describe("Maximum number of results (1-50)"),
  },
  async ({ query, limit }) => {
    const trimmed = query.trim();
    if (!trimmed) {
      return { content: [{ type: "text", text: "[]" }] };
    }

    const searchTerm = `%${trimmed}%`;
    const rows = dbInstance
      .prepare(
        `SELECT id, name, category, price_cents, description, in_stock
         FROM products
         WHERE (name LIKE ? OR description LIKE ?) AND in_stock = 1
         ORDER BY name
         LIMIT ?`
      )
      .all(searchTerm, searchTerm, limit) as Product[];

    return {
      content: [{ type: "text", text: JSON.stringify(rows, null, 2) }],
    };
  }
);

// ---------------------------------------------------------------------------
// Tool: get_product
// ---------------------------------------------------------------------------

server.tool(
  "get_product",
  "Get a single product by its ID. Returns null if not found.",
  {
    product_id: z.string().describe("Product ID (e.g. 'P001')"),
  },
  async ({ product_id }) => {
    const row = dbInstance
      .prepare("SELECT * FROM products WHERE id = ?")
      .get(product_id) as Product | undefined;

    return {
      content: [
        { type: "text", text: row ? JSON.stringify(row, null, 2) : "null" },
      ],
    };
  }
);

// ---------------------------------------------------------------------------
// Resource: product://catalog/{category}
// ---------------------------------------------------------------------------

server.resource(
  "product-catalog",
  new ResourceTemplate("product://catalog/{category}", { list: undefined }),
  async (uri, { category }) => {
    // ResourceTemplate may give category as string or string[]
    const cat = Array.isArray(category) ? category[0] : category;

    const rows: Product[] =
      cat === "all"
        ? (dbInstance
            .prepare(
              `SELECT id, name, category, price_cents, description
               FROM products WHERE in_stock = 1 ORDER BY category, name`
            )
            .all() as Product[])
        : (dbInstance
            .prepare(
              `SELECT id, name, category, price_cents, description
               FROM products WHERE category = ? AND in_stock = 1 ORDER BY name`
            )
            .all(cat) as Product[]);

    return {
      contents: [
        {
          uri: uri.href,
          mimeType: "application/json",
          text: JSON.stringify(rows, null, 2),
        },
      ],
    };
  }
);

// ---------------------------------------------------------------------------
// Prompt: product_summary
// ---------------------------------------------------------------------------

server.prompt(
  "product_summary",
  "Generate a prompt to write a product summary.",
  {
    product_id: z.string().describe("Product ID to summarize (e.g. 'P001')"),
    style: z
      .enum(["brief", "detailed"])
      .default("brief")
      .describe("'brief' for a snippet, 'detailed' for a full description"),
  },
  async ({ product_id, style }) => {
    const product = dbInstance
      .prepare("SELECT * FROM products WHERE id = ?")
      .get(product_id) as Product | undefined;

    if (!product) {
      return {
        messages: [
          {
            role: "user" as const,
            content: {
              type: "text" as const,
              text: `No product found with ID '${product_id}'. Please check the product ID.`,
            },
          },
        ],
      };
    }

    const price = `$${(product.price_cents / 100).toFixed(2)}`;
    const stockStatus = product.in_stock ? "In stock" : "Out of stock";

    const base =
      `Product: ${product.name} (ID: ${product.id})\n` +
      `Category: ${product.category}\n` +
      `Price: ${price}\n` +
      `Status: ${stockStatus}\n` +
      `Description: ${product.description}\n\n`;

    const instruction =
      style === "brief"
        ? "Write a 1-2 sentence product summary suitable for a search result snippet. Lead with the most distinctive feature."
        : "Write a detailed product description with:\n" +
          "1. A compelling headline\n" +
          "2. Key features as bullet points\n" +
          "3. Ideal use case (who is this for?)\n" +
          "4. A closing sentence on value for money";

    return {
      messages: [
        {
          role: "user" as const,
          content: { type: "text" as const, text: base + instruction },
        },
      ],
    };
  }
);

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Log to stderr only - stdout is reserved for JSON-RPC
  process.stderr.write("Product Catalog MCP Server (TypeScript) started\n");
}

main().catch((err: Error) => {
  process.stderr.write(`Fatal error: ${err.message}\n`);
  process.exit(1);
});
