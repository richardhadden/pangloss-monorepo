use zed_extension_api::{self as zed, settings::LspSettings, LanguageServerId, Result};

struct PanglossExtension;

impl zed::Extension for PanglossExtension {
    fn new() -> Self {
        PanglossExtension
    }

    fn language_server_command(
        &mut self,
        language_server_id: &LanguageServerId,
        worktree: &zed::Worktree,
    ) -> Result<zed::Command> {
        let configured = LspSettings::for_worktree(language_server_id.as_ref(), worktree)
            .ok()
            .and_then(|settings| settings.binary);

        // The server has to be the project's own: it runs the project's models. (Zed leaves what git
        // ignores, `.venv` among it, out of the worktree, so the file cannot be looked for: if it is not
        // there, the editor says so when it starts it.)
        let command = match configured.as_ref().and_then(|binary| binary.path.clone()) {
            Some(path) => path,
            None => match worktree.which("pangloss-lsp") {
                Some(path) => path,
                None => format!("{}/.venv/bin/pangloss-lsp", worktree.root_path()),
            },
        };
        Ok(zed::Command {
            command,
            args: configured
                .and_then(|binary| binary.arguments)
                .unwrap_or_default(),
            env: worktree.shell_env(),
        })
    }
}

zed::register_extension!(PanglossExtension);
