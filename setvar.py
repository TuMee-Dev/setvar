#!/usr/bin/env python3
"""
setvar - A shell environment variable management tool

Manages environment variables across multiple shell configurations with
backup, sync, import/export, and safety features.
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import re
from datetime import datetime
import zipfile
import shutil
from enum import Enum
import logging


__version__ = "0.1.0"


class Shell(Enum):
    """Supported shell types"""
    BASH = "bash"
    ZSH = "zsh"
    SH = "sh"
    
    @property
    def config_files(self) -> List[str]:
        """Get configuration files for each shell type"""
        home = Path.home()
        if self == Shell.BASH:
            return [
                str(home / ".bashrc"),
                str(home / ".bash_profile"),
                str(home / ".profile")
            ]
        elif self == Shell.ZSH:
            return [
                str(home / ".zshrc"),
                str(home / ".zprofile"),
                str(home / ".zshenv")
            ]
        elif self == Shell.SH:
            return [
                str(home / ".profile")
            ]
        return []


class SetVar:
    """Main setvar application class"""
    
    def __init__(self, config_dir: Optional[str] = None, 
                 backup_enabled: bool = True,
                 verbose: bool = False,
                 dry_run: bool = False):
        self.config_dir = Path(config_dir or os.path.expanduser("~/.config/setvar"))
        self.backup_dir = self.config_dir / "backups"
        self.backup_enabled = backup_enabled
        self.verbose = verbose
        self.dry_run = dry_run
        
        # Set up logging
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(levelname)s: %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Create directories if they don't exist
        if not dry_run:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            if backup_enabled:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message: str, level: str = "info"):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            getattr(self.logger, level)(message)
    
    def detect_current_shell(self) -> Optional[Shell]:
        """Detect the current shell type"""
        shell_env = os.environ.get('SHELL', '')
        self.log(f"Detected SHELL environment: {shell_env}")
        
        if 'bash' in shell_env:
            return Shell.BASH
        elif 'zsh' in shell_env:
            return Shell.ZSH
        elif 'sh' in shell_env:
            return Shell.SH
        
        # Try alternative detection methods
        try:
            parent_process = os.popen('ps -p $$ -o comm=').read().strip()
            self.log(f"Parent process: {parent_process}")
            if 'bash' in parent_process:
                return Shell.BASH
            elif 'zsh' in parent_process:
                return Shell.ZSH
            elif 'sh' in parent_process:
                return Shell.SH
        except:
            pass
        
        return None
    
    def find_existing_config_files(self, shell: Shell) -> List[str]:
        """Find which config files exist for a given shell"""
        existing_files = []
        for config_file in shell.config_files:
            if Path(config_file).exists():
                existing_files.append(config_file)
                self.log(f"Found config file: {config_file}")
        return existing_files
    
    def get_primary_config_file(self, shell: Shell) -> str:
        """Get the primary config file for a shell (creates if needed)"""
        existing = self.find_existing_config_files(shell)
        if existing:
            return existing[0]
        
        # Default to the first option if none exist
        primary = shell.config_files[0]
        if not self.dry_run:
            Path(primary).touch()
            self.log(f"Created new config file: {primary}")
        return primary
    
    def read_config_file(self, filepath: str) -> List[str]:
        """Read a shell configuration file"""
        try:
            with open(filepath, 'r') as f:
                return f.readlines()
        except FileNotFoundError:
            self.log(f"Config file not found: {filepath}", "warning")
            return []
        except Exception as e:
            self.log(f"Error reading {filepath}: {e}", "error")
            return []
    
    def write_config_file(self, filepath: str, lines: List[str]):
        """Write to a shell configuration file"""
        if self.dry_run:
            self.log(f"[DRY RUN] Would write to {filepath}")
            return
        
        try:
            with open(filepath, 'w') as f:
                f.writelines(lines)
            self.log(f"Updated {filepath}")
        except Exception as e:
            self.log(f"Error writing to {filepath}: {e}", "error")
            raise
    
    def parse_export_line(self, line: str) -> Optional[Tuple[str, str]]:
        """Parse an export line to extract variable name and value"""
        # Match various export formats
        patterns = [
            r'^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$',  # export VAR=value
            r'^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$',  # VAR=value
        ]
        
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                name = match.group(1)
                value = match.group(2).strip()
                
                # Remove quotes if present
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                
                return (name, value)
        
        return None
    
    def format_export_line(self, name: str, value: str) -> str:
        """Format a variable export line"""
        # Check if value needs quoting
        needs_quotes = any(c in value for c in [' ', '\t', '$', '`', '"', "'", '\\', '!', '*', '?', '[', ']', '(', ')', '{', '}', '<', '>', '|', '&', ';'])
        
        if needs_quotes:
            # Escape double quotes in the value
            escaped_value = value.replace('"', '\\"')
            return f'export {name}="{escaped_value}"\n'
        else:
            return f'export {name}={value}\n'
    
    def get_variables_from_file(self, filepath: str) -> Dict[str, str]:
        """Extract all environment variables from a config file"""
        variables = {}
        lines = self.read_config_file(filepath)
        
        for line in lines:
            parsed = self.parse_export_line(line)
            if parsed:
                name, value = parsed
                variables[name] = value
                self.log(f"Found variable: {name}={value}")
        
        return variables
    
    def get_all_variables(self, shells: List[Shell]) -> Dict[str, Dict[str, str]]:
        """Get all variables from specified shells"""
        all_vars = {}
        
        for shell in shells:
            shell_vars = {}
            for config_file in self.find_existing_config_files(shell):
                file_vars = self.get_variables_from_file(config_file)
                shell_vars.update(file_vars)
            
            all_vars[shell.value] = shell_vars
        
        return all_vars
    
    def create_backup(self, files_to_backup: List[str], message: Optional[str] = None) -> Optional[str]:
        """Create a backup of specified files"""
        if not self.backup_enabled or self.dry_run:
            if self.dry_run:
                self.log("[DRY RUN] Would create backup")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}.zip"
        backup_path = self.backup_dir / backup_name
        
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filepath in files_to_backup:
                    if Path(filepath).exists():
                        zf.write(filepath, Path(filepath).name)
                        self.log(f"Added {filepath} to backup")
                
                # Add metadata
                metadata = {
                    "timestamp": timestamp,
                    "files": files_to_backup,
                    "message": message or "Auto-backup before changes"
                }
                zf.writestr("metadata.json", json.dumps(metadata, indent=2))
            
            self.log(f"Created backup: {backup_path}")
            return str(backup_path)
        except Exception as e:
            self.log(f"Failed to create backup: {e}", "error")
            return None
    
    def list_backups(self, limit: int = 10) -> List[Dict[str, any]]:
        """List available backups"""
        backups = []
        
        if not self.backup_dir.exists():
            return backups
        
        backup_files = sorted(self.backup_dir.glob("backup_*.zip"), reverse=True)[:limit]
        
        for backup_file in backup_files:
            try:
                with zipfile.ZipFile(backup_file, 'r') as zf:
                    if "metadata.json" in zf.namelist():
                        metadata = json.loads(zf.read("metadata.json"))
                        backups.append({
                            "path": str(backup_file),
                            "name": backup_file.name,
                            "timestamp": metadata.get("timestamp"),
                            "message": metadata.get("message"),
                            "files": metadata.get("files", [])
                        })
                    else:
                        # Old backup format without metadata
                        backups.append({
                            "path": str(backup_file),
                            "name": backup_file.name,
                            "timestamp": backup_file.stem.replace("backup_", ""),
                            "message": "Legacy backup",
                            "files": zf.namelist()
                        })
            except Exception as e:
                self.log(f"Error reading backup {backup_file}: {e}", "warning")
        
        return backups
    
    def restore_backup(self, backup_id: str) -> bool:
        """Restore files from a backup"""
        if self.dry_run:
            self.log(f"[DRY RUN] Would restore backup {backup_id}")
            return True
        
        # Find the backup file
        backup_path = None
        if Path(backup_id).exists():
            backup_path = Path(backup_id)
        else:
            # Try to find by timestamp or filename
            for backup_file in self.backup_dir.glob("backup_*.zip"):
                if backup_id in str(backup_file):
                    backup_path = backup_file
                    break
        
        if not backup_path:
            self.log(f"Backup not found: {backup_id}", "error")
            return False
        
        try:
            # Create a restore backup first
            files_to_backup = []
            with zipfile.ZipFile(backup_path, 'r') as zf:
                for filename in zf.namelist():
                    if filename != "metadata.json":
                        target_path = Path.home() / f".{filename}"
                        if target_path.exists():
                            files_to_backup.append(str(target_path))
            
            if files_to_backup:
                self.create_backup(files_to_backup, f"Pre-restore backup (restoring from {backup_path.name})")
            
            # Perform the restore
            with zipfile.ZipFile(backup_path, 'r') as zf:
                for filename in zf.namelist():
                    if filename != "metadata.json":
                        content = zf.read(filename)
                        target_path = Path.home() / f".{filename}"
                        target_path.write_bytes(content)
                        self.log(f"Restored {target_path}")
            
            self.log(f"Successfully restored from {backup_path.name}")
            return True
        except Exception as e:
            self.log(f"Failed to restore backup: {e}", "error")
            return False
    
    def set_variable(self, name: str, value: str, shells: List[Shell], 
                    skip_confirmation: bool = False, specific_file: Optional[str] = None) -> bool:
        """Set or update an environment variable across specified shells"""
        # Validate variable name
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
            print(f"Error: Invalid variable name '{name}'. Must start with letter/underscore and contain only letters, numbers, and underscores.")
            return False
        
        # Collect files to modify and their current values
        files_to_modify = []
        current_values = {}
        
        if specific_file:
            # Use specific file if provided
            if Path(specific_file).exists():
                files_to_modify.append(specific_file)
                vars_in_file = self.get_variables_from_file(specific_file)
                if name in vars_in_file:
                    current_values[specific_file] = vars_in_file[name]
            else:
                print(f"Error: File '{specific_file}' does not exist")
                return False
        else:
            # Find files for each shell
            for shell in shells:
                config_files = self.find_existing_config_files(shell)
                if not config_files:
                    # Create primary config if none exist
                    primary = self.get_primary_config_file(shell)
                    config_files = [primary]
                
                # Check which file contains the variable (if any)
                found_in_file = None
                for config_file in config_files:
                    vars_in_file = self.get_variables_from_file(config_file)
                    if name in vars_in_file:
                        found_in_file = config_file
                        current_values[config_file] = vars_in_file[name]
                        break
                
                # If not found, use the primary config file
                file_to_modify = found_in_file or config_files[0]
                if file_to_modify not in files_to_modify:
                    files_to_modify.append(file_to_modify)
        
        # Show what will be changed and get confirmation
        if not skip_confirmation and not self.dry_run:
            print("\nProposed changes:")
            print("-" * 50)
            for filepath in files_to_modify:
                print(f"\nFile: {filepath}")
                if filepath in current_values:
                    print(f"  Current: {name}={current_values[filepath]}")
                    print(f"  New:     {name}={value}")
                else:
                    print(f"  Adding:  {name}={value}")
            
            print("\n" + "-" * 50)
            response = input("Proceed with these changes? [y/N]: ").lower().strip()
            if response != 'y':
                print("Operation cancelled.")
                return False
        
        # Create backup if enabled
        if self.backup_enabled and not self.dry_run and files_to_modify:
            self.create_backup(files_to_modify, f"Before setting {name}={value}")
        
        # Apply changes
        success = True
        for filepath in files_to_modify:
            if self.update_variable_in_file(filepath, name, value):
                if self.dry_run:
                    print(f"[DRY RUN] Would update {filepath}")
                else:
                    print(f"✓ Updated {filepath}")
            else:
                print(f"✗ Failed to update {filepath}")
                success = False
        
        return success
    
    def update_variable_in_file(self, filepath: str, name: str, value: str) -> bool:
        """Update or add a variable in a specific file"""
        if self.dry_run:
            return True
        
        try:
            lines = self.read_config_file(filepath)
            new_lines = []
            variable_updated = False
            formatted_line = self.format_export_line(name, value)
            
            # Update existing variable
            for line in lines:
                parsed = self.parse_export_line(line)
                if parsed and parsed[0] == name:
                    new_lines.append(formatted_line)
                    variable_updated = True
                else:
                    new_lines.append(line)
            
            # Add new variable if not found
            if not variable_updated:
                # Add newline if file doesn't end with one
                if new_lines and not new_lines[-1].endswith('\n'):
                    new_lines.append('\n')
                new_lines.append(formatted_line)
            
            self.write_config_file(filepath, new_lines)
            return True
        except Exception as e:
            self.log(f"Error updating {filepath}: {e}", "error")
            return False
    
    def remove_variable(self, name: str, shells: List[Shell], 
                       skip_confirmation: bool = False) -> bool:
        """Remove an environment variable from specified shells"""
        # Find files containing the variable
        files_to_modify = []
        found_values = {}
        
        for shell in shells:
            for config_file in self.find_existing_config_files(shell):
                vars_in_file = self.get_variables_from_file(config_file)
                if name in vars_in_file:
                    files_to_modify.append(config_file)
                    found_values[config_file] = vars_in_file[name]
        
        if not files_to_modify:
            print(f"Variable '{name}' not found in any configuration files.")
            return True
        
        # Show what will be removed and get confirmation
        if not skip_confirmation and not self.dry_run:
            print("\nVariables to be removed:")
            print("-" * 50)
            for filepath in files_to_modify:
                print(f"\nFile: {filepath}")
                print(f"  Removing: {name}={found_values[filepath]}")
            
            print("\n" + "-" * 50)
            response = input("Proceed with removal? [y/N]: ").lower().strip()
            if response != 'y':
                print("Operation cancelled.")
                return False
        
        # Create backup if enabled
        if self.backup_enabled and not self.dry_run:
            self.create_backup(files_to_modify, f"Before removing {name}")
        
        # Remove variable from files
        success = True
        for filepath in files_to_modify:
            if self.remove_variable_from_file(filepath, name):
                if self.dry_run:
                    print(f"[DRY RUN] Would update {filepath}")
                else:
                    print(f"✓ Removed from {filepath}")
            else:
                print(f"✗ Failed to update {filepath}")
                success = False
        
        return success
    
    def remove_variable_from_file(self, filepath: str, name: str) -> bool:
        """Remove a variable from a specific file"""
        if self.dry_run:
            return True
        
        try:
            lines = self.read_config_file(filepath)
            new_lines = []
            
            for line in lines:
                parsed = self.parse_export_line(line)
                if not (parsed and parsed[0] == name):
                    new_lines.append(line)
            
            self.write_config_file(filepath, new_lines)
            return True
        except Exception as e:
            self.log(f"Error removing from {filepath}: {e}", "error")
            return False
    
    def sync_variables(self, from_shell: Shell, to_shells: List[Shell], 
                      keys: Optional[List[str]] = None, skip_confirmation: bool = False) -> bool:
        """Sync variables from one shell to others"""
        # Get variables from source shell
        source_vars = {}
        for config_file in self.find_existing_config_files(from_shell):
            file_vars = self.get_variables_from_file(config_file)
            source_vars.update(file_vars)
        
        if not source_vars:
            print(f"No variables found in {from_shell.value} configuration")
            return True
        
        # Filter by keys if provided
        if keys:
            import fnmatch
            filtered_vars = {}
            for var_name, var_value in source_vars.items():
                for pattern in keys:
                    if fnmatch.fnmatch(var_name, pattern):
                        filtered_vars[var_name] = var_value
                        break
            source_vars = filtered_vars
        
        if not source_vars:
            print("No variables matched the specified patterns")
            return True
        
        # Determine which variables need syncing
        sync_plan = {}
        for to_shell in to_shells:
            if to_shell == from_shell:
                continue
            
            shell_vars = {}
            for config_file in self.find_existing_config_files(to_shell):
                file_vars = self.get_variables_from_file(config_file)
                shell_vars.update(file_vars)
            
            changes = {}
            for var_name, var_value in source_vars.items():
                if var_name not in shell_vars or shell_vars[var_name] != var_value:
                    changes[var_name] = {
                        'new_value': var_value,
                        'old_value': shell_vars.get(var_name, '[not set]')
                    }
            
            if changes:
                sync_plan[to_shell] = changes
        
        if not sync_plan:
            print("All variables are already in sync")
            return True
        
        # Show sync plan and get confirmation
        if not skip_confirmation and not self.dry_run:
            print(f"\nSync Plan: {from_shell.value} -> {', '.join(s.value for s in to_shells)}")
            print("=" * 70)
            
            for to_shell, changes in sync_plan.items():
                print(f"\nChanges for {to_shell.value}:")
                for var_name, change_info in changes.items():
                    if change_info['old_value'] == '[not set]':
                        print(f"  + {var_name} = {change_info['new_value']}")
                    else:
                        print(f"  ~ {var_name}")
                        print(f"    old: {change_info['old_value']}")
                        print(f"    new: {change_info['new_value']}")
            
            print("\n" + "=" * 70)
            response = input("Proceed with sync? [y/N]: ").lower().strip()
            if response != 'y':
                print("Sync cancelled.")
                return False
        
        # Perform sync
        success = True
        for to_shell, changes in sync_plan.items():
            for var_name, change_info in changes.items():
                if not self.set_variable(var_name, change_info['new_value'], 
                                       [to_shell], skip_confirmation=True):
                    success = False
        
        if success:
            print(f"\n✓ Successfully synced {len(source_vars)} variable(s)")
        
        return success
    
    def export_variables(self, output_path: str, format: str, shell: Optional[Shell] = None,
                        keys: Optional[List[str]] = None) -> bool:
        """Export variables to a file"""
        # Determine which shell to export from
        if not shell:
            shell = self.detect_current_shell()
            if not shell:
                print("Error: Could not detect current shell. Please specify with --shell")
                return False
        
        # Get variables
        shell_vars = {}
        for config_file in self.find_existing_config_files(shell):
            file_vars = self.get_variables_from_file(config_file)
            shell_vars.update(file_vars)
        
        # Filter by keys if provided
        if keys:
            import fnmatch
            filtered_vars = {}
            for var_name, var_value in shell_vars.items():
                for pattern in keys:
                    if fnmatch.fnmatch(var_name, pattern):
                        filtered_vars[var_name] = var_value
                        break
            shell_vars = filtered_vars
        
        if not shell_vars:
            print("No variables found to export")
            return True
        
        try:
            output_path = Path(output_path)
            
            if format == 'json':
                with open(output_path, 'w') as f:
                    json.dump(shell_vars, f, indent=2, sort_keys=True)
            
            elif format == 'env':
                with open(output_path, 'w') as f:
                    for name, value in sorted(shell_vars.items()):
                        # Escape value for .env format
                        if '"' in value or '\n' in value or '\\' in value:
                            value = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                            f.write(f'{name}="{value}"\n')
                        else:
                            f.write(f'{name}={value}\n')
            
            elif format == 'shell':
                with open(output_path, 'w') as f:
                    f.write("#!/bin/sh\n")
                    f.write("# Exported environment variables\n\n")
                    for name, value in sorted(shell_vars.items()):
                        f.write(self.format_export_line(name, value))
                
                # Make shell script executable
                output_path.chmod(0o755)
            
            print(f"✓ Exported {len(shell_vars)} variable(s) to {output_path}")
            return True
        
        except Exception as e:
            print(f"Error exporting variables: {e}")
            return False
    
    def import_variables(self, input_path: str, shells: List[Shell], 
                        keys: Optional[List[str]] = None, skip_confirmation: bool = False) -> bool:
        """Import variables from a file"""
        try:
            input_path = Path(input_path)
            
            if not input_path.exists():
                print(f"Error: File '{input_path}' does not exist")
                return False
            
            # Detect format and load variables
            variables = {}
            
            if input_path.suffix == '.json':
                with open(input_path, 'r') as f:
                    variables = json.load(f)
            
            elif input_path.suffix in ['.env', '.txt'] or input_path.stem.startswith('.env'):
                with open(input_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Parse KEY=value format
                            match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
                            if match:
                                name = match.group(1)
                                value = match.group(2)
                                # Remove quotes if present
                                if (value.startswith('"') and value.endswith('"')) or \
                                   (value.startswith("'") and value.endswith("'")):
                                    value = value[1:-1]
                                variables[name] = value
            
            else:
                # Try to parse as shell script
                with open(input_path, 'r') as f:
                    for line in f:
                        parsed = self.parse_export_line(line)
                        if parsed:
                            variables[parsed[0]] = parsed[1]
            
            if not variables:
                print("No variables found in input file")
                return True
            
            # Filter by keys if provided
            if keys:
                import fnmatch
                filtered_vars = {}
                for var_name, var_value in variables.items():
                    for pattern in keys:
                        if fnmatch.fnmatch(var_name, pattern):
                            filtered_vars[var_name] = var_value
                            break
                variables = filtered_vars
            
            if not variables:
                print("No variables matched the specified patterns")
                return True
            
            # Show import plan and get confirmation
            if not skip_confirmation and not self.dry_run:
                print(f"\nImporting {len(variables)} variable(s) from {input_path.name}")
                print("=" * 70)
                for name, value in sorted(variables.items()):
                    print(f"{name} = {value}")
                print("=" * 70)
                
                response = input("Proceed with import? [y/N]: ").lower().strip()
                if response != 'y':
                    print("Import cancelled.")
                    return False
            
            # Import variables
            success = True
            imported_count = 0
            for name, value in variables.items():
                if self.set_variable(name, value, shells, skip_confirmation=True):
                    imported_count += 1
                else:
                    success = False
            
            print(f"\n✓ Imported {imported_count} variable(s)")
            return success
        
        except Exception as e:
            print(f"Error importing variables: {e}")
            return False


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser"""
    parser = argparse.ArgumentParser(
        prog='setvar',
        description='Manage environment variables across multiple shell configurations',
        epilog='Examples:\n'
               '  setvar set API_KEY "your-secret-key"\n'
               '  setvar list --shell bash\n'
               '  setvar sync --from bash --to zsh\n'
               '  setvar export --keys "*_API_*" --output env.json',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Global options
    parser.add_argument('-V', '--version', action='version', 
                      version=f'%(prog)s {__version__}',
                      help='show version number and exit')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='enable verbose output')
    parser.add_argument('-n', '--dry-run', action='store_true',
                      help='show what would be done without making changes')
    parser.add_argument('-y', '--yes', action='store_true',
                      help='skip confirmation prompts')
    parser.add_argument('--no-backup', action='store_true',
                      help='disable automatic backups')
    parser.add_argument('--config-dir', type=str,
                      help='custom configuration directory (default: ~/.config/setvar)')
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='available commands')
    
    # set command
    set_parser = subparsers.add_parser('set', help='set or update an environment variable')
    set_parser.add_argument('name', help='variable name')
    set_parser.add_argument('value', help='variable value (use quotes for values with spaces)')
    set_parser.add_argument('-s', '--shell', type=str, nargs='*',
                          choices=['bash', 'zsh', 'sh', 'all'],
                          default=['all'],
                          help='target shell(s) (default: all)')
    set_parser.add_argument('-f', '--file', type=str,
                          help='specific config file to update')
    
    # get command
    get_parser = subparsers.add_parser('get', help='get value of an environment variable')
    get_parser.add_argument('name', help='variable name')
    get_parser.add_argument('-s', '--shell', type=str,
                          choices=['bash', 'zsh', 'sh'],
                          help='shell to check (default: current shell)')
    
    # list command
    list_parser = subparsers.add_parser('list', help='list environment variables')
    list_parser.add_argument('-s', '--shell', type=str, nargs='*',
                           choices=['bash', 'zsh', 'sh', 'all'],
                           default=['all'],
                           help='shell(s) to list from (default: all)')
    list_parser.add_argument('-p', '--pattern', type=str,
                           help='filter variables by pattern (supports wildcards)')
    list_parser.add_argument('--sync-check', action='store_true',
                           help='highlight variables that differ between shells')
    
    # remove command
    remove_parser = subparsers.add_parser('remove', help='remove an environment variable')
    remove_parser.add_argument('name', help='variable name')
    remove_parser.add_argument('-s', '--shell', type=str, nargs='*',
                             choices=['bash', 'zsh', 'sh', 'all'],
                             default=['all'],
                             help='target shell(s) (default: all)')
    
    # sync command
    sync_parser = subparsers.add_parser('sync', help='synchronize variables between shells')
    sync_parser.add_argument('--from', dest='from_shell', required=True,
                           choices=['bash', 'zsh', 'sh'],
                           help='source shell')
    sync_parser.add_argument('--to', dest='to_shell', nargs='*',
                           choices=['bash', 'zsh', 'sh', 'all'],
                           default=['all'],
                           help='target shell(s) (default: all)')
    sync_parser.add_argument('-k', '--keys', type=str, nargs='*',
                           help='specific variable names or patterns to sync')
    
    # export command
    export_parser = subparsers.add_parser('export', help='export variables to file')
    export_parser.add_argument('-o', '--output', type=str, required=True,
                             help='output file path')
    export_parser.add_argument('-f', '--format', choices=['json', 'env', 'shell'],
                             default='json',
                             help='export format (default: json)')
    export_parser.add_argument('-s', '--shell', type=str,
                             choices=['bash', 'zsh', 'sh'],
                             help='source shell (default: current shell)')
    export_parser.add_argument('-k', '--keys', type=str, nargs='*',
                             help='variable names or patterns to export (e.g., "*_API_*")')
    
    # import command
    import_parser = subparsers.add_parser('import', help='import variables from file')
    import_parser.add_argument('file', help='input file path')
    import_parser.add_argument('-s', '--shell', type=str, nargs='*',
                             choices=['bash', 'zsh', 'sh', 'all'],
                             default=['all'],
                             help='target shell(s) (default: all)')
    import_parser.add_argument('-k', '--keys', type=str, nargs='*',
                             help='specific variable names or patterns to import')
    
    # backup command
    backup_parser = subparsers.add_parser('backup', help='manage configuration backups')
    backup_subparsers = backup_parser.add_subparsers(dest='backup_command')
    
    backup_create = backup_subparsers.add_parser('create', help='create a backup')
    backup_create.add_argument('-m', '--message', type=str,
                             help='backup description')
    
    backup_list = backup_subparsers.add_parser('list', help='list available backups')
    backup_list.add_argument('-n', '--limit', type=int, default=10,
                           help='number of backups to show (default: 10)')
    
    backup_restore = backup_subparsers.add_parser('restore', help='restore from backup')
    backup_restore.add_argument('backup_id', help='backup ID or timestamp')
    
    return parser


