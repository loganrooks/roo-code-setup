#!/usr/bin/env python3
"""
Generate a codebase context file for Gemini 2.5 Pro by concatenating relevant files.

This script combines all relevant files in a codebase with separation headers
containing important file information to reduce API calls when using Gemini 2.5 Pro.
"""

import os
import argparse
import datetime
import mimetypes
import re
import fnmatch
from pathlib import Path
from typing import List, Set, Dict, Any, Optional


def get_file_info(file_path: Path) -> Dict[str, Any]:
    """
    Get relevant information about a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary containing file information
    """
    stats = file_path.stat()
    
    # Try to detect the file type
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type is None:
        # Try to determine type from extension or content
        if file_path.suffix in ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.php', '.rb']:
            file_type = "code"
        elif file_path.suffix in ['.md', '.txt', '.rst', '.adoc']:
            file_type = "documentation"
        elif file_path.name.lower() in ['readme', 'license', 'contributing', 'changelog', 'authors']:
            file_type = "documentation"
        elif 'adr' in str(file_path).lower() and file_path.suffix == '.md':
            file_type = "architecture_decision"
        else:
            file_type = "unknown"
    else:
        if mime_type.startswith('text'):
            if 'markdown' in mime_type:
                file_type = "documentation"
            else:
                file_type = "code" if mime_type.split('/')[-1] in ['x-python', 'javascript', 'x-java', 'x-c'] else "text"
        else:
            file_type = "binary"
    
    return {
        "path": str(file_path),
        "relative_path": str(file_path).replace(str(file_path.cwd()) + '/', ''),
        "size_bytes": stats.st_size,
        "last_modified": datetime.datetime.fromtimestamp(stats.st_mtime).isoformat(),
        "type": file_type,
        "extension": file_path.suffix,
        "filename": file_path.name
    }


def is_binary_file(file_path: Path) -> bool:
    """
    Check if a file is binary.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if the file is binary, False otherwise
    """
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type and not mime_type.startswith('text'):
        return True
    
    # Additional check by reading a small chunk and looking for null bytes
    try:
        with open(file_path, 'rb') as file:
            chunk = file.read(1024)
            if b'\x00' in chunk:
                return True
            
            # Try to decode as text
            try:
                chunk.decode('utf-8')
                return False
            except UnicodeDecodeError:
                return True
    except Exception:
        return True


