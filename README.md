# setvar - Shell Environment Variable Manager

A powerful command-line tool for managing environment variables across multiple shell configurations (bash, zsh, sh) with backup, sync, import/export capabilities.

## Features

- **Multi-shell support**: Manage variables across bash, zsh, and sh simultaneously
- **Automatic backups**: Creates zip backups before making changes (configurable)
- **Dry-run mode**: Preview changes without modifying files
- **Sync functionality**: Synchronize variables between different shells
- **Import/Export**: Save and load variables in JSON, .env, or shell script formats
- **Pattern matching**: Filter variables using wildcards
- **Confirmation prompts**: Safety checks before making changes
- **Verbose mode**: Detailed logging for troubleshooting

## Installation

```bash
# Make the script executable
chmod +x setvar.py

# Optionally, create a symlink in your PATH
ln -s $(pwd)/setvar.py /usr/local/bin/setvar
```

## Usage

### Basic Commands

```bash
# Set a variable across all shells
setvar set API_KEY "your-secret-key"

# Set a variable in specific shells
setvar set DATABASE_URL "postgres://localhost/mydb" --shell bash zsh

# Get a variable value
setvar get API_KEY

# List all variables
setvar list

# List with sync status check
setvar list --sync-check

# Remove a variable
setvar remove OLD_VAR
```

### Advanced Features

```bash
# Sync variables from bash to all other shells
setvar sync --from bash --to all

# Sync specific variables using patterns
setvar sync --from zsh --to bash --keys "*_API_*" "*_URL"

# Export variables to different formats
setvar export --output env_vars.json --format json
setvar export --output .env --format env --keys "*_KEY" "*_TOKEN"
setvar export --output setup_env.sh --format shell

# Import variables from files
setvar import config.json
setvar import .env --shell bash --keys "DB_*"

# Backup management
setvar backup create --message "Before major changes"
setvar backup list
setvar backup restore backup_20240101_120000.zip
```

### Command-line Options

Global options:

- `-V, --version`: Show version
- `-v, --verbose`: Enable verbose output
- `-n, --dry-run`: Preview changes without applying them
- `-y, --yes`: Skip confirmation prompts
- `--no-backup`: Disable automatic backups
- `--config-dir`: Custom config directory (default: ~/.config/setvar)

## Examples

### Setting Up Development Environment

```bash
# Import development variables
setvar import dev.env --shell all

# Check sync status
setvar list --sync-check

# Fix any out-of-sync variables
setvar sync --from bash --to all
```

### Migrating to a New Shell

```bash
# Export all bash variables
setvar export --shell bash --output my_vars.json

# Import into zsh
setvar import my_vars.json --shell zsh
```

### Pattern-based Operations

```bash
# List all API-related variables
setvar list --pattern "*API*"

# Export only database configurations
setvar export --keys "DB_*" "DATABASE_*" --output db_config.env

# Remove all test variables
setvar remove TEST_VAR_1 --shell all
```

## Safety Features

1. **Confirmations**: Shows proposed changes and asks for confirmation
2. **Backups**: Automatically creates backups before modifications
3. **Dry-run**: Test commands without making changes
4. **Validation**: Validates variable names and values

## File Locations

- Config files checked:
  - Bash: `~/.bashrc`, `~/.bash_profile`, `~/.profile`
  - Zsh: `~/.zshrc`, `~/.zprofile`, `~/.zshenv`
  - Sh: `~/.profile`
- Backups: `~/.config/setvar/backups/`

## Notes

- Variables are added using the `export` syntax
- Handles quoted values and special characters properly
- Creates config files if they don't exist
- Respects existing variable locations when updatin
