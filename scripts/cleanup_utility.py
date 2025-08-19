#!/usr/bin/env python3
"""
DSLD Cleanup Utility
Handles cleanup of output directories before processing runs
"""
import os
import shutil
from pathlib import Path
import logging
from typing import List, Dict
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class DSLDCleanupUtility:
    """Utility for cleaning up output directories before processing"""
    
    def __init__(self, base_output_dir: str = "output"):
        self.base_output_dir = Path(base_output_dir)
        self.subdirs = ["cleaned", "needs_review", "incomplete", "errors"]
        
    def scan_output_directories(self) -> Dict[str, List[str]]:
        """
        Scan all output directories and return file counts
        
        Returns:
            Dict with directory names and list of files
        """
        scan_results = {}
        
        for subdir in self.subdirs:
            dir_path = self.base_output_dir / subdir
            if dir_path.exists():
                files = [f for f in os.listdir(dir_path) 
                        if f.endswith('.json') and not f.startswith('.')]
                scan_results[subdir] = files
            else:
                scan_results[subdir] = []
                
        return scan_results
    
    def create_backup(self, backup_name: str = None) -> str:
        """
        Create a backup of current output directories
        
        Args:
            backup_name: Optional custom backup name
            
        Returns:
            Path to backup directory
        """
        if backup_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}"
            
        backup_dir = self.base_output_dir.parent / "backups" / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy each output subdirectory to backup
        for subdir in self.subdirs:
            src_dir = self.base_output_dir / subdir
            if src_dir.exists() and any(src_dir.iterdir()):
                dest_dir = backup_dir / subdir
                shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)
                
        # Create backup manifest
        scan_results = self.scan_output_directories()
        manifest = {
            "backup_created": datetime.now().isoformat(),
            "total_files": sum(len(files) for files in scan_results.values()),
            "directories": scan_results
        }
        
        with open(backup_dir / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
            
        logger.info(f"Backup created at: {backup_dir}")
        return str(backup_dir)
    
    def clean_output_directories(self, preserve_files: bool = False) -> Dict[str, int]:
        """
        Clean all output directories
        
        Args:
            preserve_files: If True, create backup before cleaning
            
        Returns:
            Dict with counts of files removed per directory
        """
        removal_counts = {}
        
        # Create backup if requested
        if preserve_files:
            backup_path = self.create_backup()
            logger.info(f"Files backed up to: {backup_path}")
        
        # Clean each directory
        for subdir in self.subdirs:
            dir_path = self.base_output_dir / subdir
            count = 0
            
            if dir_path.exists():
                for file in dir_path.glob("*.json"):
                    if not file.name.startswith('.'):
                        file.unlink()
                        count += 1
                        
            removal_counts[subdir] = count
            
        return removal_counts
    
    def interactive_cleanup(self):
        """Interactive cleanup with user prompts"""
        print("🧹 DSLD Output Directory Cleanup Utility")
        print("=" * 50)
        
        # Scan current state
        scan_results = self.scan_output_directories()
        total_files = sum(len(files) for files in scan_results.values())
        
        if total_files == 0:
            print("✅ No files found in output directories. Nothing to clean!")
            return
            
        print(f"\nCurrent files in output directories:")
        for subdir, files in scan_results.items():
            if files:
                print(f"  📁 {subdir}: {len(files)} files")
                for file in files[:3]:  # Show first 3 files
                    print(f"     - {file}")
                if len(files) > 3:
                    print(f"     ... and {len(files) - 3} more")
            else:
                print(f"  📁 {subdir}: empty")
                
        print(f"\nTotal files: {total_files}")
        
        # Get user choice
        print("\nChoose an option:")
        print("1. Clean all directories (with backup)")
        print("2. Clean all directories (no backup)")
        print("3. Clean specific directories")
        print("4. Just create backup (no cleanup)")
        print("5. Cancel")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            backup_path = self.create_backup()
            counts = self.clean_output_directories(preserve_files=False)
            print(f"\n✅ Cleanup complete! Backup saved to: {backup_path}")
            self._print_removal_summary(counts)
            
        elif choice == "2":
            confirm = input("⚠️  Are you sure? This will permanently delete all files (y/N): ")
            if confirm.lower() == 'y':
                counts = self.clean_output_directories(preserve_files=False)
                print("\n✅ Cleanup complete!")
                self._print_removal_summary(counts)
            else:
                print("Cleanup cancelled.")
                
        elif choice == "3":
            self._selective_cleanup(scan_results)
            
        elif choice == "4":
            backup_path = self.create_backup()
            print(f"✅ Backup created at: {backup_path}")
            
        elif choice == "5":
            print("Cleanup cancelled.")
            
        else:
            print("Invalid choice. Cleanup cancelled.")
    
    def _selective_cleanup(self, scan_results: Dict[str, List[str]]):
        """Handle selective directory cleanup"""
        print("\nSelect directories to clean:")
        
        dirs_with_files = [d for d, files in scan_results.items() if files]
        if not dirs_with_files:
            print("No directories have files to clean.")
            return
            
        for i, subdir in enumerate(dirs_with_files, 1):
            file_count = len(scan_results[subdir])
            print(f"{i}. {subdir} ({file_count} files)")
            
        selections = input(f"\nEnter directory numbers (1-{len(dirs_with_files)}, comma-separated): ")
        
        try:
            indices = [int(x.strip()) - 1 for x in selections.split(',')]
            selected_dirs = [dirs_with_files[i] for i in indices if 0 <= i < len(dirs_with_files)]
            
            if not selected_dirs:
                print("No valid directories selected.")
                return
                
            # Confirm backup
            backup_choice = input("Create backup before cleaning? (y/N): ")
            if backup_choice.lower() == 'y':
                self.create_backup()
                
            # Clean selected directories
            counts = {}
            for subdir in selected_dirs:
                dir_path = self.base_output_dir / subdir
                count = 0
                for file in dir_path.glob("*.json"):
                    if not file.name.startswith('.'):
                        file.unlink()
                        count += 1
                counts[subdir] = count
                
            print("\n✅ Selective cleanup complete!")
            self._print_removal_summary(counts)
            
        except ValueError:
            print("Invalid input. Cleanup cancelled.")
    
    def _print_removal_summary(self, counts: Dict[str, int]):
        """Print summary of files removed"""
        total_removed = sum(counts.values())
        print(f"\nFiles removed:")
        for subdir, count in counts.items():
            if count > 0:
                print(f"  📁 {subdir}: {count} files")
        print(f"Total removed: {total_removed} files")

def main():
    """Main function for standalone usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DSLD Output Directory Cleanup Utility")
    parser.add_argument("--output-dir", default="output", 
                       help="Base output directory (default: output)")
    parser.add_argument("--config", 
                       help="Use output directory from config file instead")
    parser.add_argument("--auto-clean", action="store_true",
                       help="Clean all directories with backup (non-interactive)")
    parser.add_argument("--backup-only", action="store_true", 
                       help="Only create backup, don't clean")
    parser.add_argument("--scan-only", action="store_true",
                       help="Only scan and report, don't clean")
    
    args = parser.parse_args()
    
    # Determine output directory
    output_dir = args.output_dir
    if args.config:
        import json
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
                output_dir = config["paths"]["output_directory"]
                print(f"Using output directory from config: {output_dir}")
        except Exception as e:
            print(f"Error reading config file: {e}")
            print(f"Using default output directory: {output_dir}")
    
    cleanup = DSLDCleanupUtility(output_dir)
    
    if args.scan_only:
        scan_results = cleanup.scan_output_directories()
        total_files = sum(len(files) for files in scan_results.values())
        print(f"Output directory scan results:")
        for subdir, files in scan_results.items():
            print(f"  {subdir}: {len(files)} files")
        print(f"Total: {total_files} files")
        
    elif args.backup_only:
        backup_path = cleanup.create_backup()
        print(f"Backup created at: {backup_path}")
        
    elif args.auto_clean:
        backup_path = cleanup.create_backup()
        counts = cleanup.clean_output_directories(preserve_files=False)
        print(f"Cleanup complete! Backup saved to: {backup_path}")
        cleanup._print_removal_summary(counts)
        
    else:
        cleanup.interactive_cleanup()

if __name__ == "__main__":
    main()