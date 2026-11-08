import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";

let client: LanguageClient | undefined;

// The server has to be the project's own: it runs the project's models
function serverCommand(): string {
  const configured = vscode.workspace.getConfiguration("pangloss").get<string>("serverPath");
  if (configured) {
    return configured;
  }
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    const candidate = path.join(folder.uri.fsPath, ".venv", "bin", "pangloss-lsp");
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return "pangloss-lsp";
}

export async function activate(): Promise<void> {
  client = new LanguageClient(
    "pangloss",
    "Pangloss",
    { command: serverCommand() },
    { documentSelector: [{ scheme: "file", language: "python" }] },
  );
  await client.start();
}

export async function deactivate(): Promise<void> {
  await client?.stop();
}
