#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const HOME = os.homedir();
const CREDENTIALS_FILE = path.join(HOME, ".email-mcp", "credentials.enc");
const PBKDF2_ITERATIONS = 100000;

function parseArgs(argv) {
  const args = { attachments: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (!value.startsWith("--")) continue;
    const key = value.slice(2);
    const next = argv[index + 1];
    if (key === "attachment") {
      if (next && !next.startsWith("--")) {
        args.attachments.push(next);
        index += 1;
      }
      continue;
    }
    if (!next || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      index += 1;
    }
  }
  return args;
}

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function decryptCredentials() {
  const encrypted = JSON.parse(fs.readFileSync(CREDENTIALS_FILE, "utf8"));
  const seed = `email-mcp:${os.hostname()}:${os.userInfo().username}`;
  const key = crypto.pbkdf2Sync(
    seed,
    Buffer.from(encrypted.salt, "hex"),
    PBKDF2_ITERATIONS,
    32,
    "sha512",
  );
  const decipher = crypto.createDecipheriv(
    "aes-256-gcm",
    key,
    Buffer.from(encrypted.iv, "hex"),
  );
  decipher.setAuthTag(Buffer.from(encrypted.authTag, "hex"));
  let decrypted = decipher.update(encrypted.data, "hex", "utf8");
  decrypted += decipher.final("utf8");
  return JSON.parse(decrypted);
}

function loadNodemailer() {
  const npxRoot = path.join(HOME, ".npm", "_npx");
  for (const entry of fs.readdirSync(npxRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const packageJson = path.join(npxRoot, entry.name, "node_modules", "nodemailer", "package.json");
    if (fs.existsSync(packageJson)) {
      return createRequire(packageJson)("nodemailer");
    }
  }
  throw new Error("nodemailer not found in ~/.npm/_npx");
}

function getAccount(credentials, selector) {
  const accounts = Object.values(credentials.accounts ?? {});
  const account = accounts.find((item) => item.id === selector || item.email === selector);
  if (!account) {
    throw new Error(`email account not found: ${selector}`);
  }
  if (!account.password?.password) {
    throw new Error(`email account has no password credentials: ${account.email}`);
  }
  return account;
}

function htmlToText(html) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|tr|table|h[1-6])>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s+/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const accountSelector = args.account;
  const to = args.to;
  const subject = args.subject;

  if (!accountSelector || !to || !subject) {
    throw new Error(
      "usage: send_email_with_attachment_via_email_mcp.mjs --account <id-or-email> --to <email> --subject <subject> [--html] [--attachment <path>]",
    );
  }

  const body = await readStdin();
  const credentials = decryptCredentials();
  const account = getAccount(credentials, accountSelector);
  const password = account.password;
  const smtpHost = password.smtpHost || password.host.replace("imap", "smtp");
  const smtpPort = Number(password.smtpPort || 587);
  const nodemailer = loadNodemailer();

  const attachments = args.attachments.map((attachmentPath) => {
    const resolved = path.resolve(attachmentPath);
    if (!fs.existsSync(resolved)) {
      throw new Error(`attachment not found: ${resolved}`);
    }
    return {
      filename: path.basename(resolved),
      path: resolved,
      contentType: resolved.endsWith(".md") ? "text/markdown; charset=utf-8" : undefined,
    };
  });

  const transport = nodemailer.createTransport({
    host: smtpHost,
    port: smtpPort,
    secure: smtpPort === 465,
    auth: {
      user: account.email,
      pass: password.password,
    },
  });

  const message = {
    from: account.name ? `"${account.name}" <${account.email}>` : account.email,
    to,
    subject,
    attachments,
  };

  if (args.html) {
    message.html = body;
    message.text = htmlToText(body);
  } else {
    message.text = body;
  }

  const result = await transport.sendMail(message);
  console.log(result.messageId || "sent");
}

main().catch((error) => {
  console.error(error.message || String(error));
  process.exit(1);
});