def load_context_ignore(root_dir: Path) -> List[str]:
    """
    Load patterns from .context-ignore file if it exists.
    
    Args:
        root_dir: Root directory of the codebase
        
    Returns:
        List of patterns to exclude
    """
    ignore_patterns = []
    ignore_file_path = root_dir / '.context-ignore'
    
    if ignore_file_path.exists():
        print(f"Found .context-ignore file at {ignore_file_path}")
        try:
            with open(ignore_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        ignore_patterns.append(line)
        except Exception as e:
            print(f"Error reading .context-ignore file: {str(e)}")
    
    return ignore_patterns


def is_ignored_by_patterns(file_path: Path, root_dir: Path, ignore_patterns: List[str]) -> bool:
    """
    Check if a file is ignored by the patterns in .context-ignore.
    
    Args:
        file_path: Path to the file
        root_dir: Root directory of the codebase
        ignore_patterns: List of patterns to check
        
    Returns:
        True if the file should be ignored, False otherwise
    """
    if not ignore_patterns:
        return False
    
    # Get relative path from the root directory
    try:
        rel_path = file_path.relative_to(root_dir)
        rel_path_str = str(rel_path)
    except ValueError:
        rel_path_str = str(file_path)
    
    # Check each pattern
    for pattern in ignore_patterns:
        # Handle directory patterns (ending with /)
        if pattern.endswith('/'):
            # Check if this file is inside the ignored directory
            dir_pattern = pattern[:-1]  # Remove trailing slash
            if rel_path_str == dir_pattern or rel_path_str.startswith(f"{dir_pattern}/"):
                return True
        # Handle file patterns with glob syntax
        elif fnmatch.fnmatch(rel_path_str, pattern):
            return True
        # Handle exact matches
        elif rel_path_str == pattern:
            return True
    
    return False


def should_include_file(file_path: Path, root_dir: Path, exclude_patterns: List[str], ignore_patterns: List[str]) -> bool:
    """
    Determine if a file should be included in the context file.
    
    Args:
        file_path: Path to the file
        root_dir: Root directory of the codebase
        exclude_patterns: Regex patterns to exclude files
        ignore_patterns: Patterns from .context-ignore file
        
    Returns:
        True if the file should be included, False otherwise
    """
    # Get the relative path string
    rel_path_str = str(file_path)
    
    # Check against exclude patterns
    for pattern in exclude_patterns:
        if re.search(pattern, rel_path_str):
            return False
    
    # Check against .context-ignore patterns
    if is_ignored_by_patterns(file_path, root_dir, ignore_patterns):
        return False
    
    # Skip binary files
    if is_binary_file(file_path):
        return False
    
    # Skip very large files (greater than 1MB)
    if file_path.stat().st_size > 1_000_000:
        return False
    
    return True


def create_context_file(
    root_dir: Path, 
    output_file: str, 
    exclude_patterns: List[str],
    include_patterns: Optional[List[str]] = None
) -> None:
    """
    Create a context file by concatenating all relevant files with separation headers.
    
    Args:
        root_dir: Root directory of the codebase
        output_file: Path to the output context file
        exclude_patterns: Regex patterns to exclude files
        include_patterns: Regex patterns to specifically include files (optional)
    """
    print(f"Scanning directory: {root_dir}")
    
    # Load patterns from .context-ignore file
    ignore_patterns = load_context_ignore(root_dir)
    if ignore_patterns:
        print(f"Loaded {len(ignore_patterns)} patterns from .context-ignore")
    
    with open(output_file, 'w', encoding='utf-8') as out_file:
        # Write the header for the context file
        out_file.write("# Codebase Context File for Gemini 2.5 Pro\n\n")
        out_file.write(f"Generated on: {datetime.datetime.now().isoformat()}\n")
        out_file.write(f"Root directory: {root_dir}\n\n")
        
        # Keep track of processed files for statistics
        processed_files = 0
        skipped_files = 0
        ignored_files = 0
        total_size = 0
        
        # Find all files in the directory
        all_files = list(root_dir.glob('**/*'))
        all_files = [f for f in all_files if f.is_file()]
        
        # If include patterns are provided, filter files that match any of these patterns
        if include_patterns:
            filtered_files = []
            for file_path in all_files:
                rel_path_str = str(file_path)
                for pattern in include_patterns:
                    if re.search(pattern, rel_path_str):
                        filtered_files.append(file_path)
                        break
            all_files = filtered_files
        
        # Process all files
        for file_path in sorted(all_files, key=lambda x: str(x)):
            # Skip the output file itself to avoid an infinite loop
            if str(file_path) == output_file:
                skipped_files += 1
                continue
                
            if should_include_file(file_path, root_dir, exclude_patterns, ignore_patterns):
                try:
                    file_info = get_file_info(file_path)
                    
                    # Write the file separator with information
                    out_file.write(f"\n\n{'=' * 80}\n")
                    out_file.write(f"FILE: {file_info['relative_path']}\n")
                    out_file.write(f"TYPE: {file_info['type']}\n")
                    out_file.write(f"SIZE: {file_info['size_bytes']} bytes\n")
                    out_file.write(f"LAST MODIFIED: {file_info['last_modified']}\n")
                    out_file.write(f"{'=' * 80}\n\n")
                    
                    # Read and write the file content
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as in_file:
                        content = in_file.read()
                        out_file.write(content)
                    
                    processed_files += 1
                    total_size += file_info['size_bytes']
                except Exception as e:
                    print(f"Error processing file {file_path}: {str(e)}")
                    skipped_files += 1
            else:
                if is_ignored_by_patterns(file_path, root_dir, ignore_patterns):
                    ignored_files += 1
                else:
                    skipped_files += 1
        
        # Write summary at the end
        out_file.write(f"\n\n{'=' * 80}\n")
        out_file.write(f"SUMMARY\n")
        out_file.write(f"Files processed: {processed_files}\n")
        out_file.write(f"Files ignored by .context-ignore: {ignored_files}\n")
        out_file.write(f"Files skipped for other reasons: {skipped_files}\n")
        out_file.write(f"Total size: {total_size} bytes\n")
        out_file.write(f"{'=' * 80}\n")
    
    print(f"Context file created at: {output_file}")
    print(f"Files processed: {processed_files}")
    print(f"Files ignored by .context-ignore: {ignored_files}")
    print(f"Files skipped for other reasons: {skipped_files}")
    print(f"Total size: {total_size} bytes")


def main():
    """Main function to parse arguments and create context file."""
    parser = argparse.ArgumentParser(
        description='Create a codebase context file for Gemini 2.5 Pro.'
    )
    
    parser.add_argument(
        '-d', '--directory',
        default='.',
        help='Root directory of the codebase (default: current directory)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='gemini_context.txt',
        help='Output file path (default: gemini_context.txt)'
    )
    
    parser.add_argument(
        '-e', '--exclude',
        action='append',
        default=[
            r'\.git',
            r'__pycache__',
            r'\.pyc$',
            r'\.DS_Store$',
            r'node_modules',
            r'\.venv',
            r'venv',
            r'\.env',
            r'\.idea',
            r'\.vscode',
            r'dist',
            r'build',
            r'coverage',
            r'\.coverage',
            r'\.pytest_cache',
            r'\.tox',
        ],
        help='Regex patterns to exclude files (can be used multiple times)'
    )
    
    parser.add_argument(
        '-i', '--include',
        action='append',
        help='Regex patterns to specifically include files (can be used multiple times)'
    )
    
    args = parser.parse_args()
    
    root_dir = Path(args.directory).resolve()
    create_context_file(
        root_dir=root_dir,
        output_file=args.output,
        exclude_patterns=args.exclude,
        include_patterns=args.include
    )


if __name__ == "__main__":
    main()