def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Show help if no command provided
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # Initialize SetVar with global options
    app = SetVar(
        config_dir=args.config_dir,
        backup_enabled=not args.no_backup,
        verbose=args.verbose,
        dry_run=args.dry_run
    )
    
    # Handle commands
    if args.command == 'set':
        # Parse shell arguments
        if 'all' in args.shell:
            shells = list(Shell)
        else:
            shells = [Shell(s) for s in args.shell]
        
        success = app.set_variable(
            name=args.name,
            value=args.value,
            shells=shells,
            skip_confirmation=args.yes,
            specific_file=args.file
        )
        sys.exit(0 if success else 1)
    
    elif args.command == 'get':
        # Determine which shell to check
        shell = None
        if args.shell:
            shell = Shell(args.shell)
        else:
            shell = app.detect_current_shell()
            if not shell:
                print("Error: Could not detect current shell. Please specify with --shell")
                sys.exit(1)
        
        # Find the variable
        found = False
        for config_file in app.find_existing_config_files(shell):
            vars_in_file = app.get_variables_from_file(config_file)
            if args.name in vars_in_file:
                print(vars_in_file[args.name])
                found = True
                break
        
        if not found:
            print(f"Variable '{args.name}' not found in {shell.value} configuration")
            sys.exit(1)
    
    elif args.command == 'list':
        # Parse shell arguments
        if 'all' in args.shell:
            shells = list(Shell)
        else:
            shells = [Shell(s) for s in args.shell]
        
        all_vars = app.get_all_variables(shells)
        
        # Apply pattern filter if provided
        if args.pattern:
            import fnmatch
            filtered_vars = {}
            for shell_name, shell_vars in all_vars.items():
                filtered = {k: v for k, v in shell_vars.items() 
                          if fnmatch.fnmatch(k, args.pattern)}
                if filtered:
                    filtered_vars[shell_name] = filtered
            all_vars = filtered_vars
        
        # Display results
        if not all_vars or not any(all_vars.values()):
            print("No variables found")
            sys.exit(0)
        
        if args.sync_check:
            # Check for sync discrepancies
            all_var_names = set()
            for shell_vars in all_vars.values():
                all_var_names.update(shell_vars.keys())
            
            print("Variable Sync Status:")
            print("=" * 70)
            
            for var_name in sorted(all_var_names):
                values_by_shell = {}
                for shell_name, shell_vars in all_vars.items():
                    if var_name in shell_vars:
                        values_by_shell[shell_name] = shell_vars[var_name]
                
                # Check if all values are the same
                unique_values = set(values_by_shell.values())
                if len(unique_values) > 1:
                    print(f"\n⚠️  {var_name} (OUT OF SYNC)")
                    for shell_name, value in values_by_shell.items():
                        print(f"  {shell_name:8} = {value}")
                else:
                    print(f"\n✓ {var_name}")
                    for shell_name, value in values_by_shell.items():
                        print(f"  {shell_name:8} = {value}")
        else:
            # Regular list display
            for shell_name, shell_vars in all_vars.items():
                if shell_vars:
                    print(f"\n{shell_name.upper()} Variables:")
                    print("-" * 50)
                    for name, value in sorted(shell_vars.items()):
                        print(f"{name}={value}")
    
    elif args.command == 'remove':
        # Parse shell arguments
        if 'all' in args.shell:
            shells = list(Shell)
        else:
            shells = [Shell(s) for s in args.shell]
        
        success = app.remove_variable(
            name=args.name,
            shells=shells,
            skip_confirmation=args.yes
        )
        sys.exit(0 if success else 1)
    
    elif args.command == 'sync':
        from_shell = Shell(args.from_shell)
        
        # Parse target shells
        if 'all' in args.to_shell:
            to_shells = [s for s in Shell if s != from_shell]
        else:
            to_shells = [Shell(s) for s in args.to_shell]
        
        success = app.sync_variables(
            from_shell=from_shell,
            to_shells=to_shells,
            keys=args.keys,
            skip_confirmation=args.yes
        )
        sys.exit(0 if success else 1)
    
    elif args.command == 'export':
        shell = Shell(args.shell) if args.shell else None
        
        success = app.export_variables(
            output_path=args.output,
            format=args.format,
            shell=shell,
            keys=args.keys
        )
        sys.exit(0 if success else 1)
    
    elif args.command == 'import':
        # Parse shell arguments
        if 'all' in args.shell:
            shells = list(Shell)
        else:
            shells = [Shell(s) for s in args.shell]
        
        success = app.import_variables(
            input_path=args.file,
            shells=shells,
            keys=args.keys,
            skip_confirmation=args.yes
        )
        sys.exit(0 if success else 1)
    
    elif args.command == 'backup':
        if args.backup_command == 'create':
            # Get all shell config files for backup
            all_files = []
            for shell in Shell:
                all_files.extend(app.find_existing_config_files(shell))
            
            if all_files:
                backup_path = app.create_backup(all_files, args.message)
                if backup_path:
                    print(f"Backup created: {backup_path}")
                else:
                    print("Failed to create backup")
                    sys.exit(1)
            else:
                print("No configuration files found to backup")
        
        elif args.backup_command == 'list':
            backups = app.list_backups(args.limit)
            if not backups:
                print("No backups found")
            else:
                print(f"\nAvailable backups (showing last {args.limit}):")
                print("=" * 70)
                for backup in backups:
                    print(f"\nBackup: {backup['name']}")
                    print(f"  Time: {backup['timestamp']}")
                    print(f"  Message: {backup['message']}")
                    print(f"  Files: {', '.join(Path(f).name for f in backup['files'])}")
        
        elif args.backup_command == 'restore':
            if app.restore_backup(args.backup_id):
                print("Backup restored successfully")
            else:
                print("Failed to restore backup")
                sys.exit(1)


if __name__ == '__main__':
    main()