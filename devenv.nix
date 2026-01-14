{ pkgs, lib, config, inputs, ... }:

{
  dotenv.enable = true;

  # Claude Code integration
  claude.code.enable = true;
  claude.code.mcpServers = {
    devenv = {
      type = "stdio";
      command = "devenv";
      args = [ "mcp" ];
      env = {
        DEVENV_ROOT = config.devenv.root;
      };
    };
    docs-langchain = {
      type = "http";
      url = "https://docs.langchain.com/mcp";
    };
  };

  # Claude Code hooks for automatic quality checks
  claude.code.hooks = {
    # Format and lint Python files after editing
    format-python = {
      enable = true;
      name = "Format and lint Python files";
      hookType = "PostToolUse";
      matcher = "^(Edit|Write)$";
      command = ''
        FILE_PATH=$(echo "$HOOK_INPUT" | ${pkgs.jq}/bin/jq -r '.tool_input.file_path // empty')
        if [[ "$FILE_PATH" == *.py ]]; then
          cd "$CLAUDE_PROJECT_DIR"
          ${pkgs.ruff}/bin/ruff format "$FILE_PATH"
          ${pkgs.ruff}/bin/ruff check --fix "$FILE_PATH"
          echo "✓ Formatted and linted: $FILE_PATH"
        fi
      '';
    };

    # Type check before git commits
    type-check-pre-commit = {
      enable = true;
      name = "Type check before commit";
      hookType = "PreToolUse";
      matcher = "^Bash$";
      command = ''
        BASH_CMD=$(echo "$HOOK_INPUT" | ${pkgs.jq}/bin/jq -r '.tool_input.command // empty')
        if [[ "$BASH_CMD" == *"git commit"* ]]; then
          cd "$CLAUDE_PROJECT_DIR"
          echo "Running type check before commit..."
          uvx ty check .
          echo "✓ Type check passed"
        fi
      '';
    };
  };

  # Python language configuration
  languages.python = {
    enable = true;
    venv.enable = true;

    uv = {
      enable = true;
      sync = {
        enable = true;        # Auto-run uv sync on shell entry
        allExtras = true;     # Install all optional dependencies
      };
    };
  };

  # Python tools
  packages = with pkgs; [
    ruff
    jq  # For hook JSON parsing
  ];

  # Git pre-commit hooks
  git-hooks.hooks = {
    # Format Python code
    ruff-format = {
      enable = true;
      name = "ruff-format";
      entry = "${pkgs.ruff}/bin/ruff format";
      files = "\\.py$";
      language = "system";
    };

    # Lint and auto-fix Python code
    ruff = {
      enable = true;
      entry = lib.mkForce "${pkgs.ruff}/bin/ruff check --fix";
    };

    # Type check with ty
    ty-check = {
      enable = true;
      name = "ty type check";
      entry = "uvx ty check";
      files = "\\.py$";
      language = "system";
      pass_filenames = false;
    };
  };

  # See full reference at https://devenv.sh/reference/options/
}
