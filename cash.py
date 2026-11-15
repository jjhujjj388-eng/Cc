#!/usr/bin/env python3
"""
cash.py - Black X Card Bot Cache Cleaner
Only cleans Python cache files and temporary files
"""

import os
import shutil
import glob
import sys
from pathlib import Path

# Colors for terminal output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_banner():
    """Print banner"""
    banner = f"""
{BLUE}╔══════════════════════════════════════════════════════════╗
║                                                              ║
║   {GREEN}██████╗ ██╗      █████╗  ██████╗██╗  ██╗{BLUE}               ║
║   {GREEN}██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝{BLUE}               ║
║   {GREEN}██████╔╝██║     ███████║██║     █████╔╝ {BLUE}               ║
║   {GREEN}██╔══██╗██║     ██╔══██║██║     ██╔═██╗ {BLUE}               ║
║   {GREEN}██████╔╝███████╗██║  ██║╚██████╗██║  ██╗{BLUE}               ║
║   {GREEN}╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝{BLUE}               ║
║                                                              ║
║              {YELLOW}Python Cache Cleaner v1.0{RESET}{BLUE}                   ║
║         {YELLOW}Cleans __pycache__ and .pyc files only{RESET}{BLUE}           ║
╚══════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)

def get_size(path):
    """Get file/folder size in human readable format"""
    if os.path.isfile(path):
        size = os.path.getsize(path)
    elif os.path.isdir(path):
        size = 0
        for root, dirs, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if os.path.exists(fp):
                    size += os.path.getsize(fp)
    else:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def clean_pycache():
    """Remove __pycache__ folders"""
    count = 0
    size = 0
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            try:
                folder_size = 0
                for f in os.listdir(pycache_path):
                    fp = os.path.join(pycache_path, f)
                    if os.path.isfile(fp):
                        folder_size += os.path.getsize(fp)
                
                shutil.rmtree(pycache_path)
                count += 1
                size += folder_size
                print(f"{GREEN}  ✅ Removed:{RESET} {pycache_path} ({get_size(pycache_path)})")
            except Exception as e:
                print(f"{RED}  ❌ Error removing {pycache_path}: {e}{RESET}")
    return count, size

def clean_pyc_files():
    """Remove all .pyc files"""
    count = 0
    size = 0
    for pyc_file in glob.glob('**/*.pyc', recursive=True):
        try:
            file_size = os.path.getsize(pyc_file)
            os.remove(pyc_file)
            count += 1
            size += file_size
            print(f"{GREEN}  ✅ Removed:{RESET} {pyc_file} ({get_size(pyc_file)})")
        except Exception as e:
            print(f"{RED}  ❌ Error removing {pyc_file}: {e}{RESET}")
    return count, size

def clean_pyo_files():
    """Remove all .pyo files"""
    count = 0
    size = 0
    for pyo_file in glob.glob('**/*.pyo', recursive=True):
        try:
            file_size = os.path.getsize(pyo_file)
            os.remove(pyo_file)
            count += 1
            size += file_size
            print(f"{GREEN}  ✅ Removed:{RESET} {pyo_file} ({get_size(pyo_file)})")
        except Exception as e:
            print(f"{RED}  ❌ Error removing {pyo_file}: {e}{RESET}")
    return count, size

def clean_temp_files():
    """Remove temporary files like .tmp, .temp, .swp"""
    patterns = ['*.tmp', '*.temp', '*.swp', '*.swo', '*~']
    count = 0
    size = 0
    
    for pattern in patterns:
        for temp_file in glob.glob(f'**/{pattern}', recursive=True):
            # Skip if in venv or env
            if '/venv/' in temp_file or '/env/' in temp_file or '/.git/' in temp_file:
                continue
            try:
                file_size = os.path.getsize(temp_file)
                os.remove(temp_file)
                count += 1
                size += file_size
                print(f"{GREEN}  ✅ Removed:{RESET} {temp_file} ({get_size(temp_file)})")
            except Exception as e:
                print(f"{RED}  ❌ Error removing {temp_file}: {e}{RESET}")
    return count, size

def main():
    """Main function"""
    print_banner()
    
    print(f"\n{YELLOW}🔍 Scanning for Python cache files...{RESET}\n")
    
    total_count = 0
    total_size = 0
    
    # Clean only Python cache and temp files
    cleaners = [
        ("Python Cache Folders (__pycache__)", clean_pycache),
        ("Python Compiled Files (.pyc)", clean_pyc_files),
        ("Python Optimized Files (.pyo)", clean_pyo_files),
        ("Temporary Files (.tmp, .temp, .swp)", clean_temp_files),
    ]
    
    for name, cleaner in cleaners:
        print(f"\n{BLUE}📦 Cleaning {name}...{RESET}")
        count, size = cleaner()
        total_count += count
        total_size += size
        if count == 0:
            print(f"{YELLOW}  ℹ️ No files found{RESET}")
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{GREEN}✅ Cleaning Complete!{RESET}")
    print(f"{BLUE}📊 Total Items Removed: {YELLOW}{total_count}{RESET}")
    
    if total_size > 0:
        if total_size < 1024:
            size_str = f"{total_size:.2f} B"
        elif total_size < 1024*1024:
            size_str = f"{total_size/1024:.2f} KB"
        else:
            size_str = f"{total_size/(1024*1024):.2f} MB"
        print(f"{BLUE}💾 Total Space Freed: {YELLOW}{size_str}{RESET}")
    else:
        print(f"{BLUE}💾 Total Space Freed: {YELLOW}0 B{RESET}")
    
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    print(f"{GREEN}✨ Python cache cleaned successfully!{RESET}")
    print(f"{YELLOW}💡 Note: Proxy, cookie, and other files were NOT touched{RESET}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}⚠️ Cleaning interrupted by user{RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")
        sys.exit(1)